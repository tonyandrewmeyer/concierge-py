"""Juju handler for installation and bootstrap."""

import asyncio
import shlex
from pathlib import Path

import yaml
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from concierge.config.models import ConciergeConfig
from concierge.core.logging import get_logger
from concierge.juju.credentials import build_credentials_yaml
from concierge.packages.snap_handler import SnapHandler
from concierge.providers.base import Provider
from concierge.system.command import Command, CommandError
from concierge.system.models import Snap
from concierge.system.worker import Worker

logger = get_logger(__name__)


def _merge_dicts[T](base: dict[str, T], override: dict[str, T]) -> dict[str, T]:
    """Merge two dictionaries, with override taking precedence.

    Args:
        base: Base dictionary
        override: Override dictionary

    Returns:
        Merged dictionary
    """
    result = base.copy()
    result.update(override)
    return result


class JujuHandler:
    """Handler for Juju installation and bootstrap.

    This handler manages the Juju lifecycle, including installation,
    credential management, and bootstrapping controllers across providers.
    """

    def __init__(
        self,
        system: Worker,
        config: ConciergeConfig,
        providers: list[Provider],
    ) -> None:
        """Initialize the Juju handler.

        Args:
            system: System worker for executing commands
            config: Concierge configuration
            providers: List of providers to bootstrap
        """
        self.system = system
        self.providers = providers

        # Apply channel override if present
        channel = config.juju.channel
        if config.overrides.juju_channel:
            channel = config.overrides.juju_channel

        self.channel = channel
        self.agent_version = config.juju.agent_version
        self.model_defaults = config.juju.model_defaults
        self.bootstrap_constraints = config.juju.bootstrap_constraints
        self.extra_bootstrap_args = config.juju.extra_bootstrap_args

        self.snaps = [Snap(name="juju", channel=channel)]

    async def prepare(self) -> None:
        """Prepare Juju by installing, configuring, and bootstrapping.

        Raises:
            Exception: If preparation fails
        """
        await self._install()

        # Create Juju data directory
        await self.system.mk_home_subdir(Path(".local/share/juju"))

        # Write credentials
        await self._write_credentials()

        # Bootstrap all providers
        await self._bootstrap()

    async def restore(self) -> None:
        """Restore Juju by killing controllers and removing data.

        Raises:
            Exception: If restoration fails
        """
        # Kill controllers for credentialed providers
        for provider in self.providers:
            if not provider.credentials():
                continue

            await self._kill_provider(provider)

        # Remove Juju data directory
        await self.system.remove_all_home(Path(".local/share/juju"))

        # Uninstall Juju snap
        snap_handler = SnapHandler(self.system, self.snaps)
        await snap_handler.restore()

        logger.info("Restored Juju")

    async def _install(self) -> None:
        """Install the Juju snap.

        Raises:
            Exception: If installation fails
        """
        snap_handler = SnapHandler(self.system, self.snaps)
        await snap_handler.prepare()

    async def _write_credentials(self) -> None:
        """Write Juju credentials file.

        Raises:
            Exception: If writing credentials fails
        """
        credentials_data = build_credentials_yaml(self.providers)

        # Don't write if no credentials
        if not credentials_data["credentials"]:
            return

        # Serialize to YAML
        content = yaml.safe_dump(credentials_data, default_flow_style=False)

        # Write to credentials.yaml
        await self.system.write_home_file(
            Path(".local/share/juju/credentials.yaml"), content.encode("utf-8")
        )

    async def _bootstrap(self) -> None:
        """Bootstrap Juju on all configured providers concurrently.

        Raises:
            Exception: If bootstrap fails
        """
        # Bootstrap all providers concurrently
        tasks = [self._bootstrap_provider(provider) for provider in self.providers]
        await asyncio.gather(*tasks)

    async def _bootstrap_provider(self, provider: Provider) -> None:
        """Bootstrap Juju on a specific provider.

        Args:
            provider: Provider to bootstrap

        Raises:
            Exception: If bootstrap fails
        """
        if not provider.bootstrap():
            return

        controller_name = f"concierge-{provider.name()}"

        # Check if already bootstrapped
        if await self._check_bootstrapped(controller_name):
            logger.info("Previous Juju controller found", provider=provider.name())
            return

        logger.info("Bootstrapping Juju", provider=provider.name())

        # Build bootstrap command arguments
        args = [
            "bootstrap",
            provider.cloud_name(),
            controller_name,
            "--verbose",
        ]

        # Add agent version if specified
        if self.agent_version:
            args.extend(["--agent-version", self.agent_version])

        # Merge global and provider-specific configs
        model_defaults = _merge_dicts(self.model_defaults, provider.model_defaults())
        bootstrap_constraints = _merge_dicts(
            self.bootstrap_constraints, provider.bootstrap_constraints()
        )

        # Add model-defaults
        for key in sorted(model_defaults.keys()):
            args.extend(["--model-default", f"{key}={model_defaults[key]}"])

        # Add bootstrap-constraints
        for key in sorted(bootstrap_constraints.keys()):
            args.extend(["--bootstrap-constraints", f"{key}={bootstrap_constraints[key]}"])

        # Add extra bootstrap args if present
        if self.extra_bootstrap_args:
            extra_args = shlex.split(self.extra_bootstrap_args)
            args.extend(extra_args)

        # Execute bootstrap
        username = self.system.username()
        group = provider.group_name()
        cmd = Command(executable="juju", args=args, user=username, group=group)

        await self.system.run_with_retries(cmd, 5 * 60 * 1000)  # 5 minutes in ms

        # Create testing model
        cmd = Command(
            executable="juju",
            args=["add-model", "-c", controller_name, "testing"],
            user=username,
        )
        await self.system.run(cmd)

        logger.info("Bootstrapped Juju", provider=provider.name())

    async def _check_bootstrapped(self, controller_name: str) -> bool:
        """Check if a Juju controller exists.

        Args:
            controller_name: Name of the controller

        Returns:
            True if controller exists

        Raises:
            Exception: If check fails unexpectedly
        """
        username = self.system.username()
        cmd = Command(
            executable="juju",
            args=["show-controller", controller_name],
            user=username,
        )

        # Retry the check with exponential backoff
        try:
            async for attempt in AsyncRetrying(
                wait=wait_exponential(multiplier=1, min=1, max=10),
                stop=stop_after_attempt(10),
                retry=retry_if_exception_type(CommandError),
                reraise=False,
            ):
                with attempt:
                    await self.system.run(cmd)
                    return True
        except RetryError:
            pass

        # If all retries failed, check if it's because controller doesn't exist
        try:
            await self.system.run(cmd)
            return True
        except CommandError as e:
            # Check if error is "controller not found"
            if f"controller {controller_name} not found" in e.output:
                return False
            # Other errors should be re-raised
            raise

        return False

    async def _kill_provider(self, provider: Provider) -> None:
        """Destroy the Juju controller for a provider.

        Args:
            provider: Provider whose controller to destroy

        Raises:
            Exception: If controller destruction fails
        """
        controller_name = f"concierge-{provider.name()}"

        # Check if controller exists
        if not await self._check_bootstrapped(controller_name):
            logger.info("No Juju controller found", provider=provider.name())
            return

        logger.info("Destroying Juju controller", provider=provider.name())

        # Kill controller
        username = self.system.username()
        cmd = Command(
            executable="juju",
            args=["kill-controller", "--verbose", "--no-prompt", controller_name],
            user=username,
        )

        await self.system.run(cmd)

        logger.info("Destroyed Juju controller", provider=provider.name())
