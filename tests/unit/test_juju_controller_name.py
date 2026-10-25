"""Unit tests for per-provider Juju controller names."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from concierge.config.models import BootstrappedController, ConciergeConfig
from concierge.core.manager import Manager
from concierge.core.plan import Plan
from concierge.juju.handler import JujuHandler
from concierge.providers.base import is_local_cloud
from concierge.providers.factory import SUPPORTED_PROVIDERS, create_provider
from concierge.system.command import Command, CommandError


def _config(**providers: dict[str, object]) -> ConciergeConfig:
    return ConciergeConfig.from_dict({"providers": providers})


def _show_controller(name: str, cloud: str, uuid: str) -> bytes:
    return json.dumps({name: {"details": {"cloud": cloud, "uuid": uuid}}}).encode()


def _provider(
    name: str, cloud: str, controller: str | None = None, bootstrap: bool = True
) -> MagicMock:
    provider = MagicMock()
    provider.name.return_value = name
    provider.cloud_name.return_value = cloud
    provider.controller_name.return_value = controller or f"concierge-{name}"
    provider.bootstrap.return_value = bootstrap
    provider.group_name.return_value = ""
    provider.model_defaults.return_value = {}
    provider.bootstrap_constraints.return_value = {}
    return provider


def _system(controllers: dict[str, tuple[str, str]]) -> MagicMock:
    """Build a system whose juju knows the given controllers (name -> cloud, uuid)."""
    system = MagicMock()
    system.username.return_value = "ubuntu"
    system.calls = []

    async def run(cmd: Command) -> bytes:
        system.calls.append(cmd.args)
        if cmd.args[0] == "show-controller":
            name = cmd.args[1]
            if name not in controllers:
                raise CommandError(["juju"], 1, f"ERROR controller {name} not found")
            return _show_controller(name, *controllers[name])
        return b""

    system.run = AsyncMock(side_effect=run)
    return system


def _commands(system: MagicMock, verb: str) -> list[list[str]]:
    return [args for args in system.calls if args[0] == verb]


class TestProviderControllerName:
    @pytest.mark.parametrize("name", SUPPORTED_PROVIDERS)
    def test_default(self, name: str) -> None:
        config = _config(**{name: {"enable": True}})
        provider = create_provider(name, MagicMock(), config)
        assert provider is not None
        assert provider.controller_name() == f"concierge-{name}"

    @pytest.mark.parametrize("name", SUPPORTED_PROVIDERS)
    def test_configured(self, name: str) -> None:
        config = _config(**{name: {"enable": True, "controller-name": f"{name}-dev"}})
        provider = create_provider(name, MagicMock(), config)
        assert provider is not None
        assert provider.controller_name() == f"{name}-dev"

    def test_only_google_is_remote(self) -> None:
        """Restore skips local clouds, so a provider that costs money must never be local."""
        config = _config(**{name: {"enable": True} for name in SUPPORTED_PROVIDERS})
        for name in SUPPORTED_PROVIDERS:
            provider = create_provider(name, MagicMock(), config)
            assert provider is not None
            assert is_local_cloud(provider.cloud_name()) == (name != "google")


class TestConfig:
    def test_bootstrapped_controllers_round_trip(self) -> None:
        config = ConciergeConfig()
        config.bootstrapped_controllers["dev"] = BootstrappedController(cloud="google", uuid="u1")

        loaded = ConciergeConfig.from_dict(config.to_dict())

        assert loaded.bootstrapped_controllers == {
            "dev": BootstrappedController(cloud="google", uuid="u1")
        }


class TestPlanValidation:
    def _plan(self, **providers: dict[str, object]) -> Plan:
        return Plan(_config(**providers), MagicMock())

    async def test_defaults_are_valid(self) -> None:
        plan = self._plan(lxd={"enable": True, "bootstrap": True}, k8s={"enable": True})
        await plan._validate()

    @pytest.mark.parametrize("name", ["Dev", "-dev", "dev_1", "dev.1", "dev\n"])
    async def test_invalid_name(self, name: str) -> None:
        plan = self._plan(lxd={"enable": True, "bootstrap": True, "controller-name": name})
        with pytest.raises(ValueError, match="invalid controller name"):
            await plan._validate()

    async def test_shared_name(self) -> None:
        plan = self._plan(
            lxd={"enable": True, "bootstrap": True, "controller-name": "shared"},
            k8s={"enable": True, "bootstrap": True, "controller-name": "shared"},
        )
        with pytest.raises(ValueError, match="cannot share"):
            await plan._validate()

    async def test_not_bootstrapped_is_ignored(self) -> None:
        plan = self._plan(lxd={"enable": True, "controller-name": "Bad Name"})
        await plan._validate()

    async def test_skipped_when_juju_disabled(self) -> None:
        config = _config(lxd={"enable": True, "bootstrap": True, "controller-name": "Bad Name"})
        config.juju.disable = True
        await Plan(config, MagicMock())._validate()


class TestBootstrap:
    async def test_records_controller_with_uuid(self) -> None:
        system = _system({})
        provider = _provider("lxd", "localhost", "dev-mirror")
        handler = JujuHandler(system, ConciergeConfig(), [provider])

        # The controller exists once the bootstrap has run.
        async def run(cmd: Command) -> bytes:
            system.calls.append(cmd.args)
            if cmd.args[0] == "show-controller":
                if cmd.args[-1] != "json":
                    raise CommandError(["juju"], 1, "ERROR controller dev-mirror not found")
                return _show_controller("dev-mirror", "localhost", "uuid-1")
            return b""

        system.run = AsyncMock(side_effect=run)
        await handler._bootstrap_provider(provider)

        assert _commands(system, "bootstrap")[0][1:3] == ["localhost", "dev-mirror"]
        assert handler.config.bootstrapped_controllers == {
            "dev-mirror": BootstrappedController(cloud="localhost", uuid="uuid-1")
        }

    async def test_recorded_even_if_add_model_fails(self) -> None:
        provider = _provider("google", "google")
        config = ConciergeConfig()
        system = _system({"concierge-google": ("google", "u")})
        handler = JujuHandler(system, config, [provider])

        with patch.object(handler, "_check_bootstrapped", AsyncMock(return_value=False)):
            original = system.run.side_effect

            async def run(cmd: Command) -> bytes:
                if cmd.args[0] == "add-model":
                    raise CommandError(["juju"], 1, "boom")
                return await original(cmd)

            system.run = AsyncMock(side_effect=run)
            with pytest.raises(CommandError):
                await handler._bootstrap_provider(provider)

        assert "concierge-google" in config.bootstrapped_controllers

    async def test_nothing_recorded_in_dry_run(self) -> None:
        config = ConciergeConfig(dry_run=True)
        provider = _provider("lxd", "localhost")
        system = _system({})
        handler = JujuHandler(system, config, [provider])

        with patch.object(handler, "_check_bootstrapped", AsyncMock(return_value=False)):
            await handler._bootstrap_provider(provider)

        assert config.bootstrapped_controllers == {}
        assert not any(args[0] == "show-controller" for args in system.calls)

    async def test_existing_controller_on_same_cloud_is_reused(self) -> None:
        system = _system({"concierge-lxd": ("localhost", "u")})
        provider = _provider("lxd", "localhost")
        handler = JujuHandler(system, ConciergeConfig(), [provider])

        await handler._bootstrap_provider(provider)

        assert _commands(system, "bootstrap") == []
        assert handler.config.bootstrapped_controllers == {}

    async def test_existing_controller_on_other_cloud_fails(self) -> None:
        system = _system({"mine": ("aws", "u")})
        provider = _provider("lxd", "localhost", "mine")
        handler = JujuHandler(system, ConciergeConfig(), [provider])

        with pytest.raises(RuntimeError, match="set a different controller-name"):
            await handler._bootstrap_provider(provider)


class TestRestore:
    def _handler(
        self,
        system: MagicMock,
        recorded: dict[str, BootstrappedController],
        providers: list[MagicMock],
    ) -> JujuHandler:
        config = ConciergeConfig()
        config.bootstrapped_controllers = recorded
        return JujuHandler(system, config, providers)

    async def test_destroys_recorded_remote_controller_under_any_name(self) -> None:
        system = _system({"old-name": ("google", "u1")})
        handler = self._handler(
            system,
            {"old-name": BootstrappedController("google", "u1")},
            [_provider("google", "google")],
        )

        await handler._destroy_controller(
            "old-name", handler.config.bootstrapped_controllers["old-name"]
        )

        assert _commands(system, "kill-controller")[0][-1] == "old-name"

    async def test_skips_local_cloud(self) -> None:
        system = _system({"concierge-lxd": ("localhost", "u")})
        handler = self._handler(system, {}, [])

        await handler._destroy_controller(
            "concierge-lxd", BootstrappedController("localhost", "u")
        )

        assert system.calls == []

    async def test_skips_reused_name(self) -> None:
        system = _system({"dev": ("google", "other-uuid")})
        handler = self._handler(system, {}, [])

        await handler._destroy_controller("dev", BootstrappedController("google", "u1"))

        assert _commands(system, "kill-controller") == []

    async def test_skips_controller_on_different_cloud(self) -> None:
        system = _system({"dev": ("aws", "u1")})
        handler = self._handler(system, {}, [])

        await handler._destroy_controller("dev", BootstrappedController("google", "u1"))

        assert _commands(system, "kill-controller") == []

    async def test_missing_controller_is_not_an_error(self) -> None:
        system = _system({})
        handler = self._handler(system, {}, [])

        await handler._destroy_controller("gone", BootstrappedController("google", "u1"))

        assert _commands(system, "kill-controller") == []

    def test_unrecorded_default_named_remote_controller_is_included(self) -> None:
        providers = [_provider("google", "google"), _provider("lxd", "localhost")]
        handler = self._handler(MagicMock(), {}, providers)

        assert handler._controllers_to_destroy() == {
            "concierge-google": BootstrappedController(cloud="google")
        }

    def test_renamed_provider_opts_out_of_default_name_fallback(self) -> None:
        providers = [_provider("google", "google", "custom")]
        handler = self._handler(MagicMock(), {}, providers)

        assert handler._controllers_to_destroy() == {}

    def test_record_wins_over_fallback(self) -> None:
        record = {"concierge-google": BootstrappedController("google", "u1")}
        handler = self._handler(MagicMock(), record, [_provider("google", "google")])

        assert handler._controllers_to_destroy() == record

    async def test_restore_destroys_in_sorted_order(self) -> None:
        system = _system({"b": ("google", "u"), "a": ("google", "u")})
        system.home_dir.return_value = Path("/home/ubuntu")
        system.remove_path = AsyncMock()
        record = {
            "b": BootstrappedController("google", "u"),
            "a": BootstrappedController("google", "u"),
        }
        handler = self._handler(system, record, [])

        with patch("concierge.juju.handler.SnapHandler") as snap_handler:
            snap_handler.return_value.restore = AsyncMock()
            await handler.restore()

        assert [args[-1] for args in _commands(system, "kill-controller")] == ["a", "b"]


class TestManagerCarriesRecordForward:
    def _manager(self) -> Manager:
        manager = Manager(ConciergeConfig())
        manager.system = MagicMock()
        return manager

    async def test_reads_previous_record(self) -> None:
        manager = self._manager()
        previous = b"bootstrapped-controllers:\n  old:\n    cloud: google\n    uuid: u1\n"

        with patch("concierge.core.manager.read_home_file", AsyncMock(return_value=previous)):
            result = await manager._previous_bootstrapped_controllers()

        assert result == {"old": BootstrappedController("google", "u1")}

    async def test_no_cache_means_no_controllers(self) -> None:
        manager = self._manager()

        with patch(
            "concierge.core.manager.read_home_file", AsyncMock(side_effect=FileNotFoundError)
        ):
            assert await manager._previous_bootstrapped_controllers() == {}

    async def test_unreadable_cache_warns_and_continues(self) -> None:
        manager = self._manager()

        with patch("concierge.core.manager.read_home_file", AsyncMock(return_value=b"a: [b")):
            assert await manager._previous_bootstrapped_controllers() == {}
