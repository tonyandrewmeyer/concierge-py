"""Logging configuration for Concierge using stdlib logging with rich."""

import logging
from collections.abc import MutableMapping
from typing import Any

from rich.console import Console
from rich.logging import RichHandler


class StructuredLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that formats kwargs as structured context data.

    This adapter preserves the structlog-like API where context data
    can be passed as kwargs to logging methods, making the migration
    from structlog to stdlib logging seamless.

    Example:
        logger = get_logger(__name__)
        logger.info("Bootstrap complete", provider="lxd", duration=42.5)
        # Output: Bootstrap complete [provider=lxd duration=42.5]
    """

    def process(
        self, msg: Any, kwargs: MutableMapping[str, Any]
    ) -> tuple[Any, MutableMapping[str, Any]]:
        """Process log message and kwargs to extract context data.

        Args:
            msg: Log message
            kwargs: Keyword arguments including context data

        Returns:
            Tuple of (formatted_message, cleaned_kwargs)
        """
        # Standard library logging kwargs that should not be treated as context
        stdlib_kwargs = {"exc_info", "stack_info", "stacklevel", "extra"}

        # Extract context data (anything not a stdlib logging kwarg)
        context = {k: v for k, v in kwargs.items() if k not in stdlib_kwargs}
        clean_kwargs = {k: v for k, v in kwargs.items() if k in stdlib_kwargs}

        # Format context data as a visually distinct suffix
        if context:
            context_items = [f"{k}={v}" for k, v in sorted(context.items())]
            context_str = " ".join(context_items)
            msg = f"{msg} [dim][[/dim]{context_str}[dim]][/dim]"

        return msg, clean_kwargs


def setup_logging(verbose: bool = False, trace: bool = False) -> None:
    """Configure structured logging with rich integration.

    This function sets up the logging system with rich's RichHandler for
    colored output, timestamps, and enhanced exception formatting.

    Args:
        verbose: Enable debug logging
        trace: Enable trace logging (most verbose)
    """
    # Determine log level based on flags
    if trace:
        log_level = logging.DEBUG  # Use DEBUG for trace (most verbose)
    elif verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    # Configure rich console for stderr output
    console = Console(stderr=True, force_terminal=True)

    # Create rich handler with desired formatting
    handler = RichHandler(
        console=console,
        show_time=True,  # Show timestamps
        show_path=trace,  # Show module and line number in trace mode
        markup=True,  # Enable rich markup in messages
        rich_tracebacks=True,  # Enhanced exception rendering
        tracebacks_show_locals=verbose or trace,  # Show local vars in verbose/trace mode
        log_time_format="[%Y-%m-%d %H:%M:%S]",
    )

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        handlers=[handler],
        force=True,
    )


def get_logger(name: str = "") -> StructuredLoggerAdapter:
    """Get a structured logger instance.

    This function returns a logger adapter that supports passing context
    data as keyword arguments, maintaining API compatibility with structlog.

    Args:
        name: Logger name (typically __name__ of the module)

    Returns:
        Configured logger adapter with structured logging support

    Example:
        logger = get_logger(__name__)
        logger.info("Processing item", item_id=123, status="active")
    """
    # Use the provided name, or fall back to this module's name if not specified
    logger = logging.getLogger(name) if name else logging.getLogger(__name__)

    return StructuredLoggerAdapter(logger, {})
