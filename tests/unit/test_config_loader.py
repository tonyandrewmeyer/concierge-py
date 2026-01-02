"""Unit tests for configuration loader."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from concierge.config.loader import (
    _apply_overrides,
    _load_from_file,
    get_env_overrides,
    load_config,
)
from concierge.config.models import ConciergeConfig, ConfigOverrides, SnapConfig


class TestLoadFromFile:
    """Tests for _load_from_file function."""

    def test_load_valid_yaml_file(self, tmp_path: Path) -> None:
        """Test loading a valid YAML configuration file."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "juju": {"disable": True, "channel": "3.5/stable"},
            "providers": {"lxd": {"enable": True}},
            "host": {"packages": ["git"]},
        }
        config_file.write_text(yaml.dump(config_data))

        config = _load_from_file(config_file)
        assert isinstance(config, ConciergeConfig)
        assert config.juju.disable is True
        assert config.juju.channel == "3.5/stable"
        assert config.providers.lxd.enable is True
        assert config.host.packages == ["git"]

    def test_load_file_not_found(self, tmp_path: Path) -> None:
        """Test that FileNotFoundError is raised for non-existent file."""
        non_existent = tmp_path / "does-not-exist.yaml"
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            _load_from_file(non_existent)

    def test_load_invalid_yaml(self, tmp_path: Path) -> None:
        """Test that ValueError is raised for invalid YAML."""
        config_file = tmp_path / "invalid.yaml"
        config_file.write_text("invalid: yaml: content: [[[")

        with pytest.raises(ValueError, match="Invalid YAML"):
            _load_from_file(config_file)

    def test_load_non_dict_yaml(self, tmp_path: Path) -> None:
        """Test that ValueError is raised when YAML is not a mapping."""
        config_file = tmp_path / "list.yaml"
        config_file.write_text("- item1\n- item2")

        with pytest.raises(ValueError, match="must contain a YAML mapping"):
            _load_from_file(config_file)

    def test_load_empty_file(self, tmp_path: Path) -> None:
        """Test loading an empty YAML file (treated as empty config)."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        # Empty files are now treated as empty configs with defaults
        config = _load_from_file(config_file)
        assert config is not None
        assert isinstance(config, ConciergeConfig)

    def test_load_minimal_config(self, tmp_path: Path) -> None:
        """Test loading a minimal valid configuration."""
        config_file = tmp_path / "minimal.yaml"
        config_file.write_text("{}")

        config = _load_from_file(config_file)
        assert isinstance(config, ConciergeConfig)
        # Should have all defaults
        assert config.juju.disable is False
        assert config.providers.lxd.enable is False


class TestApplyOverrides:
    """Tests for _apply_overrides function."""

    def test_disable_juju_override(self) -> None:
        """Test that disable_juju override works."""
        config = ConciergeConfig()
        overrides = ConfigOverrides(disable_juju=True)
        _apply_overrides(config, overrides)
        assert config.juju.disable is True

    def test_juju_channel_override(self) -> None:
        """Test that juju_channel override works."""
        config = ConciergeConfig()
        overrides = ConfigOverrides(juju_channel="3.5/stable")
        _apply_overrides(config, overrides)
        assert config.juju.channel == "3.5/stable"

    def test_lxd_channel_override(self) -> None:
        """Test that lxd_channel override works."""
        config = ConciergeConfig()
        overrides = ConfigOverrides(lxd_channel="latest/edge")
        _apply_overrides(config, overrides)
        assert config.providers.lxd.channel == "latest/edge"

    def test_microk8s_channel_override(self) -> None:
        """Test that microk8s_channel override works."""
        config = ConciergeConfig()
        overrides = ConfigOverrides(microk8s_channel="1.28/stable")
        _apply_overrides(config, overrides)
        assert config.providers.microk8s.channel == "1.28/stable"

    def test_k8s_channel_override(self) -> None:
        """Test that k8s_channel override works."""
        config = ConciergeConfig()
        overrides = ConfigOverrides(k8s_channel="1.29/stable")
        _apply_overrides(config, overrides)
        assert config.providers.k8s.channel == "1.29/stable"

    def test_google_credential_file_override(self) -> None:
        """Test that google_credential_file override works."""
        config = ConciergeConfig()
        overrides = ConfigOverrides(google_credential_file="/path/to/creds.json")
        _apply_overrides(config, overrides)
        assert config.providers.google.credentials_file == "/path/to/creds.json"

    def test_charmcraft_channel_override_new_snap(self) -> None:
        """Test that charmcraft_channel creates snap if not present."""
        config = ConciergeConfig()
        overrides = ConfigOverrides(charmcraft_channel="latest/edge")
        _apply_overrides(config, overrides)
        assert "charmcraft" in config.host.snaps
        assert config.host.snaps["charmcraft"].channel == "latest/edge"

    def test_charmcraft_channel_override_existing_snap(self) -> None:
        """Test that charmcraft_channel updates existing snap."""
        config = ConciergeConfig(
            host={"snaps": {"charmcraft": SnapConfig(channel="latest/stable")}}
        )
        overrides = ConfigOverrides(charmcraft_channel="latest/edge")
        _apply_overrides(config, overrides)
        assert config.host.snaps["charmcraft"].channel == "latest/edge"

    def test_snapcraft_channel_override(self) -> None:
        """Test that snapcraft_channel override works."""
        config = ConciergeConfig()
        overrides = ConfigOverrides(snapcraft_channel="latest/edge")
        _apply_overrides(config, overrides)
        assert "snapcraft" in config.host.snaps
        assert config.host.snaps["snapcraft"].channel == "latest/edge"

    def test_rockcraft_channel_override(self) -> None:
        """Test that rockcraft_channel override works."""
        config = ConciergeConfig()
        overrides = ConfigOverrides(rockcraft_channel="latest/edge")
        _apply_overrides(config, overrides)
        assert "rockcraft" in config.host.snaps
        assert config.host.snaps["rockcraft"].channel == "latest/edge"

    def test_extra_snaps_override(self) -> None:
        """Test that extra_snaps override adds new snaps."""
        config = ConciergeConfig()
        overrides = ConfigOverrides(extra_snaps=["snap1", "snap2"])
        _apply_overrides(config, overrides)
        assert "snap1" in config.host.snaps
        assert "snap2" in config.host.snaps

    def test_extra_snaps_does_not_override_existing(self) -> None:
        """Test that extra_snaps doesn't override existing snaps."""
        config = ConciergeConfig(host={"snaps": {"snap1": SnapConfig(channel="latest/stable")}})
        overrides = ConfigOverrides(extra_snaps=["snap1", "snap2"])
        _apply_overrides(config, overrides)
        # snap1 should keep its original channel
        assert config.host.snaps["snap1"].channel == "latest/stable"
        # snap2 should be added
        assert "snap2" in config.host.snaps

    def test_extra_debs_override(self) -> None:
        """Test that extra_debs override adds new packages."""
        config = ConciergeConfig()
        overrides = ConfigOverrides(extra_debs=["pkg1", "pkg2"])
        _apply_overrides(config, overrides)
        assert "pkg1" in config.host.packages
        assert "pkg2" in config.host.packages

    def test_extra_debs_does_not_add_duplicates(self) -> None:
        """Test that extra_debs doesn't add duplicate packages."""
        config = ConciergeConfig(host={"packages": ["pkg1"]})
        overrides = ConfigOverrides(extra_debs=["pkg1", "pkg2"])
        _apply_overrides(config, overrides)
        # pkg1 should appear only once
        assert config.host.packages.count("pkg1") == 1
        assert "pkg2" in config.host.packages

    def test_multiple_overrides_applied(self) -> None:
        """Test that multiple overrides are applied together."""
        config = ConciergeConfig()
        overrides = ConfigOverrides(
            disable_juju=True,
            juju_channel="3.5/stable",
            lxd_channel="latest/edge",
            extra_snaps=["mysnap"],
            extra_debs=["mypkg"],
        )
        _apply_overrides(config, overrides)
        assert config.juju.disable is True
        assert config.juju.channel == "3.5/stable"
        assert config.providers.lxd.channel == "latest/edge"
        assert "mysnap" in config.host.snaps
        assert "mypkg" in config.host.packages

    def test_empty_overrides_does_nothing(self) -> None:
        """Test that empty overrides don't modify config."""
        config = ConciergeConfig(juju={"channel": "3.5/stable"}, host={"packages": ["git"]})
        original_juju_channel = config.juju.channel
        original_packages = config.host.packages.copy()

        overrides = ConfigOverrides()
        _apply_overrides(config, overrides)

        assert config.juju.channel == original_juju_channel
        assert config.host.packages == original_packages


