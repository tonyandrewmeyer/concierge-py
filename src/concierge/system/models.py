"""Data models for system operations.

This module provides dataclasses for working with snap packages
and snap information from the snapd API.
"""

from dataclasses import dataclass, field


@dataclass
class InstalledSnapInfo:
    """Information about the locally installed copy of a snap.

    This is fetched from the snapd API without querying the snap store.

    Attributes:
        installed: Whether the snap is currently installed (active or disabled)
        active: Whether the snap is installed and enabled. False for installed
            but disabled snaps (e.g. during a refresh).
        tracking_channel: The channel the snap is tracking (if installed)
        revision: The installed revision (if installed)
        version: The installed version (if installed)
    """

    installed: bool = False
    active: bool = False
    tracking_channel: str = ""
    revision: str = ""
    version: str = ""


@dataclass
class SnapInfo(InstalledSnapInfo):
    """Information about a snap from the snapd API.

    This includes details that require querying the snap store.

    Attributes:
        classic: Whether the snap uses classic confinement
    """

    classic: bool = False


@dataclass
class Snap:
    """Represents a snap package.

    Attributes:
        name: Name of the snap
        channel: Snap Store channel to install from
        default_channel: Channel to install from when `channel` is empty and the
            snap is not yet installed. An installed snap stays on its tracking channel.
        revision: Snap Store revision to install. If both channel and revision
            are set, snap uses the revision; channel is only used for tracking
            after install.
        connections: List of snap connections to establish
    """

    name: str
    channel: str = ""
    default_channel: str = ""
    revision: str = ""
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
