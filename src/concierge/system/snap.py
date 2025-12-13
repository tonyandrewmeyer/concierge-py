"""Snapd HTTP API client for querying snap information."""

import asyncio
from pathlib import Path
from typing import Any

import aiohttp
import structlog
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from concierge.system.models import SnapInfo

logger = structlog.get_logger()

SNAPD_SOCKET = Path("/run/snapd.socket")


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
        installed, tracking_channel = await self._snap_installed_info(snap_name)

        # Check if snap uses classic confinement
        classic = await self._snap_is_classic(snap_name, channel)

        logger.debug(
            "Queried snapd API",
            snap=snap_name,
            installed=installed,
            classic=classic,
            tracking=tracking_channel,
        )

        return SnapInfo(
            installed=installed,
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

    async def _snap_installed_info(self, snap_name: str) -> tuple[bool, str]:
        """Check if snap is installed and get its tracking channel.

        Args:
            snap_name: Name of the snap

        Returns:
            Tuple of (is_installed, tracking_channel)
        """
        try:
            snap_data = await self._get_snap(snap_name)

            if snap_data and snap_data.get("status") == "active":
                tracking_channel = snap_data.get("tracking-channel", "")
                if not tracking_channel:
                    tracking_channel = snap_data.get("channel", "")
                return True, tracking_channel

            return False, ""

        except Exception as e:
            # If snap is not installed, the API returns an error
            if "snap not installed" in str(e).lower():
                return False, ""
            # For other errors, re-raise
            raise

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
            result = await self._request("GET", f"/v2/snaps/{snap_name}")
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
            result = await self._request("GET", f"/v2/find?name={snap_name}")

            if isinstance(result, list) and len(result) > 0:
                # Find exact match
                for snap in result:
                    if snap.get("name") == snap_name:
                        return snap
                # If no exact match, return first result
                return result[0]

            raise ValueError(f"Snap '{snap_name}' not found in store")

        return await self._with_retry(_attempt)

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

        url = f"http://localhost{endpoint}"

        connector = aiohttp.UnixConnector(path=str(self.socket_path))
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout
        ) as session:
            async with session.request(method, url) as response:
                response_data = await response.json()

                if response_data.get("status-code") != 200:
                    error_msg = response_data.get("result", {}).get("message", "Unknown error")
                    raise Exception(f"Snapd API error: {error_msg}")

                return response_data.get("result")

    async def _with_retry[T](self, func: callable) -> T:
        """Execute a function with retry logic.

        Args:
            func: Async function to execute

        Returns:
            Function result

        Raises:
            Exception: If all retries fail
        """
        try:
            async for attempt in AsyncRetrying(
                wait=wait_exponential(multiplier=1, min=1, max=10),
                stop=stop_after_attempt(10),
                retry=retry_if_exception_type(Exception),
                reraise=True,
            ):
                with attempt:
                    return await func()
        except RetryError as e:
            if e.last_attempt.exception():
                raise e.last_attempt.exception() from e
            raise

        # This should never be reached
        raise RuntimeError("Unexpected retry error")


# Integrate snapd client with System class
def add_snap_support(system: "System") -> None:
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

    # Bind methods to the instance
    system.snap_info = snap_info  # type: ignore
    system.snap_channels = snap_channels  # type: ignore
