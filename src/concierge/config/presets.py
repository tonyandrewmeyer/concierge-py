"""Built-in configuration presets for Concierge."""

from importlib import resources

import yaml

from concierge.config.models import ConciergeConfig


def _load_all_presets() -> dict[str, ConciergeConfig]:
    """Load all presets from the bundled YAML files."""
    presets: dict[str, ConciergeConfig] = {}
    preset_files = resources.files("concierge.presets")
    for item in preset_files.iterdir():
        if item.name.endswith(".yaml"):
            name = item.name.removesuffix(".yaml")
            data = yaml.safe_load(item.read_text())
            presets[name] = ConciergeConfig.model_validate(data)
    return presets


PRESETS: dict[str, ConciergeConfig] = _load_all_presets()


def get_available_presets() -> list[str]:
    """Get list of available preset names."""
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
