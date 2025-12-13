"""Logging configuration for Concierge using structlog."""

import logging
import sys

import structlog


def setup_logging(verbose: bool = False, trace: bool = False) -> None:
    """Configure structured logging for the application.

    Args:
        verbose: Enable verbose (DEBUG) logging
        trace: Enable trace logging (more detailed than DEBUG)
    """
    # Determine log level
    if trace:
        log_level = logging.DEBUG
    elif verbose:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING

    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "") -> structlog.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Optional logger name for context

    Returns:
        Configured structlog logger
    """
    if name:
        return structlog.get_logger().bind(logger=name)
    return structlog.get_logger()
