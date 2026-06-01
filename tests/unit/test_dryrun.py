"""Unit tests for DryRunWorker."""

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from concierge.system.command import Command
from concierge.system.dryrun import DryRunWorker
from concierge.system.models import SnapInfo

MOCK_SNAP_INFO = SnapInfo(installed=True, classic=False, tracking_channel="latest/stable")


@pytest.fixture
def mock_system() -> MagicMock:
    system = MagicMock()
    system.username.return_value = "testuser"
    system.home_dir.return_value = Path("/home/testuser")
    system.run = AsyncMock(return_value=b"output")
    system.run_exclusive = AsyncMock(return_value=b"output")
    system.run_with_retries = AsyncMock(return_value=b"output")
    system.read_home_file = AsyncMock(return_value=b"file contents")
    system.read_file = AsyncMock(return_value=b"file contents")
    system.snap_info = AsyncMock(return_value=MOCK_SNAP_INFO)
    system.snap_channels = AsyncMock(return_value=["latest/stable"])
    return system


class TestDryRunWorker:
    """Tests for DryRunWorker."""

    async def test_run_prints_command(self, mock_system: MagicMock) -> None:
        out = io.StringIO()
        worker = DryRunWorker(mock_system, out=out)
        cmd = Command(executable="snap", args=["install", "juju"])
        result = await worker.run(cmd)
        assert result == b""
        assert "snap" in out.getvalue()
        assert "install" in out.getvalue()
        mock_system.run.assert_not_called()

    async def test_run_delegates_read_only(self, mock_system: MagicMock) -> None:
        out = io.StringIO()
        worker = DryRunWorker(mock_system, out=out)
        cmd = Command(executable="k8s", args=["status"], read_only=True)
        result = await worker.run(cmd)
        assert result == b"output"
        assert out.getvalue() == ""
        mock_system.run.assert_called_once()

    async def test_write_file_prints(self, mock_system: MagicMock) -> None:
        out = io.StringIO()
        worker = DryRunWorker(mock_system, out=out)
        await worker.write_file(Path("/home/testuser/.cache/test"), b"data")
        assert "# Write file: /home/testuser/.cache/test" in out.getvalue()

    async def test_mkdir_all_prints(self, mock_system: MagicMock) -> None:
        out = io.StringIO()
        worker = DryRunWorker(mock_system, out=out)
        await worker.mkdir_all(Path("/home/testuser/.local/share/juju"))
        assert "mkdir -p /home/testuser/.local/share/juju" in out.getvalue()

    async def test_remove_path_prints(self, mock_system: MagicMock) -> None:
        out = io.StringIO()
        worker = DryRunWorker(mock_system, out=out)
        await worker.remove_path(Path("/home/testuser/.kube"))
        assert "rm -rf /home/testuser/.kube" in out.getvalue()

    async def test_read_file_delegates(self, mock_system: MagicMock) -> None:
        worker = DryRunWorker(mock_system)
        result = await worker.read_file(Path("/home/testuser/.config/test"))
        assert result == b"file contents"
        mock_system.read_file.assert_called_once()

    async def test_snap_info_delegates(self, mock_system: MagicMock) -> None:
        worker = DryRunWorker(mock_system)
        result = await worker.snap_info("juju")
        assert result.installed is True
        mock_system.snap_info.assert_called_once()

    async def test_snap_channels_delegates(self, mock_system: MagicMock) -> None:
        worker = DryRunWorker(mock_system)
        result = await worker.snap_channels("juju")
        assert result == ["latest/stable"]
        mock_system.snap_channels.assert_called_once()

    def test_username_delegates(self, mock_system: MagicMock) -> None:
        worker = DryRunWorker(mock_system)
        assert worker.username() == "testuser"

    def test_home_dir_delegates(self, mock_system: MagicMock) -> None:
        worker = DryRunWorker(mock_system)
        assert worker.home_dir() == Path("/home/testuser")
