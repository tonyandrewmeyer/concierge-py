"""System command runner implementation."""

import asyncio
import os
import pwd
import shutil
from pathlib import Path

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_delay,
    wait_exponential,
)

from concierge.core.logging import get_logger
from concierge.system.command import Command, CommandError
from concierge.system.models import SnapInfo
from concierge.system.snap import SnapdClient

logger = get_logger(__name__)


def _get_shell_path() -> str:
    """Get path to the shell to use for command execution.

    Returns:
        Path to shell executable

    Raises:
        RuntimeError: If no shell can be found
    """
    # Try SHELL environment variable first
    shell = os.getenv("SHELL")
    if shell:
        return shell

    # Try common shells
    for candidate in ["bash", "/bin/bash", "sh", "/bin/sh"]:
        if Path(candidate).exists():
            return candidate
        # Try finding in PATH
        path = shutil.which(candidate)
        if path:
            return path

    raise RuntimeError("Could not find path to a shell")


def _get_real_user() -> tuple[str, str]:
    """Get the real username and home directory.

    When running with sudo, this returns the original user instead of root.

    Returns:
        Tuple of (username, home_directory)
    """
    # Check if running under sudo
    sudo_user = os.getenv("SUDO_USER")
    if sudo_user:
        # Get home directory for sudo user
        sudo_home = os.getenv("SUDO_HOME") or f"/home/{sudo_user}"
        return sudo_user, sudo_home

    # Not running under sudo, use current user
    username = os.getenv("USER", "root")
    home = os.getenv("HOME", f"/home/{username}")
    return username, home


