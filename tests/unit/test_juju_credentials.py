"""Unit tests for Juju credentials management."""

from unittest.mock import Mock

from concierge.juju.credentials import build_credentials_yaml


class TestBuildCredentialsYaml:
    """Tests for build_credentials_yaml function."""

    def test_empty_providers_list(self) -> None:
        """Test building credentials YAML with empty providers list."""
        result = build_credentials_yaml([])
        assert result == {"credentials": {}}

    def test_single_provider_with_credentials(self) -> None:
        """Test building credentials YAML with single provider."""
        provider = Mock()
        provider.cloud_name.return_value = "lxd"
        provider.credentials.return_value = {
            "auth-type": "interactive",
            "trust-password": "test",
        }

        result = build_credentials_yaml([provider])

        assert "credentials" in result
        assert "lxd" in result["credentials"]
        assert "concierge" in result["credentials"]["lxd"]
        assert result["credentials"]["lxd"]["concierge"]["auth-type"] == "interactive"

    def test_single_provider_without_credentials(self) -> None:
        """Test that provider without credentials is skipped."""
        provider = Mock()
        provider.cloud_name.return_value = "lxd"
        provider.credentials.return_value = None

        result = build_credentials_yaml([provider])

        assert result == {"credentials": {}}

    def test_single_provider_empty_credentials(self) -> None:
        """Test that provider with empty dict credentials is skipped."""
        provider = Mock()
        provider.cloud_name.return_value = "lxd"
        provider.credentials.return_value = {}

        result = build_credentials_yaml([provider])

        # Empty dict is falsy, so should be skipped
        assert result == {"credentials": {}}

    def test_multiple_providers_with_credentials(self) -> None:
        """Test building credentials YAML with multiple providers."""
        lxd_provider = Mock()
        lxd_provider.cloud_name.return_value = "lxd"
        lxd_provider.credentials.return_value = {
            "auth-type": "interactive",
        }

        google_provider = Mock()
        google_provider.cloud_name.return_value = "google"
        google_provider.credentials.return_value = {
            "auth-type": "oauth2",
            "project-id": "test-project",
        }

        result = build_credentials_yaml([lxd_provider, google_provider])

        assert "credentials" in result
        assert "lxd" in result["credentials"]
        assert "google" in result["credentials"]
        assert "concierge" in result["credentials"]["lxd"]
        assert "concierge" in result["credentials"]["google"]

    def test_multiple_providers_mixed_credentials(self) -> None:
        """Test with mix of providers with and without credentials."""
        provider_with_creds = Mock()
        provider_with_creds.cloud_name.return_value = "lxd"
        provider_with_creds.credentials.return_value = {"auth-type": "interactive"}

        provider_without_creds = Mock()
        provider_without_creds.cloud_name.return_value = "k8s"
        provider_without_creds.credentials.return_value = None

        result = build_credentials_yaml([provider_with_creds, provider_without_creds])

        assert "credentials" in result
        assert "lxd" in result["credentials"]
        assert "k8s" not in result["credentials"]

    def test_credentials_nested_under_concierge(self) -> None:
        """Test that credentials are nested under 'concierge' key."""
        provider = Mock()
        provider.cloud_name.return_value = "lxd"
        provider.credentials.return_value = {"auth-type": "interactive"}

        result = build_credentials_yaml([provider])

        # Structure should be: credentials -> cloud_name -> concierge -> actual creds
        assert result["credentials"]["lxd"]["concierge"]["auth-type"] == "interactive"

    def test_credentials_yaml_structure(self) -> None:
        """Test the overall structure of credentials YAML."""
        provider1 = Mock()
        provider1.cloud_name.return_value = "lxd"
        provider1.credentials.return_value = {"auth-type": "interactive"}

        provider2 = Mock()
        provider2.cloud_name.return_value = "google"
        provider2.credentials.return_value = {"auth-type": "oauth2"}

        result = build_credentials_yaml([provider1, provider2])

        # Top-level should have "credentials" key
        assert list(result.keys()) == ["credentials"]

        # Under credentials, should have cloud names
        assert set(result["credentials"].keys()) == {"lxd", "google"}

        # Under each cloud, should have "concierge" key
        assert "concierge" in result["credentials"]["lxd"]
        assert "concierge" in result["credentials"]["google"]

    def test_complex_credentials_data(self) -> None:
        """Test with complex nested credentials data."""
        provider = Mock()
        provider.cloud_name.return_value = "google"
        provider.credentials.return_value = {
            "auth-type": "jsonfile",
            "file": "/path/to/creds.json",
            "project": "my-project",
            "metadata": {"key": "value", "nested": {"data": "here"}},
        }

        result = build_credentials_yaml([provider])

        creds = result["credentials"]["google"]["concierge"]
        assert creds["auth-type"] == "jsonfile"
        assert creds["file"] == "/path/to/creds.json"
        assert creds["project"] == "my-project"
        assert creds["metadata"]["key"] == "value"
        assert creds["metadata"]["nested"]["data"] == "here"

    def test_provider_methods_called_correctly(self) -> None:
        """Test that provider methods are called as expected."""
        provider = Mock()
        provider.cloud_name.return_value = "test-cloud"
        provider.credentials.return_value = {"auth": "test"}

        build_credentials_yaml([provider])

        provider.cloud_name.assert_called_once()
        provider.credentials.assert_called_once()

    def test_preserves_credential_types(self) -> None:
        """Test that credential value types are preserved."""
        provider = Mock()
        provider.cloud_name.return_value = "test"
        provider.credentials.return_value = {
            "string": "value",
            "number": 42,
            "boolean": True,
            "list": [1, 2, 3],
            "dict": {"nested": "data"},
        }

        result = build_credentials_yaml([provider])
        creds = result["credentials"]["test"]["concierge"]

        assert isinstance(creds["string"], str)
        assert isinstance(creds["number"], int)
        assert isinstance(creds["boolean"], bool)
        assert isinstance(creds["list"], list)
        assert isinstance(creds["dict"], dict)
