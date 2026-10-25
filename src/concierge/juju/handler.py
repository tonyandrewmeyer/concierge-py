"""Juju handler for installation and bootstrap."""

import asyncio
import json
import platform
import shlex
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from concierge import securitylog
from concierge.config.models import BootstrappedController
from concierge.core.logging import get_logger
from concierge.juju.credentials import build_credentials_yaml
from concierge.packages.snap_handler import SnapHandler
from concierge.providers.base import default_controller_name, is_local_cloud
from concierge.system.command import Command, CommandError
from concierge.system.helpers import mk_home_subdir, run_with_retries, write_home_file
from concierge.system.models import Snap
from concierge.system.retry import retry_with_backoff

if TYPE_CHECKING:
    from concierge.config.models import ConciergeConfig
    from concierge.providers.base import Provider
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


def _get_juju_arch() -> str:
    """Get the Juju/Debian architecture name for the current platform.

    Translates Python's platform.machine() values to Juju/Debian architecture names.

    Returns:
        Juju-compatible architecture string (e.g., 'amd64', 'arm64')
    """
    machine = platform.machine()
    arch_map = {
        "x86_64": "amd64",
        "aarch64": "arm64",
        "ppc64le": "ppc64el",  # Python uses ppc64le, Juju/Debian uses ppc64el
        "s390x": "s390x",
        "riscv64": "riscv64",
    }
    return arch_map.get(machine, machine)


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

        # Held so that controllers can be recorded as they are bootstrapped, and read back
        # during restore.
        self.config = config

        # Apply channel override if present
        channel = config.juju.channel
        if config.overrides.juju_channel:
            channel = config.overrides.juju_channel

        # Apply revision override if present
        revision = config.juju.revision
        if config.overrides.juju_revision:
            revision = config.overrides.juju_revision

        self.channel = channel
        self.revision = revision
        self.agent_version = config.juju.agent_version
        self.model_defaults = config.juju.model_defaults
        self.bootstrap_constraints = config.juju.bootstrap_constraints
        self.extra_bootstrap_args = config.juju.extra_bootstrap_args

        self.snaps = [Snap(name="juju", channel=channel, revision=revision)]

    async def prepare(self) -> None:
        """Prepare Juju by installing, configuring, and bootstrapping.

        Raises:
            Exception: If preparation fails
        """
        await self._install()

        # Create Juju data directory
        await mk_home_subdir(self.system, Path(".local/share/juju"))

        # Write credentials
        await self._write_credentials()

        # Bootstrap all providers
        await self._bootstrap()

    async def restore(self) -> None:
        """Restore Juju by killing controllers and removing data.

        Raises:
            Exception: If restoration fails
        """
        # Destroy the controllers that Concierge recorded bootstrapping. The record includes
        # controllers from earlier prepares under a different name, and never includes a
        # controller that Concierge found already running. Sorted so that the order is
        # predictable.
        controllers = self._controllers_to_destroy()
        for name in sorted(controllers):
            await self._destroy_controller(name, controllers[name])

        # Remove Juju data directory
        await self.system.remove_path(self.system.home_dir() / ".local/share/juju")

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
        credentials_path = Path(".local/share/juju/credentials.yaml")
        await write_home_file(self.system, credentials_path, content.encode("utf-8"))

        # Record that cloud credentials were written. The credential contents
        # are deliberately not included in the event.
        securitylog.emit(
            securitylog.EVENT_AUTHZ_ADMIN,
            f"{securitylog.user_id()},write_credentials",
            "wrote Juju cloud credentials file",
            path=str(self.system.home_dir() / credentials_path),
            clouds=len(credentials_data["credentials"]),
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

        controller_name = provider.controller_name()

        # Check if already bootstrapped
        if await self._check_bootstrapped(controller_name):
            # With a user-chosen name the existing controller could belong to a different
            # cloud (or to the user), in which case skipping the bootstrap would leave this
            # provider with no controller and no error. A dry run only prints commands, so
            # there is nothing real to inspect.
            if not self.config.dry_run:
                details = await self._controller_details(controller_name)
                if details.cloud != provider.cloud_name():
                    raise RuntimeError(
                        f"existing controller '{controller_name}' is on cloud "
                        f"'{details.cloud}', but provider '{provider.name()}' uses cloud "
                        f"'{provider.cloud_name()}'; set a different controller-name"
                    )

            logger.info(
                "Previous Juju controller found",
                provider=provider.name(),
                controller=controller_name,
            )
            return

        logger.info("Bootstrapping Juju", provider=provider.name(), controller=controller_name)

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

        # `juju bootstrap` can take 10+ minutes per attempt to fail on a slow
        # runner (controller pod takes time to expose its API), so a 5-minute
        # retry budget elapses inside the first attempt and we never retry.
        # Use a 30-minute budget so a transient failure gets a real second go.
        await run_with_retries(self.system, cmd, 30 * 60 * 1000)

        # Record the controller as soon as it exists, so that restore still destroys it if one
        # of the steps below fails.
        await self._record_bootstrapped_controller(controller_name, provider.cloud_name())

        # Create testing model
        cmd = Command(
            executable="juju",
            args=["add-model", "-c", controller_name, "testing"],
            user=username,
        )
        await self.system.run(cmd)

        # Set architecture constraint on the testing model
        model_name = f"{controller_name}:testing"
        arch = _get_juju_arch()
        cmd = Command(
            executable="juju",
            args=["set-model-constraints", "-m", model_name, f"arch={arch}"],
            user=username,
        )
        await self.system.run(cmd)

        logger.info("Bootstrapped Juju", provider=provider.name(), controller=controller_name)

    async def _record_bootstrapped_controller(self, controller_name: str, cloud: str) -> None:
        """Record that Concierge bootstrapped a controller, including its UUID.

        Args:
            controller_name: Name of the controller
            cloud: Cloud the controller was bootstrapped on
        """
        # Nothing was bootstrapped in a dry run, and the runtime config is not written.
        if self.config.dry_run:
            return

        record = BootstrappedController(cloud=cloud)
        try:
            record.uuid = (await self._controller_details(controller_name)).uuid
        except (CommandError, ValueError) as e:
            # Restore can still identify the controller by name and cloud.
            logger.warning(
                "Failed to read the UUID of the new controller",
                controller=controller_name,
                error=str(e),
            )

        self.config.bootstrapped_controllers[controller_name] = record

    def _controllers_to_destroy(self) -> dict[str, BootstrappedController]:
        """Get the recorded controllers, plus unrecorded default-named ones on remote clouds.

        Versions of Concierge before the record existed destroyed the default-named controller
        of each bootstrapped provider on restore. Including those that are missing from the
        record keeps a controller bootstrapped by one of them from being left running (and, on
        a paid cloud, costing money) after an upgrade between prepare and restore. They have no
        UUID, so only their cloud is checked.

        Returns:
            Controllers to destroy, keyed by name
        """
        controllers = dict(self.config.bootstrapped_controllers)

        for provider in self.providers:
            name = default_controller_name(provider.name())
            if (
                not provider.bootstrap()
                or provider.controller_name() != name
                or is_local_cloud(provider.cloud_name())
                or name in controllers
            ):
                continue

            logger.debug(
                "Including unrecorded controller with the default name",
                controller=name,
                cloud=provider.cloud_name(),
            )
            controllers[name] = BootstrappedController(cloud=provider.cloud_name())

        return controllers

    async def _controller_details(self, controller_name: str) -> BootstrappedController:
        """Read the cloud and UUID of an existing controller from `juju show-controller`.

        Args:
            controller_name: Name of the controller

        Returns:
            The controller's cloud and UUID

        Raises:
            ValueError: If the output cannot be parsed
            CommandError: If the command fails
        """
        cmd = Command(
            executable="juju",
            args=["show-controller", controller_name, "--format", "json"],
            user=self.system.username(),
            read_only=True,
        )
        output = await self.system.run(cmd)

        try:
            controller = json.loads(output)[controller_name]
            details = controller["details"]
            return BootstrappedController(cloud=details["cloud"], uuid=details["uuid"])
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise ValueError(
                f"failed to parse details of controller '{controller_name}': {e!r}"
            ) from e

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

        # Custom retry predicate that only retries transient errors
        # Don't retry if the controller definitively doesn't exist
        controller_not_found = f"controller {controller_name} not found"

        def should_retry(exception: Exception) -> bool:
            if isinstance(exception, CommandError):
                # Retry transient errors, but not if controller definitively not found
                return controller_not_found not in exception.output
            return False

        # Retry the check with exponential backoff
        try:
            await retry_with_backoff(
                lambda: self.system.run(cmd),
                max_attempts=10,
                min_wait=1,
                max_wait=10,
                is_retryable=should_retry,
            )
            return True
        except CommandError as e:
            # Check if error is "controller not found"
            if controller_not_found in e.output:
                return False
            # Other errors should be re-raised
            raise

    async def _destroy_controller(
        self, controller_name: str, record: BootstrappedController
    ) -> None:
        """Destroy a controller that Concierge recorded bootstrapping, if it is still that one.

        Args:
            controller_name: Name of the controller
            record: What Concierge recorded about the controller

        Raises:
            Exception: If controller destruction fails
        """
        # Controllers on local clouds run on this machine, and restoring their provider (which
        # happens before Juju is restored) has already removed them. Contacting one would only
        # wait for a connection that cannot succeed.
        if is_local_cloud(record.cloud):
            logger.debug(
                "Skipping controller on a local cloud",
                controller=controller_name,
                cloud=record.cloud,
            )
            return

        if not await self._check_bootstrapped(controller_name):
            logger.info("No Juju controller found", controller=controller_name, cloud=record.cloud)
            return

        # The name may have been reused, since Concierge recorded it, for a controller that
        # Concierge did not create.
        details = await self._controller_details(controller_name)
        if details.cloud != record.cloud or (record.uuid and details.uuid != record.uuid):
            logger.warning(
                "Controller is not the one Concierge bootstrapped, leaving in place",
                controller=controller_name,
                cloud=details.cloud,
                uuid=details.uuid,
            )
            return

        logger.info("Destroying Juju controller", controller=controller_name, cloud=record.cloud)

        cmd = Command(
            executable="juju",
            args=["kill-controller", "--verbose", "--no-prompt", controller_name],
            user=self.system.username(),
        )
        await self.system.run(cmd)

        logger.info("Destroyed Juju controller", controller=controller_name, cloud=record.cloud)