class System:
    """System implementation that executes commands on the local machine.

    This class implements the Worker protocol and provides methods for
    executing commands, managing files, and interacting with snapd.
    """

    def __init__(self, trace: bool = False) -> None:
        """Initialize the System.

        Args:
            trace: Enable trace logging for all command output
        """
        self._trace = trace
        self._shell = _get_shell_path()
        self._username, self._home_dir = _get_real_user()
        self._command_locks: dict[str, asyncio.Lock] = {}
        self._snapd_client = SnapdClient()

    def username(self) -> str:
        """Get the real username.

        Returns:
            Username
        """
        return self._username

    def home_dir(self) -> Path:
        """Get the real user's home directory.

        Returns:
            Path to home directory
        """
        return Path(self._home_dir)

    async def run(self, cmd: Command) -> bytes:
        """Execute a command and return its output.

        Args:
            cmd: Command to execute

        Returns:
            Combined stdout/stderr output as bytes

        Raises:
            CommandError: If the command fails
        """
        command_string = cmd.command_string

        log_ctx = {}
        if cmd.user:
            log_ctx["user"] = cmd.user
        if cmd.group:
            log_ctx["group"] = cmd.group

        logger.debug("Starting command", command=command_string, **log_ctx)

        # Create subprocess
        process = await asyncio.create_subprocess_shell(
            command_string,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            executable=self._shell,
        )

        # Wait for command to complete
        stdout, _ = await process.communicate()

        if process.returncode != 0:
            output_str = stdout.decode("utf-8", errors="replace")
            if self._trace:
                self._print_trace(command_string, output_str)
            # After communicate(), returncode should always be set
            returncode = process.returncode if process.returncode is not None else 1
            raise CommandError(command_string, returncode, output_str)

        if self._trace:
            output_str = stdout.decode("utf-8", errors="replace")
            self._print_trace(command_string, output_str)

        logger.debug("Finished command", command=command_string)

        return stdout

    async def run_exclusive(self, cmd: Command) -> bytes:
        """Execute a command with exclusive locking.

        Args:
            cmd: Command to execute

        Returns:
            Combined stdout/stderr output as bytes

        Raises:
            CommandError: If the command fails
        """
        # Get or create lock for this executable
        if cmd.executable not in self._command_locks:
            self._command_locks[cmd.executable] = asyncio.Lock()

        lock = self._command_locks[cmd.executable]

        async with lock:
            return await self.run(cmd)

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
        max_duration_sec = max_duration_ms / 1000.0
        # Use 90% of max duration for each attempt to leave room for retries.
        per_attempt_timeout = max_duration_sec * 0.9

        try:
            async for attempt in AsyncRetrying(
                wait=wait_exponential(multiplier=1, min=1, max=60),
                stop=stop_after_delay(max_duration_sec),
                reraise=True,
                retry=retry_if_exception_type((CommandError, asyncio.TimeoutError)),
            ):
                with attempt:
                    return await asyncio.wait_for(self.run(cmd), timeout=per_attempt_timeout)
        except RetryError as e:
            # Re-raise the original exception
            exc = e.last_attempt.exception()
            if exc is not None:
                raise exc from e
            raise
        except TimeoutError as e:
            # Convert timeout to CommandError for consistency.
            raise CommandError(cmd.command_string, -1, "Command timed out") from e

        # This should never be reached due to reraise=True
        raise RuntimeError("Unexpected retry error")

    async def write_home_file(self, filepath: Path, contents: bytes) -> None:
        """Write a file to the user's home directory.

        Args:
            filepath: Relative path within home directory
            contents: File contents to write

        Raises:
            ValueError: If filepath is absolute
            OSError: If file cannot be written
        """
        if filepath.is_absolute():
            raise ValueError("Only relative paths are supported")

        # Ensure parent directory exists
        await self.mk_home_subdir(filepath.parent)

        # Write file
        full_path = self.home_dir() / filepath
        full_path.write_bytes(contents)

        # Change ownership if running as sudo
        await self._chown_recursive(full_path)

        logger.debug("Wrote file", path=str(full_path))

    async def mk_home_subdir(self, subdirectory: Path) -> None:
        """Create a directory in the user's home directory.

        Args:
            subdirectory: Relative path within home directory

        Raises:
            ValueError: If path is absolute
            OSError: If directory cannot be created
        """
        if subdirectory.is_absolute():
            raise ValueError("Only relative paths are supported")

        full_path = self.home_dir() / subdirectory
        full_path.mkdir(parents=True, exist_ok=True)

        # Change ownership of the top-level directory
        if subdirectory.parts:
            top_level = self.home_dir() / subdirectory.parts[0]
            await self._chown_recursive(top_level)

        logger.debug("Created directory", path=str(full_path))

    async def remove_all_home(self, filepath: Path) -> None:
        """Recursively remove a file or directory from the user's home.

        Args:
            filepath: Relative path within home directory

        Raises:
            OSError: If removal fails
        """
        full_path = self.home_dir() / filepath
        if full_path.exists():
            if full_path.is_dir():
                shutil.rmtree(full_path)
            else:
                full_path.unlink()
            logger.debug("Removed path", path=str(full_path))

    async def read_home_file(self, filepath: Path) -> bytes:
        """Read a file from the user's home directory.

        Args:
            filepath: Relative path within home directory

        Returns:
            File contents as bytes

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        full_path = self.home_dir() / filepath
        return await self.read_file(full_path)

    async def read_file(self, filepath: Path) -> bytes:
        """Read a file from anywhere on the filesystem.

        Args:
            filepath: Absolute path to file

        Returns:
            File contents as bytes

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        if not filepath.exists():
            raise FileNotFoundError(f"File '{filepath}' does not exist")

        return filepath.read_bytes()

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
        return await self._snapd_client.snap_info(snap, channel)

    async def snap_channels(self, snap: str) -> list[str]:
        """Get list of available channels for a snap.

        Args:
            snap: Name of the snap

        Returns:
            List of channel names, sorted

        Raises:
            Exception: If snapd API fails
        """
        return await self._snapd_client.snap_channels(snap)

    async def _chown_recursive(self, path: Path) -> None:
        """Change ownership of a path recursively to the real user.

        Args:
            path: Path to change ownership of
        """
        # Only change ownership if running as sudo
        sudo_user = os.getenv("SUDO_USER")
        if not sudo_user:
            return

        # Get UID/GID for the real user
        try:
            user_info = pwd.getpwnam(sudo_user)
            uid = user_info.pw_uid
            gid = user_info.pw_gid
        except KeyError:
            logger.warning("Could not find user info", user=sudo_user)
            return

        # Recursively change ownership
        for item in path.rglob("*"):
            try:
                os.chown(item, uid, gid)
            except OSError as e:
                logger.warning("Failed to change ownership", path=str(item), error=str(e))

        # Also change the root path itself
        try:
            os.chown(path, uid, gid)
        except OSError as e:
            logger.warning("Failed to change ownership", path=str(path), error=str(e))

        logger.debug("Changed ownership", path=str(path), user=sudo_user)

    def _print_trace(self, command: str, output: str) -> None:
        """Print trace output for a command.

        Args:
            command: The command that was executed
            output: The command output
        """
        print(f"\n\033[1;32;4mCommand:\033[0m \033[1m{command}\033[0m")
        if output:
            print(f"\033[1;32mOutput:\033[0m\n{output}")
