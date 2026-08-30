"""Unit tests for image registry configuration."""

import base64
import os
from typing import TYPE_CHECKING

from concierge.config.loader import _expand_env_vars
from concierge.config.models import ConciergeConfig, ImageRegistryConfig
from concierge.providers.registry import build_hosts_toml

if TYPE_CHECKING:
    import pytest


class TestImageRegistryConfig:
    """Tests for ImageRegistryConfig model."""

    def test_defaults(self) -> None:
        config = ImageRegistryConfig()
        assert config.url == ""
        assert config.username == ""
        assert config.password == ""

    def test_from_dict(self) -> None:
        config = ImageRegistryConfig(
            url="https://mirror.example.com", username="user", password="pass"
        )
        assert config.url == "https://mirror.example.com"
        assert config.username == "user"
        assert config.password == "pass"

    def test_alias_in_config(self) -> None:
        data = {
            "providers": {
                "k8s": {
                    "image-registry": {
                        "url": "https://mirror.example.com",
                    }
                }
            }
        }
        config = ConciergeConfig.from_dict(data)
        assert config.providers.k8s.image_registry.url == "https://mirror.example.com"


class TestExpandEnvVars:
    """Tests for _expand_env_vars function."""

    def test_dollar_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MY_URL", "https://mirror.example.com")
        assert _expand_env_vars("$MY_URL") == "https://mirror.example.com"

    def test_braced_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MY_URL", "https://mirror.example.com")
        assert _expand_env_vars("${MY_URL}") == "https://mirror.example.com"

    def test_missing_var_returns_empty(self) -> None:
        # Ensure variable doesn't exist
        os.environ.pop("NONEXISTENT_VAR", None)
        assert _expand_env_vars("$NONEXISTENT_VAR") == ""

    def test_multiple_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOST", "example.com")
        monkeypatch.setenv("PORT", "5000")
        assert _expand_env_vars("https://$HOST:${PORT}") == "https://example.com:5000"

    def test_no_vars(self) -> None:
        assert _expand_env_vars("plain string") == "plain string"


class TestBuildHostsToml:
    """Tests for build_hosts_toml function."""

    def test_without_auth(self) -> None:
        registry = ImageRegistryConfig(url="https://mirror.example.com")
        result = build_hosts_toml(registry)
        assert 'server = "https://mirror.example.com"' in result
        assert '[host."https://mirror.example.com"]' in result
        assert '  capabilities = ["pull", "resolve"]' in result
        assert "Authorization" not in result

    def test_with_auth(self) -> None:
        registry = ImageRegistryConfig(
            url="https://mirror.example.com", username="user", password="pass"
        )
        result = build_hosts_toml(registry)
        expected_creds = base64.b64encode(b"user:pass").decode()
        assert f'Authorization = ["Basic {expected_creds}"]' in result