class TestGetEnvOverrides:
    """Tests for get_env_overrides function."""

    def test_no_env_vars(self) -> None:
        """Test that get_env_overrides returns defaults when no env vars set."""
        with patch.dict(os.environ, {}, clear=True):
            overrides = get_env_overrides()
            assert overrides.disable_juju is False
            assert overrides.juju_channel == ""
            assert overrides.extra_snaps == []
            assert overrides.extra_debs == []

    def test_disable_juju_true_variants(self) -> None:
        """Test that various truthy values work for disable_juju."""
        for value in ["1", "true", "True", "TRUE", "yes", "Yes", "YES"]:
            with patch.dict(os.environ, {"CONCIERGE_DISABLE_JUJU": value}, clear=True):
                overrides = get_env_overrides()
                assert overrides.disable_juju is True, f"Failed for value: {value}"

    def test_disable_juju_false_variants(self) -> None:
        """Test that non-truthy values result in disable_juju being False."""
        for value in ["0", "false", "False", "no", "No", ""]:
            with patch.dict(os.environ, {"CONCIERGE_DISABLE_JUJU": value}, clear=True):
                overrides = get_env_overrides()
                assert overrides.disable_juju is False, f"Failed for value: {value}"

    def test_string_env_vars(self) -> None:
        """Test that string environment variables are read correctly."""
        env_vars = {
            "CONCIERGE_JUJU_CHANNEL": "3.5/stable",
            "CONCIERGE_K8S_CHANNEL": "1.28/stable",
            "CONCIERGE_MICROK8S_CHANNEL": "1.27/stable",
            "CONCIERGE_LXD_CHANNEL": "latest/edge",
            "CONCIERGE_CHARMCRAFT_CHANNEL": "latest/edge",
            "CONCIERGE_SNAPCRAFT_CHANNEL": "latest/edge",
            "CONCIERGE_ROCKCRAFT_CHANNEL": "latest/edge",
            "CONCIERGE_GOOGLE_CREDENTIAL_FILE": "/path/to/creds.json",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            overrides = get_env_overrides()
            assert overrides.juju_channel == "3.5/stable"
            assert overrides.k8s_channel == "1.28/stable"
            assert overrides.microk8s_channel == "1.27/stable"
            assert overrides.lxd_channel == "latest/edge"
            assert overrides.charmcraft_channel == "latest/edge"
            assert overrides.snapcraft_channel == "latest/edge"
            assert overrides.rockcraft_channel == "latest/edge"
            assert overrides.google_credential_file == "/path/to/creds.json"

    def test_list_env_vars_single_item(self) -> None:
        """Test parsing list environment variables with single item."""
        with patch.dict(
            os.environ, {"CONCIERGE_EXTRA_SNAPS": "snap1", "CONCIERGE_EXTRA_DEBS": "pkg1"}
        ):
            overrides = get_env_overrides()
            assert overrides.extra_snaps == ["snap1"]
            assert overrides.extra_debs == ["pkg1"]

    def test_list_env_vars_multiple_items(self) -> None:
        """Test parsing list environment variables with multiple items."""
        with patch.dict(
            os.environ,
            {"CONCIERGE_EXTRA_SNAPS": "snap1,snap2,snap3", "CONCIERGE_EXTRA_DEBS": "pkg1,pkg2"},
        ):
            overrides = get_env_overrides()
            assert overrides.extra_snaps == ["snap1", "snap2", "snap3"]
            assert overrides.extra_debs == ["pkg1", "pkg2"]

    def test_list_env_vars_with_whitespace(self) -> None:
        """Test that whitespace is stripped from list items."""
        with patch.dict(
            os.environ,
            {
                "CONCIERGE_EXTRA_SNAPS": "snap1 , snap2 , snap3",
                "CONCIERGE_EXTRA_DEBS": " pkg1, pkg2 ",
            },
        ):
            overrides = get_env_overrides()
            assert overrides.extra_snaps == ["snap1", "snap2", "snap3"]
            assert overrides.extra_debs == ["pkg1", "pkg2"]

    def test_list_env_vars_empty_string(self) -> None:
        """Test that empty string results in empty list."""
        with patch.dict(os.environ, {"CONCIERGE_EXTRA_SNAPS": "", "CONCIERGE_EXTRA_DEBS": ""}):
            overrides = get_env_overrides()
            assert overrides.extra_snaps == []
            assert overrides.extra_debs == []

    def test_list_env_vars_only_commas(self) -> None:
        """Test that string with only commas/whitespace results in empty list."""
        with patch.dict(os.environ, {"CONCIERGE_EXTRA_SNAPS": " , , , "}):
            overrides = get_env_overrides()
            assert overrides.extra_snaps == []


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_from_preset(self) -> None:
        """Test loading configuration from a preset."""
        config = load_config(preset="dev")
        assert isinstance(config, ConciergeConfig)
        assert config.providers.lxd.enable is True
        assert config.providers.k8s.enable is True

    def test_load_from_file(self, tmp_path: Path) -> None:
        """Test loading configuration from a file."""
        config_file = tmp_path / "config.yaml"
        config_data = {"juju": {"disable": True}, "host": {"packages": ["git"]}}
        config_file.write_text(yaml.dump(config_data))

        config = load_config(config_file=str(config_file))
        assert config.juju.disable is True
        assert config.host.packages == ["git"]

    def test_load_from_default_location(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test loading configuration from default concierge.yaml location."""
        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / "concierge.yaml"
        config_data = {"juju": {"channel": "3.5/stable"}}
        config_file.write_text(yaml.dump(config_data))

        config = load_config()
        assert config.juju.channel == "3.5/stable"

    def test_load_uses_dev_preset_when_no_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that dev preset is used when no config file exists."""
        monkeypatch.chdir(tmp_path)
        config = load_config()
        # Should be dev preset
        assert config.providers.lxd.enable is True
        assert config.providers.k8s.enable is True

    def test_load_with_overrides(self) -> None:
        """Test that overrides are applied to loaded config."""
        overrides = ConfigOverrides(disable_juju=True, juju_channel="3.5/stable")
        config = load_config(preset="dev", overrides=overrides)
        assert config.juju.disable is True
        assert config.juju.channel == "3.5/stable"
        assert config.overrides == overrides

    def test_preset_takes_precedence_over_default_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that explicit preset takes precedence over default file."""
        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / "concierge.yaml"
        config_data = {"juju": {"disable": True}}
        config_file.write_text(yaml.dump(config_data))

        # Load with explicit preset
        config = load_config(preset="machine")
        # Should use preset, not file
        assert config.juju.disable is False  # preset default
        assert config.providers.lxd.enable is True  # machine preset

    def test_explicit_file_takes_precedence_over_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that explicit config file takes precedence over default location."""
        monkeypatch.chdir(tmp_path)

        # Create default config
        default_file = tmp_path / "concierge.yaml"
        default_file.write_text(yaml.dump({"juju": {"disable": True}}))

        # Create explicit config
        explicit_file = tmp_path / "custom.yaml"
        explicit_file.write_text(yaml.dump({"juju": {"disable": False, "channel": "custom"}}))

        config = load_config(config_file=str(explicit_file))
        # Should use explicit file
        assert config.juju.disable is False
        assert config.juju.channel == "custom"

    def test_load_invalid_preset(self) -> None:
        """Test that ValueError is raised for invalid preset."""
        with pytest.raises(ValueError, match="Unknown preset"):
            load_config(preset="invalid-preset")

    def test_overrides_stored_in_config(self) -> None:
        """Test that overrides are stored in the returned config."""
        overrides = ConfigOverrides(juju_channel="3.5/stable")
        config = load_config(preset="dev", overrides=overrides)
        assert config.overrides.juju_channel == "3.5/stable"
