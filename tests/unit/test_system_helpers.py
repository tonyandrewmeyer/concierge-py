"""Tests for system helper functions."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from concierge.system.command import Command, CommandError
from concierge.system.helpers import (
    mk_home_subdir,
    read_home_file,
    run_exclusive,
    run_with_retries,
    write_home_file,
)


@pytest.fixture
def mock_worker() -> MagicMock:
    worker = MagicMock()
    worker.username.return_value = "testuser"
    worker.home_dir.return_value = Path("/home/testuser")
    worker.run = AsyncMock(return_value=b"output")
    worker.read_file = AsyncMock(return_value=b"file contents")
    worker.write_file = AsyncMock()
    worker.mkdir_all = AsyncMock()
    worker.remove_path = AsyncMock()
    worker.chown_all = AsyncMock()
    return worker


class TestRunExclusive:
    async def test_delegates_to_run(self, mock_worker: MagicMock) -> None:
        cmd = Command(executable="snap", args=["install", "juju"])
        result = await run_exclusive(mock_worker, cmd)
        assert result == b"output"
        mock_worker.run.assert_called_once_with(cmd)

    async def test_serializes_same_executable(self, mock_worker: MagicMock) -> None:
        """Commands with the same executable should not run concurrently."""
        call_order: list[str] = []

        async def slow_run(cmd: Command) -> bytes:
            call_order.append(f"start-{cmd.args[0]}")
            await asyncio.sleep(0.01)
            call_order.append(f"end-{cmd.args[0]}")
            return b""

        mock_worker.run = AsyncMock(side_effect=slow_run)

        cmd1 = Command(executable="snap", args=["first"])
        cmd2 = Command(executable="snap", args=["second"])

        await asyncio.gather(
            run_exclusive(mock_worker, cmd1),
            run_exclusive(mock_worker, cmd2),
        )

        # The second command should not start until the first finishes.
        assert call_order.index("end-first") < call_order.index("start-second")


class TestRunWithRetries:
    async def test_succeeds_first_try(self, mock_worker: MagicMock) -> None:
        cmd = Command(executable="k8s", args=["status"])
        result = await run_with_retries(mock_worker, cmd, 5000)
        assert result == b"output"

    async def test_retries_on_command_error(self, mock_worker: MagicMock) -> None:
        cmd = Command(executable="k8s", args=["status"])
        mock_worker.run = AsyncMock(
            side_effect=[CommandError("k8s status", 1, "not ready"), b"ready"]
        )
        result = await run_with_retries(mock_worker, cmd, 10000)
        assert result == b"ready"
        assert mock_worker.run.call_count == 2

    async def test_raises_after_all_retries_fail(self, mock_worker: MagicMock) -> None:
        cmd = Command(executable="k8s", args=["status"])
        mock_worker.run = AsyncMock(side_effect=CommandError("k8s status", 1, "not ready"))
        with pytest.raises(CommandError):
            await run_with_retries(mock_worker, cmd, 1000)


class TestReadHomeFile:
    async def test_reads_relative_to_home(self, mock_worker: MagicMock) -> None:
        result = await read_home_file(mock_worker, Path(".cache/concierge/concierge.yaml"))
        assert result == b"file contents"
        mock_worker.read_file.assert_called_once_with(
            Path("/home/testuser/.cache/concierge/concierge.yaml")
        )


class TestWriteHomeFile:
    async def test_creates_parent_dirs_and_writes(self, mock_worker: MagicMock) -> None:
        await write_home_file(mock_worker, Path(".kube/config"), b"kubeconfig")

        # Should create parent directory
        mock_worker.mkdir_all.assert_called_once_with(Path("/home/testuser/.kube"))
        # Should write file
        mock_worker.write_file.assert_called_once_with(
            Path("/home/testuser/.kube/config"), b"kubeconfig"
        )
        # Should chown both the top-level dir and the file
        assert mock_worker.chown_all.call_count == 2


class TestMkHomeSubdir:
    async def test_creates_directory_and_chowns(self, mock_worker: MagicMock) -> None:
        await mk_home_subdir(mock_worker, Path(".local/share/juju"))

        mock_worker.mkdir_all.assert_called_once_with(
            Path("/home/testuser/.local/share/juju")
        )
        # Should chown the top-level directory
        mock_worker.chown_all.assert_called_once_with(Path("/home/testuser/.local"))

    async def test_rejects_absolute_path(self, mock_worker: MagicMock) -> None:
        with pytest.raises(ValueError, match="Only relative paths"):
            await mk_home_subdir(mock_worker, Path("/absolute/path"))

    async def test_empty_path_no_chown(self, mock_worker: MagicMock) -> None:
        await mk_home_subdir(mock_worker, Path())
        mock_worker.mkdir_all.assert_called_once()
        mock_worker.chown_all.assert_not_called()
