"""Unit tests for configuration presets."""

import pytest

from concierge.config.models import (
    ConciergeConfig,
    JujuConfig,
    K8sConfig,
    LXDConfig,
    MicroK8sConfig,
    SnapConfig,
)
from concierge.config.presets import (
    DEFAULT_JUJU_CONFIG,
    DEFAULT_K8S_CONFIG,
    DEFAULT_LXD_CONFIG,
    DEFAULT_MICROK8S_CONFIG,
    DEFAULT_PACKAGES,
    DEFAULT_SNAPS,
    PRESETS,
    _merge_dicts,
    get_available_presets,
    get_preset,
)


class TestMergeDicts:
    """Tests for _merge_dicts utility function."""

    def test_merge_empty_dicts(self) -> None:
        """Test merging two empty dictionaries."""
        result = _merge_dicts({}, {})
        assert result == {}

    def test_merge_with_empty_override(self) -> None:
        """Test merging when override is empty."""
        base = {"a": "1", "b": "2"}
        result = _merge_dicts(base, {})
        assert result == {"a": "1", "b": "2"}

    def test_merge_with_empty_base(self) -> None:
        """Test merging when base is empty."""
        override = {"a": "1", "b": "2"}
        result = _merge_dicts({}, override)
        assert result == {"a": "1", "b": "2"}

    def test_merge_non_overlapping(self) -> None:
        """Test merging dictionaries with no overlapping keys."""
        base = {"a": "1", "b": "2"}
        override = {"c": "3", "d": "4"}
        result = _merge_dicts(base, override)
        assert result == {"a": "1", "b": "2", "c": "3", "d": "4"}

    def test_merge_with_overrides(self) -> None:
        """Test that override values take precedence."""
        base = {"a": "1", "b": "2", "c": "3"}
        override = {"b": "overridden", "c": "also_overridden"}
        result = _merge_dicts(base, override)
        assert result == {"a": "1", "b": "overridden", "c": "also_overridden"}

    def test_merge_does_not_modify_originals(self) -> None:
        """Test that merging doesn't modify the original dicts."""
        base = {"a": "1"}
        override = {"b": "2"}
        result = _merge_dicts(base, override)
        assert base == {"a": "1"}
        assert override == {"b": "2"}
        assert result == {"a": "1", "b": "2"}


class TestDefaultConfigs:
    """Tests for default configuration constants."""

    def test_default_juju_config(self) -> None:
        """Test that DEFAULT_JUJU_CONFIG has expected values."""
        assert isinstance(DEFAULT_JUJU_CONFIG, JujuConfig)
        assert DEFAULT_JUJU_CONFIG.disable is False
        assert "test-mode" in DEFAULT_JUJU_CONFIG.model_defaults
        assert DEFAULT_JUJU_CONFIG.model_defaults["test-mode"] == "true"
        assert "automatically-retry-hooks" in DEFAULT_JUJU_CONFIG.model_defaults
        assert DEFAULT_JUJU_CONFIG.model_defaults["automatically-retry-hooks"] == "false"

    def test_default_packages(self) -> None:
        """Test that DEFAULT_PACKAGES contains expected packages."""
        assert isinstance(DEFAULT_PACKAGES, list)
        assert "python3-pip" in DEFAULT_PACKAGES
        assert "python3-venv" in DEFAULT_PACKAGES

    def test_default_snaps(self) -> None:
        """Test that DEFAULT_SNAPS contains expected snaps."""
        assert isinstance(DEFAULT_SNAPS, dict)
        assert "charmcraft" in DEFAULT_SNAPS
        assert "jq" in DEFAULT_SNAPS
        assert "yq" in DEFAULT_SNAPS
        assert all(isinstance(snap, SnapConfig) for snap in DEFAULT_SNAPS.values())

    def test_default_lxd_config(self) -> None:
        """Test that DEFAULT_LXD_CONFIG has expected values."""
        assert isinstance(DEFAULT_LXD_CONFIG, LXDConfig)
        assert DEFAULT_LXD_CONFIG.enable is True
        assert DEFAULT_LXD_CONFIG.bootstrap is True

    def test_default_microk8s_config(self) -> None:
        """Test that DEFAULT_MICROK8S_CONFIG has expected values."""
        assert isinstance(DEFAULT_MICROK8S_CONFIG, MicroK8sConfig)
        assert DEFAULT_MICROK8S_CONFIG.enable is True
        assert DEFAULT_MICROK8S_CONFIG.bootstrap is True
        assert "hostpath-storage" in DEFAULT_MICROK8S_CONFIG.addons
        assert "dns" in DEFAULT_MICROK8S_CONFIG.addons
        assert "rbac" in DEFAULT_MICROK8S_CONFIG.addons

    def test_default_k8s_config(self) -> None:
        """Test that DEFAULT_K8S_CONFIG has expected values."""
        assert isinstance(DEFAULT_K8S_CONFIG, K8sConfig)
        assert DEFAULT_K8S_CONFIG.enable is True
        assert DEFAULT_K8S_CONFIG.bootstrap is True
        assert DEFAULT_K8S_CONFIG.bootstrap_constraints == {"root-disk": "2G"}
        assert "load-balancer" in DEFAULT_K8S_CONFIG.features
        assert "local-storage" in DEFAULT_K8S_CONFIG.features
        assert "network" in DEFAULT_K8S_CONFIG.features


