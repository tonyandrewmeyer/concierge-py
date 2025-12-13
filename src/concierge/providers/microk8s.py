"""MicroK8s provider implementation."""

from pathlib import Path
from typing import Any

from concierge.config.models import ConciergeConfig
from concierge.core.logging import get_logger
from concierge.packages.snap_handler import SnapHandler
from concierge.system.command import Command
from concierge.system.models import Snap
from concierge.system.worker import Worker

logger = get_logger(__name__)

DEFAULT_MICROK8S_CHANNEL = "1.32-strict/stable"


async def compute_default_channel(system: Worker) -> str:
    """Compute the default MicroK8s channel.

    Prefers strict variants, sorted descending by version.

    Args:
        system: System worker

    Returns:
        Channel name
    """
    try:
        channels = await system.snap_channels("microk8s")
        for channel in channels:
            if "strict" in channel and "stable" in channel:
                return channel
    except Exception as e:
        logger.warning("Failed to get MicroK8s channels", error=str(e))

    return DEFAULT_MICROK8S_CHANNEL


class MicroK8s:
    """MicroK8s provider for Juju.

    This provider installs and configures MicroK8s for use in testing
    environments, including addon management and kubectl setup.
    """

    def __init__(self, system: Worker, config: ConciergeConfig) -> None:
        """Initialize the MicroK8s provider.

        Args:
            system: System worker for executing commands
            config: Concierge configuration
        """
        self.system = system
        self._bootstrap = config.providers.microk8s.bootstrap
        self._model_defaults = config.providers.microk8s.model_defaults
        self._bootstrap_constraints = config.providers.microk8s.bootstrap_constraints
        self.addons = config.providers.microk8s.addons

        # Determine channel with precedence: override > config > computed default
        if config.overrides.microk8s_channel:
            self.channel = config.overrides.microk8s_channel
        elif config.providers.microk8s.channel:
            self.channel = config.providers.microk8s.channel
        else:
            # Will be computed asynchronously in prepare
            self.channel = ""

        self.snaps = [
            Snap(name="microk8s", channel=self.channel),
            Snap(name="kubectl", channel="stable"),
        ]

    async def prepare(self) -> None:
        """Prepare the MicroK8s provider.

        Raises:
            Exception: If preparation fails
        """
        # Compute default channel if not specified
        if not self.channel:
            self.channel = await compute_default_channel(self.system)
            self.snaps[0].channel = self.channel

        await self._install()
        await self._init()
        await self._enable_addons()
        await self._enable_non_root_user_control()
        await self._setup_kubectl()

        logger.info("Prepared provider", provider=self.name())

    async def restore(self) -> None:
        """Restore the MicroK8s provider by removing snaps.

        Raises:
            Exception: If restoration fails
        """
        snap_handler = SnapHandler(self.system, self.snaps)
        await snap_handler.restore()

        # Remove kubeconfig
        await self.system.remove_all_home(Path(".kube"))

        logger.info("Removed provider", provider=self.name())

    def name(self) -> str:
        """Get the provider name."""
        return "microk8s"

    def bootstrap(self) -> bool:
        """Check if bootstrap is enabled."""
        return self._bootstrap

    def cloud_name(self) -> str:
        """Get the Juju cloud name."""
        return "microk8s"

    def group_name(self) -> str:
        """Get the POSIX group name."""
        if "strict" in self.channel:
            return "snap_microk8s"
        return "microk8s"

    def credentials(self) -> dict[str, Any]:
        """Get Juju credentials (MicroK8s doesn't need credentials)."""
        return {}

    def model_defaults(self) -> dict[str, str]:
        """Get Juju model defaults."""
        return self._model_defaults

    def bootstrap_constraints(self) -> dict[str, str]:
        """Get Juju bootstrap constraints."""
        return self._bootstrap_constraints

    async def _install(self) -> None:
        """Install MicroK8s and kubectl snaps.

        Raises:
            Exception: If installation fails
        """
        snap_handler = SnapHandler(self.system, self.snaps)
        await snap_handler.prepare()

    async def _init(self) -> None:
        """Initialize MicroK8s and wait for ready state.

        Raises:
            Exception: If initialization fails
        """
        cmd = Command(executable="microk8s", args=["status", "--wait-ready", "--timeout", "270"])
        await self.system.run_with_retries(cmd, 5 * 60 * 1000)  # 5 minutes in ms

    async def _enable_addons(self) -> None:
        """Enable configured MicroK8s addons.

        Raises:
            Exception: If addon enabling fails
        """
        for addon in self.addons:
            enable_arg = addon

            # Special handling for metallb addon
            if addon == "metallb":
                enable_arg = "metallb:10.64.140.43-10.64.140.49"

            cmd = Command(executable="microk8s", args=["enable", enable_arg])
            await self.system.run_with_retries(cmd, 5 * 60 * 1000)  # 5 minutes in ms

    async def _enable_non_root_user_control(self) -> None:
        """Enable non-root user to control MicroK8s.

        Raises:
            Exception: If configuration fails
        """
        username = self.system.username()

        cmd = Command(executable="usermod", args=["-a", "-G", self.group_name(), username])
        await self.system.run(cmd)

    async def _setup_kubectl(self) -> None:
        """Setup kubectl configuration for MicroK8s.

        Raises:
            Exception: If kubectl setup fails
        """
        # Get MicroK8s config
        cmd = Command(executable="microk8s", args=["config"])
        result = await self.system.run(cmd)

        # Write to .kube/config
        await self.system.write_home_file(Path(".kube/config"), result)
