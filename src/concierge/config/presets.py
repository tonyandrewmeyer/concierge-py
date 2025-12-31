"""Built-in configuration presets for Concierge."""

from concierge.config.models import (
    ConciergeConfig,
    HostConfig,
    JujuConfig,
    K8sConfig,
    LXDConfig,
    MicroK8sConfig,
    ProviderConfig,
    SnapConfig,
)


def _merge_dicts[T](base: dict[str, T], override: dict[str, T]) -> dict[str, T]:
    """Merge two dictionaries, with override taking precedence."""
    result = base.copy()
    result.update(override)
    return result


# Default configurations used across presets
DEFAULT_JUJU_CONFIG = JujuConfig.model_validate(
    {
        "disable": False,
        "model-defaults": {
            "test-mode": "true",
            "automatically-retry-hooks": "false",
        },
    }
)

DEFAULT_PACKAGES = [
    "python3-pip",
    "python3-venv",
]

DEFAULT_SNAPS = {
    "charmcraft": SnapConfig(channel="latest/stable"),
    "jq": SnapConfig(channel="latest/stable"),
    "yq": SnapConfig(channel="latest/stable"),
}

DEFAULT_LXD_CONFIG = LXDConfig(
    enable=True,
    bootstrap=True,
)

DEFAULT_MICROK8S_CONFIG = MicroK8sConfig(
    enable=True,
    bootstrap=True,
    addons=[
        "hostpath-storage",
        "dns",
        "rbac",
        "metallb:10.64.140.43-10.64.140.49",
    ],
)

DEFAULT_K8S_CONFIG = K8sConfig.model_validate(
    {
        "enable": True,
        "bootstrap": True,
        "bootstrap-constraints": {"root-disk": "2G"},
        "features": {
            "load-balancer": {
                "l2-mode": "true",
                "cidrs": "10.43.45.0/28",
            },
            "local-storage": {},
            "network": {},
        },
    }
)


def _machine_preset() -> ConciergeConfig:
    """Configuration preset for testing machine charms."""
    return ConciergeConfig(
        juju=DEFAULT_JUJU_CONFIG.model_copy(deep=True),
        providers=ProviderConfig(
            lxd=DEFAULT_LXD_CONFIG.model_copy(deep=True),
        ),
        host=HostConfig(
            packages=DEFAULT_PACKAGES.copy(),
            snaps=_merge_dicts(
                DEFAULT_SNAPS,
                {
                    "snapcraft": SnapConfig(channel="latest/stable"),
                },
            ),
        ),
    )


def _k8s_preset() -> ConciergeConfig:
    """Configuration preset for testing k8s charms."""
    return ConciergeConfig(
        juju=DEFAULT_JUJU_CONFIG.model_copy(deep=True),
        providers=ProviderConfig(
            lxd=LXDConfig(enable=True),  # Enable for building, no bootstrap
            k8s=DEFAULT_K8S_CONFIG.model_copy(deep=True),
        ),
        host=HostConfig(
            packages=DEFAULT_PACKAGES.copy(),
            snaps=_merge_dicts(
                DEFAULT_SNAPS,
                {
                    "rockcraft": SnapConfig(channel="latest/stable"),
                },
            ),
        ),
    )


def _microk8s_preset() -> ConciergeConfig:
    """Configuration preset for testing k8s charms with MicroK8s."""
    return ConciergeConfig(
        juju=DEFAULT_JUJU_CONFIG.model_copy(deep=True),
        providers=ProviderConfig(
            lxd=LXDConfig(enable=True),  # Enable for building, no bootstrap
            microk8s=DEFAULT_MICROK8S_CONFIG.model_copy(deep=True),
        ),
        host=HostConfig(
            packages=DEFAULT_PACKAGES.copy(),
            snaps=_merge_dicts(
                DEFAULT_SNAPS,
                {
                    "rockcraft": SnapConfig(channel="latest/stable"),
                },
            ),
        ),
    )


def _dev_preset() -> ConciergeConfig:
    """Full development preset combining LXD and K8s."""
    return ConciergeConfig(
        juju=DEFAULT_JUJU_CONFIG.model_copy(deep=True),
        providers=ProviderConfig(
            lxd=DEFAULT_LXD_CONFIG.model_copy(deep=True),
            k8s=DEFAULT_K8S_CONFIG.model_copy(deep=True),
        ),
        host=HostConfig(
            packages=DEFAULT_PACKAGES.copy(),
            snaps=_merge_dicts(
                DEFAULT_SNAPS,
                {
                    "rockcraft": SnapConfig(channel="latest/stable"),
                    "snapcraft": SnapConfig(channel="latest/stable"),
                    "jhack": SnapConfig(
                        channel="latest/stable",
                        connections=["jhack:dot-local-share-juju"],
                    ),
                },
            ),
        ),
    )


def _crafts_preset() -> ConciergeConfig:
    """Preset for building artifacts only, with Juju disabled."""
    return ConciergeConfig(
        juju=JujuConfig(disable=True),
        providers=ProviderConfig(
            lxd=DEFAULT_LXD_CONFIG.model_copy(deep=True),
        ),
        host=HostConfig(
            packages=DEFAULT_PACKAGES.copy(),
            snaps=_merge_dicts(
                DEFAULT_SNAPS,
                {
                    "rockcraft": SnapConfig(channel="latest/stable"),
                    "snapcraft": SnapConfig(channel="latest/stable"),
                },
            ),
        ),
    )


PRESETS: dict[str, ConciergeConfig] = {
    "machine": _machine_preset(),
    "k8s": _k8s_preset(),
    "microk8s": _microk8s_preset(),
    "dev": _dev_preset(),
    "crafts": _crafts_preset(),
}


def get_available_presets() -> list[str]:
    """Get list of available preset names.

    Returns:
        List of preset names
    """
    return list(PRESETS.keys())


def get_preset(name: str) -> ConciergeConfig:
    """Get a configuration preset by name.

    Args:
        name: Preset name (machine, k8s, microk8s, dev, crafts)

    Returns:
        Deep copy of the preset configuration

    Raises:
        ValueError: If preset name is not recognized
    """
    if name not in PRESETS:
        raise ValueError(f"Unknown preset '{name}'. Available presets: {', '.join(PRESETS.keys())}")
    return PRESETS[name].model_copy(deep=True)
