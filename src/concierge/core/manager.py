"""Manager for orchestrating Concierge operations."""

from pathlib import Path

import yaml

from concierge import securitylog
from concierge.config.models import ConciergeConfig, Status
from concierge.core.logging import get_logger
from concierge.core.plan import Plan
from concierge.system.dryrun import DryRunWorker
from concierge.system.helpers import read_home_file, write_home_file
from concierge.system.runner import System
from concierge.system.worker import Worker

logger = get_logger(__name__)


class Manager:
    """Manager coordinates the overall execution of Concierge.

    The Manager handles loading configuration, creating execution plans,
    and managing the prepare/restore lifecycle.
    """

    def __init__(self, config: ConciergeConfig, trace: bool = False, dry_run: bool = False) -> None:
        """Initialize the Manager.

        Args:
            config: Concierge configuration
            trace: Enable trace logging
            dry_run: Print commands without executing them
        """
        self.config = config
        self._dry_run = dry_run
        real_system = System(trace=trace)
        self.system: Worker = DryRunWorker(real_system) if dry_run else real_system
        self.plan: Plan | None = None

    async def prepare(self) -> None:
        """Prepare the system according to configuration.

        Raises:
            Exception: If preparation fails
        """
        # Record the start of the machine provisioning lifecycle. Skipped in
        # dry-run mode, where no real changes are made.
        if not self._dry_run:
            securitylog.emit(
                securitylog.EVENT_SYS_STARTUP,
                securitylog.user_id(),
                "machine provisioning started",
                action="prepare",
                user=self.system.username(),
            )

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
        # Record the start of machine decommissioning. Skipped in dry-run
        # mode, where no real changes are made.
        if not self._dry_run:
            securitylog.emit(
                securitylog.EVENT_SYS_SHUTDOWN,
                securitylog.user_id(),
                "machine restoration started",
                action="restore",
                user=self.system.username(),
            )

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
            contents = await read_home_file(self.system, record_path)
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
        if self._dry_run:
            return

        self.config.status = status

        # Serialize config to YAML
        config_dict = self.config.model_dump(mode="json", by_alias=True)
        config_yaml = yaml.safe_dump(config_dict, default_flow_style=False)

        # Write to cache
        filepath = Path(".cache/concierge/concierge.yaml")
        await write_home_file(self.system, filepath, config_yaml.encode("utf-8"))

        logger.debug("Merged runtime configuration saved", path=str(filepath))

    async def _load_runtime_config(self) -> None:
        """Load the runtime configuration from cache.

        Raises:
            FileNotFoundError: If no cached config exists
            Exception: If loading fails
        """
        record_path = Path(".cache/concierge/concierge.yaml")

        contents = await read_home_file(self.system, record_path)
        data = yaml.safe_load(contents)

        # Preserve CLI flags from current config
        loaded_config = ConciergeConfig.model_validate(data)
        loaded_config.dry_run = self.config.dry_run
        loaded_config.trace = self.config.trace
        loaded_config.verbose = self.config.verbose
        self.config = loaded_config

        logger.debug("Loaded previous runtime configuration", path=str(record_path))
