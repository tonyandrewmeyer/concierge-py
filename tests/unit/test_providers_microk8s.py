"""Unit tests for the MicroK8s provider."""

import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest

from concierge.config.models import (
    ConciergeConfig,
    ConfigOverrides,
    ImageRegistryConfig,
    MicroK8sConfig,
    ProviderConfig,
)
from concierge.providers.microk8s import MicroK8s, compute_default_channel
from concierge.system.models import InstalledSnapInfo, SnapInfo


def _make_microk8s(*, image_registry_url: str = "") -> MicroK8s:
    """Construct a MicroK8s provider with a mocked worker."""
    worker = MagicMock()
    worker.run = AsyncMock(return_value=b"")
    worker.run_with_retries = AsyncMock(return_value=b"")
    worker.snap_channels = AsyncMock(return_value=["1.32-strict/stable"])
    worker.username = MagicMock(return_value="ubuntu")

    config = ConciergeConfig(
        providers=ProviderConfig(
            microk8s=MicroK8sConfig(
                enable=True,
                bootstrap=True,
                channel="1.32-strict/stable",
                image_registry=ImageRegistryConfig(url=image_registry_url),
            )
        ),
        overrides=ConfigOverrides(),
    )
    return MicroK8s(worker, config)


class TestMicroK8sPrepareImageRegistryOrder:
    """The MicroK8s init/wait-ready must run before image-registry stop/start.

    Otherwise `microk8s stop` races with snapd's in-progress
    `service-control` change from the just-completed `snap install microk8s`,
    leaving the cluster wedged.
    """

    @pytest.mark.asyncio
    async def test_wait_ready_before_and_after_stop_start(self) -> None:
        microk8s = _make_microk8s(image_registry_url="https://mirror.example.com")

        # Skip steps that don't matter for ordering and would require more mocking.
        microk8s._install = AsyncMock()  # type: ignore[method-assign]
        microk8s._enable_addons = AsyncMock()  # type: ignore[method-assign]
        microk8s._enable_non_root_user_control = AsyncMock()  # type: ignore[method-assign]
        microk8s._setup_kubectl = AsyncMock()  # type: ignore[method-assign]

        await microk8s.prepare()

        # run_with_retries is the standalone helper, not a worker method,
        # so the wait-ready calls flow through worker.run instead.
        run_cmds = [
            (c.args[0].executable, tuple(c.args[0].args))
            for c in microk8s.system.run.await_args_list
        ]
        wait_ready = ("microk8s", ("status", "--wait-ready", "--timeout", "270"))
        stop = ("microk8s", ("stop",))
        start = ("microk8s", ("start",))

        wait_ready_indices = [i for i, c in enumerate(run_cmds) if c == wait_ready]
        stop_indices = [i for i, c in enumerate(run_cmds) if c == stop]
        start_indices = [i for i, c in enumerate(run_cmds) if c == start]

        assert len(wait_ready_indices) >= 2, "expected wait-ready before stop and after start"
        assert len(stop_indices) == 1
        assert len(start_indices) == 1

        assert wait_ready_indices[0] < stop_indices[0], "first wait-ready must run before stop"
        assert start_indices[0] < wait_ready_indices[-1], "final wait-ready must run after start"

    @pytest.mark.asyncio
    async def test_wait_ready_runs_even_without_image_registry(self) -> None:
        microk8s = _make_microk8s(image_registry_url="")

        microk8s._install = AsyncMock()  # type: ignore[method-assign]
        microk8s._enable_addons = AsyncMock()  # type: ignore[method-assign]
        microk8s._enable_non_root_user_control = AsyncMock()  # type: ignore[method-assign]
        microk8s._setup_kubectl = AsyncMock()  # type: ignore[method-assign]

        await microk8s.prepare()

        run_cmds = [
            (c.args[0].executable, tuple(c.args[0].args))
            for c in microk8s.system.run.await_args_list
        ]
        wait_ready = ("microk8s", ("status", "--wait-ready", "--timeout", "270"))
        assert run_cmds.count(wait_ready) == 1
        # No stop/start without an image registry configured.
        assert ("microk8s", ("stop",)) not in run_cmds
        assert ("microk8s", ("start",)) not in run_cmds


