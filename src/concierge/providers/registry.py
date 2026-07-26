"""Shared image registry configuration for containerd-based providers."""

import base64
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from concierge.config.models import ImageRegistryConfig


def build_hosts_toml(registry: ImageRegistryConfig) -> str:
    """Build containerd hosts.toml configuration for a registry mirror."""
    lines = [
        f'server = "{registry.url}"',
        "",
        f'[host."{registry.url}"]',
        '  capabilities = ["pull", "resolve"]',
    ]
    if registry.username:
        lines.append(f'  [host."{registry.url}".header]')
        credentials = base64.b64encode(
            f"{registry.username}:{registry.password}".encode()
        ).decode()
        lines.append(f'    Authorization = ["Basic {credentials}"]')
    return "\n".join(lines) + "\n"
