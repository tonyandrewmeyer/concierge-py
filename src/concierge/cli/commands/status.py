"""Status command implementation."""

import asyncio

from concierge.config.models import ConciergeConfig
from concierge.core.logging import get_logger
from concierge.core.manager import Manager

logger = get_logger(__name__)


def run_status() -> None:
    """Show the status of the Concierge environment."""
    logger.info("Checking environment status")

    # Run async status check
    asyncio.run(_async_status())


async def _async_status() -> None:
    """Async implementation of status check."""
    # Create a minimal config for manager (will be loaded from cache)
    config = ConciergeConfig()
    manager = Manager(config)

    try:
        status = await manager.status()
        print(f"Concierge status: {status.value}")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        logger.exception("No previous Concierge preparation found")
