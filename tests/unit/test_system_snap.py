"""Unit tests for the SnapdClient sentinel error handling."""

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

from concierge.system.snap import (
    SnapdAPIError,
    SnapdClient,
    SnapNotFoundError,
    SnapNotInstalledError,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


async def _passthrough[T](func: Callable[[], Awaitable[T]]) -> T:
    return await func()


def _client() -> SnapdClient:
    client = SnapdClient()
    client._with_retry = _passthrough  # ty: ignore[invalid-assignment]
    return client


class TestGetSnap:
    """`_get_snap` translates a 404 from snapd into `SnapNotInstalledError`."""

    @pytest.mark.asyncio
    async def test_returns_dict_on_success(self) -> None:
        client = _client()
        client._request = AsyncMock(return_value={"status": "active"})  # ty: ignore[invalid-assignment]

        result = await client._get_snap("juju")

        assert result == {"status": "active"}

    @pytest.mark.asyncio
    async def test_404_translates_to_not_installed(self) -> None:
        client = _client()
        client._request = AsyncMock(  # ty: ignore[invalid-assignment]
            side_effect=SnapdAPIError("Snapd API error: snap not installed", 404),
        )

        with pytest.raises(SnapNotInstalledError):
            await client._get_snap("nonexistent")

    @pytest.mark.asyncio
    async def test_other_status_propagates_snapd_api_error(self) -> None:
        client = _client()
        client._request = AsyncMock(  # ty: ignore[invalid-assignment]
            side_effect=SnapdAPIError("Snapd API error: boom", 500),
        )

        with pytest.raises(SnapdAPIError):
            await client._get_snap("juju")


class TestFindSnap:
    """`_find_snap` translates 404s and empty result sets into `SnapNotFoundError`."""

    @pytest.mark.asyncio
    async def test_exact_match_returned(self) -> None:
        client = _client()
        client._request = AsyncMock(  # ty: ignore[invalid-assignment]
            return_value=[{"name": "juju", "channels": {}}],
        )

        result = await client._find_snap("juju")

        assert result == {"name": "juju", "channels": {}}

    @pytest.mark.asyncio
    async def test_404_translates_to_not_found(self) -> None:
        client = _client()
        client._request = AsyncMock(  # ty: ignore[invalid-assignment]
            side_effect=SnapdAPIError("Snapd API error: snap not found", 404),
        )

        with pytest.raises(SnapNotFoundError):
            await client._find_snap("nonexistent")

    @pytest.mark.asyncio
    async def test_empty_results_translates_to_not_found(self) -> None:
        client = _client()
        client._request = AsyncMock(return_value=[])  # ty: ignore[invalid-assignment]

        with pytest.raises(SnapNotFoundError):
            await client._find_snap("nonexistent")

    @pytest.mark.asyncio
    async def test_other_status_propagates_snapd_api_error(self) -> None:
        client = _client()
        client._request = AsyncMock(  # ty: ignore[invalid-assignment]
            side_effect=SnapdAPIError("Snapd API error: boom", 500),
        )

        with pytest.raises(SnapdAPIError):
            await client._find_snap("juju")


class TestSnapInstalledInfo:
    """`_snap_installed_info` swallows `SnapNotInstalledError` and only that."""

    @pytest.mark.asyncio
    async def test_missing_snap_returns_defaults(self) -> None:
        client = SnapdClient()
        client._get_snap = AsyncMock(  # ty: ignore[invalid-assignment]
            side_effect=SnapNotInstalledError("snap not installed: juju"),
        )

        installed, active, tracking = await client._snap_installed_info("juju")

        assert (installed, active, tracking) == (False, False, "")

    @pytest.mark.asyncio
    async def test_other_errors_propagate(self) -> None:
        client = SnapdClient()
        client._get_snap = AsyncMock(  # ty: ignore[invalid-assignment]
            side_effect=SnapdAPIError("Snapd API error: boom", 500),
        )

        with pytest.raises(SnapdAPIError):
            await client._snap_installed_info("juju")

    @pytest.mark.asyncio
    async def test_active_snap_reports_tracking_channel(self) -> None:
        client = SnapdClient()
        client._get_snap = AsyncMock(  # ty: ignore[invalid-assignment]
            return_value={"status": "active", "tracking-channel": "3/stable"},
        )

        installed, active, tracking = await client._snap_installed_info("juju")

        assert (installed, active, tracking) == (True, True, "3/stable")


class TestSnapChannels:
    """`snap_channels` surfaces `SnapNotFoundError` unchanged to callers."""

    @pytest.mark.asyncio
    async def test_missing_snap_raises_not_found(self) -> None:
        client = SnapdClient()
        client._find_snap = AsyncMock(  # ty: ignore[invalid-assignment]
            side_effect=SnapNotFoundError("snap not found: nonexistent"),
        )

        with pytest.raises(SnapNotFoundError):
            await client.snap_channels("nonexistent")

    @pytest.mark.asyncio
    async def test_returns_sorted_channels(self) -> None:
        client = SnapdClient()
        client._find_snap = AsyncMock(  # ty: ignore[invalid-assignment]
            return_value={
                "channels": {
                    "latest/stable": {},
                    "3/stable": {},
                    "2.9/stable": {},
                },
            },
        )

        channels = await client.snap_channels("juju")

        assert channels == sorted(channels, reverse=True)


class TestRetry:
    """The retry policy short-circuits sentinel errors instead of retrying them."""

    @pytest.mark.asyncio
    async def test_not_installed_is_not_retried(self) -> None:
        client = SnapdClient()
        calls = 0

        async def _attempt() -> dict[str, Any]:
            nonlocal calls
            calls += 1
            raise SnapNotInstalledError("snap not installed: juju")

        with pytest.raises(SnapNotInstalledError):
            await client._with_retry(_attempt)

        assert calls == 1

    @pytest.mark.asyncio
    async def test_not_found_is_not_retried(self) -> None:
        client = SnapdClient()
        calls = 0

        async def _attempt() -> dict[str, Any]:
            nonlocal calls
            calls += 1
            raise SnapNotFoundError("snap not found: juju")

        with pytest.raises(SnapNotFoundError):
            await client._with_retry(_attempt)

        assert calls == 1
