"""Sync orchestration for configarr."""

import logging
from typing import Literal, Union

from rich.console import Console

from configarr.bazarr import BazarrClient
from configarr.models import (
    ArrServiceConfig,
    BazarrConfig,
    ProwlarrConfig,
    SabnzbdConfig,
    SyncStatus,
)
from configarr.prowlarr import ProwlarrClient
from configarr.radarr import RadarrClient
from configarr.sabnzbd import SabnzbdClient
from configarr.sonarr import SonarrClient

ArrClient = Union[RadarrClient, SonarrClient]

console = Console()
log = logging.getLogger(__name__)

ServiceType = Literal["radarr", "sonarr"]

# Status icons
ICON_CREATED = "[green]✓[/green]"
ICON_WOULD = "[yellow]⊙[/yellow]"
ICON_EXISTS = "[blue]ℹ[/blue]"
ICON_FAILED = "[red]✗[/red]"


def _status_update(dry_run: bool) -> str:
    """Return status icon for updates."""
    if dry_run:
        return f"{ICON_WOULD} Would update"
    return f"{ICON_CREATED} Updated"


def _print_header(service: str, name: str, url: str, color: str):
    """Print service header."""
    console.print(f"[bold {color}]{service}[/bold {color}] › [bold]{name}[/bold]")
    console.print(f"[dim]{url}[/dim]")
    console.print()


def _print_section(title: str):
    """Print section header."""
    console.print(f"[bold]{title}[/bold]")


def _sync_items(section: str, items, sync_fn) -> tuple[int, int]:
    """Sync an iterable of (label, value) pairs through ``sync_fn(label, value)``,
    printing per-item status. Returns (success, failure).

    A failure is reported and counted, but its traceback is logged at debug level
    instead of being swallowed, so ``--debug`` surfaces the underlying error.
    """
    _print_section(section)
    success = 0
    failure = 0
    for label, value in items:
        try:
            status = sync_fn(label, value)
            if status in (SyncStatus.CREATED, SyncStatus.UPDATED):
                verb = "Created" if status == SyncStatus.CREATED else "Updated"
                console.print(f"  {ICON_CREATED} {verb} {label}")
                success += 1
            elif status == SyncStatus.UNCHANGED:
                console.print(f"  {ICON_EXISTS} Already exists {label}")
        except Exception as e:
            console.print(f"  {ICON_FAILED} Failed {label}: {e}")
            log.debug("Failed to sync '%s' in %s", label, section, exc_info=True)
            failure += 1
    console.print()
    return success, failure


def _sync_single(section: str, label: str, fn) -> tuple[int, int]:
    """Run a single sync call that returns UPDATED on success. Returns (success,
    failure); a failure logs its traceback at debug level."""
    _print_section(section)
    try:
        status = fn()
        if status == SyncStatus.UPDATED:
            console.print(f"  {ICON_CREATED} Updated {label}")
            console.print()
            return 1, 0
    except Exception as e:
        console.print(f"  {ICON_FAILED} Failed to update {label}: {e}")
        log.debug("Failed to update %s", label, exc_info=True)
        console.print()
        return 0, 1
    console.print()
    return 0, 0


def sync_arr(
    service_type: ServiceType,
    config: ArrServiceConfig,
) -> tuple[int, int]:
    """Sync a Radarr or Sonarr instance. Returns (success_count, failure_count)."""
    success = 0
    failure = 0

    color = "cyan" if service_type == "radarr" else "magenta"
    _print_header(service_type.upper(), config.name, config.base_url, color)

    # Create appropriate client
    client: ArrClient
    if service_type == "radarr":
        client = RadarrClient(config.base_url, config.api_key)
    else:
        client = SonarrClient(config.base_url, config.api_key)

    def tally(result: tuple[int, int]) -> None:
        nonlocal success, failure
        success += result[0]
        failure += result[1]

    # Root folders (path is either a bare string or a {"path": ...} mapping)
    if config.root_folders:
        paths = [
            folder.get("path", folder) if isinstance(folder, dict) else folder
            for folder in config.root_folders
        ]
        tally(
            _sync_items(
                "Root Folders",
                [(path, path) for path in paths],
                lambda path, _value: client.sync_root_folder(path),
            )
        )

    # Naming configuration
    if config.naming_config:
        tally(
            _sync_single(
                "Naming",
                "naming configuration",
                lambda: client.sync_naming_config(config.naming_config),
            )
        )

    # Delay profiles
    if config.delay_profiles:
        tally(
            _sync_items(
                "Delay Profiles",
                [(p.get("name", "Unknown"), p) for p in config.delay_profiles],
                client.sync_delay_profile,
            )
        )

    # Release profiles (Sonarr only)
    if config.release_profiles and isinstance(client, SonarrClient):
        tally(
            _sync_items(
                "Release Profiles",
                [(p.get("name", "Unknown"), p) for p in config.release_profiles],
                client.sync_release_profile,
            )
        )

    # Quality definitions
    if config.quality_definitions:
        tally(
            _sync_single(
                "Quality Definitions",
                "quality definitions",
                lambda: client.sync_quality_definitions(config.quality_definitions),
            )
        )

    # Custom formats (must be synced before quality profiles)
    if config.custom_formats:
        tally(
            _sync_items(
                "Custom Formats",
                config.custom_formats.items(),
                client.sync_custom_format,
            )
        )

    # Quality profiles
    if config.quality_profiles:
        tally(
            _sync_items(
                "Quality Profiles",
                [(p.get("name", "Unknown"), p) for p in config.quality_profiles],
                client.sync_quality_profile,
            )
        )

    # Download clients
    if config.download_clients:
        tally(
            _sync_items(
                "Download Clients",
                config.download_clients.items(),
                client.sync_download_client,
            )
        )

    # Notifications (Connections)
    if config.notifications:
        tally(
            _sync_items(
                "Notifications", config.notifications.items(), client.sync_notification
            )
        )

    return success, failure


