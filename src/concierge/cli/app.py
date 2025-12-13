"""Main CLI application for Concierge."""

import typer
from typing_extensions import Annotated

app = typer.Typer(
    name="concierge",
    help="Provision and manage charm development environments",
    no_args_is_help=True,
)


@app.callback()
def main(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose logging")] = False,
    trace: Annotated[bool, typer.Option("--trace", help="Enable trace logging")] = False,
) -> None:
    """Concierge - Charm development environment provisioning."""
    from concierge.core.logging import setup_logging

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
        list[str],
        typer.Option("--extra-snaps", help="Additional snaps to install"),
    ] = [],
    extra_debs: Annotated[
        list[str],
        typer.Option("--extra-debs", help="Additional deb packages to install"),
    ] = [],
) -> None:
    """Provision a charm development environment."""
    import asyncio

    from concierge.cli.commands.prepare import run_prepare
    from concierge.config.loader import get_env_overrides
    from concierge.config.models import ConfigOverrides

    # Merge CLI flags and environment overrides
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
        extra_snaps=extra_snaps or env_overrides.extra_snaps,
        extra_debs=extra_debs or env_overrides.extra_debs,
    )

    asyncio.run(run_prepare(config, preset, cli_overrides))


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
    import asyncio

    from concierge.cli.commands.restore import run_restore

    asyncio.run(run_restore(config, preset))


@app.command()
def status() -> None:
    """Show the status of the Concierge environment."""
    from concierge.cli.commands.status import run_status

    run_status()


if __name__ == "__main__":
    app()
