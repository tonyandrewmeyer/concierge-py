"""Snap package handler for installing and managing snaps."""

from concierge.core.logging import get_logger
from concierge.system.command import Command
from concierge.system.models import Snap
from concierge.system.worker import Worker

logger = get_logger(__name__)


class SnapHandler:
    """Handler for managing snap packages.

    This handler can install, refresh, and remove snap packages,
    including handling classic confinement and snap connections.
    """

    def __init__(self, system: Worker, snaps: list[Snap]) -> None:
        """Initialize the SnapHandler.

        Args:
            system: System worker for executing commands
            snaps: List of snaps to manage
        """
        self.snaps = snaps
        self.system = system

    async def prepare(self) -> None:
        """Install all configured snaps.

        Raises:
            Exception: If snap installation fails
        """
        for snap in self.snaps:
            await self._install_snap(snap)
            await self._connect_snap(snap)

    async def restore(self) -> None:
        """Remove all configured snaps.

        Raises:
            Exception: If snap removal fails
        """
        for snap in self.snaps:
            await self._remove_snap(snap)

    async def _install_snap(self, snap: Snap) -> None:
        """Install or refresh a snap.

        Args:
            snap: Snap to install

        Raises:
            Exception: If installation fails
        """
        logger.debug("Installing snap", snap=snap.name)

        # Get snap information to determine if it's already installed
        snap_info = await self.system.snap_info(snap.name, snap.channel)

        # Determine action: install or refresh
        if snap_info.installed:
            action = "refresh"
            log_action = "Refreshed"
        else:
            action = "install"
            log_action = "Installed"

        # Build command arguments
        args = [action, snap.name]

        if snap.channel:
            args.extend(["--channel", snap.channel])

        if snap_info.classic:
            args.append("--classic")

        # Execute command
        cmd = Command(executable="snap", args=args)
        await self.system.run_exclusive(cmd)

        logger.info(f"{log_action} snap", snap=snap.name)

    async def _connect_snap(self, snap: Snap) -> None:
        """Connect snap interfaces.

        Args:
            snap: Snap with connections to establish

        Raises:
            Exception: If connection fails
        """
        for connection in snap.connections:
            # Parse connection string (format: "plug" or "plug slot")
            parts = connection.split()
            if len(parts) > 2:
                raise ValueError(f"Too many arguments in snap connection string '{connection}'")

            args = ["connect", *parts]

            cmd = Command(executable="snap", args=args)
            await self.system.run_exclusive(cmd)

    async def _remove_snap(self, snap: Snap) -> None:
        """Remove a snap from the system.

        Args:
            snap: Snap to remove

        Raises:
            Exception: If removal fails
        """
        logger.debug("Removing snap", snap=snap.name)

        args = ["remove", snap.name, "--purge"]
        cmd = Command(executable="snap", args=args)

        await self.system.run_exclusive(cmd)

        logger.info("Removed snap", snap=snap.name)
