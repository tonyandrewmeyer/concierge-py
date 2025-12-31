"""Unit tests for provider factory."""

from unittest.mock import Mock

from concierge.config.models import (
    ConciergeConfig,
    GoogleConfig,
    K8sConfig,
    LXDConfig,
    MicroK8sConfig,
    ProviderConfig,
)
from concierge.providers.factory import SUPPORTED_PROVIDERS, create_all_providers, create_provider
from concierge.providers.google import Google
from concierge.providers.k8s import K8s
from concierge.providers.lxd import LXD
from concierge.providers.microk8s import MicroK8s


class TestSupportedProviders:
    """Tests for SUPPORTED_PROVIDERS constant."""

    def test_supported_providers_list(self) -> None:
        """Test that SUPPORTED_PROVIDERS contains expected providers."""
        assert isinstance(SUPPORTED_PROVIDERS, list)
        assert "lxd" in SUPPORTED_PROVIDERS
        assert "microk8s" in SUPPORTED_PROVIDERS
        assert "k8s" in SUPPORTED_PROVIDERS
        assert "google" in SUPPORTED_PROVIDERS

    def test_supported_providers_count(self) -> None:
        """Test that SUPPORTED_PROVIDERS has expected number of providers."""
        assert len(SUPPORTED_PROVIDERS) == 4


class TestCreateProvider:
    """Tests for create_provider function."""

    def test_create_lxd_enabled(self) -> None:
        """Test creating LXD provider when enabled."""
        config = ConciergeConfig(providers=ProviderConfig(lxd=LXDConfig(enable=True)))
        system = Mock()

        provider = create_provider("lxd", system, config)
        assert provider is not None
        assert isinstance(provider, LXD)

    def test_create_lxd_disabled(self) -> None:
        """Test that LXD provider returns None when disabled."""
        config = ConciergeConfig(providers=ProviderConfig(lxd=LXDConfig(enable=False)))
        system = Mock()

        provider = create_provider("lxd", system, config)
        assert provider is None

    def test_create_microk8s_enabled(self) -> None:
        """Test creating MicroK8s provider when enabled."""
        config = ConciergeConfig(providers=ProviderConfig(microk8s=MicroK8sConfig(enable=True)))
        system = Mock()

        provider = create_provider("microk8s", system, config)
        assert provider is not None
        assert isinstance(provider, MicroK8s)

    def test_create_microk8s_disabled(self) -> None:
        """Test that MicroK8s provider returns None when disabled."""
        config = ConciergeConfig(providers=ProviderConfig(microk8s=MicroK8sConfig(enable=False)))
        system = Mock()

        provider = create_provider("microk8s", system, config)
        assert provider is None

    def test_create_k8s_enabled(self) -> None:
        """Test creating K8s provider when enabled."""
        config = ConciergeConfig(providers=ProviderConfig(k8s=K8sConfig(enable=True)))
        system = Mock()

        provider = create_provider("k8s", system, config)
        assert provider is not None
        assert isinstance(provider, K8s)

    def test_create_k8s_disabled(self) -> None:
        """Test that K8s provider returns None when disabled."""
        config = ConciergeConfig(providers=ProviderConfig(k8s=K8sConfig(enable=False)))
        system = Mock()

        provider = create_provider("k8s", system, config)
        assert provider is None

    def test_create_google_enabled(self) -> None:
        """Test creating Google provider when enabled."""
        config = ConciergeConfig(providers=ProviderConfig(google=GoogleConfig(enable=True)))
        system = Mock()

        provider = create_provider("google", system, config)
        assert provider is not None
        assert isinstance(provider, Google)

    def test_create_google_disabled(self) -> None:
        """Test that Google provider returns None when disabled."""
        config = ConciergeConfig(providers=ProviderConfig(google=GoogleConfig(enable=False)))
        system = Mock()

        provider = create_provider("google", system, config)
        assert provider is None

    def test_create_unknown_provider(self) -> None:
        """Test that unknown provider name returns None."""
        config = ConciergeConfig()
        system = Mock()

        provider = create_provider("unknown", system, config)
        assert provider is None

    def test_create_provider_passes_system(self) -> None:
        """Test that created provider receives system instance."""
        config = ConciergeConfig(providers=ProviderConfig(lxd=LXDConfig(enable=True)))
        system = Mock()

        provider = create_provider("lxd", system, config)
        assert provider is not None
        assert provider.system == system

    def test_create_provider_receives_config(self) -> None:
        """Test that created provider is initialized with config data."""
        config = ConciergeConfig(
            providers=ProviderConfig(lxd=LXDConfig(enable=True, channel="5.21/stable"))
        )
        system = Mock()

        provider = create_provider("lxd", system, config)
        assert provider is not None
        # Provider extracts data from config during initialization
        assert provider.channel == "5.21/stable"


