"""Configuration models for Concierge using Pydantic."""

from enum import Enum

from pydantic import BaseModel, Field


class Status(str, Enum):
    """Status of concierge on a given machine."""

    PROVISIONING = "provisioning"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ConfigOverrides(BaseModel):
    """CLI flag and environment variable overrides for configuration."""

    disable_juju: bool = False
    juju_channel: str = ""
    k8s_channel: str = ""
    microk8s_channel: str = ""
    lxd_channel: str = ""
    charmcraft_channel: str = ""
    snapcraft_channel: str = ""
    rockcraft_channel: str = ""
    google_credential_file: str = ""
    extra_snaps: list[str] = Field(default_factory=list)
    extra_debs: list[str] = Field(default_factory=list)


class JujuConfig(BaseModel):
    """Configuration for Juju installation and bootstrap."""

    model_config = {"populate_by_name": True}

    disable: bool = False
    channel: str = ""
    agent_version: str = Field("", alias="agent-version")
    model_defaults: dict[str, str] = Field(default_factory=dict, alias="model-defaults")
    bootstrap_constraints: dict[str, str] = Field(
        default_factory=dict, alias="bootstrap-constraints"
    )
    extra_bootstrap_args: str = Field("", alias="extra-bootstrap-args")


class LXDConfig(BaseModel):
    """Configuration for LXD provider."""

    model_config = {"populate_by_name": True}

    enable: bool = False
    bootstrap: bool = False
    channel: str = ""
    model_defaults: dict[str, str] = Field(default_factory=dict, alias="model-defaults")
    bootstrap_constraints: dict[str, str] = Field(
        default_factory=dict, alias="bootstrap-constraints"
    )


class GoogleConfig(BaseModel):
    """Configuration for Google Cloud provider."""

    model_config = {"populate_by_name": True}

    enable: bool = False
    bootstrap: bool = False
    credentials_file: str = Field("", alias="credentials-file")
    model_defaults: dict[str, str] = Field(default_factory=dict, alias="model-defaults")
    bootstrap_constraints: dict[str, str] = Field(
        default_factory=dict, alias="bootstrap-constraints"
    )


class MicroK8sConfig(BaseModel):
    """Configuration for MicroK8s provider."""

    model_config = {"populate_by_name": True}

    enable: bool = False
    bootstrap: bool = False
    channel: str = ""
    addons: list[str] = Field(default_factory=list)
    model_defaults: dict[str, str] = Field(default_factory=dict, alias="model-defaults")
    bootstrap_constraints: dict[str, str] = Field(
        default_factory=dict, alias="bootstrap-constraints"
    )


class K8sConfig(BaseModel):
    """Configuration for Kubernetes provider."""

    model_config = {"populate_by_name": True}

    enable: bool = False
    bootstrap: bool = False
    channel: str = ""
    features: dict[str, dict[str, str]] = Field(default_factory=dict)
    model_defaults: dict[str, str] = Field(default_factory=dict, alias="model-defaults")
    bootstrap_constraints: dict[str, str] = Field(
        default_factory=dict, alias="bootstrap-constraints"
    )


class ProviderConfig(BaseModel):
    """Configuration for all providers."""

    lxd: LXDConfig = Field(default_factory=LXDConfig)
    google: GoogleConfig = Field(default_factory=GoogleConfig)
    microk8s: MicroK8sConfig = Field(default_factory=MicroK8sConfig)
    k8s: K8sConfig = Field(default_factory=K8sConfig)


class SnapConfig(BaseModel):
    """Configuration for a specific snap to be installed."""

    channel: str = ""
    connections: list[str] = Field(default_factory=list)


class HostConfig(BaseModel):
    """Configuration for host packages and snaps."""

    packages: list[str] = Field(default_factory=list)
    snaps: dict[str, SnapConfig] = Field(default_factory=dict)


class ConciergeConfig(BaseModel):
    """Main configuration for Concierge."""

    juju: JujuConfig = Field(default_factory=JujuConfig)
    providers: ProviderConfig = Field(default_factory=ProviderConfig)
    host: HostConfig = Field(default_factory=HostConfig)

    # Runtime fields
    overrides: ConfigOverrides = Field(default_factory=ConfigOverrides)
    status: Status = Status.PROVISIONING
    verbose: bool = False
    trace: bool = False
