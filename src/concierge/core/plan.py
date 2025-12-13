"""Plan for executing Concierge operations."""

import asyncio

from concierge.config.models import ConciergeConfig
from concierge.core.executable import Executable
from concierge.core.logging import get_logger
from concierge.juju.handler import JujuHandler
from concierge.packages.deb_handler import DebHandler
from concierge.packages.snap_handler import SnapHandler
from concierge.providers.base import Provider
from concierge.providers.factory import SUPPORTED_PROVIDERS, create_provider
from concierge.system.models import Snap
from concierge.system.worker import Worker

logger = get_logger(__name__)


async def do_action(executable: Executable, action: str) -> None:
    """Execute prepare or restore on an Executable.

    Args:
        executable: Component to execute action on
        action: Action to execute ("prepare" or "restore")

    Raises:
        ValueError: If action is unknown
        Exception: If execution fails
    """
    if action == "prepare":
        await executable.prepare()
    elif action == "restore":
        await executable.restore()
    else:
        raise ValueError(f"Unknown action: {action}")


def _get_snap_channel_override(config: ConciergeConfig, snap_name: str) -> str:
    """Get channel override for a snap if present.

    Args:
        config: Concierge configuration
        snap_name: Name of the snap

    Returns:
        Override channel or empty string
    """
    overrides = {
        "charmcraft": config.overrides.charmcraft_channel,
        "snapcraft": config.overrides.snapcraft_channel,
        "rockcraft": config.overrides.rockcraft_channel,
    }
    return overrides.get(snap_name, "")


class Plan:
    """Plan represents the set of operations to execute.

    A Plan consists of snaps, debs, providers, and Juju configuration
    that need to be prepared or restored.
    """

    def __init__(self, config: ConciergeConfig, system: Worker) -> None:
        """Initialize the Plan.

        Args:
            config: Concierge configuration
            system: System worker
        """
        self.config = config
        self.system = system
        self.snaps: list[Snap] = []
        self.debs: list[str] = []
        self.providers: list[Provider] = []

        # Build list of snaps from config
        for snap_name, snap_config in config.host.snaps.items():
            channel = snap_config.channel
            # Check for channel override
            channel_override = _get_snap_channel_override(config, snap_name)
            if channel_override:
                channel = channel_override

            snap = Snap(
                name=snap_name,
                channel=channel,
                connections=snap_config.connections,
            )
            self.snaps.append(snap)

        # Add extra snaps from overrides
        for snap_str in config.overrides.extra_snaps:
            snap = Snap.from_string(snap_str)
            # Check for channel override
            channel_override = _get_snap_channel_override(config, snap.name)
            if channel_override:
                snap.channel = channel_override
            self.snaps.append(snap)

        # Build list of debs
        self.debs = config.host.packages + config.overrides.extra_debs

        # Build list of providers
        for provider_name in SUPPORTED_PROVIDERS:
            provider = create_provider(provider_name, system, config)
            if provider:
                self.providers.append(provider)

                # Warn if provider wants bootstrap but Juju is disabled
                if config.overrides.disable_juju and provider.bootstrap():
                    logger.warning(
                        "Provider will not be bootstrapped because Juju is disabled",
                        provider=provider_name,
                    )

        # Apply Juju disable override
        if config.overrides.disable_juju:
            self.config.juju.disable = True

    async def execute(self, action: str) -> None:
        """Execute the plan (prepare or restore).

        Args:
            action: Action to execute ("prepare" or "restore")

        Raises:
            Exception: If execution fails
        """
        # Validate plan (could add validators here)
        await self._validate()

        # Prepare/restore packages concurrently
        snap_handler = SnapHandler(self.system, self.snaps)
        deb_handler = DebHandler(self.system, self.debs)

        await asyncio.gather(
            do_action(snap_handler, action),
            do_action(deb_handler, action),
        )

        # Prepare/restore providers concurrently
        provider_tasks = [do_action(provider, action) for provider in self.providers]
        await asyncio.gather(*provider_tasks)

        # Skip Juju if disabled
        if self.config.juju.disable:
            return

        # Prepare/restore Juju
        juju_handler = JujuHandler(self.system, self.config, self.providers)
        await do_action(juju_handler, action)

    async def _validate(self) -> None:
        """Validate the plan.

        Raises:
            Exception: If validation fails
        """
        # Could add validation logic here
        # For now, this is a placeholder
