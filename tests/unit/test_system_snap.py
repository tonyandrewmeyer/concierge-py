"""Unit tests for the SnapdClient sentinel error handling and Unix socket transport."""

import contextlib
import http.server
import json
import socketserver
import threading
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

from concierge.system.models import InstalledSnapInfo, SnapInfo
from concierge.system.snap import (
    SnapdAPIError,
    SnapdClient,
    SnapNotFoundError,
    SnapNotInstalledError,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator
    from pathlib import Path


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
    """`snap_installed_info` swallows `SnapNotInstalledError` and only that."""

    @pytest.mark.asyncio
    async def test_missing_snap_returns_defaults(self) -> None:
        client = SnapdClient()
        client._get_snap = AsyncMock(  # ty: ignore[invalid-assignment]
            side_effect=SnapNotInstalledError("snap not installed: juju"),
        )

        info = await client.snap_installed_info("juju")

        assert info == InstalledSnapInfo()

    @pytest.mark.asyncio
    async def test_other_errors_propagate(self) -> None:
        client = SnapdClient()
        client._get_snap = AsyncMock(  # ty: ignore[invalid-assignment]
            side_effect=SnapdAPIError("Snapd API error: boom", 500),
        )

        with pytest.raises(SnapdAPIError):
            await client.snap_installed_info("juju")

    @pytest.mark.asyncio
    async def test_active_snap_reports_tracking_channel(self) -> None:
        client = SnapdClient()
        client._get_snap = AsyncMock(  # ty: ignore[invalid-assignment]
            return_value={"status": "active", "tracking-channel": "3/stable"},
        )

        info = await client.snap_installed_info("juju")

        assert (info.installed, info.active, info.tracking_channel) == (True, True, "3/stable")

    @pytest.mark.asyncio
    async def test_reports_revision_and_version(self) -> None:
        client = SnapdClient()
        client._get_snap = AsyncMock(  # ty: ignore[invalid-assignment]
            return_value={
                "status": "installed",
                "channel": "latest/stable",
                "revision": "1234",
                "version": "5.21.3",
            },
        )

        info = await client.snap_installed_info("lxd")

        assert info == InstalledSnapInfo(
            installed=True,
            active=False,
            tracking_channel="latest/stable",
            revision="1234",
            version="5.21.3",
        )

    @pytest.mark.asyncio
    async def test_other_status_is_not_installed(self) -> None:
        client = SnapdClient()
        client._get_snap = AsyncMock(  # ty: ignore[invalid-assignment]
            return_value={"status": "available", "revision": "1"},
        )

        assert await client.snap_installed_info("juju") == InstalledSnapInfo()


class TestSnapInfo:
    """`snap_info` combines the installed details with the store confinement."""

    @pytest.mark.asyncio
    async def test_combines_installed_info_and_classic(self) -> None:
        client = SnapdClient()
        installed = InstalledSnapInfo(
            installed=True,
            active=True,
            tracking_channel="3/stable",
            revision="31337",
            version="3.6.9",
        )
        client.snap_installed_info = AsyncMock(  # ty: ignore[invalid-assignment]
            return_value=installed,
        )
        client._snap_is_classic = AsyncMock(return_value=True)  # ty: ignore[invalid-assignment]

        info = await client.snap_info("juju", "3/stable")

        assert info == SnapInfo(
            installed=True,
            active=True,
            tracking_channel="3/stable",
            revision="31337",
            version="3.6.9",
            classic=True,
        )

    @pytest.mark.asyncio
    async def test_snapd_failure_is_an_error(self) -> None:
        """Failing to query the local snapd is reported, not treated as not installed."""
        client = SnapdClient()
        client._get_snap = AsyncMock(  # ty: ignore[invalid-assignment]
            side_effect=SnapdAPIError("Snapd API error: boom", 500),
        )
        client._snap_is_classic = AsyncMock(return_value=False)  # ty: ignore[invalid-assignment]

        with pytest.raises(SnapdAPIError):
            await client.snap_info("juju")


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


@contextlib.contextmanager
def _snapd_server(
    socket_path: Path,
    routes: dict[str, tuple[int, dict[str, Any]]],
) -> Iterator[None]:
    """Serve canned snapd JSON over a Unix socket, as snapd itself does."""

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self) -> None:
            status, payload = routes[self.path]
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: Any) -> None:
            # The default implementation writes every request to stderr.
            pass

        def address_string(self) -> str:
            # A Unix peer has no address, so the base implementation would
            # index an empty string and raise.
            return "unix"

    server = socketserver.ThreadingUnixStreamServer(str(socket_path), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class TestUnixSocketTransport:
    """`_request` speaks HTTP to snapd over its Unix socket."""

    @pytest.mark.asyncio
    async def test_installed_snap(self, tmp_path: Path) -> None:
        socket_path = tmp_path / "snapd.socket"
        routes = {
            "/v2/snaps/juju": (
                200,
                {
                    "type": "sync",
                    "status-code": 200,
                    "result": {
                        "name": "juju",
                        "status": "active",
                        "tracking-channel": "3/stable",
                        "revision": "31337",
                        "version": "3.6.9",
                    },
                },
            ),
        }

        with _snapd_server(socket_path, routes):
            client = SnapdClient(socket_path)
            result = await client._request("GET", "/v2/snaps/juju")
            info = await client.snap_installed_info("juju")

        assert result["tracking-channel"] == "3/stable"
        assert info == InstalledSnapInfo(
            installed=True,
            active=True,
            tracking_channel="3/stable",
            revision="31337",
            version="3.6.9",
        )

    @pytest.mark.asyncio
    async def test_find_keeps_channels_map(self, tmp_path: Path) -> None:
        socket_path = tmp_path / "snapd.socket"
        routes = {
            "/v2/find?name=juju": (
                200,
                {
                    "type": "sync",
                    "status-code": 200,
                    "result": [
                        {
                            "name": "juju",
                            "confinement": "classic",
                            "channels": {
                                "latest/stable": {"confinement": "classic"},
                                "3/stable": {"confinement": "classic"},
                            },
                        },
                    ],
                },
            ),
        }

        with _snapd_server(socket_path, routes):
            client = SnapdClient(socket_path)
            channels = await client.snap_channels("juju")
            classic = await client._snap_is_classic("juju", "3/stable")

        assert channels == ["latest/stable", "3/stable"]
        assert classic is True

    @pytest.mark.asyncio
    async def test_404_body(self, tmp_path: Path) -> None:
        socket_path = tmp_path / "snapd.socket"
        routes = {
            "/v2/snaps/nope": (
                404,
                {
                    "type": "error",
                    "status-code": 404,
                    "result": {"message": 'snap "nope" not found', "kind": "snap-not-found"},
                },
            ),
        }

        with _snapd_server(socket_path, routes):
            client = SnapdClient(socket_path)

            with pytest.raises(SnapdAPIError) as request_error:
                await client._request("GET", "/v2/snaps/nope")

            with pytest.raises(SnapNotInstalledError):
                await client._get_snap("nope")

        assert request_error.value.status_code == 404
        assert 'snap "nope" not found' in str(request_error.value)

    @pytest.mark.asyncio
    async def test_error_status_in_body(self, tmp_path: Path) -> None:
        # snapd can answer HTTP 200 while reporting a failure in the body, so
        # the body's status-code is what decides success.
        socket_path = tmp_path / "snapd.socket"
        routes = {
            "/v2/snaps/juju": (
                200,
                {
                    "type": "error",
                    "status-code": 500,
                    "result": {"message": "internal server error"},
                },
            ),
        }

        with _snapd_server(socket_path, routes):
            client = SnapdClient(socket_path)

            with pytest.raises(SnapdAPIError) as error:
                await client._request("GET", "/v2/snaps/juju")

        assert error.value.status_code == 500
        assert "internal server error" in str(error.value)

    @pytest.mark.asyncio
    async def test_missing_socket(self, tmp_path: Path) -> None:
        client = SnapdClient(tmp_path / "absent.socket")

        with pytest.raises(FileNotFoundError):
            await client._request("GET", "/v2/snaps/juju")
