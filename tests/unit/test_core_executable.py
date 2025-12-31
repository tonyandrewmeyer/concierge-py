"""Unit tests for Executable protocol."""

import pytest

from concierge.core.executable import Executable


class MockExecutableValid:
    """Valid implementation of Executable protocol."""

    async def prepare(self) -> None:
        """Prepare implementation."""

    async def restore(self) -> None:
        """Restore implementation."""


class MockExecutableInvalid:
    """Invalid implementation missing protocol methods."""

    async def prepare(self) -> None:
        """Only has prepare."""


class TestExecutableProtocol:
    """Tests for Executable protocol."""

    def test_valid_implementation(self) -> None:
        """Test that valid implementation is recognized as Executable."""
        valid = MockExecutableValid()
        assert isinstance(valid, Executable)

    def test_invalid_implementation(self) -> None:
        """Test that invalid implementation is not recognized as Executable."""
        invalid = MockExecutableInvalid()
        assert not isinstance(invalid, Executable)

    def test_protocol_has_prepare_method(self) -> None:
        """Test that Executable protocol requires prepare method."""
        assert hasattr(Executable, "prepare")

    def test_protocol_has_restore_method(self) -> None:
        """Test that Executable protocol requires restore method."""
        assert hasattr(Executable, "restore")

    @pytest.mark.asyncio
    async def test_executable_methods_are_async(self) -> None:
        """Test that protocol methods can be awaited."""
        valid = MockExecutableValid()
        # Should not raise - methods are async
        await valid.prepare()
        await valid.restore()
