"""Juju credentials management."""

from typing import Any

from concierge.providers.base import Provider


def build_credentials_yaml(providers: list[Provider]) -> dict[str, Any]:
    """Build Juju credentials YAML from providers.

    Args:
        providers: List of providers to extract credentials from

    Returns:
        Credentials YAML structure
    """
    credentials_data: dict[str, Any] = {"credentials": {}}

    for provider in providers:
        provider_creds = provider.credentials()
        if not provider_creds:
            continue

        credentials_data["credentials"][provider.cloud_name()] = {"concierge": provider_creds}

    return credentials_data
