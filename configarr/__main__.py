#!/usr/bin/env python3
"""Configarr CLI - Configuration manager for *arr applications."""

import logging
import sys
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel

from configarr.config import parse_config
from configarr.sync import sync_arr, sync_bazarr, sync_prowlarr, sync_sabnzbd

console = Console()
log = logging.getLogger("configarr")


@click.command()
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd() / "configarr.yml",
    help="Path to configarr.yml configuration file",
)
@click.option(
    "--service",
    type=click.Choice(
        ["radarr", "sonarr", "prowlarr", "bazarr", "sabnzbd"], case_sensitive=False
    ),
    help="Only process specific service type",
)
@click.option(
    "--instance",
    help="Only process specific instance name",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without making changes (Bazarr only)",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Enable verbose logging with payloads (Bazarr only)",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug logging",
)
@click.option(
    "--plan",
    "plan_only",
    is_flag=True,
    help="Show what would change for supported resources, then exit (no writes).",
)
def main(
    config_path: Path,
    service: str | None,
    instance: str | None,
    dry_run: bool,
    verbose: bool,
    debug: bool,
    plan_only: bool,
):
    """
    Configarr - Configuration manager for *arr applications and SABnzbd.

    Manages quality profiles, naming, delay profiles, release profiles,
    indexers, applications, and download clients for Radarr, Sonarr, Prowlarr,
    Bazarr, and SABnzbd.
    """
    # Configure logging
    if debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        log.debug("Debug logging enabled")

    console.print(
        Panel.fit(
            "[bold cyan]Configarr[/bold cyan]\n"
            "Configuration manager for Radarr, Sonarr, Prowlarr, Bazarr, and SABnzbd",
            border_style="cyan",
        )
    )
    console.print()

    if dry_run:
        console.print(
            "[yellow]DRY RUN MODE - only Bazarr is simulated. Radarr, Sonarr, Prowlarr, and "
            "SABnzbd do not support dry-run and are skipped (no changes are made to them).[/yellow]\n"
        )

    console.print(f"[dim]Configuration file:[/dim] {config_path}\n")

    try:
        config = parse_config(config_path)
    except FileNotFoundError:
        console.print(
            f"[bold red]Configuration file not found:[/bold red] {config_path}"
        )
        sys.exit(1)
    except yaml.YAMLError as e:
        console.print(f"[bold red]Invalid YAML syntax:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Configuration error:[/bold red] {e}")
        sys.exit(1)

    if plan_only:
        from configarr.diff.runner import run_plan

        click.echo(run_plan(config, service=service, instance=instance))
        return

    # Validate --service / --instance against what's actually configured, so a typo
    # doesn't silently no-op and still exit 0. This is independent of --dry-run.
    available = {
        "radarr": [c.name for c in config.radarr],
        "sonarr": [c.name for c in config.sonarr],
        "prowlarr": [c.name for c in config.prowlarr],
        "bazarr": [c.name for c in config.bazarr],
        "sabnzbd": [c.name for c in config.sabnzbd],
    }
    if service and not available[service.lower()]:
        console.print(f"[bold red]No '{service}' instances are configured.[/bold red]")
        sys.exit(2)
    if instance:
        selected = [service.lower()] if service else list(available)
        candidate_names = [n for svc in selected for n in available[svc]]
        if instance not in candidate_names:
            scope = f"service '{service}'" if service else "any configured service"
            console.print(
                f"[bold red]No instance named '{instance}' found in {scope}.[/bold red]"
            )
            sys.exit(2)

    total_success = 0
    total_failure = 0

    # Process SABnzbd instances FIRST (categories must exist before *arr apps reference them).
    # Skipped under --dry-run: these sync paths are not dry-run-aware and would write to the live API.
    if (service is None or service.lower() == "sabnzbd") and not dry_run:
        for sabnzbd_config in config.sabnzbd:
            if instance and sabnzbd_config.name != instance:
                continue
            s, f = sync_sabnzbd(sabnzbd_config)
            total_success += s
            total_failure += f

    # Process Radarr instances (skipped under --dry-run: not dry-run-aware, would write live)
    if (service is None or service.lower() == "radarr") and not dry_run:
        for radarr_config in config.radarr:
            if instance and radarr_config.name != instance:
                continue
            s, f = sync_arr("radarr", radarr_config)
            total_success += s
            total_failure += f

    # Process Sonarr instances (skipped under --dry-run: not dry-run-aware, would write live)
    if (service is None or service.lower() == "sonarr") and not dry_run:
        for sonarr_config in config.sonarr:
            if instance and sonarr_config.name != instance:
                continue
            s, f = sync_arr("sonarr", sonarr_config)
            total_success += s
            total_failure += f

    # Process Prowlarr instances (skipped under --dry-run: not dry-run-aware, would write live)
    if (service is None or service.lower() == "prowlarr") and not dry_run:
        for prowlarr_config in config.prowlarr:
            if instance and prowlarr_config.name != instance:
                continue
            s, f = sync_prowlarr(prowlarr_config)
            total_success += s
            total_failure += f

    # Process Bazarr instances
    if service is None or service.lower() == "bazarr":
        for bazarr_config in config.bazarr:
            if instance and bazarr_config.name != instance:
                continue
            s, f = sync_bazarr(bazarr_config, dry_run, verbose)
            total_success += s
            total_failure += f

    # Summary
    console.rule("[bold]Summary[/bold]", style="cyan")

    if total_success > 0:
        console.print(f"[green]Success:[/green] {total_success}")
    if total_failure > 0:
        console.print(f"[red]Failed:[/red] {total_failure}")

    console.print()

    if total_failure > 0:
        console.print("[bold red]Some operations failed[/bold red]")
        sys.exit(1)
    else:
        console.print("[bold green]All operations completed successfully![/bold green]")
        sys.exit(0)


if __name__ == "__main__":
    main()
