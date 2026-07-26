"""Unit tests for the DebHandler."""

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from concierge.packages.deb_handler import DebHandler

if TYPE_CHECKING:
    from concierge.system.command import Command

APT_ENV_PREFIX = "DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a"


def _make_handler(packages: list[str]) -> tuple[DebHandler, MagicMock]:
    worker = MagicMock()
    worker.run = AsyncMock()
    return DebHandler(worker, packages), worker


def _commands(worker: MagicMock) -> list[Command]:
    return [call.args[0] for call in worker.run.await_args_list]


class TestDebHandlerCommands:
    """Tests that DebHandler emits non-interactive apt-get commands.

    All apt-get invocations must carry the non-interactive environment
    (`DEBIAN_FRONTEND` and `NEEDRESTART_MODE`), and installs must additionally
    keep dpkg from prompting on conffile conflicts. Without these, a real
    `concierge prepare` run has been observed to hang forever on the
    needrestart "which services should be restarted?" post-invoke dialog.
    """

    @pytest.mark.asyncio
    async def test_prepare_runs_update_then_install_non_interactively(self) -> None:
        handler, worker = _make_handler(["cowsay", "python3-venv"])

        await handler.prepare()

        commands = _commands(worker)
        assert [c.executable for c in commands] == ["apt-get", "apt-get", "apt-get"]
        assert [c.args for c in commands] == [
            ["-y", "update"],
            [
                "-y",
                "install",
                "-o",
                "Dpkg::Options::=--force-confdef",
                "-o",
                "Dpkg::Options::=--force-confold",
                "cowsay",
            ],
            [
                "-y",
                "install",
                "-o",
                "Dpkg::Options::=--force-confdef",
                "-o",
                "Dpkg::Options::=--force-confold",
                "python3-venv",
            ],
        ]
        for c in commands:
            assert c.env == ["DEBIAN_FRONTEND=noninteractive", "NEEDRESTART_MODE=a"]
            assert c.command_string.startswith(APT_ENV_PREFIX + " ")

    @pytest.mark.asyncio
    async def test_restore_runs_remove_then_autoremove_non_interactively(self) -> None:
        handler, worker = _make_handler(["cowsay", "python3-venv"])

        await handler.restore()

        commands = _commands(worker)
        assert [c.executable for c in commands] == ["apt-get", "apt-get", "apt-get"]
        assert [c.args for c in commands] == [
            ["-y", "remove", "cowsay"],
            ["-y", "remove", "python3-venv"],
            ["-y", "autoremove"],
        ]
        for c in commands:
            assert c.env == ["DEBIAN_FRONTEND=noninteractive", "NEEDRESTART_MODE=a"]
            assert c.command_string.startswith(APT_ENV_PREFIX + " ")

    @pytest.mark.asyncio
    async def test_prepare_with_no_packages_is_a_no_op(self) -> None:
        handler, worker = _make_handler([])

        await handler.prepare()

        worker.run.assert_not_awaited()