def _microk8s_with_snapd(
    local: InstalledSnapInfo, *, channel: str = "", skip_snap_refresh: bool = False
) -> tuple[MicroK8s, MagicMock]:
    worker = MagicMock()
    worker.run = AsyncMock(return_value=b"")
    worker.username = MagicMock(return_value="ubuntu")
    worker.snap_channels = AsyncMock(return_value=["1.34-strict/stable", "1.34/stable"])
    worker.snap_installed_info = AsyncMock(return_value=local)
    worker.snap_info = AsyncMock(
        side_effect=lambda name, channel="": SnapInfo(
            **dataclasses.asdict(local if name == "microk8s" else InstalledSnapInfo())
        )
    )
    config = ConciergeConfig(
        providers=ProviderConfig(microk8s=MicroK8sConfig(enable=True, channel=channel)),
        overrides=ConfigOverrides(skip_snap_refresh=skip_snap_refresh),
    )
    return MicroK8s(worker, config), worker


async def _prepare_snaps(microk8s: MicroK8s) -> None:
    """Run the parts of prepare that choose the channel and install the snaps."""
    if not microk8s.channel:
        microk8s.snaps[0].default_channel = await compute_default_channel(microk8s.system)
        microk8s.channel = microk8s.snaps[0].default_channel
    await microk8s._install()


def _snap_args(worker: MagicMock) -> list[list[str]]:
    return [
        call.args[0].args
        for call in worker.run.await_args_list
        if call.args[0].executable == "snap"
    ]


class TestMicroK8sChannel:
    """Tests for the MicroK8s channel, where the default only applies to fresh installs."""

    def test_requested_channel(self) -> None:
        microk8s, _ = _microk8s_with_snapd(InstalledSnapInfo(), channel="1.29-strict/stable")

        assert microk8s.snaps[0].channel == "1.29-strict/stable"
        assert microk8s.snaps[0].default_channel == ""
        assert microk8s.channel == "1.29-strict/stable"

    @pytest.mark.asyncio
    async def test_prepare_sets_default_channel_not_channel(self) -> None:
        microk8s, _ = _microk8s_with_snapd(InstalledSnapInfo())
        for step in (
            "_install",
            "_init",
            "_configure_image_registry",
            "_enable_addons",
            "_enable_non_root_user_control",
            "_setup_kubectl",
        ):
            setattr(microk8s, step, AsyncMock())

        await microk8s.prepare()

        assert microk8s.snaps[0].channel == ""
        assert microk8s.snaps[0].default_channel == "1.34-strict/stable"
        assert microk8s.channel == "1.34-strict/stable"

    @pytest.mark.asyncio
    async def test_fresh_install_uses_default_channel(self) -> None:
        microk8s, worker = _microk8s_with_snapd(InstalledSnapInfo())

        await _prepare_snaps(microk8s)

        assert ["install", "microk8s", "--channel", "1.34-strict/stable"] in _snap_args(worker)
        assert microk8s.group_name() == "snap_microk8s"

    @pytest.mark.asyncio
    async def test_installed_microk8s_keeps_its_channel(self) -> None:
        microk8s, worker = _microk8s_with_snapd(
            InstalledSnapInfo(installed=True, active=True, tracking_channel="1.30/stable")
        )

        await _prepare_snaps(microk8s)

        assert ["refresh", "microk8s"] in _snap_args(worker)
        # The group follows the installed channel, which is not strict.
        assert microk8s.channel == "1.30/stable"
        assert microk8s.group_name() == "microk8s"

    @pytest.mark.asyncio
    async def test_skip_snap_refresh_keeps_installed_channel(self) -> None:
        microk8s, worker = _microk8s_with_snapd(
            InstalledSnapInfo(installed=True, active=True, tracking_channel="1.30/stable"),
            skip_snap_refresh=True,
        )
        worker.snap_info.side_effect = None
        worker.snap_info.return_value = SnapInfo()
        worker.snap_installed_info.side_effect = lambda name: (
            InstalledSnapInfo(installed=True, active=True, tracking_channel="1.30/stable")
            if name == "microk8s"
            else InstalledSnapInfo(installed=True, active=True, tracking_channel="latest/stable")
        )

        await microk8s._install()

        # With no channel requested, the installed channel will do, so nothing is
        # refreshed, and finding that channel needs only the local snapd.
        assert _snap_args(worker) == []
        worker.snap_info.assert_not_awaited()
        assert microk8s.channel == "1.30/stable"

    @pytest.mark.asyncio
    async def test_requested_channel_is_not_replaced_by_installed_one(self) -> None:
        microk8s, worker = _microk8s_with_snapd(
            InstalledSnapInfo(installed=True, active=True, tracking_channel="1.30/stable"),
            channel="1.32-strict/stable",
        )

        await microk8s._install()

        assert ["refresh", "microk8s", "--channel", "1.32-strict/stable"] in _snap_args(worker)
        assert microk8s.channel == "1.32-strict/stable"
        assert microk8s.group_name() == "snap_microk8s"
