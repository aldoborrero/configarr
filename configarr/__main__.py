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
from configarr.runner import run_apply, run_plan
from configarr.trash import TrashError, resolve_trash

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
    help="Only process this service type",
)
@click.option(
    "--instance",
    help="Only process this instance name",
)
@click.option(
    "--plan",
    "--dry-run",
    "plan_only",
    is_flag=True,
    help="Preview what would change, then exit without writing anything.",
)
@click.option(
    "--prune",
    is_flag=True,
    help="Also delete unmanaged resources (present on the server but absent from "
    "config) for providers that support deletion. Sync is additive by default; "
    "combine with --plan to preview deletions first.",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug logging",
)
@click.option(
    "--output",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format for --plan: 'json' emits a machine-readable diff for CI.",
)
def main(
    config_path: Path,
    service: str | None,
    instance: str | None,
    plan_only: bool,
    prune: bool,
    debug: bool,
    output: str,
) -> None:
    """
    Configarr - declaratively manage Radarr, Sonarr, Prowlarr, Bazarr, and SABnzbd.

    Diffs your configarr.yml against each service and applies only what changed.
    Run with --plan to preview the diff without writing; add --prune to also remove
    resources the config no longer declares.
    """
    if debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        log.debug("Debug logging enabled")

    # In JSON plan mode, stdout must be pure JSON — suppress the decorative chrome.
    json_mode = plan_only and output == "json"
    if not json_mode:
        console.print(
            Panel.fit(
                "[bold cyan]Configarr[/bold cyan]\n"
                "Configuration manager for Radarr, Sonarr, Prowlarr, "
                "Bazarr, and SABnzbd",
                border_style="cyan",
            )
        )
        console.print()
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

    # Validate --service / --instance against what's configured so a typo doesn't
    # silently no-op and still exit 0.
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

    # Expand any TRaSH-Guides imports into each in-scope instance's own custom
    # formats / quality definitions. Separate from parse_config so parsing stays
    # pure; scoped to --service/--instance so an out-of-scope guide is never read.
    try:
        resolve_trash(config, config_path.parent, service=service, instance=instance)
    except TrashError as e:
        console.print(f"[bold red]TRaSH import error:[/bold red] {e}")
        sys.exit(1)

    try:
        if plan_only:
            result = run_plan(
                config,
                service=service,
                instance=instance,
                prune=prune,
                output=output,
            )
        else:
            result = run_apply(config, service=service, instance=instance, prune=prune)
    except Exception as e:
        action = "Plan" if plan_only else "Apply"
        console.print(f"[bold red]{action} failed:[/bold red] {e}")
        sys.exit(1)

    click.echo(result)


if __name__ == "__main__":
    main()
