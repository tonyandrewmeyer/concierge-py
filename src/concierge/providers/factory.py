"""Factory for creating provider instances."""

from concierge.config.models import ConciergeConfig
from concierge.providers.base import Provider
from concierge.providers.google import Google
from concierge.providers.k8s import K8s
from concierge.providers.lxd import LXD
from concierge.providers.microk8s import MicroK8s
from concierge.system.worker import Worker

SUPPORTED_PROVIDERS = ["lxd", "microk8s", "k8s", "google"]


def create_provider(
    provider_name: str,
    system: Worker,
    config: ConciergeConfig,
) -> Provider | None:
    """Create a provider instance by name.

    Args:
        provider_name: Name of the provider to create
        system: System worker
        config: Concierge configuration

    Returns:
        Provider instance or None if provider is not enabled
    """
    if provider_name == "lxd" and config.providers.lxd.enable:
        return LXD(system, config)
    if provider_name == "microk8s" and config.providers.microk8s.enable:
        return MicroK8s(system, config)
    if provider_name == "k8s" and config.providers.k8s.enable:
        return K8s(system, config)
    if provider_name == "google" and config.providers.google.enable:
        return Google(system, config)

    return None


def create_all_providers(
    system: Worker,
    config: ConciergeConfig,
) -> list[Provider]:
    """Create all enabled providers.

    Args:
        system: System worker
        config: Concierge configuration

    Returns:
        List of enabled provider instances
    """
    providers = []

    for provider_name in SUPPORTED_PROVIDERS:
        provider = create_provider(provider_name, system, config)
        if provider:
            providers.append(provider)

    return providers