class TestCreateAllProviders:
    """Tests for create_all_providers function."""

    def test_create_all_providers_none_enabled(self) -> None:
        """Test that create_all_providers returns empty list when no providers enabled."""
        config = ConciergeConfig()
        system = Mock()

        providers = create_all_providers(system, config)
        assert providers == []

    def test_create_all_providers_single_enabled(self) -> None:
        """Test create_all_providers with single provider enabled."""
        config = ConciergeConfig(providers=ProviderConfig(lxd=LXDConfig(enable=True)))
        system = Mock()

        providers = create_all_providers(system, config)
        assert len(providers) == 1
        assert isinstance(providers[0], LXD)

    def test_create_all_providers_multiple_enabled(self) -> None:
        """Test create_all_providers with multiple providers enabled."""
        config = ConciergeConfig(
            providers=ProviderConfig(
                lxd=LXDConfig(enable=True),
                k8s=K8sConfig(enable=True),
                microk8s=MicroK8sConfig(enable=True),
            )
        )
        system = Mock()

        providers = create_all_providers(system, config)
        assert len(providers) == 3

        # Check that we got the right provider types
        provider_types = [type(p) for p in providers]
        assert LXD in provider_types
        assert K8s in provider_types
        assert MicroK8s in provider_types

    def test_create_all_providers_all_enabled(self) -> None:
        """Test create_all_providers with all providers enabled."""
        config = ConciergeConfig(
            providers=ProviderConfig(
                lxd=LXDConfig(enable=True),
                k8s=K8sConfig(enable=True),
                microk8s=MicroK8sConfig(enable=True),
                google=GoogleConfig(enable=True),
            )
        )
        system = Mock()

        providers = create_all_providers(system, config)
        assert len(providers) == 4

        # Check that we got all provider types
        provider_types = [type(p) for p in providers]
        assert LXD in provider_types
        assert K8s in provider_types
        assert MicroK8s in provider_types
        assert Google in provider_types

    def test_create_all_providers_respects_order(self) -> None:
        """Test that create_all_providers respects SUPPORTED_PROVIDERS order."""
        config = ConciergeConfig(
            providers=ProviderConfig(
                lxd=LXDConfig(enable=True),
                microk8s=MicroK8sConfig(enable=True),
                k8s=K8sConfig(enable=True),
                google=GoogleConfig(enable=True),
            )
        )
        system = Mock()

        providers = create_all_providers(system, config)

        # Order should match SUPPORTED_PROVIDERS: lxd, microk8s, k8s, google
        assert isinstance(providers[0], LXD)
        assert isinstance(providers[1], MicroK8s)
        assert isinstance(providers[2], K8s)
        assert isinstance(providers[3], Google)

    def test_create_all_providers_mixed_enabled_disabled(self) -> None:
        """Test create_all_providers with mix of enabled/disabled providers."""
        config = ConciergeConfig(
            providers=ProviderConfig(
                lxd=LXDConfig(enable=True),
                microk8s=MicroK8sConfig(enable=False),
                k8s=K8sConfig(enable=True),
                google=GoogleConfig(enable=False),
            )
        )
        system = Mock()

        providers = create_all_providers(system, config)
        assert len(providers) == 2

        provider_types = [type(p) for p in providers]
        assert LXD in provider_types
        assert K8s in provider_types
        assert MicroK8s not in provider_types
        assert Google not in provider_types

    def test_create_all_providers_returns_list(self) -> None:
        """Test that create_all_providers always returns a list."""
        config = ConciergeConfig()
        system = Mock()

        providers = create_all_providers(system, config)
        assert isinstance(providers, list)
