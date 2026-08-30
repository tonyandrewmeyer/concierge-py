"""Snapd HTTP API client for querying snap information."""

import asyncio
import http.client
import json
import socket
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tenacity import (
    AsyncRetrying,
    RetryCallState,
    RetryError,
    stop_after_attempt,
    wait_exponential,
)

from concierge.core.logging import get_logger
from concierge.system.models import SnapInfo

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from concierge.system.runner import System

logger = get_logger(__name__)

SNAPD_SOCKET = Path("/run/snapd.socket")

SNAPD_TIMEOUT = 30


class _UnixSocketHTTPConnection(http.client.HTTPConnection):
    """An `http.client` connection that speaks HTTP over an `AF_UNIX` socket.

    snapd listens on a Unix socket rather than a TCP port, so only the socket
    path is meaningful and the host name exists purely to satisfy the `Host`
    header. Upstream Go concierge does the same thing by handing `net/http` a
    custom unix `DialContext`.
    """

    def __init__(self, socket_path: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(self.socket_path)
        except OSError:
            sock.close()
            raise
        self.sock = sock


class SnapdAPIError(Exception):
    """Raised when the snapd API returns a non-successful status code."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class SnapNotFoundError(Exception):
    """Raised when a snap is not found in the snap store."""


class SnapNotInstalledError(Exception):
    """Raised when a snap is not installed on the system."""


class SnapdClient:
    """Client for interacting with the snapd HTTP API via Unix socket."""

    def __init__(self, socket_path: Path = SNAPD_SOCKET) -> None:
        """Initialize the snapd client.

        Args:
            socket_path: Path to the snapd Unix socket
        """
        self.socket_path = socket_path

    async def snap_info(self, snap_name: str, channel: str = "") -> SnapInfo:
        """Get information about a snap.

        Args:
            snap_name: Name of the snap
            channel: Optional channel to query for classic confinement info

        Returns:
            SnapInfo with installation and confinement details

        Raises:
            Exception: If snapd API fails
        """
        # Check if snap is installed and get tracking channel
        installed, active, tracking_channel = await self._snap_installed_info(snap_name)

        # Check if snap uses classic confinement
        classic = await self._snap_is_classic(snap_name, channel)

        logger.debug(
            "Queried snapd API",
            snap=snap_name,
            installed=installed,
            active=active,
            classic=classic,
            tracking=tracking_channel,
        )

        return SnapInfo(
            installed=installed,
            active=active,
            classic=classic,
            tracking_channel=tracking_channel,
        )

    async def snap_channels(self, snap_name: str) -> list[str]:
        """Get list of available channels for a snap.

        Args:
            snap_name: Name of the snap

        Returns:
            List of channel names, sorted in reverse order

        Raises:
            Exception: If snapd API fails or snap not found
        """
        store_info = await self._find_snap(snap_name)

        if "channels" not in store_info:
            return []

        channels = list(store_info["channels"].keys())
        channels.sort(reverse=True)

        return channels

    async def _snap_installed_info(self, snap_name: str) -> tuple[bool, bool, str]:
        """Check if snap is installed and get its tracking channel.

        snapd reports "active" for a normal installed-and-enabled snap, and
        "installed" for a snap that is installed but disabled (e.g. while a
        refresh is in progress). Both states mean the snap is present on disk
        and should be refreshed rather than installed afresh.

        Args:
            snap_name: Name of the snap

        Returns:
            Tuple of (is_installed, is_active, tracking_channel). `is_active`
            is True only for the "active" status; a disabled snap has
            `is_installed=True` and `is_active=False`.
        """
        try:
            snap_data = await self._get_snap(snap_name)
        except SnapNotInstalledError:
            return False, False, ""

        if snap_data:
            status = snap_data.get("status")
            if status in ("active", "installed"):
                tracking_channel = snap_data.get("tracking-channel", "")
                if not tracking_channel:
                    tracking_channel = snap_data.get("channel", "")
                return True, status == "active", tracking_channel

        return False, False, ""

    async def _snap_is_classic(self, snap_name: str, channel: str) -> bool:
        """Check if snap uses classic confinement.

        Args:
            snap_name: Name of the snap
            channel: Channel to check (if empty, checks default)

        Returns:
            True if snap uses classic confinement
        """
        try:
            store_info = await self._find_snap(snap_name)

            # If a specific channel is requested, check that channel
            if channel and "channels" in store_info:
                channel_info = store_info["channels"].get(channel)
                if channel_info:
                    return channel_info.get("confinement") == "classic"

            # Otherwise check the default confinement
            return store_info.get("confinement") == "classic"

        except Exception as e:
            logger.warning("Failed to check snap confinement", snap=snap_name, error=str(e))
            return False

    async def _get_snap(self, snap_name: str) -> dict[str, Any]:
        """Get information about an installed snap.

        Args:
            snap_name: Name of the snap

        Returns:
            Snap information from snapd

        Raises:
            Exception: If snap is not installed or API fails
        """

        async def _attempt() -> dict[str, Any]:
            try:
                result = await self._request("GET", f"/v2/snaps/{snap_name}")
            except SnapdAPIError as e:
                if e.status_code == 404:
                    raise SnapNotInstalledError(f"snap not installed: {snap_name}") from e
                raise
            if not isinstance(result, dict):
                raise ValueError(f"Unexpected response type: {type(result)}")
            return result

        return await self._with_retry(_attempt)

    async def _find_snap(self, snap_name: str) -> dict[str, Any]:
        """Find a snap in the store.

        Args:
            snap_name: Name of the snap

        Returns:
            Snap information from the store

        Raises:
            Exception: If snap is not found or API fails
        """

        async def _attempt() -> dict[str, Any]:
            try:
                result = await self._request("GET", f"/v2/find?name={snap_name}")
            except SnapdAPIError as e:
                if e.status_code == 404:
                    raise SnapNotFoundError(f"snap not found: {snap_name}") from e
                raise

            if isinstance(result, list) and len(result) > 0:
                # Find exact match
                for snap in result:
                    if snap.get("name") == snap_name:
                        return snap
                # If no exact match, return first result
                return result[0]

            raise SnapNotFoundError(f"snap not found: {snap_name}")

        return await self._with_retry(_attempt)

    def _request_sync(self, method: str, endpoint: str) -> Any:
        """Make a blocking HTTP request to the snapd API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path

        Returns:
            Response data from the 'result' field

        Raises:
            SnapdAPIError: If the response body reports a non-200 status code
        """
        conn = _UnixSocketHTTPConnection(str(self.socket_path), SNAPD_TIMEOUT)
        try:
            conn.request(method, endpoint)
            body = conn.getresponse().read()
        finally:
            conn.close()

        # snapd reports its own status in the body, so the body is parsed for
        # error responses too rather than keying off the HTTP status line.
        response_data = json.loads(body)

        status_code = response_data.get("status-code", 0)
        if status_code != 200:
            error_msg = response_data.get("result", {}).get("message", "Unknown error")
            raise SnapdAPIError(f"Snapd API error: {error_msg}", status_code)

        return response_data.get("result")

    async def _request(self, method: str, endpoint: str) -> Any:
        """Make an HTTP request to the snapd API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path

        Returns:
            Response data from the 'result' field

        Raises:
            Exception: If request fails
        """
        if not self.socket_path.exists():
            raise FileNotFoundError(f"Snapd socket not found at {self.socket_path}")

        # `http.client` is blocking, so it is driven from a worker thread to
        # keep the event loop free while snapd answers.
        return await asyncio.to_thread(self._request_sync, method, endpoint)

    async def _with_retry[T](self, func: Callable[[], Awaitable[T]]) -> T:
        """Execute a function with retry logic.

        Args:
            func: Async function to execute

        Returns:
            Function result

        Raises:
            Exception: If all retries fail
        """

        def should_retry(retry_state: RetryCallState) -> bool:
            """Determine if an exception should trigger a retry.

            Returns:
                False for permanent failures like the snap being missing from the
                store or not installed on the system.
            """
            if retry_state.outcome is None:
                return True

            exception = retry_state.outcome.exception()
            if exception is None:
                return False

            # Don't retry on expected/permanent errors surfaced via typed sentinels.
            return not isinstance(exception, (SnapNotInstalledError, SnapNotFoundError))

        try:
            async for attempt in AsyncRetrying(
                wait=wait_exponential(multiplier=1, min=1, max=10),
                stop=stop_after_attempt(10),
                retry=should_retry,
                reraise=True,
            ):
                with attempt:
                    return await func()
        except RetryError as e:
            exc = e.last_attempt.exception()
            if exc is not None:
                raise exc from e
            raise

        # This should never be reached
        raise RuntimeError("Unexpected retry error")


# Integrate snapd client with System class
def add_snap_support(system: System) -> None:
    """Add snap support methods to a System instance.

    This function patches the System class to add snap_info and snap_channels methods.

    Args:
        system: System instance to patch
    """
    snapd_client = SnapdClient()

    async def snap_info(snap: str, channel: str = "") -> SnapInfo:
        return await snapd_client.snap_info(snap, channel)

    async def snap_channels(snap: str) -> list[str]:
        return await snapd_client.snap_channels(snap)

    # Bind methods to the instance.
    system.snap_info = snap_info  # ty: ignore[invalid-assignment]
    system.snap_channels = snap_channels  # ty: ignore[invalid-assignment]
