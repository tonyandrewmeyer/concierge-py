"""Main CLI application for Concierge."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

from concierge import securitylog
from concierge.cli.commands.prepare import run_prepare
from concierge.cli.commands.restore import run_restore
from concierge.cli.commands.status import run_status
from concierge.config.loader import get_env_overrides
from concierge.config.models import ConfigOverrides
from concierge.config.presets import get_available_presets
from concierge.core.logging import setup_logging
from concierge.system.command import CommandError

if TYPE_CHECKING:
    from collections.abc import Sequence


def _appid() -> str:
    """Build the SEC0045 appid string, embedding the installed package version."""
    try:
        pkg_version = version("concierge")
    except PackageNotFoundError:
        pkg_version = "unknown"
    return f"concierge@{pkg_version}"


def _split_comma_list(items: list[str]) -> list[str]:
    """Split comma-separated values (like Go's StringSlice)."""
    result = []
    for item in items:
        # Split on comma and strip whitespace
        result.extend([s.strip() for s in item.split(",") if s.strip()])
    return result


def _validate_preset(preset: str) -> None:
    """Exit with an error if the preset is not one Concierge knows about."""
    if preset:
        available = get_available_presets()
        if preset not in available:
            print(
                f"Error: Unknown preset '{preset}'. Available presets: {', '.join(available)}",
                file=sys.stderr,
            )
            raise SystemExit(1)


def _handle_privilege_error(e: CommandError) -> None:
    """Re-raise a command error, or explain that it was caused by a lack of root."""
    # Check for permission-related errors
    if os.geteuid() != 0 and (
        "Permission denied" in e.output
        or "Could not open lock file" in e.output
        or e.returncode == 100
    ):
        print(
            "Error: This command requires root privileges. Please run with sudo.",
            file=sys.stderr,
        )
        raise SystemExit(1) from e
    # Re-raise for other command errors to show full context
    raise e


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser and its subcommands."""
    # Upstream declares --verbose and --trace as cobra persistent flags, which
    # are accepted either before or after the subcommand name. Attaching this
    # parent parser to the root parser and to every subparser reproduces that.
    # The flags default to SUPPRESS so that a subcommand parsed without them
    # does not overwrite a value the root parser already stored: argparse
    # copies every attribute of the subparser's namespace over the outer one.
    global_options = argparse.ArgumentParser(add_help=False)
    global_options.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Enable debug logging",
    )
    global_options.add_argument(
        "--trace",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Enable trace logging (most verbose)",
    )

    parser = argparse.ArgumentParser(
        prog="concierge",
        description="Provision and manage charm development environments",
        parents=[global_options],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser(
        "prepare",
        parents=[global_options],
        help="Provision a charm development environment",
        description="Provision a charm development environment",
    )
    prepare.set_defaults(func=_prepare)
    prepare.add_argument("--config", "-c", default="", help="Path to configuration file")
    prepare.add_argument(
        "--preset",
        "-p",
        default="",
        help="Configuration preset (dev, machine, k8s, microk8s, crafts)",
    )
    prepare.add_argument("--disable-juju", action="store_true", help="Disable Juju installation")
    prepare.add_argument("--juju-channel", default="", help="Juju snap channel override")
    prepare.add_argument("--juju-revision", default="", help="Juju snap revision override")
    prepare.add_argument("--lxd-channel", default="", help="LXD snap channel override")
    prepare.add_argument("--microk8s-channel", default="", help="MicroK8s snap channel override")
    prepare.add_argument("--k8s-channel", default="", help="K8s snap channel override")
    prepare.add_argument(
        "--charmcraft-channel", default="", help="Charmcraft snap channel override"
    )
    prepare.add_argument("--snapcraft-channel", default="", help="Snapcraft snap channel override")
    prepare.add_argument("--rockcraft-channel", default="", help="Rockcraft snap channel override")
    prepare.add_argument(
        "--google-credential-file", default="", help="Google Cloud credentials file"
    )
    prepare.add_argument("--extra-snaps", action="append", help="Additional snaps to install")
    prepare.add_argument(
        "--extra-debs", action="append", help="Additional deb packages to install"
    )
    prepare.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    restore = subparsers.add_parser(
        "restore",
        parents=[global_options],
        help="Restore the system to its pre-Concierge state",
        description="Restore the system to its pre-Concierge state",
    )
    restore.set_defaults(func=_restore)
    restore.add_argument("--config", "-c", default="", help="Path to configuration file")
    restore.add_argument(
        "--preset",
        "-p",
        default="",
        help="Configuration preset (dev, machine, k8s, microk8s, crafts)",
    )
    restore.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    status = subparsers.add_parser(
        "status",
        parents=[global_options],
        help="Show the status of the Concierge environment",
        description="Show the status of the Concierge environment",
    )
    status.set_defaults(func=_status)

    return parser


def _prepare(args: argparse.Namespace) -> None:
    """Provision a charm development environment."""
    # Merge CLI flags and environment overrides
    extra_snaps = _split_comma_list(args.extra_snaps or [])
    extra_debs = _split_comma_list(args.extra_debs or [])

    # Validate preset if provided
    _validate_preset(args.preset)

    env_overrides = get_env_overrides()
    cli_overrides = ConfigOverrides(
        disable_juju=args.disable_juju or env_overrides.disable_juju,
        juju_channel=args.juju_channel or env_overrides.juju_channel,
        juju_revision=args.juju_revision or env_overrides.juju_revision,
        k8s_channel=args.k8s_channel or env_overrides.k8s_channel,
        microk8s_channel=args.microk8s_channel or env_overrides.microk8s_channel,
        lxd_channel=args.lxd_channel or env_overrides.lxd_channel,
        charmcraft_channel=args.charmcraft_channel or env_overrides.charmcraft_channel,
        snapcraft_channel=args.snapcraft_channel or env_overrides.snapcraft_channel,
        rockcraft_channel=args.rockcraft_channel or env_overrides.rockcraft_channel,
        google_credential_file=args.google_credential_file or env_overrides.google_credential_file,
        # Merge CLI and env extra snaps/debs (CLI doesn't replace env, they combine)
        extra_snaps=extra_snaps + env_overrides.extra_snaps,
        extra_debs=extra_debs + env_overrides.extra_debs,
    )

    try:
        asyncio.run(run_prepare(args.config, args.preset, cli_overrides, dry_run=args.dry_run))
    except CommandError as e:
        _handle_privilege_error(e)


def _restore(args: argparse.Namespace) -> None:
    """Restore the system to its pre-Concierge state."""
    # Validate preset if provided
    _validate_preset(args.preset)

    try:
        asyncio.run(run_restore(args.config, args.preset, dry_run=args.dry_run))
    except CommandError as e:
        _handle_privilege_error(e)


def _status(args: argparse.Namespace) -> None:
    """Show the status of the Concierge environment."""
    run_status()


def main(argv: Sequence[str] | None = None) -> None:
    """Concierge - Charm development environment provisioning."""
    parser = _build_parser()
    arguments = sys.argv[1:] if argv is None else list(argv)

    # A bare `concierge` invocation shows the help text rather than the usage
    # error argparse would produce for the missing subcommand.
    if not arguments:
        parser.print_help()
        raise SystemExit(0)

    args = parser.parse_args(arguments)

    verbose = getattr(args, "verbose", False)
    trace = getattr(args, "trace", False)
    setup_logging(verbose=verbose, trace=trace)

    # Configure the SEC0045 security event logger so audit events carry the
    # Concierge version in their appid. Events are emitted as structured JSON
    # to the system journal via syslog(3), tagged "concierge", so the audit
    # stream stays separate from Concierge's stderr; falls back to stderr if
    # syslog is unreachable.
    securitylog.configure_default(_appid())

    args.func(args)


if __name__ == "__main__":
    main()
