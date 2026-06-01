"""Unit tests for configuration presets."""

import pytest

from concierge.config.models import ConciergeConfig
from concierge.config.presets import PRESETS, get_available_presets, get_preset


class TestGetAvailablePresets:
    """Tests for get_available_presets function."""

    def test_returns_list_of_strings(self) -> None:
        presets = get_available_presets()
        assert isinstance(presets, list)
        assert all(isinstance(p, str) for p in presets)

    def test_contains_expected_presets(self) -> None:
        presets = get_available_presets()
        assert "machine" in presets
        assert "k8s" in presets
        assert "microk8s" in presets
        assert "dev" in presets
        assert "crafts" in presets

    def test_matches_presets_dict(self) -> None:
        presets = get_available_presets()
        assert set(presets) == set(PRESETS.keys())


class TestGetPreset:
    """Tests for get_preset function."""

    def test_get_machine_preset(self) -> None:
        config = get_preset("machine")
        assert isinstance(config, ConciergeConfig)
        assert config.providers.lxd.enable is True
        assert config.providers.lxd.bootstrap is True
        assert "snapcraft" in config.host.snaps
        assert "charmcraft" in config.host.snaps
        assert config.juju.disable is False

    def test_get_k8s_preset(self) -> None:
        config = get_preset("k8s")
        assert isinstance(config, ConciergeConfig)
        assert config.providers.lxd.enable is True
        assert config.providers.lxd.bootstrap is False
        assert config.providers.k8s.enable is True
        assert config.providers.k8s.bootstrap is True
        assert "rockcraft" in config.host.snaps
        assert "charmcraft" in config.host.snaps

    def test_get_microk8s_preset(self) -> None:
        config = get_preset("microk8s")
        assert isinstance(config, ConciergeConfig)
        assert config.providers.lxd.enable is True
        assert config.providers.lxd.bootstrap is False
        assert config.providers.microk8s.enable is True
        assert config.providers.microk8s.bootstrap is True
        assert "rockcraft" in config.host.snaps
        assert "charmcraft" in config.host.snaps

    def test_get_dev_preset(self) -> None:
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
        config = get_preset("crafts")
        assert isinstance(config, ConciergeConfig)
        assert config.juju.disable is True
        assert config.providers.lxd.enable is True
        assert config.providers.lxd.bootstrap is True
        assert "rockcraft" in config.host.snaps
        assert "snapcraft" in config.host.snaps
        assert "charmcraft" in config.host.snaps

    def test_get_preset_returns_deep_copy(self) -> None:
        config1 = get_preset("dev")
        config2 = get_preset("dev")
        config1.juju.channel = "modified"
        config1.host.packages.append("new-package")
        assert config2.juju.channel == ""
        assert "new-package" not in config2.host.packages

    def test_get_preset_invalid_name(self) -> None:
        with pytest.raises(ValueError, match="Unknown preset 'invalid'"):
            get_preset("invalid")

    def test_get_preset_error_message_includes_available(self) -> None:
        with pytest.raises(ValueError, match="Available presets:"):
            get_preset("nonexistent")


class TestPresetContents:
    """Tests for specific preset contents."""

    def test_all_presets_have_default_packages(self) -> None:
        for preset_name in get_available_presets():
            config = get_preset(preset_name)
            assert "python3-pip" in config.host.packages
            assert "python3-venv" in config.host.packages

    def test_all_presets_have_charmcraft(self) -> None:
        for preset_name in get_available_presets():
            config = get_preset(preset_name)
            assert "charmcraft" in config.host.snaps

    def test_machine_preset_has_snapcraft(self) -> None:
        config = get_preset("machine")
        assert "snapcraft" in config.host.snaps
        assert "rockcraft" not in config.host.snaps

    def test_k8s_presets_have_rockcraft(self) -> None:
        for preset_name in ["k8s", "microk8s"]:
            config = get_preset(preset_name)
            assert "rockcraft" in config.host.snaps

    def test_dev_preset_has_all_craft_tools(self) -> None:
        config = get_preset("dev")
        assert "charmcraft" in config.host.snaps
        assert "snapcraft" in config.host.snaps
        assert "rockcraft" in config.host.snaps
        assert "jhack" in config.host.snaps
        assert "astral-uv" in config.host.snaps

    def test_crafts_preset_juju_disabled(self) -> None:
        config = get_preset("crafts")
        assert config.juju.disable is True

    def test_non_crafts_presets_juju_enabled(self) -> None:
        for preset_name in ["machine", "k8s", "microk8s", "dev"]:
            config = get_preset(preset_name)
            assert config.juju.disable is False

    def test_snaps_have_no_explicit_channel(self) -> None:
        """Snaps in presets rely on snapd's default channel behaviour."""
        for preset_name in get_available_presets():
            config = get_preset(preset_name)
            for snap_name, snap_config in config.host.snaps.items():
                assert snap_config.channel == "", (
                    f"Snap '{snap_name}' in preset '{preset_name}' has explicit channel "
                    f"'{snap_config.channel}' - snapd should decide the default"
                )
