"""Main CLI application for Concierge."""

import asyncio
import os
from typing import Annotated

import typer

from concierge.cli.commands.prepare import run_prepare
from concierge.cli.commands.restore import run_restore
from concierge.cli.commands.status import run_status
from concierge.config.loader import get_env_overrides
from concierge.config.models import ConfigOverrides
from concierge.config.presets import get_available_presets
from concierge.core.logging import setup_logging
from concierge.system.command import CommandError

app = typer.Typer(
    name="concierge",
    help="Provision and manage charm development environments",
    no_args_is_help=True,
)


@app.callback()
def main(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logging")] = False,
    trace: Annotated[
        bool, typer.Option("--trace", help="Enable trace logging (most verbose)")
    ] = False,
) -> None:
    """Concierge - Charm development environment provisioning."""
    setup_logging(verbose=verbose, trace=trace)


@app.command()
def prepare(
    config: Annotated[
        str,
        typer.Option("--config", "-c", help="Path to configuration file"),
    ] = "",
    preset: Annotated[
        str,
        typer.Option(
            "--preset",
            "-p",
            help="Configuration preset (dev, machine, k8s, microk8s, crafts)",
        ),
    ] = "",
    disable_juju: Annotated[
        bool,
        typer.Option("--disable-juju", help="Disable Juju installation"),
    ] = False,
    juju_channel: Annotated[
        str,
        typer.Option("--juju-channel", help="Juju snap channel override"),
    ] = "",
    lxd_channel: Annotated[
        str,
        typer.Option("--lxd-channel", help="LXD snap channel override"),
    ] = "",
    microk8s_channel: Annotated[
        str,
        typer.Option("--microk8s-channel", help="MicroK8s snap channel override"),
    ] = "",
    k8s_channel: Annotated[
        str,
        typer.Option("--k8s-channel", help="K8s snap channel override"),
    ] = "",
    charmcraft_channel: Annotated[
        str,
        typer.Option("--charmcraft-channel", help="Charmcraft snap channel override"),
    ] = "",
    snapcraft_channel: Annotated[
        str,
        typer.Option("--snapcraft-channel", help="Snapcraft snap channel override"),
    ] = "",
    rockcraft_channel: Annotated[
        str,
        typer.Option("--rockcraft-channel", help="Rockcraft snap channel override"),
    ] = "",
    google_credential_file: Annotated[
        str,
        typer.Option("--google-credential-file", help="Google Cloud credentials file"),
    ] = "",
    extra_snaps: Annotated[
        list[str] | None,
        typer.Option("--extra-snaps", help="Additional snaps to install"),
    ] = None,
    extra_debs: Annotated[
        list[str] | None,
        typer.Option("--extra-debs", help="Additional deb packages to install"),
    ] = None,
) -> None:
    """Provision a charm development environment."""
    # Merge CLI flags and environment overrides
    if extra_debs is None:
        extra_debs = []
    if extra_snaps is None:
        extra_snaps = []

    # Split comma-separated values (like Go's StringSlice)
    def split_comma_list(items: list[str]) -> list[str]:
        result = []
        for item in items:
            # Split on comma and strip whitespace
            result.extend([s.strip() for s in item.split(",") if s.strip()])
        return result

    extra_snaps = split_comma_list(extra_snaps)
    extra_debs = split_comma_list(extra_debs)

    # Validate preset if provided
    if preset:
        available = get_available_presets()
        if preset not in available:
            typer.echo(
                f"Error: Unknown preset '{preset}'. Available presets: {', '.join(available)}",
                err=True,
            )
            raise typer.Exit(code=1)

    env_overrides = get_env_overrides()
    cli_overrides = ConfigOverrides(
        disable_juju=disable_juju or env_overrides.disable_juju,
        juju_channel=juju_channel or env_overrides.juju_channel,
        k8s_channel=k8s_channel or env_overrides.k8s_channel,
        microk8s_channel=microk8s_channel or env_overrides.microk8s_channel,
        lxd_channel=lxd_channel or env_overrides.lxd_channel,
        charmcraft_channel=charmcraft_channel or env_overrides.charmcraft_channel,
        snapcraft_channel=snapcraft_channel or env_overrides.snapcraft_channel,
        rockcraft_channel=rockcraft_channel or env_overrides.rockcraft_channel,
        google_credential_file=google_credential_file or env_overrides.google_credential_file,
        # Merge CLI and env extra snaps/debs (CLI doesn't replace env, they combine)
        extra_snaps=extra_snaps + env_overrides.extra_snaps,
        extra_debs=extra_debs + env_overrides.extra_debs,
    )

    try:
        asyncio.run(run_prepare(config, preset, cli_overrides))
    except CommandError as e:
        # Check for permission-related errors
        if os.geteuid() != 0 and (
            "Permission denied" in e.output
            or "Could not open lock file" in e.output
            or e.returncode == 100
        ):
            typer.echo(
                "Error: This command requires root privileges. Please run with sudo.",
                err=True,
            )
            raise typer.Exit(code=1) from e
        # Re-raise for other command errors to show full context
        raise


@app.command()
def restore(
    config: Annotated[
        str,
        typer.Option("--config", "-c", help="Path to configuration file"),
    ] = "",
    preset: Annotated[
        str,
        typer.Option(
            "--preset",
            "-p",
            help="Configuration preset (dev, machine, k8s, microk8s, crafts)",
        ),
    ] = "",
) -> None:
    """Restore the system to its pre-Concierge state."""
    # Validate preset if provided
    if preset:
        available = get_available_presets()
        if preset not in available:
            typer.echo(
                f"Error: Unknown preset '{preset}'. Available presets: {', '.join(available)}",
                err=True,
            )
            raise typer.Exit(code=1)

    try:
        asyncio.run(run_restore(config, preset))
    except CommandError as e:
        # Check for permission-related errors
        if os.geteuid() != 0 and (
            "Permission denied" in e.output
            or "Could not open lock file" in e.output
            or e.returncode == 100
        ):
            typer.echo(
                "Error: This command requires root privileges. Please run with sudo.",
                err=True,
            )
            raise typer.Exit(code=1) from e
        # Re-raise for other command errors to show full context
        raise


@app.command()
def status() -> None:
    """Show the status of the Concierge environment."""
    run_status()


if __name__ == "__main__":
    app()
