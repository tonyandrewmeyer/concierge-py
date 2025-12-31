"""Unit tests for system models."""

from concierge.system.models import Snap, SnapInfo


class TestSnapInfo:
    """Tests for SnapInfo dataclass."""

    def test_create_snapinfo(self) -> None:
        """Test creating a SnapInfo instance."""
        snap_info = SnapInfo(installed=True, classic=False, tracking_channel="latest/stable")
        assert snap_info.installed is True
        assert snap_info.classic is False
        assert snap_info.tracking_channel == "latest/stable"

    def test_snapinfo_defaults(self) -> None:
        """Test SnapInfo default values."""
        snap_info = SnapInfo(installed=True, classic=False)
        assert snap_info.installed is True
        assert snap_info.classic is False
        assert snap_info.tracking_channel == ""

    def test_snapinfo_not_installed(self) -> None:
        """Test SnapInfo for non-installed snap."""
        snap_info = SnapInfo(installed=False, classic=False)
        assert snap_info.installed is False
        assert snap_info.classic is False
        assert snap_info.tracking_channel == ""

    def test_snapinfo_classic_confinement(self) -> None:
        """Test SnapInfo with classic confinement."""
        snap_info = SnapInfo(installed=True, classic=True, tracking_channel="latest/edge")
        assert snap_info.installed is True
        assert snap_info.classic is True
        assert snap_info.tracking_channel == "latest/edge"


class TestSnap:
    """Tests for Snap dataclass."""

    def test_create_snap_minimal(self) -> None:
        """Test creating a Snap with minimal arguments."""
        snap = Snap(name="charmcraft")
        assert snap.name == "charmcraft"
        assert snap.channel == ""
        assert snap.connections == []

    def test_create_snap_with_channel(self) -> None:
        """Test creating a Snap with a channel."""
        snap = Snap(name="charmcraft", channel="latest/stable")
        assert snap.name == "charmcraft"
        assert snap.channel == "latest/stable"
        assert snap.connections == []

    def test_create_snap_with_connections(self) -> None:
        """Test creating a Snap with connections."""
        connections = ["snap:plug1", "snap:plug2"]
        snap = Snap(name="mysnap", channel="latest/edge", connections=connections)
        assert snap.name == "mysnap"
        assert snap.channel == "latest/edge"
        assert snap.connections == connections

    def test_from_string_name_only(self) -> None:
        """Test parsing snap from string with name only."""
        snap = Snap.from_string("charmcraft")
        assert snap.name == "charmcraft"
        assert snap.channel == ""
        assert snap.connections == []

    def test_from_string_with_channel(self) -> None:
        """Test parsing snap from string with name and channel."""
        snap = Snap.from_string("charmcraft/latest/stable")
        assert snap.name == "charmcraft"
        assert snap.channel == "latest/stable"
        assert snap.connections == []

    def test_from_string_with_edge_channel(self) -> None:
        """Test parsing snap from string with edge channel."""
        snap = Snap.from_string("snapcraft/latest/edge")
        assert snap.name == "snapcraft"
        assert snap.channel == "latest/edge"

    def test_from_string_with_track(self) -> None:
        """Test parsing snap from string with track in channel."""
        snap = Snap.from_string("microk8s/1.28/stable")
        assert snap.name == "microk8s"
        assert snap.channel == "1.28/stable"

    def test_from_string_with_multiple_slashes(self) -> None:
        """Test parsing snap string with multiple slashes (only splits on first)."""
        snap = Snap.from_string("mysnap/track/risk/branch")
        assert snap.name == "mysnap"
        assert snap.channel == "track/risk/branch"

    def test_from_string_empty_name(self) -> None:
        """Test parsing snap from empty string."""
        snap = Snap.from_string("")
        assert snap.name == ""
        assert snap.channel == ""

    def test_from_string_with_slash_only(self) -> None:
        """Test parsing snap string that is just a slash."""
        snap = Snap.from_string("/")
        assert snap.name == ""
        assert snap.channel == ""

    def test_snap_equality(self) -> None:
        """Test that Snap dataclasses can be compared for equality."""
        snap1 = Snap(name="test", channel="latest/stable", connections=["conn1"])
        snap2 = Snap(name="test", channel="latest/stable", connections=["conn1"])
        snap3 = Snap(name="test", channel="latest/edge", connections=["conn1"])

        assert snap1 == snap2
        assert snap1 != snap3

    def test_snap_repr(self) -> None:
        """Test that Snap has a useful string representation."""
        snap = Snap(name="charmcraft", channel="latest/stable")
        repr_str = repr(snap)
        assert "charmcraft" in repr_str
        assert "latest/stable" in repr_str
