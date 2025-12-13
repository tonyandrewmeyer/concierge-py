"""Status command implementation."""

import asyncio

import structlog

from concierge.config.models import ConciergeConfig
from concierge.core.manager import Manager

logger = structlog.get_logger()


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
        logger.error("No previous Concierge preparation found")
