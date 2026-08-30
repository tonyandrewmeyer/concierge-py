"""Configuration models for Concierge."""

import dataclasses
import typing
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar, Self, get_args, get_origin


class Status(StrEnum):
    """Status of concierge on a given machine."""

    PROVISIONING = "provisioning"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def _alias(name: str) -> dict[str, str]:
    """Record the hyphenated key that a field is spelled with in YAML."""
    return {"alias": name}


def _to_str(value: Any) -> Any:
    """Coerce a YAML scalar to the string the schema declares.

    PyYAML infers types from unquoted scalars, so `revision: 123` or `channel: 1.32`
    arrives as an int or a float. Everything downstream treats these as strings, so
    they are converted here rather than being compared against string literals later.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return value


def _to_bool(value: Any) -> Any:
    """Coerce a YAML scalar to the boolean the schema declares."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(value, int | float):
        return bool(value)
    return value


def _to_int(value: Any) -> Any:
    """Coerce a YAML scalar to the integer the schema declares."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return value
    return value


def _coerce(value: Any, target: Any) -> Any:
    """Convert a value parsed from YAML to the type its field declares."""
    origin = get_origin(target)
    if origin is list:
        if not isinstance(value, list):
            return value
        (item_type,) = get_args(target)
        return [_coerce(item, item_type) for item in value]
    if origin is dict:
        if not isinstance(value, dict):
            return value
        key_type, value_type = get_args(target)
        return {_coerce(k, key_type): _coerce(v, value_type) for k, v in value.items()}
    if origin is not None or not isinstance(target, type):
        return value
    if issubclass(target, _ConfigBase):
        return target.from_dict(value)
    if issubclass(target, StrEnum):
        return target(_to_str(value))
    if target is bool:
        return _to_bool(value)
    if target is str:
        return _to_str(value)
    if target is int:
        return _to_int(value)
    return value


def _to_plain(value: Any) -> Any:
    """Convert a configuration value to something yaml.safe_dump can represent."""
    if isinstance(value, _ConfigBase):
        return value.to_dict()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    return value


class _ConfigBase:
    """Conversion between configuration dataclasses and plain YAML mappings."""

    if TYPE_CHECKING:
        # Every subclass is a dataclass, which the base class cannot express otherwise.
        __dataclass_fields__: ClassVar[dict[str, dataclasses.Field[Any]]]

    @classmethod
    def _normalize(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Adjust a raw mapping before its values are coerced onto fields."""
        return data

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        """Build a configuration object from a mapping parsed out of YAML.

        Unknown keys are ignored, and a key whose value is null leaves the field at its
        default, so that partial and hand-written configuration files keep loading.
        """
        if not isinstance(data, dict):
            return cls()
        data = cls._normalize(data)
        hints = typing.get_type_hints(cls)
        kwargs: dict[str, Any] = {}
        for f in dataclasses.fields(cls):
            alias = f.metadata.get("alias", "")
            if alias and alias in data:
                raw = data[alias]
            elif f.name in data:
                raw = data[f.name]
            else:
                continue
            if raw is None:
                continue
            kwargs[f.name] = _coerce(raw, hints[f.name])
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Render the configuration as a mapping keyed the way YAML spells it."""
        result: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            key = f.metadata.get("alias", "") or f.name
            result[key] = _to_plain(getattr(self, f.name))
        return result


@dataclass
class ConfigOverrides(_ConfigBase):
    """CLI flag and environment variable overrides for configuration."""

    disable_juju: bool = False
    juju_channel: str = ""
    juju_revision: str = ""
    k8s_channel: str = ""
    microk8s_channel: str = ""
    lxd_channel: str = ""
    charmcraft_channel: str = ""
    snapcraft_channel: str = ""
    rockcraft_channel: str = ""
    google_credential_file: str = ""
    extra_snaps: list[str] = field(default_factory=list)
    extra_debs: list[str] = field(default_factory=list)


@dataclass
class JujuConfig(_ConfigBase):
    """Configuration for Juju installation and bootstrap."""

    disable: bool = False
    channel: str = ""
    revision: str = ""
    agent_version: str = field(default="", metadata=_alias("agent-version"))
    model_defaults: dict[str, str] = field(default_factory=dict, metadata=_alias("model-defaults"))
    bootstrap_constraints: dict[str, str] = field(
        default_factory=dict, metadata=_alias("bootstrap-constraints")
    )
    extra_bootstrap_args: str = field(default="", metadata=_alias("extra-bootstrap-args"))


@dataclass
class LXDConfig(_ConfigBase):
    """Configuration for LXD provider."""

    enable: bool = False
    bootstrap: bool = False
    channel: str = ""
    model_defaults: dict[str, str] = field(default_factory=dict, metadata=_alias("model-defaults"))
    bootstrap_constraints: dict[str, str] = field(
        default_factory=dict, metadata=_alias("bootstrap-constraints")
    )


@dataclass
class GoogleConfig(_ConfigBase):
    """Configuration for Google Cloud provider."""

    enable: bool = False
    bootstrap: bool = False
    credentials_file: str = field(default="", metadata=_alias("credentials-file"))
    model_defaults: dict[str, str] = field(default_factory=dict, metadata=_alias("model-defaults"))
    bootstrap_constraints: dict[str, str] = field(
        default_factory=dict, metadata=_alias("bootstrap-constraints")
    )


@dataclass
class ImageRegistryConfig(_ConfigBase):
    """Configuration for an image registry mirror."""

    url: str = ""
    username: str = ""
    password: str = ""


@dataclass
class MicroK8sConfig(_ConfigBase):
    """Configuration for MicroK8s provider."""

    enable: bool = False
    bootstrap: bool = False
    channel: str = ""
    addons: list[str] = field(default_factory=list)
    image_registry: ImageRegistryConfig = field(
        default_factory=ImageRegistryConfig, metadata=_alias("image-registry")
    )
    model_defaults: dict[str, str] = field(default_factory=dict, metadata=_alias("model-defaults"))
    bootstrap_constraints: dict[str, str] = field(
        default_factory=dict, metadata=_alias("bootstrap-constraints")
    )


@dataclass
class K8sConfig(_ConfigBase):
    """Configuration for Kubernetes provider."""

    enable: bool = False
    bootstrap: bool = False
    channel: str = ""
    features: dict[str, dict[str, str]] = field(default_factory=dict)
    image_registry: ImageRegistryConfig = field(
        default_factory=ImageRegistryConfig, metadata=_alias("image-registry")
    )
    model_defaults: dict[str, str] = field(default_factory=dict, metadata=_alias("model-defaults"))
    bootstrap_constraints: dict[str, str] = field(
        default_factory=dict, metadata=_alias("bootstrap-constraints")
    )

    @classmethod
    def normalize_features(cls, v: Any) -> Any:
        """Normalize features dict to handle None values and convert bools to strings."""
        if not isinstance(v, dict):
            return v

        normalized: dict[str, Any] = {}
        for feature_name, feature_config in v.items():
            # A feature listed with no options at all is enabled with its defaults.
            if feature_config is None:
                normalized[feature_name] = {}
            else:
                normalized[feature_name] = feature_config

        return normalized

    @classmethod
    def _normalize(cls, data: dict[str, Any]) -> dict[str, Any]:
        if "features" not in data:
            return data
        return {**data, "features": cls.normalize_features(data["features"])}


@dataclass
class ProviderConfig(_ConfigBase):
    """Configuration for all providers."""

    lxd: LXDConfig = field(default_factory=LXDConfig)
    google: GoogleConfig = field(default_factory=GoogleConfig)
    microk8s: MicroK8sConfig = field(default_factory=MicroK8sConfig)
    k8s: K8sConfig = field(default_factory=K8sConfig)


@dataclass
class SnapConfig(_ConfigBase):
    """Configuration for a specific snap to be installed.

    Channel is optional and defaults to latest/stable when omitted.
    """

    channel: str = ""
    connections: list[str] = field(default_factory=list)


@dataclass
class HostConfig(_ConfigBase):
    """Configuration for host packages and snaps."""

    packages: list[str] = field(default_factory=list)
    snaps: dict[str, SnapConfig] = field(default_factory=dict)

    @classmethod
    def normalize_snaps(cls, v: Any) -> Any:
        """Normalize snaps dict to handle None values."""
        if not isinstance(v, dict):
            return v

        # A snap listed with no options at all is installed from its default channel.
        return {
            name: snap_config if snap_config is not None else {} for name, snap_config in v.items()
        }

    @classmethod
    def _normalize(cls, data: dict[str, Any]) -> dict[str, Any]:
        if "snaps" not in data:
            return data
        return {**data, "snaps": cls.normalize_snaps(data["snaps"])}


@dataclass
class ConciergeConfig(_ConfigBase):
    """Main configuration for Concierge."""

    juju: JujuConfig = field(default_factory=JujuConfig)
    providers: ProviderConfig = field(default_factory=ProviderConfig)
    host: HostConfig = field(default_factory=HostConfig)

    # Runtime fields
    overrides: ConfigOverrides = field(default_factory=ConfigOverrides)
    status: Status = Status.PROVISIONING
    verbose: bool = False
    trace: bool = False
    dry_run: bool = field(default=False, metadata=_alias("dry-run"))
