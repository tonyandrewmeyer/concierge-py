"""Worker protocol for system operations."""

from pathlib import Path
from typing import Protocol, runtime_checkable

from concierge.system.command import Command
from concierge.system.models import SnapInfo


@runtime_checkable
class Worker(Protocol):
    """Protocol for a system that can execute commands and perform system operations.

    This protocol defines the interface that all system implementations must follow,
    allowing for both real system operations and mocked implementations for testing.
    """

    async def run(self, cmd: Command) -> bytes:
        """Execute a command and return its output.

        Args:
            cmd: Command to execute

        Returns:
            Combined stdout/stderr output as bytes

        Raises:
            CommandError: If the command fails
        """
        ...

    async def run_exclusive(self, cmd: Command) -> bytes:
        """Execute a command with exclusive locking.

        Only one command with the same executable can run at a time.

        Args:
            cmd: Command to execute

        Returns:
            Combined stdout/stderr output as bytes

        Raises:
            CommandError: If the command fails
        """
        ...

    async def run_with_retries(self, cmd: Command, max_duration_ms: int) -> bytes:
        """Execute a command with exponential backoff retries.

        Args:
            cmd: Command to execute
            max_duration_ms: Maximum duration for retries in milliseconds

        Returns:
            Combined stdout/stderr output as bytes

        Raises:
            CommandError: If all retries fail
        """
        ...

    async def write_home_file(self, filepath: Path, contents: bytes) -> None:
        """Write a file to the user's home directory.

        Args:
            filepath: Relative path within home directory
            contents: File contents to write

        Raises:
            OSError: If file cannot be written
        """
        ...

    async def mk_home_subdir(self, subdirectory: Path) -> None:
        """Create a directory in the user's home directory.

        Args:
            subdirectory: Relative path within home directory

        Raises:
            OSError: If directory cannot be created
        """
        ...

    async def remove_all_home(self, filepath: Path) -> None:
        """Recursively remove a file or directory from the user's home.

        Args:
            filepath: Relative path within home directory

        Raises:
            OSError: If removal fails
        """
        ...

    async def read_home_file(self, filepath: Path) -> bytes:
        """Read a file from the user's home directory.

        Args:
            filepath: Relative path within home directory

        Returns:
            File contents as bytes

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        ...

    async def read_file(self, filepath: Path) -> bytes:
        """Read a file from anywhere on the filesystem.

        Args:
            filepath: Absolute path to file

        Returns:
            File contents as bytes

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        ...

    async def snap_info(self, snap: str, channel: str = "") -> SnapInfo:
        """Get information about a snap from the snapd API.

        Args:
            snap: Name of the snap
            channel: Optional channel to query

        Returns:
            Snap information

        Raises:
            Exception: If snapd API fails
        """
        ...

    async def snap_channels(self, snap: str) -> list[str]:
        """Get list of available channels for a snap.

        Args:
            snap: Name of the snap

        Returns:
            List of channel names, sorted

        Raises:
            Exception: If snapd API fails
        """
        ...

    def username(self) -> str:
        """Get the real username (not root if running with sudo).

        Returns:
            Username
        """
        ...

    def home_dir(self) -> Path:
        """Get the real user's home directory.

        Returns:
            Path to home directory
        """
        ...
