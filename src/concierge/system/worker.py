"""Worker protocol for system operations."""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path

    from concierge.system.command import Command
    from concierge.system.models import InstalledSnapInfo, SnapInfo


@runtime_checkable
class Worker(Protocol):
    """Protocol defining primitive system operations.

    Higher-level operations (run_exclusive, run_with_retries, write_home_file,
    read_home_file, mk_home_subdir) are standalone helper functions in helpers.py.
    """

    async def run(self, cmd: Command) -> bytes:
        """Execute a command and return its output."""
        ...

    async def read_file(self, filepath: Path) -> bytes:
        """Read a file from the filesystem."""
        ...

    async def write_file(self, filepath: Path, contents: bytes) -> None:
        """Write contents to a file."""
        ...

    async def mkdir_all(self, dirpath: Path) -> None:
        """Create a directory and all parent directories."""
        ...

    async def remove_path(self, filepath: Path) -> None:
        """Recursively remove a file or directory."""
        ...

    async def chown_all(self, path: Path) -> None:
        """Recursively change ownership to the real user."""
        ...

    async def snap_info(self, snap: str, channel: str = "") -> SnapInfo:
        """Get information about a snap from the snapd API."""
        ...

    async def snap_installed_info(self, snap: str) -> InstalledSnapInfo:
        """Get information about an installed snap without querying the snap store.

        A snap that is not installed is not an error, but failing to query snapd is.
        """
        ...

    async def snap_channels(self, snap: str) -> list[str]:
        """Get list of available channels for a snap."""
        ...

    def username(self) -> str:
        """Get the real username (not root if running with sudo)."""
        ...

    def home_dir(self) -> Path:
        """Get the real user's home directory."""
        ...
