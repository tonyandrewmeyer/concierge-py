"""Provider protocol for cloud/platform providers."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Provider(Protocol):
    """Protocol for cloud/platform providers that Juju can be bootstrapped onto.

    Providers handle installation and configuration of their respective platforms
    (LXD, MicroK8s, K8s, Google Cloud) and provide information for Juju bootstrap.
    """

    async def prepare(self) -> None:
        """Prepare the provider (install, configure).

        Raises:
            Exception: If preparation fails
        """
        ...

    async def restore(self) -> None:
        """Restore the provider to its pre-concierge state.

        Raises:
            Exception: If restoration fails
        """
        ...

    def name(self) -> str:
        """Get the internal provider name.

        Returns:
            Provider name (e.g., 'lxd', 'microk8s', 'k8s', 'google')
        """
        ...

    def bootstrap(self) -> bool:
        """Check if Juju should be bootstrapped on this provider.

        Returns:
            True if bootstrap is enabled
        """
        ...

    def cloud_name(self) -> str:
        """Get the provider name as Juju sees it.

        Returns:
            Juju cloud name (e.g., 'localhost', 'microk8s', 'google')
        """
        ...

    def group_name(self) -> str:
        """Get the POSIX group name for provider access.

        Returns:
            Group name (e.g., 'lxd', 'microk8s') or empty string
        """
        ...

    def credentials(self) -> dict[str, Any]:
        """Get Juju credentials for this provider.

        Returns:
            Credentials dict or empty dict if no credentials needed
        """
        ...

    def model_defaults(self) -> dict[str, str]:
        """Get Juju model-defaults specific to this provider.

        Returns:
            Model defaults dict
        """
        ...

    def bootstrap_constraints(self) -> dict[str, str]:
        """Get Juju bootstrap-constraints specific to this provider.

        Returns:
            Bootstrap constraints dict
        """
        ...