class TestGetAvailablePresets:
    """Tests for get_available_presets function."""

    def test_returns_list_of_strings(self) -> None:
        """Test that get_available_presets returns a list of strings."""
        presets = get_available_presets()
        assert isinstance(presets, list)
        assert all(isinstance(p, str) for p in presets)

    def test_contains_expected_presets(self) -> None:
        """Test that all expected presets are present."""
        presets = get_available_presets()
        assert "machine" in presets
        assert "k8s" in presets
        assert "microk8s" in presets
        assert "dev" in presets
        assert "crafts" in presets

    def test_matches_presets_dict(self) -> None:
        """Test that returned list matches PRESETS dict keys."""
        presets = get_available_presets()
        assert set(presets) == set(PRESETS.keys())


class TestGetPreset:
    """Tests for get_preset function."""

    def test_get_machine_preset(self) -> None:
        """Test retrieving machine preset."""
        config = get_preset("machine")
        assert isinstance(config, ConciergeConfig)
        assert config.providers.lxd.enable is True
        assert config.providers.lxd.bootstrap is True
        assert "snapcraft" in config.host.snaps
        assert "charmcraft" in config.host.snaps
        assert config.juju.disable is False

    def test_get_k8s_preset(self) -> None:
        """Test retrieving k8s preset."""
        config = get_preset("k8s")
        assert isinstance(config, ConciergeConfig)
        assert config.providers.lxd.enable is True
        assert config.providers.lxd.bootstrap is False  # LXD enabled but not bootstrapped
        assert config.providers.k8s.enable is True
        assert config.providers.k8s.bootstrap is True
        assert "rockcraft" in config.host.snaps
        assert "charmcraft" in config.host.snaps

    def test_get_microk8s_preset(self) -> None:
        """Test retrieving microk8s preset."""
        config = get_preset("microk8s")
        assert isinstance(config, ConciergeConfig)
        assert config.providers.lxd.enable is True
        assert config.providers.lxd.bootstrap is False  # LXD enabled but not bootstrapped
        assert config.providers.microk8s.enable is True
        assert config.providers.microk8s.bootstrap is True
        assert "rockcraft" in config.host.snaps
        assert "charmcraft" in config.host.snaps

    def test_get_dev_preset(self) -> None:
        """Test retrieving dev preset."""
        config = get_preset("dev")
        assert isinstance(config, ConciergeConfig)
        assert config.providers.lxd.enable is True
        assert config.providers.lxd.bootstrap is True
        assert config.providers.k8s.enable is True
        assert config.providers.k8s.bootstrap is True
        assert "rockcraft" in config.host.snaps
        assert "snapcraft" in config.host.snaps
        assert "jhack" in config.host.snaps
        assert "charmcraft" in config.host.snaps

    def test_get_crafts_preset(self) -> None:
        """Test retrieving crafts preset."""
        config = get_preset("crafts")
        assert isinstance(config, ConciergeConfig)
        assert config.juju.disable is True  # Juju disabled for crafts preset
        assert config.providers.lxd.enable is True
        assert config.providers.lxd.bootstrap is True
        assert "rockcraft" in config.host.snaps
        assert "snapcraft" in config.host.snaps
        assert "charmcraft" in config.host.snaps

    def test_get_preset_returns_deep_copy(self) -> None:
        """Test that get_preset returns a deep copy."""
        config1 = get_preset("dev")
        config2 = get_preset("dev")

        # Modify config1
        config1.juju.channel = "modified"
        config1.host.packages.append("new-package")

        # config2 should be unchanged
        assert config2.juju.channel == ""
        assert "new-package" not in config2.host.packages

    def test_get_preset_invalid_name(self) -> None:
        """Test that get_preset raises ValueError for invalid preset name."""
        with pytest.raises(ValueError, match="Unknown preset 'invalid'"):
            get_preset("invalid")

    def test_get_preset_error_message_includes_available(self) -> None:
        """Test that error message includes available presets."""
        with pytest.raises(ValueError, match="Available presets:"):
            get_preset("nonexistent")


class TestPresetContents:
    """Tests for specific preset contents."""

    def test_all_presets_have_default_packages(self) -> None:
        """Test that all presets include default packages."""
        for preset_name in get_available_presets():
            config = get_preset(preset_name)
            assert "python3-pip" in config.host.packages
            assert "python3-venv" in config.host.packages

    def test_all_presets_have_charmcraft(self) -> None:
        """Test that all presets include charmcraft."""
        for preset_name in get_available_presets():
            config = get_preset(preset_name)
            assert "charmcraft" in config.host.snaps

    def test_machine_preset_has_snapcraft(self) -> None:
        """Test that machine preset has snapcraft but not rockcraft."""
        config = get_preset("machine")
        assert "snapcraft" in config.host.snaps
        assert "rockcraft" not in config.host.snaps

    def test_k8s_presets_have_rockcraft(self) -> None:
        """Test that k8s and microk8s presets have rockcraft."""
        for preset_name in ["k8s", "microk8s"]:
            config = get_preset(preset_name)
            assert "rockcraft" in config.host.snaps

    def test_dev_preset_has_all_craft_tools(self) -> None:
        """Test that dev preset has all craft tools."""
        config = get_preset("dev")
        assert "charmcraft" in config.host.snaps
        assert "snapcraft" in config.host.snaps
        assert "rockcraft" in config.host.snaps
        assert "jhack" in config.host.snaps

    def test_crafts_preset_juju_disabled(self) -> None:
        """Test that crafts preset has Juju disabled."""
        config = get_preset("crafts")
        assert config.juju.disable is True

    def test_non_crafts_presets_juju_enabled(self) -> None:
        """Test that non-crafts presets have Juju enabled."""
        for preset_name in ["machine", "k8s", "microk8s", "dev"]:
            config = get_preset(preset_name)
            assert config.juju.disable is False
