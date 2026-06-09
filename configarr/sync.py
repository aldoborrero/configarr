"""Sync orchestration for configarr."""

from typing import Literal, Union

from rich.console import Console

from configarr.models import ArrServiceConfig, ProwlarrConfig, BazarrConfig, SabnzbdConfig, SyncStatus
from configarr.radarr import RadarrClient
from configarr.sonarr import SonarrClient

ArrClient = Union[RadarrClient, SonarrClient]
from configarr.prowlarr import ProwlarrClient
from configarr.bazarr import BazarrClient
from configarr.sabnzbd import SabnzbdClient

console = Console()

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

    # Root folders
    if config.root_folders:
        _print_section("Root Folders")
        for folder in config.root_folders:
            path = folder.get("path", folder) if isinstance(folder, dict) else folder
            try:
                status = client.sync_root_folder(path)
                if status == SyncStatus.CREATED:
                    console.print(f"  {ICON_CREATED} Created {path}")
                    success += 1
                elif status == SyncStatus.UNCHANGED:
                    console.print(f"  {ICON_EXISTS} Already exists {path}")
            except Exception as e:
                console.print(f"  {ICON_FAILED} Failed {path}: {e}")
                failure += 1
        console.print()

    # Naming configuration
    if config.naming_config:
        _print_section("Naming")
        try:
            status = client.sync_naming_config(config.naming_config)
            if status == SyncStatus.UPDATED:
                console.print(f"  {ICON_CREATED} Updated naming configuration")
                success += 1
        except Exception as e:
            console.print(f"  {ICON_FAILED} Failed to update naming configuration: {e}")
            failure += 1
        console.print()

    # Delay profiles
    if config.delay_profiles:
        _print_section("Delay Profiles")
        for profile_config in config.delay_profiles:
            name = profile_config.get("name", "Unknown")
            try:
                status = client.sync_delay_profile(name, profile_config)
                if status == SyncStatus.CREATED:
                    console.print(f"  {ICON_CREATED} Created {name}")
                    success += 1
                elif status == SyncStatus.UNCHANGED:
                    console.print(f"  {ICON_EXISTS} Already exists {name}")
            except Exception as e:
                console.print(f"  {ICON_FAILED} Failed {name}: {e}")
                failure += 1
        console.print()

    # Release profiles (Sonarr only)
    if config.release_profiles and isinstance(client, SonarrClient):
        _print_section("Release Profiles")
        for profile_config in config.release_profiles:
            name = profile_config.get("name", "Unknown")
            try:
                status = client.sync_release_profile(name, profile_config)
                if status == SyncStatus.CREATED:
                    console.print(f"  {ICON_CREATED} Created {name}")
                    success += 1
                elif status == SyncStatus.UNCHANGED:
                    console.print(f"  {ICON_EXISTS} Already exists {name}")
            except Exception as e:
                console.print(f"  {ICON_FAILED} Failed {name}: {e}")
                failure += 1
        console.print()

    # Quality definitions
    if config.quality_definitions:
        _print_section("Quality Definitions")
        try:
            status = client.sync_quality_definitions(config.quality_definitions)
            if status == SyncStatus.UPDATED:
                console.print(f"  {ICON_CREATED} Updated quality definitions")
                success += 1
        except Exception as e:
            console.print(f"  {ICON_FAILED} Failed to update quality definitions: {e}")
            failure += 1
        console.print()

    # Custom formats (must be synced before quality profiles)
    if config.custom_formats:
        _print_section("Custom Formats")
        for name, cf_config in config.custom_formats.items():
            try:
                status = client.sync_custom_format(name, cf_config)
                if status == SyncStatus.CREATED:
                    console.print(f"  {ICON_CREATED} Created {name}")
                    success += 1
                elif status == SyncStatus.UPDATED:
                    console.print(f"  {ICON_CREATED} Updated {name}")
                    success += 1
                elif status == SyncStatus.UNCHANGED:
                    console.print(f"  {ICON_EXISTS} Already exists {name}")
            except Exception as e:
                console.print(f"  {ICON_FAILED} Failed {name}: {e}")
                failure += 1
        console.print()

    # Quality profiles
    if config.quality_profiles:
        _print_section("Quality Profiles")
        for profile_config in config.quality_profiles:
            name = profile_config.get("name", "Unknown")
            try:
                status = client.sync_quality_profile(name, profile_config)
                if status == SyncStatus.CREATED:
                    console.print(f"  {ICON_CREATED} Created {name}")
                    success += 1
                elif status == SyncStatus.UPDATED:
                    console.print(f"  {ICON_CREATED} Updated {name}")
                    success += 1
                elif status == SyncStatus.UNCHANGED:
                    console.print(f"  {ICON_EXISTS} Already exists {name}")
            except Exception as e:
                console.print(f"  {ICON_FAILED} Failed {name}: {e}")
                failure += 1
        console.print()

    # Download clients
    if config.download_clients:
        _print_section("Download Clients")
        for name, client_config in config.download_clients.items():
            try:
                status = client.sync_download_client(name, client_config)
                if status == SyncStatus.CREATED:
                    console.print(f"  {ICON_CREATED} Created {name}")
                    success += 1
                elif status == SyncStatus.UPDATED:
                    console.print(f"  {ICON_CREATED} Updated {name}")
                    success += 1
            except Exception as e:
                console.print(f"  {ICON_FAILED} Failed {name}: {e}")
                failure += 1
        console.print()

    # Notifications (Connections)
    if config.notifications:
        _print_section("Notifications")
        for name, notif_config in config.notifications.items():
            try:
                status = client.sync_notification(name, notif_config)
                if status == SyncStatus.CREATED:
                    console.print(f"  {ICON_CREATED} Created {name}")
                    success += 1
                elif status == SyncStatus.UPDATED:
                    console.print(f"  {ICON_CREATED} Updated {name}")
                    success += 1
            except Exception as e:
                console.print(f"  {ICON_FAILED} Failed {name}: {e}")
                failure += 1
        console.print()

    return success, failure


