"""Logging configuration for Concierge using the standard library logging module."""

import logging
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import MutableMapping

_TIME_FORMAT = "[%Y-%m-%d %H:%M:%S]"

_RESET = "\033[0m"
_DIM = "\033[2m"

# Upstream's log/slog text handler is uncoloured, but concierge already writes raw ANSI
# escapes when echoing commands (see system/runner.py), so a little colour to separate the
# timestamp and level from the message is consistent with the rest of the tool.
_LEVEL_COLOURS = {
    logging.DEBUG: "\033[36m",
    logging.INFO: "\033[32m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[1;31m",
}


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

    # The stdlib LoggerAdapter methods are typed to accept only the documented
    # logging kwargs (exc_info, stack_info, stacklevel, extra). We accept
    # arbitrary **kwargs so callers can pass structlog-style context
    # (e.g. logger.info("done", provider="lxd")); process() folds those extra
    # kwargs into the formatted message at runtime. These overrides exist
    # purely to widen the signature for type checkers — the behaviour is
    # unchanged from the inherited implementations.
    def debug(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        super().debug(msg, *args, **kwargs)

    def info(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        super().info(msg, *args, **kwargs)

    def warning(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        super().warning(msg, *args, **kwargs)

    def error(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        super().error(msg, *args, **kwargs)

    def exception(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        super().exception(msg, *args, **kwargs)

    def critical(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        super().critical(msg, *args, **kwargs)

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
            msg = f"{msg} [{context_str}]"

        return msg, clean_kwargs


class ConsoleFormatter(logging.Formatter):
    """Formatter rendering records as `[timestamp] LEVEL message`, optionally coloured.

    Args:
        show_path: Append the module name and line number to each record.
        colour: Wrap the timestamp and level name in ANSI escapes.
    """

    def __init__(self, *, show_path: bool = False, colour: bool = False) -> None:
        super().__init__(datefmt=_TIME_FORMAT)
        self.show_path = show_path
        self.colour = colour

    # Named _colourise rather than _style because logging.Formatter._style is the
    # percent/brace formatting strategy object it uses internally.
    def _colourise(self, text: str, style: str) -> str:
        return f"{style}{text}{_RESET}" if self.colour else text

    def format(self, record: logging.LogRecord) -> str:
        """Render a single log record as a line of text."""
        level_colour = _LEVEL_COLOURS.get(record.levelno, "")
        parts = [
            self._colourise(self.formatTime(record, self.datefmt), _DIM),
            self._colourise(f"{record.levelname:<8}", level_colour),
            record.getMessage(),
        ]
        if self.show_path:
            parts.append(self._colourise(f"{record.module}:{record.lineno}", _DIM))
        line = " ".join(parts)

        # Exception and stack text are appended the same way the base class does it, so
        # that a cached exc_text from another handler is reused rather than recomputed.
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            line = f"{line}\n{record.exc_text}"
        if record.stack_info:
            line = f"{line}\n{self.formatStack(record.stack_info)}"

        return line


def setup_logging(verbose: bool = False, trace: bool = False) -> None:
    """Configure structured logging on stderr.

    Args:
        verbose: Enable debug logging
        trace: Enable trace logging (most verbose)
    """
    # There is no level below DEBUG in the standard library, so trace only differs from
    # verbose in showing the module and line number of each record.
    log_level = logging.DEBUG if verbose or trace else logging.INFO

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(ConsoleFormatter(show_path=trace, colour=sys.stderr.isatty()))

    logging.basicConfig(level=log_level, handlers=[handler], force=True)


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
