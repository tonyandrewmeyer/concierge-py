"""Restore command implementation."""

from concierge.config.loader import load_config
from concierge.core.logging import get_logger
from concierge.core.manager import Manager

logger = get_logger(__name__)


async def run_restore(
    config_file: str,
    preset: str,
    *,
    verbose: bool = False,
    trace: bool = False,
    dry_run: bool = False,
) -> None:
    """Execute the restore command to revert the environment.

    Args:
        config_file: Path to configuration file
        preset: Preset name to use
        verbose: Enable debug logging
        trace: Print each command and its output
        dry_run: Log the planned actions without applying them
    """
    logger.info("Starting environment restoration")

    # Load configuration (though Manager will reload from cache)
    config = load_config(config_file=config_file, preset=preset)

    # The Manager reloads the cached configuration but carries these flags over
    # from the one it was built with, so they are set here.
    config.verbose = verbose
    config.trace = trace
    config.dry_run = dry_run

    # Create manager and execute restoration
    manager = Manager(config, trace=config.trace, dry_run=dry_run)
    await manager.restore()

    logger.info("Environment restoration completed successfully")
