"""Configuration loading and parsing for Concierge."""

import os
from pathlib import Path

import yaml

from concierge.config.models import ConciergeConfig, ConfigOverrides, SnapConfig
from concierge.config.presets import get_preset
from concierge.core.logging import get_logger
from concierge.system.models import Snap

logger = get_logger(__name__)


def load_config(
    config_file: str = "",
    preset: str = "",
    overrides: ConfigOverrides | None = None,
) -> ConciergeConfig:
    """Load configuration from file, preset, or defaults.

    Args:
        config_file: Path to YAML configuration file (optional)
        preset: Name of preset to use (optional)
        overrides: Configuration overrides from CLI/env (optional)

    Returns:
        Loaded and validated configuration

    Raises:
        ValueError: If configuration is invalid
        FileNotFoundError: If specified config file doesn't exist
    """
    config: ConciergeConfig

    # Load from preset if specified
    if preset:
        logger.info("Loading preset", preset=preset)
        config = get_preset(preset)
    # Load from explicit config file if specified
    elif config_file:
        config = _load_from_file(Path(config_file))
    # Try to find config file in default location
    else:
        default_path = Path("concierge.yaml")
        if default_path.exists():
            config = _load_from_file(default_path)
        else:
            logger.info("No config file found, using 'dev' preset")
            config = get_preset("dev")

    # Apply overrides if provided
    if overrides:
        config.overrides = overrides
        _apply_overrides(config, overrides)

    return config


def _load_from_file(path: Path) -> ConciergeConfig:
    """Load configuration from a YAML file.

    Args:
        path: Path to configuration file

    Returns:
        Parsed configuration

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file is invalid YAML or doesn't match schema
    """
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    logger.info("Loading configuration file", path=str(path))

    try:
        with path.open("r") as f:
            data = yaml.safe_load(f)

        # Treat empty files as empty configuration
        if data is None:
            data = {}

        if not isinstance(data, dict):
            raise ValueError("Configuration file must contain a YAML mapping")

        return ConciergeConfig.model_validate(data)

    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in configuration file: {e}") from e
    except Exception as e:
        raise ValueError(f"Failed to parse configuration: {e}") from e


def _apply_overrides(config: ConciergeConfig, overrides: ConfigOverrides) -> None:
    """Apply configuration overrides to a config object.

    Modifies the config object in-place based on override values.

    Args:
        config: Configuration to modify
        overrides: Override values to apply
    """
    # Juju overrides
    if overrides.disable_juju:
        config.juju.disable = True
    if overrides.juju_channel:
        config.juju.channel = overrides.juju_channel

    # Provider channel overrides
    if overrides.lxd_channel:
        config.providers.lxd.channel = overrides.lxd_channel
    if overrides.microk8s_channel:
        config.providers.microk8s.channel = overrides.microk8s_channel
    if overrides.k8s_channel:
        config.providers.k8s.channel = overrides.k8s_channel

    # Google credentials override
    if overrides.google_credential_file:
        config.providers.google.credentials_file = overrides.google_credential_file

    # Snap channel overrides
    if overrides.charmcraft_channel:
        if "charmcraft" not in config.host.snaps:
            config.host.snaps["charmcraft"] = SnapConfig()
        config.host.snaps["charmcraft"].channel = overrides.charmcraft_channel

    if overrides.snapcraft_channel:
        if "snapcraft" not in config.host.snaps:
            config.host.snaps["snapcraft"] = SnapConfig()
        config.host.snaps["snapcraft"].channel = overrides.snapcraft_channel

    if overrides.rockcraft_channel:
        if "rockcraft" not in config.host.snaps:
            config.host.snaps["rockcraft"] = SnapConfig()
        config.host.snaps["rockcraft"].channel = overrides.rockcraft_channel

    # Extra snaps
    if overrides.extra_snaps:
        for snap_str in overrides.extra_snaps:
            # Parse snap specification (e.g., "jq/latest/edge" -> name="jq", channel="latest/edge")
            snap = Snap.from_string(snap_str)
            if snap.name not in config.host.snaps:
                config.host.snaps[snap.name] = SnapConfig(channel=snap.channel)
            elif snap.channel:
                # Update channel if specified (overrides preset/config channel)
                config.host.snaps[snap.name].channel = snap.channel

    # Extra debs
    if overrides.extra_debs:
        for deb_name in overrides.extra_debs:
            if deb_name not in config.host.packages:
                config.host.packages.append(deb_name)


def get_env_overrides() -> ConfigOverrides:
    """Get configuration overrides from environment variables.

    Environment variables are prefixed with CONCIERGE_ and use underscores
    instead of hyphens (e.g., CONCIERGE_JUJU_CHANNEL).

    Returns:
        ConfigOverrides populated from environment variables
    """

    def get_bool(key: str) -> bool:
        val = os.getenv(f"CONCIERGE_{key.upper()}")
        return val is not None and val.lower() in ("1", "true", "yes")

    def get_str(key: str) -> str:
        return os.getenv(f"CONCIERGE_{key.upper()}", "")

    def get_list(key: str) -> list[str]:
        val = os.getenv(f"CONCIERGE_{key.upper()}", "")
        return [item.strip() for item in val.split(",") if item.strip()]

    return ConfigOverrides(
        disable_juju=get_bool("disable_juju"),
        juju_channel=get_str("juju_channel"),
        k8s_channel=get_str("k8s_channel"),
        microk8s_channel=get_str("microk8s_channel"),
        lxd_channel=get_str("lxd_channel"),
        charmcraft_channel=get_str("charmcraft_channel"),
        snapcraft_channel=get_str("snapcraft_channel"),
        rockcraft_channel=get_str("rockcraft_channel"),
        google_credential_file=get_str("google_credential_file"),
        extra_snaps=get_list("extra_snaps"),
        extra_debs=get_list("extra_debs"),
    )
