"""Debian package handler for installing and managing apt packages."""

from concierge.core.logging import get_logger
from concierge.system.command import Command
from concierge.system.helpers import run_exclusive
from concierge.system.worker import Worker

logger = get_logger(__name__)

# Environment variables that prevent apt/dpkg (and tools hooked into them,
# such as needrestart) from blocking on interactive prompts during unattended
# package operations. Without these, `apt-get install` can hang forever on a
# needrestart "which services should be restarted?" dialog, a debconf question,
# or a dpkg conffile conflict prompt.
_APT_ENV = [
    "DEBIAN_FRONTEND=noninteractive",
    "NEEDRESTART_MODE=a",
]


def _apt_command(*args: str) -> Command:
    """Build an apt-get command that runs non-interactively."""
    return Command(executable="apt-get", args=["-y", *args], env=list(_APT_ENV))


class DebHandler:
    """Handler for managing Debian packages via apt.

    This handler can install and remove packages from the Ubuntu/Debian
    package archives using apt-get.
    """

    def __init__(self, system: Worker, packages: list[str]) -> None:
        """Initialize the DebHandler.

        Args:
            system: System worker for executing commands
            packages: List of package names to manage
        """
        self.packages = packages
        self.system = system

    async def prepare(self) -> None:
        """Install all configured packages.

        Raises:
            Exception: If package installation fails
        """
        if not self.packages:
            return

        # Update package cache first
        await self._update_apt_cache()

        # Install each package
        for package in self.packages:
            await self._install_package(package)

    async def restore(self) -> None:
        """Remove all configured packages.

        Raises:
            Exception: If package removal fails
        """
        # Remove each package
        for package in self.packages:
            await self._remove_package(package)

        # Clean up unused dependencies
        cmd = _apt_command("autoremove")
        await run_exclusive(self.system, cmd)

    async def _update_apt_cache(self) -> None:
        """Update the apt package cache.

        Raises:
            Exception: If apt update fails
        """
        cmd = _apt_command("update")
        await run_exclusive(self.system, cmd)

    async def _install_package(self, package: str) -> None:
        """Install a single package.

        Args:
            package: Package name to install

        Raises:
            Exception: If installation fails
        """
        # Force dpkg to keep the existing conffile on conflict (--force-confold)
        # unless there's a newer default (--force-confdef), so conffile conflicts
        # never prompt.
        cmd = _apt_command(
            "install",
            "-o",
            "Dpkg::Options::=--force-confdef",
            "-o",
            "Dpkg::Options::=--force-confold",
            package,
        )
        await run_exclusive(self.system, cmd)

        logger.info("Installed apt package", package=package)

    async def _remove_package(self, package: str) -> None:
        """Remove a single package.

        Args:
            package: Package name to remove

        Raises:
            Exception: If removal fails
        """
        cmd = _apt_command("remove", package)
        await run_exclusive(self.system, cmd)

        logger.info("Removed apt package", package=package)
