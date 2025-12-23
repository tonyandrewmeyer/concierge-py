"""Manager for orchestrating Concierge operations."""

from pathlib import Path

import yaml

from concierge.config.models import ConciergeConfig, Status
from concierge.core.logging import get_logger
from concierge.core.plan import Plan
from concierge.system.runner import System

logger = get_logger(__name__)


class Manager:
    """Manager coordinates the overall execution of Concierge.

    The Manager handles loading configuration, creating execution plans,
    and managing the prepare/restore lifecycle.
    """

    def __init__(self, config: ConciergeConfig, trace: bool = False) -> None:
        """Initialize the Manager.

        Args:
            config: Concierge configuration
            trace: Enable trace logging
        """
        self.config = config
        self.system = System(trace=trace)
        self.plan: Plan | None = None

    async def prepare(self) -> None:
        """Prepare the system according to configuration.

        Raises:
            Exception: If preparation fails
        """
        try:
            await self._execute("prepare")
            await self._record_runtime_config(Status.SUCCEEDED)
        except Exception:
            await self._record_runtime_config(Status.FAILED)
            raise

    async def restore(self) -> None:
        """Restore the system to its pre-Concierge state.

        Raises:
            Exception: If restoration fails
        """
        await self._load_runtime_config()
        await self._execute("restore")

    async def status(self) -> Status:
        """Get the current Concierge status.

        Returns:
            Current status

        Raises:
            FileNotFoundError: If no previous preparation found
        """
        record_path = Path(".cache/concierge/concierge.yaml")

        try:
            contents = await self.system.read_home_file(record_path)
            data = yaml.safe_load(contents)
            return Status(data.get("status", "provisioning"))
        except FileNotFoundError:
            raise FileNotFoundError(
                "Concierge has not prepared this machine and cannot report its status"
            ) from None

    async def _execute(self, action: str) -> None:
        """Execute a prepare or restore action.

        Args:
            action: Action to execute ("prepare" or "restore")

        Raises:
            ValueError: If action is unknown
            Exception: If execution fails
        """
        if action == "prepare":
            await self._record_runtime_config(Status.PROVISIONING)
        elif action == "restore":
            await self._load_runtime_config()
        else:
            raise ValueError(f"Unknown action: {action}")

        # Create and execute the plan
        self.plan = Plan(self.config, self.system)
        await self.plan.execute(action)

    async def _record_runtime_config(self, status: Status) -> None:
        """Record the runtime configuration to cache.

        Args:
            status: Current status to record

        Raises:
            Exception: If recording fails
        """
        self.config.status = status

        # Serialize config to YAML
        config_dict = self.config.model_dump(mode="json", by_alias=True)
        config_yaml = yaml.safe_dump(config_dict, default_flow_style=False)

        # Write to cache
        filepath = Path(".cache/concierge/concierge.yaml")
        await self.system.write_home_file(filepath, config_yaml.encode("utf-8"))

        logger.debug("Merged runtime configuration saved", path=str(filepath))

    async def _load_runtime_config(self) -> None:
        """Load the runtime configuration from cache.

        Raises:
            FileNotFoundError: If no cached config exists
            Exception: If loading fails
        """
        record_path = Path(".cache/concierge/concierge.yaml")

        contents = await self.system.read_home_file(record_path)
        data = yaml.safe_load(contents)

        self.config = ConciergeConfig.model_validate(data)

        logger.debug("Loaded previous runtime configuration", path=str(record_path))
