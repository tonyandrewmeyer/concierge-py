"""LXD provider implementation."""

from typing import Any

from concierge.config.models import ConciergeConfig
from concierge.core.logging import get_logger
from concierge.packages.snap_handler import SnapHandler
from concierge.system.command import Command
from concierge.system.models import Snap
from concierge.system.worker import Worker

logger = get_logger(__name__)


class LXD:
    """LXD provider for Juju.

    This provider installs and configures LXD for use in testing environments,
    including firewall deconfliction and non-root user access.
    """

    def __init__(self, system: Worker, config: ConciergeConfig) -> None:
        """Initialize the LXD provider.

        Args:
            system: System worker for executing commands
            config: Concierge configuration
        """
        self.system = system
        self._bootstrap = config.providers.lxd.bootstrap
        self._model_defaults = config.providers.lxd.model_defaults
        self._bootstrap_constraints = config.providers.lxd.bootstrap_constraints

        # Apply channel override if present
        channel = config.providers.lxd.channel
        if config.overrides.lxd_channel:
            channel = config.overrides.lxd_channel

        self.channel = channel
        self.snaps = [Snap(name="lxd", channel=channel)]

    async def prepare(self) -> None:
        """Prepare the LXD provider.

        Raises:
            Exception: If preparation fails
        """
        await self._install()
        await self._init()
        await self._enable_non_root_user_control()
        await self._deconflict_firewall()

        logger.info("Prepared provider", provider=self.name())

    async def restore(self) -> None:
        """Restore the LXD provider by removing the snap.

        Raises:
            Exception: If restoration fails
        """
        snap_handler = SnapHandler(self.system, self.snaps)
        await snap_handler.restore()

        logger.info("Restored provider", provider=self.name())

    def name(self) -> str:
        """Get the provider name."""
        return "lxd"

    def bootstrap(self) -> bool:
        """Check if bootstrap is enabled."""
        return self._bootstrap

    def cloud_name(self) -> str:
        """Get the Juju cloud name."""
        return "localhost"

    def group_name(self) -> str:
        """Get the POSIX group name."""
        return "lxd"

    def credentials(self) -> dict[str, Any]:
        """Get Juju credentials (LXD doesn't need credentials)."""
        return {}

    def model_defaults(self) -> dict[str, str]:
        """Get Juju model defaults."""
        return self._model_defaults

    def bootstrap_constraints(self) -> dict[str, str]:
        """Get Juju bootstrap constraints."""
        return self._bootstrap_constraints

    async def _install(self) -> None:
        """Install the LXD snap.

        Raises:
            Exception: If installation fails
        """
        # Check if LXD needs to be stopped for refresh
        restart = await self._workaround_refresh()

        # Install/refresh LXD
        snap_handler = SnapHandler(self.system, self.snaps)
        await snap_handler.prepare()

        # Restart LXD if we stopped it
        if restart:
            cmd = Command(executable="snap", args=["start", self.name()])
            await self.system.run_exclusive(cmd)

    async def _init(self) -> None:
        """Initialize LXD with minimal configuration.

        Raises:
            Exception: If initialization fails
        """
        # Wait for LXD to be ready
        cmd1 = Command(executable="lxd", args=["waitready", "--timeout", "270"])
        await self.system.run(cmd1)

        # Initialize with minimal config
        cmd2 = Command(executable="lxd", args=["init", "--minimal"])
        await self.system.run(cmd2)

        # Disable IPv6 on lxdbr0
        cmd3 = Command(executable="lxc", args=["network", "set", "lxdbr0", "ipv6.address", "none"])
        await self.system.run(cmd3)

    async def _enable_non_root_user_control(self) -> None:
        """Enable non-root user to control LXD.

        Raises:
            Exception: If configuration fails
        """
        username = self.system.username()

        # Make socket writable by all
        cmd1 = Command(executable="chmod", args=["a+wr", "/var/snap/lxd/common/lxd/unix.socket"])
        await self.system.run(cmd1)

        # Add user to lxd group
        cmd2 = Command(executable="usermod", args=["-a", "-G", "lxd", username])
        await self.system.run(cmd2)

    async def _deconflict_firewall(self) -> None:
        """Deconflict LXD firewall rules with Docker.

        Raises:
            Exception: If firewall configuration fails
        """
        # Flush FORWARD chain
        cmd1 = Command(executable="iptables", args=["-F", "FORWARD"])
        await self.system.run(cmd1)

        # Set FORWARD policy to ACCEPT
        cmd2 = Command(executable="iptables", args=["-P", "FORWARD", "ACCEPT"])
        await self.system.run(cmd2)

    async def _workaround_refresh(self) -> bool:
        """Stop LXD before channel refresh if needed.

        This works around a snap refresh issue with missing socket files.

        Returns:
            True if LXD was stopped and needs to be restarted

        Raises:
            Exception: If snap operations fail
        """
        snap_info = await self.system.snap_info(self.name(), self.channel)

        # Only stop if installed AND channel is changing
        if snap_info.installed:
            # No stop needed if:
            # - No channel specified (refresh on current channel)
            # - Tracking channel matches target channel
            if not self.channel or snap_info.tracking_channel == self.channel:
                logger.debug(
                    "Skipping LXD stop - no channel change required",
                    tracking=snap_info.tracking_channel,
                    target=self.channel,
                )
                return False

            # Channel mismatch - stop LXD before refresh
            logger.debug(
                "LXD channel mismatch, stopping for refresh",
                tracking=snap_info.tracking_channel,
                target=self.channel,
            )
            cmd = Command(executable="snap", args=["stop", self.name()])
            await self.system.run_exclusive(cmd)
            return True

        return False