def sync_prowlarr(config: ProwlarrConfig) -> tuple[int, int]:
    """Sync a Prowlarr instance. Returns (success_count, failure_count)."""
    success = 0
    failure = 0

    _print_header("PROWLARR", config.name, config.base_url, "yellow")

    client = ProwlarrClient(config.base_url, config.api_key)

    def tally(result: tuple[int, int]) -> None:
        nonlocal success, failure
        success += result[0]
        failure += result[1]

    if config.indexers:
        tally(_sync_items("Indexers", config.indexers.items(), client.sync_indexer))

    if config.applications:
        tally(
            _sync_items(
                "Applications", config.applications.items(), client.sync_application
            )
        )

    if config.download_clients:
        tally(
            _sync_items(
                "Download Clients",
                config.download_clients.items(),
                client.sync_download_client,
            )
        )

    return success, failure


def sync_bazarr(
    config: BazarrConfig,
    dry_run: bool,
    verbose: bool,
) -> tuple[int, int]:
    """Sync a Bazarr instance. Returns (success_count, failure_count)."""
    success = 0
    failure = 0

    _print_header("BAZARR", config.name, config.base_url, "green")

    client = BazarrClient(config.base_url, config.api_key, dry_run, verbose)

    # General settings
    if config.general:
        _print_section("General Settings")
        if client.sync_general(config.general):
            console.print(f"  {_status_update(dry_run)} general settings")
            success += 1
        else:
            console.print(f"  {ICON_FAILED} Failed to update general settings")
            failure += 1
        console.print()

    # Sonarr connection
    if config.sonarr:
        _print_section("Sonarr Connection")
        if client.sync_sonarr(config.sonarr):
            console.print(f"  {_status_update(dry_run)} sonarr connection")
            success += 1
        else:
            console.print(f"  {ICON_FAILED} Failed to update sonarr connection")
            failure += 1
        console.print()

    # Radarr connection
    if config.radarr:
        _print_section("Radarr Connection")
        if client.sync_radarr(config.radarr):
            console.print(f"  {_status_update(dry_run)} radarr connection")
            success += 1
        else:
            console.print(f"  {ICON_FAILED} Failed to update radarr connection")
            failure += 1
        console.print()

    # Providers
    if config.providers:
        _print_section("Providers")
        for name, provider_config in config.providers.items():
            if client.sync_provider(name, provider_config):
                console.print(f"  {_status_update(dry_run)} {name}")
                success += 1
            else:
                console.print(f"  {ICON_FAILED} Failed {name}")
                failure += 1
        console.print()

    # Language profiles. The save is a single batch POST, so it succeeds or fails
    # as a whole; existing profiles named in config are overwritten (not skipped).
    if config.language_profiles:
        _print_section("Language Profiles")
        created, updated, ok = client.sync_language_profiles(config.language_profiles)
        if ok:
            for name in created:
                verb = "Would create" if dry_run else "Created"
                icon = ICON_WOULD if dry_run else ICON_CREATED
                console.print(f"  {icon} {verb} {name}")
                success += 1
            for name in updated:
                console.print(f"  {_status_update(dry_run)} {name}")
                success += 1
        else:
            for name in created + updated:
                console.print(f"  {ICON_FAILED} Failed {name}")
                failure += 1
        console.print()

    return success, failure


def sync_sabnzbd(config: SabnzbdConfig) -> tuple[int, int]:
    """Sync a SABnzbd instance. Returns (success_count, failure_count)."""
    success = 0
    failure = 0

    _print_header("SABNZBD", config.name, config.base_url, "red")

    client = SabnzbdClient(config.base_url, config.api_key)

    def tally(result: tuple[int, int]) -> None:
        nonlocal success, failure
        success += result[0]
        failure += result[1]

    if config.servers:
        tally(_sync_items("Servers", config.servers.items(), client.sync_server))

    if config.categories:
        tally(
            _sync_items("Categories", config.categories.items(), client.sync_category)
        )

    if config.misc:
        tally(
            _sync_single(
                "Settings",
                "misc settings",
                lambda: client.sync_misc_settings(config.misc),
            )
        )

    return success, failure