def sync_prowlarr(config: ProwlarrConfig) -> tuple[int, int]:
    """Sync a Prowlarr instance. Returns (success_count, failure_count)."""
    success = 0
    failure = 0

    _print_header("PROWLARR", config.name, config.base_url, "yellow")

    client = ProwlarrClient(config.base_url, config.api_key)

    # Indexers
    if config.indexers:
        _print_section("Indexers")
        for name, indexer_config in config.indexers.items():
            try:
                status = client.sync_indexer(name, indexer_config)
                if status == SyncStatus.CREATED:
                    console.print(f"  {ICON_CREATED} Created {name}")
                    success += 1
                elif status == SyncStatus.UPDATED:
                    console.print(f"  {ICON_CREATED} Updated {name}")
                    success += 1
            except Exception as e:
                console.print(f"  {ICON_FAILED} Failed {name}: {e}")
                failure += 1
        console.print()

    # Applications
    if config.applications:
        _print_section("Applications")
        for name, app_config in config.applications.items():
            try:
                status = client.sync_application(name, app_config)
                if status == SyncStatus.CREATED:
                    console.print(f"  {ICON_CREATED} Created {name}")
                    success += 1
                elif status == SyncStatus.UPDATED:
                    console.print(f"  {ICON_CREATED} Updated {name}")
                    success += 1
            except Exception as e:
                console.print(f"  {ICON_FAILED} Failed {name}: {e}")
                failure += 1
        console.print()

    # Download clients
    if config.download_clients:
        _print_section("Download Clients")
        for name, client_config in config.download_clients.items():
            try:
                status = client.sync_download_client(name, client_config)
                if status == SyncStatus.CREATED:
                    console.print(f"  {ICON_CREATED} Created {name}")
                    success += 1
                elif status == SyncStatus.UPDATED:
                    console.print(f"  {ICON_CREATED} Updated {name}")
                    success += 1
            except Exception as e:
                console.print(f"  {ICON_FAILED} Failed {name}: {e}")
                failure += 1
        console.print()

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

    # Servers
    if config.servers:
        _print_section("Servers")
        for name, server_config in config.servers.items():
            try:
                status = client.sync_server(name, server_config)
                if status == SyncStatus.CREATED:
                    console.print(f"  {ICON_CREATED} Created {name}")
                    success += 1
                elif status == SyncStatus.UPDATED:
                    console.print(f"  {ICON_CREATED} Updated {name}")
                    success += 1
            except Exception as e:
                console.print(f"  {ICON_FAILED} Failed {name}: {e}")
                failure += 1
        console.print()

    # Categories
    if config.categories:
        _print_section("Categories")
        for name, category_config in config.categories.items():
            try:
                status = client.sync_category(name, category_config)
                if status == SyncStatus.CREATED:
                    console.print(f"  {ICON_CREATED} Created {name}")
                    success += 1
                elif status == SyncStatus.UPDATED:
                    console.print(f"  {ICON_CREATED} Updated {name}")
                    success += 1
            except Exception as e:
                console.print(f"  {ICON_FAILED} Failed {name}: {e}")
                failure += 1
        console.print()

    # Misc settings
    if config.misc:
        _print_section("Settings")
        try:
            status = client.sync_misc_settings(config.misc)
            if status == SyncStatus.UPDATED:
                console.print(f"  {ICON_CREATED} Updated misc settings")
                success += 1
        except Exception as e:
            console.print(f"  {ICON_FAILED} Failed misc settings: {e}")
            failure += 1
        console.print()

    return success, failure
