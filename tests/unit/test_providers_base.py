"""Unit tests for the shared provider helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from concierge.providers.base import installed_channel
from concierge.system.models import InstalledSnapInfo, Snap


def _worker(info: InstalledSnapInfo) -> MagicMock:
    worker = MagicMock()
    worker.snap_installed_info = AsyncMock(return_value=info)
    return worker


@pytest.mark.asyncio
async def test_installed_channel_when_no_channel_requested() -> None:
    worker = _worker(InstalledSnapInfo(installed=True, tracking_channel="1.30/stable"))

    assert await installed_channel(worker, Snap(name="microk8s")) == "1.30/stable"


@pytest.mark.asyncio
async def test_installed_channel_ignored_when_channel_requested() -> None:
    worker = _worker(InstalledSnapInfo(installed=True, tracking_channel="1.30/stable"))

    assert await installed_channel(worker, Snap(name="microk8s", channel="1.32/stable")) == ""
    worker.snap_installed_info.assert_not_awaited()


@pytest.mark.asyncio
async def test_installed_channel_empty_when_not_installed() -> None:
    worker = _worker(InstalledSnapInfo())

    assert await installed_channel(worker, Snap(name="microk8s")) == ""
