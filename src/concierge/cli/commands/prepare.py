"""Prepare command implementation."""

from typing import TYPE_CHECKING

from concierge.config.loader import load_config
from concierge.core.logging import get_logger
from concierge.core.manager import Manager

if TYPE_CHECKING:
    from concierge.config.models import ConfigOverrides

logger = get_logger(__name__)


async def run_prepare(
    config_file: str,
    preset: str,
    overrides: ConfigOverrides,
    *,
    dry_run: bool = False,
) -> None:
    """Execute the prepare command to provision the environment.

    Args:
        config_file: Path to configuration file
        preset: Preset name to use
        overrides: Configuration overrides from CLI/env
        dry_run: Log the planned actions without applying them
    """
    logger.info("Starting environment preparation")

    # Load configuration
    config = load_config(config_file=config_file, preset=preset, overrides=overrides)

    logger.info(
        "Configuration loaded",
        juju_enabled=not config.juju.disable,
        providers={
            "lxd": config.providers.lxd.enable,
            "microk8s": config.providers.microk8s.enable,
            "k8s": config.providers.k8s.enable,
            "google": config.providers.google.enable,
        },
    )

    # Create manager and execute preparation
    manager = Manager(config, trace=config.trace, dry_run=dry_run)
    await manager.prepare()

    logger.info("Environment preparation completed successfully")
