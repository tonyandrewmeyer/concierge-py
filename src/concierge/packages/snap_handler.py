"""Snap package handler for installing and managing snaps."""

import asyncio
import logging
from typing import TYPE_CHECKING

from concierge.core.logging import get_logger
from concierge.system.command import Command
from concierge.system.dryrun import is_dry_run
from concierge.system.helpers import run_exclusive

if TYPE_CHECKING:
    from concierge.system.models import Snap, SnapInfo
    from concierge.system.worker import Worker

logger = get_logger(__name__)

# The snapd lookup made after an install or refresh is only used for logging, so
# it is bounded to stop a snapd hiccup stalling provisioning for a log line.
SNAP_LOG_LOOKUP_TIMEOUT = 5.0


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
            snap_info = await self.system.snap_info(snap.name, snap.channel)
            await self.prepare_snap(snap, snap_info)

    async def prepare_snap(self, snap: Snap, snap_info: SnapInfo) -> None:
        """Install (or refresh) and connect a single snap.

        This uses snap details that the caller has already looked up with
        `snap_info`, so callers that need the details before installing avoid
        a second snap store query.

        Args:
            snap: Snap to install
            snap_info: Details of the snap from `Worker.snap_info`

        Raises:
            Exception: If installation or connection fails
        """
        await self._install_snap(snap, snap_info)
        await self._connect_snap(snap)

    async def restore(self) -> None:
        """Remove all configured snaps.

        Raises:
            Exception: If snap removal fails
        """
        for snap in self.snaps:
            await self._remove_snap(snap)

    async def _install_snap(self, snap: Snap, snap_info: SnapInfo) -> None:
        """Install or refresh a snap.

        Args:
            snap: Snap to install
            snap_info: Details of the snap from `Worker.snap_info`

        Raises:
            Exception: If installation fails
        """
        logger.debug("Installing snap", snap=snap.name)

        if snap_info.installed:
            # A disabled snap must be enabled before it can be refreshed.
            if not snap_info.active:
                enable_cmd = Command(executable="snap", args=["enable", snap.name])
                await run_exclusive(self.system, enable_cmd)
                logger.info(
                    "Enabled disabled snap",
                    snap=snap.name,
                    version=snap_info.version,
                    revision=snap_info.revision,
                    tracking=snap_info.tracking_channel,
                )
            action = "refresh"
            log_action = "Refreshed"
        else:
            action = "install"
            log_action = "Installed"

        # Build command arguments
        args = [action, snap.name]

        if snap.channel:
            args.extend(["--channel", snap.channel])

        if snap.revision:
            args.extend(["--revision", snap.revision])

        if snap_info.classic:
            args.append("--classic")

        # Execute command
        cmd = Command(executable="snap", args=args)
        await run_exclusive(self.system, cmd)

        await self._log_snap_operation(log_action, snap, snap_info)

    async def _log_snap_operation(self, log_action: str, snap: Snap, before: SnapInfo) -> None:
        """Log that a snap was installed or refreshed.

        The log includes the new version, revision and tracking channel, and
        those that it was refreshed from.
        """
        # The lookup below is only needed for this log line, so skip it if it
        # would not be shown.
        if not logger.isEnabledFor(logging.INFO):
            return

        attrs: dict[str, str] = {}

        # In a dry run nothing was installed or refreshed, so looking the snap up
        # again would just report its unchanged state as the new one.
        if not is_dry_run(self.system):
            try:
                async with asyncio.timeout(SNAP_LOG_LOOKUP_TIMEOUT):
                    after = await self.system.snap_installed_info(snap.name)
            except Exception as e:
                logger.debug(
                    "Could not look up snap details after operation", snap=snap.name, error=str(e)
                )
            else:
                if after.installed:
                    attrs.update(
                        version=after.version,
                        revision=after.revision,
                        tracking=after.tracking_channel,
                    )

        # The "from" details are already known, so log them even if the lookup failed.
        if before.installed:
            attrs.update(
                {
                    "from.version": before.version,
                    "from.revision": before.revision,
                    "from.tracking": before.tracking_channel,
                }
            )

        logger.info(f"{log_action} snap", snap=snap.name, **attrs)

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
            await run_exclusive(self.system, cmd)

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

        await run_exclusive(self.system, cmd)

        logger.info("Removed snap", snap=snap.name)
