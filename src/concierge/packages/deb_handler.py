"""Debian package handler for installing and managing apt packages."""

from concierge.core.logging import get_logger
from concierge.system.command import Command
from concierge.system.worker import Worker

logger = get_logger(__name__)


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
        cmd = Command(executable="apt-get", args=["autoremove", "-y"])
        await self.system.run_exclusive(cmd)

    async def _update_apt_cache(self) -> None:
        """Update the apt package cache.

        Raises:
            Exception: If apt update fails
        """
        cmd = Command(executable="apt-get", args=["update"])
        await self.system.run_exclusive(cmd)

    async def _install_package(self, package: str) -> None:
        """Install a single package.

        Args:
            package: Package name to install

        Raises:
            Exception: If installation fails
        """
        cmd = Command(executable="apt-get", args=["install", "-y", package])
        await self.system.run_exclusive(cmd)

        logger.info("Installed apt package", package=package)

    async def _remove_package(self, package: str) -> None:
        """Remove a single package.

        Args:
            package: Package name to remove

        Raises:
            Exception: If removal fails
        """
        cmd = Command(executable="apt-get", args=["remove", "-y", package])
        await self.system.run_exclusive(cmd)

        logger.info("Removed apt package", package=package)
