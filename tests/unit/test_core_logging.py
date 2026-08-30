"""Tests for the logging configuration."""

import logging
import re
import sys

import pytest

from concierge.core.logging import ConsoleFormatter, get_logger, setup_logging


def make_record(
    level: int = logging.INFO, msg: str = "hello", **kwargs: object
) -> logging.LogRecord:
    record = logging.LogRecord(
        name="concierge.test",
        level=level,
        pathname="/src/concierge/core/thing.py",
        lineno=42,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in kwargs.items():
        setattr(record, key, value)
    return record


def test_formatter_renders_timestamp_level_and_message() -> None:
    formatted = ConsoleFormatter().format(make_record())

    assert re.fullmatch(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] INFO {5}hello", formatted)


def test_formatter_omits_path_by_default() -> None:
    assert "thing:42" not in ConsoleFormatter().format(make_record())


def test_formatter_shows_path_when_requested() -> None:
    assert ConsoleFormatter(show_path=True).format(make_record()).endswith(" thing:42")


def test_formatter_emits_no_escapes_without_colour() -> None:
    assert "\033" not in ConsoleFormatter(show_path=True).format(make_record(logging.ERROR))


def test_formatter_colours_timestamp_and_level() -> None:
    formatted = ConsoleFormatter(colour=True).format(make_record(logging.WARNING))

    assert "\033[2m[" in formatted
    assert "\033[33mWARNING " in formatted
    assert formatted.endswith("hello")


def test_formatter_appends_exception_text() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = make_record(exc_info=sys.exc_info())

    formatted = ConsoleFormatter().format(record)

    assert "Traceback (most recent call last):" in formatted
    assert formatted.endswith("ValueError: boom")


def test_adapter_appends_context_without_markup(caplog: pytest.LogCaptureFixture) -> None:
    logger = get_logger("concierge.test.context")

    with caplog.at_level(logging.INFO):
        logger.info("Bootstrap complete", provider="lxd", duration=42.5)

    assert caplog.messages == ["Bootstrap complete [duration=42.5 provider=lxd]"]


def test_adapter_leaves_message_alone_without_context(caplog: pytest.LogCaptureFixture) -> None:
    logger = get_logger("concierge.test.plain")

    with caplog.at_level(logging.INFO):
        logger.info("Bootstrap complete", exc_info=False)

    assert caplog.messages == ["Bootstrap complete"]


@pytest.mark.parametrize(
    ("verbose", "trace", "expected_level", "expected_path"),
    [
        (False, False, logging.INFO, False),
        (True, False, logging.DEBUG, False),
        (False, True, logging.DEBUG, True),
    ],
)
def test_setup_logging_configures_stderr_handler(
    verbose: bool, trace: bool, expected_level: int, expected_path: bool
) -> None:
    try:
        setup_logging(verbose=verbose, trace=trace)

        root = logging.getLogger()
        assert root.level == expected_level
        (handler,) = root.handlers
        assert isinstance(handler, logging.StreamHandler)
        formatter = handler.formatter
        assert isinstance(formatter, ConsoleFormatter)
        assert formatter.show_path is expected_path
    finally:
        # Other tests rely on pytest's own root handlers, which force=True has replaced.
        logging.basicConfig(force=True)
