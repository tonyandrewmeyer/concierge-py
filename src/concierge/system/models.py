"""Data models for system operations.

This module provides dataclasses for working with snap packages
and snap information from the snapd API.
"""

from dataclasses import dataclass, field


@dataclass
class SnapInfo:
    """Information about a snap from the snapd API.

    Attributes:
        installed: Whether the snap is currently installed
        classic: Whether the snap uses classic confinement
        tracking_channel: The channel the snap is tracking (if installed)
    """

    installed: bool
    classic: bool
    tracking_channel: str = ""


@dataclass
class Snap:
    """Represents a snap package.

    Attributes:
        name: Name of the snap
        channel: Snap Store channel to install from
        connections: List of snap connections to establish
    """

    name: str
    channel: str = ""
    connections: list[str] = field(default_factory=list)

    @staticmethod
    def from_string(snap_str: str) -> Snap:
        """Parse a snap from shorthand form (e.g., 'charmcraft/latest/edge').

        Args:
            snap_str: Snap string in format 'name' or 'name/channel'

        Returns:
            Snap instance
        """
        parts = snap_str.split("/", 1)
        if len(parts) == 2:
            return Snap(name=parts[0], channel=parts[1])
        return Snap(name=parts[0])
