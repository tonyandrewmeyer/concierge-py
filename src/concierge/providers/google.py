"""Google Cloud provider implementation."""

from pathlib import Path
from typing import Any

import yaml

from concierge.config.models import ConciergeConfig
from concierge.core.logging import get_logger
from concierge.system.worker import Worker

logger = get_logger(__name__)


class Google:
    """Google Cloud provider for Juju.

    This provider reads Google Cloud credentials from a file and
    provides them to Juju for bootstrap.
    """

    def __init__(self, system: Worker, config: ConciergeConfig) -> None:
        """Initialize the Google provider.

        Args:
            system: System worker for executing commands
            config: Concierge configuration
        """
        self.system = system
        self._bootstrap = config.providers.google.bootstrap
        self._model_defaults = config.providers.google.model_defaults
        self._bootstrap_constraints = config.providers.google.bootstrap_constraints

        # Apply credential file override if present
        credentials_file = config.providers.google.credentials_file
        if config.overrides.google_credential_file:
            credentials_file = config.overrides.google_credential_file

        self.credentials_file = credentials_file
        self._credentials: dict[str, Any] = {}

    async def prepare(self) -> None:
        """Prepare the Google provider by loading credentials.

        Raises:
            FileNotFoundError: If credentials file doesn't exist
            ValueError: If credentials file is invalid
        """
        if not self.credentials_file:
            return

        # Read credentials file
        contents = await self.system.read_file(Path(self.credentials_file))

        # Parse YAML credentials
        try:
            credentials = yaml.safe_load(contents)
            if not isinstance(credentials, dict):
                raise ValueError("Credentials file must contain a YAML mapping")

            self._credentials = credentials

        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse Google Cloud credentials: {e}") from e

        logger.info("Prepared provider", provider=self.name())

    async def restore(self) -> None:
        """Restore the Google provider (no-op).

        The Google provider doesn't install anything locally, so restoration
        is a no-op.
        """
        logger.info("Restored provider", provider=self.name())

    def name(self) -> str:
        """Get the provider name."""
        return "google"

    def bootstrap(self) -> bool:
        """Check if bootstrap is enabled."""
        return self._bootstrap

    def cloud_name(self) -> str:
        """Get the Juju cloud name."""
        return "google"

    def group_name(self) -> str:
        """Get the POSIX group name (none for Google)."""
        return ""

    def credentials(self) -> dict[str, Any]:
        """Get Juju credentials."""
        return self._credentials

    def model_defaults(self) -> dict[str, str]:
        """Get Juju model defaults."""
        return self._model_defaults

    def bootstrap_constraints(self) -> dict[str, str]:
        """Get Juju bootstrap constraints."""
        return self._bootstrap_constraints
