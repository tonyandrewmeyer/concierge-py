"""Kubernetes (k8s) provider implementation."""

import asyncio
import shutil
from pathlib import Path
from typing import Any

from concierge.config.models import ConciergeConfig
from concierge.core.logging import get_logger
from concierge.packages.deb_handler import DebHandler
from concierge.packages.snap_handler import SnapHandler
from concierge.system.command import Command, CommandError
from concierge.system.models import Snap
from concierge.system.worker import Worker

logger = get_logger(__name__)

DEFAULT_K8S_CHANNEL = "1.32-classic/stable"


class K8s:
    """Kubernetes provider for Juju.

    This provider installs and configures Canonical Kubernetes for use in
    testing environments, including feature configuration and kubectl setup.
    """

    def __init__(self, system: Worker, config: ConciergeConfig) -> None:
        """Initialize the K8s provider.

        Args:
            system: System worker for executing commands
            config: Concierge configuration
        """
        self.system = system
        self._bootstrap = config.providers.k8s.bootstrap
        self._model_defaults = config.providers.k8s.model_defaults
        self._bootstrap_constraints = config.providers.k8s.bootstrap_constraints
        self.features = config.providers.k8s.features

        # Determine channel with precedence: override > config > default
        if config.overrides.k8s_channel:
            self.channel = config.overrides.k8s_channel
        elif config.providers.k8s.channel:
            self.channel = config.providers.k8s.channel
        else:
            self.channel = DEFAULT_K8S_CHANNEL

        self.debs = ["iptables"]
        self.snaps = [
            Snap(name="k8s", channel=self.channel),
            Snap(name="kubectl", channel="stable"),
        ]

    async def prepare(self) -> None:
        """Prepare the K8s provider.

        Raises:
            Exception: If preparation fails
        """
        await self._install()
        await self._init()
        await self._configure_features()
        await self._setup_kubectl()

        logger.info("Prepared provider", provider=self.name())

    async def restore(self) -> None:
        """Restore the K8s provider by removing snaps.

        Raises:
            Exception: If restoration fails
        """
        snap_handler = SnapHandler(self.system, self.snaps)
        await snap_handler.restore()

        # Remove kubeconfig
        await self.system.remove_all_home(Path(".kube"))

        # Restore containerd if we stopped it during prepare
        await self._restore_containerd()

        logger.info("Removed provider", provider=self.name())

    def name(self) -> str:
        """Get the provider name."""
        return "k8s"

    def bootstrap(self) -> bool:
        """Check if bootstrap is enabled."""
        return self._bootstrap

    def cloud_name(self) -> str:
        """Get the Juju cloud name."""
        return "k8s"

    def group_name(self) -> str:
        """Get the POSIX group name (none for k8s)."""
        return ""

    def credentials(self) -> dict[str, Any]:
        """Get Juju credentials (K8s doesn't need credentials)."""
        return {}

    def model_defaults(self) -> dict[str, str]:
        """Get Juju model defaults."""
        return self._model_defaults

    def bootstrap_constraints(self) -> dict[str, str]:
        """Get Juju bootstrap constraints."""
        return self._bootstrap_constraints

    async def _install(self) -> None:
        """Install K8s snap and dependencies.

        Installs iptables if needed and k8s/kubectl snaps concurrently.

        Raises:
            Exception: If installation fails
        """

        async def install_iptables() -> None:
            """Install iptables if not present."""
            try:
                cmd = Command(executable="which", args=["iptables"])
                await self.system.run(cmd)
            except CommandError:
                # iptables not found, install it
                deb_handler = DebHandler(self.system, self.debs)
                await deb_handler.prepare()

        async def install_snaps() -> None:
            """Install k8s and kubectl snaps."""
            snap_handler = SnapHandler(self.system, self.snaps)
            await snap_handler.prepare()

        # Run installations concurrently
        await asyncio.gather(install_iptables(), install_snaps())

    async def _init(self) -> None:
        """Initialize K8s cluster.

        Bootstraps the cluster if needed and waits for ready state.

        Raises:
            Exception: If initialization fails
        """
        # Handle pre-existing containerd that would conflict with k8s snap
        await self._handle_existing_containerd()

        # Bootstrap if cluster not already created
        if await self._needs_bootstrap():
            cmd = Command(executable="k8s", args=["bootstrap"])
            await self.system.run_with_retries(cmd, 5 * 60 * 1000)  # 5 minutes in ms

        # Wait for cluster to be ready
        cmd = Command(executable="k8s", args=["status", "--wait-ready", "--timeout", "270s"])
        await self.system.run_with_retries(cmd, 5 * 60 * 1000)  # 5 minutes in ms

    async def _needs_bootstrap(self) -> bool:
        """Check if the cluster needs to be bootstrapped.

        Returns:
            True if cluster is not initialized

        Raises:
            Exception: If status check fails unexpectedly
        """
        try:
            cmd = Command(executable="k8s", args=["status"])
            await self.system.run(cmd)
            return False
        except CommandError as e:
            if "The node is not part of a Kubernetes cluster" in e.output:
                return True
            # Other errors should be re-raised
            raise

    async def _configure_features(self) -> None:
        """Configure and enable K8s features.

        Raises:
            Exception: If feature configuration fails
        """
        for feature_name, conf in self.features.items():
            # Set feature configuration
            for key, value in conf.items():
                feature_config = f"{feature_name}.{key}={value}"
                cmd = Command(executable="k8s", args=["set", feature_config])
                await self.system.run(cmd)

            # Enable the feature
            cmd = Command(executable="k8s", args=["enable", feature_name])
            await self.system.run_with_retries(cmd, 5 * 60 * 1000)  # 5 minutes in ms

    async def _setup_kubectl(self) -> None:
        """Setup kubectl configuration for K8s.

        Raises:
            Exception: If kubectl setup fails
        """
        # Get K8s kubeconfig
        cmd = Command(executable="k8s", args=["kubectl", "config", "view", "--raw"])
        result = await self.system.run(cmd)

        # Write to .kube/config
        await self.system.write_home_file(Path(".kube/config"), result)

    async def _handle_existing_containerd(self) -> None:
        """Handle pre-existing containerd installations.

        Canonical K8s recommends installing on a clean machine. However, some
        environments (e.g., GitHub runners) have an existing containerd service.
        This stops the service and removes /run/containerd to allow k8s to
        bootstrap successfully.
        """
        # Check if containerd service is active
        try:
            cmd = Command(executable="systemctl", args=["is-active", "containerd.service"])
            output = await self.system.run(cmd)
            is_active = output.decode().strip() == "active"
        except CommandError:
            # Service doesn't exist or other error - nothing to do
            logger.debug("Containerd service is not active or does not exist")
            return

        if is_active:
            logger.debug("Containerd service is active, stopping it")
            try:
                cmd = Command(executable="systemctl", args=["stop", "containerd.service"])
                await self.system.run(cmd)
                logger.debug("Successfully stopped containerd service")
            except CommandError as e:
                logger.warning("Failed to stop containerd service", error=str(e))

        # Remove /run/containerd directory
        containerd_path = Path("/run/containerd")
        if containerd_path.exists():
            logger.debug("Removing /run/containerd directory")
            try:
                shutil.rmtree(containerd_path)
                logger.debug("Successfully removed /run/containerd directory")
            except OSError as e:
                logger.warning("Failed to remove /run/containerd directory", error=str(e))

    async def _restore_containerd(self) -> None:
        """Restore containerd service if it was stopped during prepare."""
        # Check if containerd service exists
        try:
            cmd = Command(executable="systemctl", args=["cat", "containerd.service"])
            await self.system.run(cmd)
        except CommandError:
            # Service doesn't exist - nothing to restore
            return

        # Restart the service
        logger.debug("Restarting containerd service")
        try:
            cmd = Command(executable="systemctl", args=["start", "containerd.service"])
            await self.system.run(cmd)
            logger.debug("Successfully restarted containerd service")
        except CommandError as e:
            logger.warning("Failed to restart containerd service", error=str(e))
