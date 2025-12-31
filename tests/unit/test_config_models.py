"""Unit tests for configuration models."""

from concierge.config.models import (
    ConciergeConfig,
    ConfigOverrides,
    GoogleConfig,
    HostConfig,
    JujuConfig,
    K8sConfig,
    LXDConfig,
    MicroK8sConfig,
    ProviderConfig,
    SnapConfig,
    Status,
)


class TestStatus:
    """Tests for Status enum."""

    def test_status_values(self) -> None:
        """Test that Status enum has expected values."""
        assert Status.PROVISIONING == "provisioning"
        assert Status.SUCCEEDED == "succeeded"
        assert Status.FAILED == "failed"

    def test_status_from_string(self) -> None:
        """Test creating Status from string value."""
        assert Status("provisioning") == Status.PROVISIONING
        assert Status("succeeded") == Status.SUCCEEDED
        assert Status("failed") == Status.FAILED


class TestConfigOverrides:
    """Tests for ConfigOverrides model."""

    def test_default_values(self) -> None:
        """Test that ConfigOverrides has correct defaults."""
        overrides = ConfigOverrides()
        assert overrides.disable_juju is False
        assert overrides.juju_channel == ""
        assert overrides.k8s_channel == ""
        assert overrides.microk8s_channel == ""
        assert overrides.lxd_channel == ""
        assert overrides.charmcraft_channel == ""
        assert overrides.snapcraft_channel == ""
        assert overrides.rockcraft_channel == ""
        assert overrides.google_credential_file == ""
        assert overrides.extra_snaps == []
        assert overrides.extra_debs == []

    def test_custom_values(self) -> None:
        """Test creating ConfigOverrides with custom values."""
        overrides = ConfigOverrides(
            disable_juju=True,
            juju_channel="3.5/stable",
            extra_snaps=["snap1", "snap2"],
            extra_debs=["deb1"],
        )
        assert overrides.disable_juju is True
        assert overrides.juju_channel == "3.5/stable"
        assert overrides.extra_snaps == ["snap1", "snap2"]
        assert overrides.extra_debs == ["deb1"]


class TestJujuConfig:
    """Tests for JujuConfig model."""

    def test_default_values(self) -> None:
        """Test that JujuConfig has correct defaults."""
        config = JujuConfig()
        assert config.disable is False
        assert config.channel == ""
        assert config.agent_version == ""
        assert config.model_defaults == {}
        assert config.bootstrap_constraints == {}
        assert config.extra_bootstrap_args == ""

    def test_alias_fields(self) -> None:
        """Test that aliased fields work correctly."""
        config = JujuConfig.model_validate(
            {
                "disable": True,
                "agent-version": "3.5.0",
                "model-defaults": {"test-mode": "true"},
                "bootstrap-constraints": {"mem": "4G"},
                "extra-bootstrap-args": "--debug",
            }
        )
        assert config.disable is True
        assert config.agent_version == "3.5.0"
        assert config.model_defaults == {"test-mode": "true"}
        assert config.bootstrap_constraints == {"mem": "4G"}
        assert config.extra_bootstrap_args == "--debug"

    def test_populate_by_name(self) -> None:
        """Test that populate_by_name allows both names."""
        # Using underscored name should also work
        config = JujuConfig(model_defaults={"test": "value"}, bootstrap_constraints={"cpu": "2"})
        assert config.model_defaults == {"test": "value"}
        assert config.bootstrap_constraints == {"cpu": "2"}


class TestLXDConfig:
    """Tests for LXDConfig model."""

    def test_default_values(self) -> None:
        """Test that LXDConfig has correct defaults."""
        config = LXDConfig()
        assert config.enable is False
        assert config.bootstrap is False
        assert config.channel == ""
        assert config.model_defaults == {}
        assert config.bootstrap_constraints == {}

    def test_custom_values(self) -> None:
        """Test creating LXDConfig with custom values."""
        config = LXDConfig(
            enable=True, bootstrap=True, channel="latest/stable", model_defaults={"key": "val"}
        )
        assert config.enable is True
        assert config.bootstrap is True
        assert config.channel == "latest/stable"
        assert config.model_defaults == {"key": "val"}


class TestGoogleConfig:
    """Tests for GoogleConfig model."""

    def test_default_values(self) -> None:
        """Test that GoogleConfig has correct defaults."""
        config = GoogleConfig()
        assert config.enable is False
        assert config.bootstrap is False
        assert config.credentials_file == ""
        assert config.model_defaults == {}
        assert config.bootstrap_constraints == {}

    def test_alias_credentials_file(self) -> None:
        """Test that credentials-file alias works."""
        config = GoogleConfig.model_validate(
            {"enable": True, "credentials-file": "/path/to/creds.json"}
        )
        assert config.enable is True
        assert config.credentials_file == "/path/to/creds.json"


class TestMicroK8sConfig:
    """Tests for MicroK8sConfig model."""

    def test_default_values(self) -> None:
        """Test that MicroK8sConfig has correct defaults."""
        config = MicroK8sConfig()
        assert config.enable is False
        assert config.bootstrap is False
        assert config.channel == ""
        assert config.addons == []
        assert config.model_defaults == {}
        assert config.bootstrap_constraints == {}

    def test_with_addons(self) -> None:
        """Test creating MicroK8sConfig with addons."""
        config = MicroK8sConfig(enable=True, bootstrap=True, addons=["dns", "storage", "rbac"])
        assert config.enable is True
        assert config.bootstrap is True
        assert config.addons == ["dns", "storage", "rbac"]


