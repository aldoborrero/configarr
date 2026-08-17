#!/usr/bin/env python3
"""Configarr CLI - Configuration manager for *arr applications."""

import json
import logging
import sys
from pathlib import Path

import click
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel

from configarr import __version__
from configarr.config import parse_config
from configarr.runner import run_apply, run_plan
from configarr.schema import build_json_schema
from configarr.trash import TrashError, resolve_trash

console = Console()
log = logging.getLogger("configarr")


def _print_schema(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Eager --print-schema callback: emit the JSON Schema to stdout and exit, before
    --config (which requires an existing file) is validated."""
    if not value or ctx.resilient_parsing:
        return
    click.echo(json.dumps(build_json_schema(), indent=2))
    ctx.exit()


@click.command()
@click.version_option(version=__version__, prog_name="configarr")
@click.option(
    "--print-schema",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_print_schema,
    help="Print a JSON Schema for configarr.yml (for editor autocomplete/validation) "
    "and exit.",
)
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
        ["radarr", "sonarr", "prowlarr", "bazarr", "sabnzbd", "lingarr"],
        case_sensitive=False,
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
@click.option(
    "--check",
    is_flag=True,
    help="Validate the config offline — parse it, check the models, and resolve any "
    "TRaSH imports — then exit without contacting any service. For CI.",
)
@click.option(
    "--strict",
    is_flag=True,
    help="Treat unrecognized config keys as an error instead of a warning.",
)
def main(
    config_path: Path,
    service: str | None,
    instance: str | None,
    plan_only: bool,
    prune: bool,
    debug: bool,
    output: str,
    check: bool,
    strict: bool,
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

    # --output json is a plan-only concern: apply prints a human summary, so a JSON
    # apply would silently emit un-parseable text. Reject the combination up front.
    if output == "json" and not plan_only:
        console.print(
            "[bold red]--output json requires --plan[/bold red] "
            "(apply has no JSON output)."
        )
        sys.exit(2)

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
        config = parse_config(config_path, strict=strict)
    except FileNotFoundError:
        console.print(
            f"[bold red]Configuration file not found:[/bold red] {config_path}"
        )
        sys.exit(1)
    except yaml.YAMLError as e:
        console.print(f"[bold red]Invalid YAML syntax:[/bold red] {e}")
        sys.exit(1)
    except (ValidationError, ValueError, KeyError) as e:
        # Known config-shape errors get a friendly message: Pydantic validation,
        # explicit ValueErrors in the parser, and a missing required key (KeyError
        # from a `config[...]` access). Anything else (a genuine code defect, e.g.
        # TypeError/AttributeError) is left to surface as a traceback, not mislabelled.
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

    # --check stops here: the config parsed, the models validated, the scope
    # resolved, and every TRaSH import expanded — all without touching a service.
    # Everything below reaches the network.
    if check:
        instance_count = sum(len(names) for names in available.values())
        service_count = sum(1 for names in available.values() if names)
        console.print(
            f"[bold green]OK[/bold green] — configuration is valid "
            f"({instance_count} instance(s) across {service_count} service(s)); "
            "no service was contacted."
        )
        sys.exit(0)

    # Ownership state lives next to the config; it records what configarr manages
    # so --prune only deletes configarr-created resources, never user-made ones.
    state_path = config_path.parent / ".configarr-state.json"
    try:
        if plan_only:
            result = run_plan(
                config,
                service=service,
                instance=instance,
                prune=prune,
                output=output,
                state_path=state_path,
            )
        else:
            result = run_apply(
                config,
                service=service,
                instance=instance,
                prune=prune,
                state_path=state_path,
            )
    except Exception as e:
        action = "Plan" if plan_only else "Apply"
        console.print(f"[bold red]{action} failed:[/bold red] {e}")
        sys.exit(1)

    click.echo(result)


if __name__ == "__main__":
    main()
