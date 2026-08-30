"""Tests that --verbose and --trace reach the configuration and the runner."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from concierge.cli import app
from concierge.cli.commands.prepare import run_prepare
from concierge.cli.commands.restore import run_restore
from concierge.config.models import ConciergeConfig, ConfigOverrides


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace the Manager used by both commands with a recording double."""
    factory = MagicMock()
    factory.return_value.prepare = AsyncMock()
    factory.return_value.restore = AsyncMock()
    monkeypatch.setattr("concierge.cli.commands.prepare.Manager", factory)
    monkeypatch.setattr("concierge.cli.commands.restore.Manager", factory)
    return factory


def config_of(manager: MagicMock) -> ConciergeConfig:
    """Return the configuration the Manager was constructed with."""
    return manager.call_args.args[0]


async def test_prepare_passes_trace_to_the_manager(manager: MagicMock) -> None:
    await run_prepare("", "dev", ConfigOverrides(), verbose=True, trace=True)

    assert config_of(manager).verbose is True
    assert config_of(manager).trace is True
    assert manager.call_args.kwargs["trace"] is True


async def test_prepare_defaults_to_no_tracing(manager: MagicMock) -> None:
    await run_prepare("", "dev", ConfigOverrides())

    assert config_of(manager).trace is False
    assert manager.call_args.kwargs["trace"] is False


async def test_prepare_flag_overrides_the_configuration_file(
    manager: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`trace` is a command line flag, so a config file cannot turn it on."""
    from_file = ConciergeConfig.from_dict({"trace": True})
    monkeypatch.setattr("concierge.cli.commands.prepare.load_config", lambda **_: from_file)

    await run_prepare("concierge.yaml", "", ConfigOverrides())

    assert config_of(manager).trace is False


async def test_restore_passes_trace_to_the_manager(manager: MagicMock) -> None:
    await run_restore("", "dev", verbose=True, trace=True)

    assert config_of(manager).verbose is True
    assert config_of(manager).trace is True
    assert manager.call_args.kwargs["trace"] is True


@pytest.mark.parametrize(
    "argv",
    [
        ["prepare", "--trace", "--preset", "dev"],
        ["--trace", "prepare", "--preset", "dev"],
    ],
)
def test_cli_forwards_trace_to_prepare(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}

    async def fake_prepare(*args: Any, **kwargs: Any) -> None:
        recorded.update(kwargs)

    monkeypatch.setattr(app, "run_prepare", fake_prepare)

    app.main(argv)

    assert recorded["trace"] is True
    assert recorded["verbose"] is False


def test_cli_forwards_trace_to_restore(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}

    async def fake_restore(*args: Any, **kwargs: Any) -> None:
        recorded.update(kwargs)

    monkeypatch.setattr(app, "run_restore", fake_restore)

    app.main(["restore", "--trace", "--verbose"])

    assert recorded["trace"] is True
    assert recorded["verbose"] is True
