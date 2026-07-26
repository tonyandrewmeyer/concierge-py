"""System command runner implementation."""

import asyncio
import os
import pwd
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

from concierge import securitylog
from concierge.core.logging import get_logger
from concierge.system.command import Command, CommandError
from concierge.system.snap import SnapdClient

if TYPE_CHECKING:
    from concierge.system.models import SnapInfo

logger = get_logger(__name__)


def _log_privileged_command(cmd: Command, command_string: str, elapsed: float, err: str) -> None:
    """Emit an OWASP authz_admin security event for a privileged command execution.

    Concierge runs as root, so every command it executes is administrative
    activity. Read-only state checks are skipped to keep the audit trail
    focused on state-changing actions and to avoid noise from retried lookups.
    """
    if cmd.read_only:
        return

    run_as = cmd.user or "root"
    outcome = "failure" if err else "success"
    description = "privileged command failed" if err else "privileged command executed"
    securitylog.emit(
        securitylog.EVENT_AUTHZ_ADMIN,
        f"{securitylog.user_id()},exec",
        description,
        command=command_string,
        run_as=run_as,
        outcome=outcome,
        elapsed=f"{elapsed:.2f}s",
    )


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
        sudo_home = os.getenv("SUDO_HOME") or f"/home/{sudo_user}"
        return sudo_user, sudo_home

    # Not running under sudo, use current user
    username = os.getenv("USER", "root")
    home = os.getenv("HOME", f"/home/{username}")
    return username, home


class System:
    """System implementation that executes commands on the local machine.

    Implements the Worker protocol with primitive operations. Higher-level
    operations like run_exclusive and write_home_file are standalone helper
    functions in concierge.system.helpers.
    """

    def __init__(self, trace: bool = False) -> None:
        self._trace = trace
        self._shell = _get_shell_path()
        self._username, self._home_dir = _get_real_user()
        self._snapd_client = SnapdClient()

    def username(self) -> str:
        return self._username

    def home_dir(self) -> Path:
        return Path(self._home_dir)

    async def run(self, cmd: Command) -> bytes:
        """Execute a command and return its output."""
        command_string = cmd.command_string

        log_ctx = {}
        if cmd.user:
            log_ctx["user"] = cmd.user
        if cmd.group:
            log_ctx["group"] = cmd.group

        logger.debug("Starting command", command=command_string, **log_ctx)

        start_time = time.monotonic()
        process = await asyncio.create_subprocess_shell(
            command_string,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            executable=self._shell,
        )

        stdout, _ = await process.communicate()
        elapsed = time.monotonic() - start_time

        if process.returncode != 0:
            output_str = stdout.decode("utf-8", errors="replace")
            if self._trace:
                self._print_trace(command_string, output_str)
            # After communicate(), returncode should always be set
            returncode = process.returncode if process.returncode is not None else 1
            _log_privileged_command(cmd, command_string, elapsed, err=output_str or "failed")
            raise CommandError(command_string, returncode, output_str)

        if self._trace:
            output_str = stdout.decode("utf-8", errors="replace")
            self._print_trace(command_string, output_str)

        logger.debug("Finished command", command=command_string, elapsed=f"{elapsed:.2f}s")
        _log_privileged_command(cmd, command_string, elapsed, err="")

        return stdout

    async def read_file(self, filepath: Path) -> bytes:
        """Read a file from the filesystem."""
        if not filepath.exists():
            raise FileNotFoundError(f"File '{filepath}' does not exist")
        return filepath.read_bytes()

    async def write_file(self, filepath: Path, contents: bytes) -> None:
        """Write contents to a file."""
        filepath.write_bytes(contents)
        logger.debug("Wrote file", path=str(filepath))

    async def mkdir_all(self, dirpath: Path) -> None:
        """Create a directory and all parent directories."""
        dirpath.mkdir(parents=True, exist_ok=True)
        logger.debug("Created directory", path=str(dirpath))

    async def remove_path(self, filepath: Path) -> None:
        """Recursively remove a file or directory."""
        if filepath.exists():
            if filepath.is_dir():
                shutil.rmtree(filepath)
            else:
                filepath.unlink()
            logger.debug("Removed path", path=str(filepath))

    async def chown_all(self, path: Path) -> None:
        """Recursively change ownership of a path to the real user.

        Uses lchown to avoid dereferencing symlinks, which prevents failures
        with dangling symlinks and avoids changing ownership of symlink targets
        that may be outside the intended directory tree.
        """
        sudo_user = os.getenv("SUDO_USER")
        if not sudo_user:
            return

        try:
            user_info = pwd.getpwnam(sudo_user)
            uid = user_info.pw_uid
            gid = user_info.pw_gid
        except KeyError:
            logger.warning("Could not find user info", user=sudo_user)
            return

        for item in path.rglob("*"):
            try:
                os.lchown(item, uid, gid)
            except OSError as e:
                logger.warning("Failed to change ownership", path=str(item), error=str(e))

        try:
            os.lchown(path, uid, gid)
        except OSError as e:
            logger.warning("Failed to change ownership", path=str(path), error=str(e))

        logger.debug("Changed ownership", path=str(path), user=sudo_user)

        # The OWASP schema for this event is "userid,file,fromlevel,tolevel".
        # Concierge is changing ownership rather than mode bits, so the "level"
        # here is the owning user; the previous owner is not tracked, so the
        # fromlevel slot is left empty.
        securitylog.emit(
            securitylog.EVENT_PRIVILEGE_PERMISSIONS_CHANGED,
            f"{securitylog.user_id()},{path},,{sudo_user}",
            "filesystem ownership changed",
            path=str(path),
            user=sudo_user,
            uid=uid,
            gid=gid,
        )

    async def snap_info(self, snap: str, channel: str = "") -> SnapInfo:
        return await self._snapd_client.snap_info(snap, channel)

    async def snap_channels(self, snap: str) -> list[str]:
        return await self._snapd_client.snap_channels(snap)

    def _print_trace(self, command: str, output: str) -> None:
        print(f"\n\033[1;32;4mCommand:\033[0m \033[1m{command}\033[0m")
        if output:
            print(f"\033[1;32mOutput:\033[0m\n{output}")