class TestK8sConfig:
    """Tests for K8sConfig model."""

    def test_default_values(self) -> None:
        """Test that K8sConfig has correct defaults."""
        config = K8sConfig()
        assert config.enable is False
        assert config.bootstrap is False
        assert config.channel == ""
        assert config.features == {}
        assert config.model_defaults == {}
        assert config.bootstrap_constraints == {}

    def test_with_features(self) -> None:
        """Test creating K8sConfig with features."""
        features = {"load-balancer": {"l2-mode": "true"}, "network": {}}
        config = K8sConfig(enable=True, bootstrap=True, features=features)
        assert config.enable is True
        assert config.bootstrap is True
        assert config.features == features


class TestProviderConfig:
    """Tests for ProviderConfig model."""

    def test_default_values(self) -> None:
        """Test that ProviderConfig initializes all providers with defaults."""
        config = ProviderConfig()
        assert isinstance(config.lxd, LXDConfig)
        assert isinstance(config.google, GoogleConfig)
        assert isinstance(config.microk8s, MicroK8sConfig)
        assert isinstance(config.k8s, K8sConfig)
        assert config.lxd.enable is False
        assert config.google.enable is False
        assert config.microk8s.enable is False
        assert config.k8s.enable is False

    def test_custom_providers(self) -> None:
        """Test creating ProviderConfig with custom provider configs."""
        config = ProviderConfig(
            lxd=LXDConfig(enable=True, bootstrap=True),
            k8s=K8sConfig(enable=True, channel="1.28/stable"),
        )
        assert config.lxd.enable is True
        assert config.lxd.bootstrap is True
        assert config.k8s.enable is True
        assert config.k8s.channel == "1.28/stable"
        assert config.google.enable is False  # Still has default


class TestSnapConfig:
    """Tests for SnapConfig model."""

    def test_default_values(self) -> None:
        """Test that SnapConfig has correct defaults."""
        config = SnapConfig()
        assert config.channel == ""
        assert config.connections == []

    def test_with_channel_and_connections(self) -> None:
        """Test creating SnapConfig with channel and connections."""
        config = SnapConfig(channel="latest/edge", connections=["snap:plug"])
        assert config.channel == "latest/edge"
        assert config.connections == ["snap:plug"]


class TestHostConfig:
    """Tests for HostConfig model."""

    def test_default_values(self) -> None:
        """Test that HostConfig has correct defaults."""
        config = HostConfig()
        assert config.packages == []
        assert config.snaps == {}

    def test_with_packages_and_snaps(self) -> None:
        """Test creating HostConfig with packages and snaps."""
        config = HostConfig(
            packages=["python3-pip", "git"],
            snaps={"charmcraft": SnapConfig(channel="latest/stable")},
        )
        assert config.packages == ["python3-pip", "git"]
        assert "charmcraft" in config.snaps
        assert config.snaps["charmcraft"].channel == "latest/stable"


class TestConciergeConfig:
    """Tests for ConciergeConfig model."""

    def test_default_values(self) -> None:
        """Test that ConciergeConfig has correct defaults."""
        config = ConciergeConfig()
        assert isinstance(config.juju, JujuConfig)
        assert isinstance(config.providers, ProviderConfig)
        assert isinstance(config.host, HostConfig)
        assert isinstance(config.overrides, ConfigOverrides)
        assert config.status == Status.PROVISIONING
        assert config.verbose is False
        assert config.trace is False

    def test_full_config(self) -> None:
        """Test creating a complete ConciergeConfig."""
        config = ConciergeConfig(
            juju=JujuConfig(disable=False, channel="3.5/stable"),
            providers=ProviderConfig(
                lxd=LXDConfig(enable=True, bootstrap=True),
                k8s=K8sConfig(enable=True, bootstrap=True),
            ),
            host=HostConfig(
                packages=["python3-pip"],
                snaps={"charmcraft": SnapConfig(channel="latest/stable")},
            ),
            status=Status.SUCCEEDED,
            verbose=True,
        )
        assert config.juju.channel == "3.5/stable"
        assert config.providers.lxd.enable is True
        assert config.providers.k8s.enable is True
        assert "charmcraft" in config.host.snaps
        assert config.status == Status.SUCCEEDED
        assert config.verbose is True

    def test_model_copy_deep(self) -> None:
        """Test that model_copy(deep=True) creates independent copies."""
        original = ConciergeConfig(
            juju=JujuConfig(model_defaults={"test": "value"}),
            host=HostConfig(packages=["pkg1"]),
        )
        copy = original.model_copy(deep=True)

        # Modify the copy
        copy.juju.model_defaults["test"] = "changed"
        copy.host.packages.append("pkg2")

        # Original should be unchanged
        assert original.juju.model_defaults["test"] == "value"
        assert original.host.packages == ["pkg1"]
        assert copy.juju.model_defaults["test"] == "changed"
        assert copy.host.packages == ["pkg1", "pkg2"]

    def test_validation_from_dict(self) -> None:
        """Test creating ConciergeConfig from dict via model_validate."""
        data = {
            "juju": {"disable": True, "channel": "3.5/stable"},
            "providers": {"lxd": {"enable": True}},
            "host": {"packages": ["git"]},
        }
        config = ConciergeConfig.model_validate(data)
        assert config.juju.disable is True
        assert config.juju.channel == "3.5/stable"
        assert config.providers.lxd.enable is True
        assert config.host.packages == ["git"]
