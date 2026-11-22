"""Unit tests for the LXD provider."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from concierge.config.models import ConciergeConfig, ConfigOverrides, LXDConfig, ProviderConfig
from concierge.providers.lxd import LXD
from concierge.system.command import Command, CommandError
from concierge.system.models import SnapInfo


def _make_lxd(
    snap_info: SnapInfo, *, channel: str = "5.21/stable", skip_snap_refresh: bool = False
) -> tuple[LXD, MagicMock]:
    worker = MagicMock()
    worker.run = AsyncMock()
    worker.snap_info = AsyncMock(return_value=snap_info)
    worker.snap_installed_info = AsyncMock(return_value=snap_info)
    config = ConciergeConfig(
        providers=ProviderConfig(lxd=LXDConfig(enable=True, channel=channel)),
        overrides=ConfigOverrides(skip_snap_refresh=skip_snap_refresh),
    )
    return LXD(worker, config), worker


def _snap_commands(worker: MagicMock) -> list[list[str]]:
    commands: list[Command] = [call.args[0] for call in worker.run.await_args_list]
    return [c.args for c in commands if c.executable == "snap"]


class TestLXDInstall:
    """Tests for LXD._install, which wraps the snap refresh workaround."""

    @pytest.mark.asyncio
    async def test_looks_up_snap_once(self) -> None:
        lxd, worker = _make_lxd(
            SnapInfo(installed=True, active=True, tracking_channel="5.0/stable")
        )

        await lxd._install()

        worker.snap_info.assert_awaited_once_with("lxd", "5.21/stable")
        assert _snap_commands(worker) == [
            ["stop", "lxd"],
            ["refresh", "lxd", "--channel", "5.21/stable"],
            ["start", "lxd"],
        ]

    @pytest.mark.asyncio
    async def test_no_stop_when_channel_unchanged(self) -> None:
        lxd, worker = _make_lxd(
            SnapInfo(installed=True, active=True, tracking_channel="5.21/stable")
        )

        await lxd._install()

        assert _snap_commands(worker) == [["refresh", "lxd", "--channel", "5.21/stable"]]

    @pytest.mark.asyncio
    async def test_failed_lookup_leaves_lxd_untouched(self) -> None:
        lxd, worker = _make_lxd(SnapInfo())
        worker.snap_info.side_effect = RuntimeError("store unreachable")

        with pytest.raises(RuntimeError):
            await lxd._install()

        worker.run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_restarts_lxd_even_if_refresh_fails(self) -> None:
        lxd, worker = _make_lxd(
            SnapInfo(installed=True, active=True, tracking_channel="5.0/stable")
        )

        async def run(cmd: Command) -> bytes:
            if cmd.args[0] == "refresh":
                raise CommandError("snap refresh lxd", 1, "refresh failed")
            return b""

        worker.run.side_effect = run

        with pytest.raises(CommandError):
            await lxd._install()

        assert _snap_commands(worker)[-1] == ["start", "lxd"]

    @pytest.mark.asyncio
    async def test_no_stop_when_channel_only_differs_in_form(self) -> None:
        lxd, worker = _make_lxd(
            SnapInfo(installed=True, active=True, tracking_channel="latest/stable"),
            channel="stable",
        )

        await lxd._install()

        assert _snap_commands(worker) == [["refresh", "lxd", "--channel", "stable"]]

    @pytest.mark.asyncio
    async def test_skip_snap_refresh_leaves_current_lxd_alone(self) -> None:
        lxd, worker = _make_lxd(
            SnapInfo(installed=True, active=True, tracking_channel="5.21/stable"),
            skip_snap_refresh=True,
        )

        await lxd._install()

        worker.snap_info.assert_not_awaited()
        assert _snap_commands(worker) == []

    @pytest.mark.asyncio
    async def test_skip_snap_refresh_still_changes_channel(self) -> None:
        lxd, worker = _make_lxd(
            SnapInfo(installed=True, active=True, tracking_channel="5.0/stable"),
            skip_snap_refresh=True,
        )

        await lxd._install()

        assert _snap_commands(worker) == [
            ["stop", "lxd"],
            ["refresh", "lxd", "--channel", "5.21/stable"],
            ["start", "lxd"],
        ]
