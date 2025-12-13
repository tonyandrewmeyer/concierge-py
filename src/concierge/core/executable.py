"""Executable protocol for prepare/restore operations."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Executable(Protocol):
    """Protocol for components that can be prepared and restored.

    This protocol defines the interface for handlers and providers that
    perform system setup (prepare) and teardown (restore) operations.
    """

    async def prepare(self) -> None:
        """Prepare the component (install, configure, bootstrap).

        Raises:
            Exception: If preparation fails
        """
        ...

    async def restore(self) -> None:
        """Restore the component to its pre-concierge state.

        Raises:
            Exception: If restoration fails
        """
        ...
