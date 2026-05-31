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


def _install_args(worker: MagicMock) -> list[str]:
    commands: list[Command] = [call.args[0] for call in worker.run_exclusive.await_args_list]
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
