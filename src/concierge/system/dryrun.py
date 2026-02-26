"""Dry-run worker that prints commands without executing them."""

import sys
from pathlib import Path
from typing import TextIO

from concierge.system.command import Command
from concierge.system.models import SnapInfo
from concierge.system.worker import Worker


class DryRunWorker:
    """Worker that outputs what would happen without making changes.

    Read operations are delegated to the real system for accurate conditional
    logic. Write/execute operations print what would be done.
    """

    def __init__(self, real_system: Worker, out: TextIO = sys.stdout) -> None:
        self._real = real_system
        self._out = out

    def username(self) -> str:
        return self._real.username()

    def home_dir(self) -> Path:
        return self._real.home_dir()

    async def run(self, cmd: Command) -> bytes:
        if cmd.read_only:
            return await self._real.run(cmd)
        print(cmd.command_string, file=self._out)
        return b""

    async def run_exclusive(self, cmd: Command) -> bytes:
        if cmd.read_only:
            return await self._real.run_exclusive(cmd)
        print(cmd.command_string, file=self._out)
        return b""

    async def run_with_retries(self, cmd: Command, max_duration_ms: int) -> bytes:
        if cmd.read_only:
            return await self._real.run_with_retries(cmd, max_duration_ms)
        print(cmd.command_string, file=self._out)
        return b""

    async def write_home_file(self, filepath: Path, _contents: bytes) -> None:
        full_path = self._real.home_dir() / filepath
        print(f"# Write file: {full_path}", file=self._out)

    async def mk_home_subdir(self, subdirectory: Path) -> None:
        full_path = self._real.home_dir() / subdirectory
        print(f"mkdir -p {full_path}", file=self._out)

    async def remove_all_home(self, filepath: Path) -> None:
        full_path = self._real.home_dir() / filepath
        print(f"rm -rf {full_path}", file=self._out)

    async def read_home_file(self, filepath: Path) -> bytes:
        return await self._real.read_home_file(filepath)

    async def read_file(self, filepath: Path) -> bytes:
        return await self._real.read_file(filepath)

    async def snap_info(self, snap: str, channel: str = "") -> SnapInfo:
        return await self._real.snap_info(snap, channel)

    async def snap_channels(self, snap: str) -> list[str]:
        return await self._real.snap_channels(snap)
