"""Restore command implementation."""

import structlog

from concierge.config.loader import load_config
from concierge.core.manager import Manager

logger = structlog.get_logger()


async def run_restore(config_file: str, preset: str) -> None:
    """Execute the restore command to revert the environment.

    Args:
        config_file: Path to configuration file
        preset: Preset name to use
    """
    logger.info("Starting environment restoration")

    # Load configuration (though Manager will reload from cache)
    config = load_config(config_file=config_file, preset=preset)

    # Create manager and execute restoration
    manager = Manager(config)
    await manager.restore()

    logger.info("Environment restoration completed successfully")
