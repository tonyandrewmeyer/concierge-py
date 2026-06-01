"""Unit tests for the SnapHandler."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from concierge.packages.snap_handler import SnapHandler
from concierge.system.command import Command
from concierge.system.models import Snap, SnapInfo


def _make_handler(snap: Snap, snap_info: SnapInfo) -> tuple[SnapHandler, MagicMock]:
    worker = MagicMock()
    worker.snap_info = AsyncMock(return_value=snap_info)
    worker.run = AsyncMock()
    worker.run_exclusive = AsyncMock()
    handler = SnapHandler(worker, [snap])
    return handler, worker


def _commands(worker: MagicMock) -> list[Command]:
    return [call.args[0] for call in worker.run.await_args_list]


def _install_args(worker: MagicMock) -> list[str]:
    commands = _commands(worker)
    assert len(commands) == 1
    return commands[0].args


class TestSnapHandlerRevision:
    """Tests for how SnapHandler passes the snap revision through to snap install."""

    @pytest.mark.asyncio
    async def test_revision_only(self) -> None:
        """A revision-only snap should produce a --revision argument."""
        handler, worker = _make_handler(
            Snap(name="juju", revision="30000"),
            SnapInfo(installed=False, classic=False),
        )

        await handler.prepare()

        assert _install_args(worker) == ["install", "juju", "--revision", "30000"]

    @pytest.mark.asyncio
    async def test_channel_and_revision(self) -> None:
        """Both --channel and --revision should appear when both are set.

        Snap installs the specified revision and uses the channel only for
        tracking after install.
        """
        handler, worker = _make_handler(
            Snap(name="juju", channel="3.6/stable", revision="30000"),
            SnapInfo(installed=False, classic=False),
        )

        await handler.prepare()

        assert _install_args(worker) == [
            "install",
            "juju",
            "--channel",
            "3.6/stable",
            "--revision",
            "30000",
        ]


class TestSnapHandlerInstall:
    """Tests for SnapHandler._install_snap."""

    @pytest.mark.asyncio
    async def test_active_snap_is_refreshed(self) -> None:
        """An installed and active snap should be refreshed, not enabled."""
        handler, worker = _make_handler(
            Snap(name="hello-world", channel="latest/stable"),
            SnapInfo(installed=True, classic=False, active=True),
        )

        await handler.prepare()

        actions = [(c.executable, c.args[0]) for c in _commands(worker)]
        assert ("snap", "refresh") in actions
        assert ("snap", "enable") not in actions
        assert ("snap", "install") not in actions

    @pytest.mark.asyncio
    async def test_disabled_snap_is_enabled_then_refreshed(self) -> None:
        """A disabled-but-installed snap must be enabled before refresh.

        Otherwise `snap refresh` will fail because snapd refuses to refresh a
        disabled snap, and we must not fall back to `snap install` because the
        snap is already on disk.
        """
        handler, worker = _make_handler(
            Snap(name="hello-world", channel="latest/stable"),
            SnapInfo(installed=True, classic=False, active=False),
        )

        await handler.prepare()

        actions = [(c.executable, c.args[0], c.args[1]) for c in _commands(worker)]
        assert ("snap", "enable", "hello-world") in actions
        assert ("snap", "refresh", "hello-world") in actions
        # Crucially, install must NOT be used for a snap that is already on disk.
        assert ("snap", "install", "hello-world") not in actions

        # Enable must come before refresh.
        enable_index = actions.index(("snap", "enable", "hello-world"))
        refresh_index = actions.index(("snap", "refresh", "hello-world"))
        assert enable_index < refresh_index

    @pytest.mark.asyncio
    async def test_not_installed_snap_is_installed(self) -> None:
        """A snap that is not on the system is installed (not enabled or refreshed)."""
        handler, worker = _make_handler(
            Snap(name="hello-world", channel="latest/stable"),
            SnapInfo(installed=False, classic=False, active=False),
        )

        await handler.prepare()

        actions = [(c.executable, c.args[0]) for c in _commands(worker)]
        assert ("snap", "install") in actions
        assert ("snap", "enable") not in actions
        assert ("snap", "refresh") not in actions
