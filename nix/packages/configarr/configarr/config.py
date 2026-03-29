"""Configuration parsing for configarr."""

import os
import re
from pathlib import Path
from typing import Any

import yaml

from configarr.models import (
    ArrServiceConfig,
    BazarrConfig,
    ConfigarrConfig,
    ProwlarrConfig,
    RadarrConfig,
    SabnzbdConfig,
    SonarrConfig,
)

# Re-export for backwards compatibility
__all__ = [
    "parse_config",
    "load_env_file",
    "expand_env_vars",
    "RadarrConfig",
    "SonarrConfig",
    "ProwlarrConfig",
    "BazarrConfig",
    "SabnzbdConfig",
    "ConfigarrConfig",
]


def load_env_file(env_path: Path) -> None:
    """Load environment variables from a .env file."""
    if not env_path.exists():
        return

    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue
            # Parse KEY=value
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Remove surrounding quotes if present
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                # Only set if not already in environment
                if key not in os.environ:
                    os.environ[key] = value


def expand_env_vars(value: Any) -> Any:
    """Recursively expand environment variables in config values.

    Supports ${VAR} syntax. Missing env vars are left as-is.
    """
    if isinstance(value, str):

        def replace_env(match: re.Match[str]) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))

        return re.sub(r"\$\{([^}]+)\}", replace_env, value)
    elif isinstance(value, dict):
        return {k: expand_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [expand_env_vars(item) for item in value]
    return value


def parse_quality_profiles(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse quality profiles from nested YAML structure to flat list."""
    quality_profiles = []
    profiles = config.get("profiles", {})
    quality_profiles_section = profiles.get("quality_profiles", {})
    profiles_config = quality_profiles_section.get("definitions", {})

    for profile_name, profile_def in profiles_config.items():
        qualities_raw = profile_def.get("qualities", [])
        qualities = [{"name": q} if isinstance(q, str) else q for q in qualities_raw]

        quality_profiles.append({
            "name": profile_name,
            "upgrade": {
                "allowed": profile_def.get("upgrades_allowed", True),
                "until_quality": profile_def.get("upgrade_until_quality", "WEBDL-1080p"),
                "until_score": profile_def.get(
                    "upgrade_until_custom_format_score", 10000
                ),
            },
            "min_format_score": profile_def.get("minimum_custom_format_score", 0),
            "quality_sort": "top",
            "qualities": qualities,
        })

    return quality_profiles


def parse_arr_instance(name: str, config: dict[str, Any]) -> ArrServiceConfig:
    """Parse a Radarr or Sonarr instance configuration."""
    return ArrServiceConfig(
        name=name,
        base_url=config["base_url"],
        api_key=config["api_key"],
        quality_profiles=parse_quality_profiles(config),
        naming_config=config.get("settings", {}).get("media_management"),
        delay_profiles=config.get("profiles", {}).get("delay_profiles"),
        release_profiles=config.get("profiles", {}).get("release_profiles"),
        quality_definitions=config.get("profiles", {}).get("quality_definitions"),
        root_folders=config.get("settings", {}).get("root_folders"),
        download_clients=config.get("download_clients", {}).get("definitions", {}),
    )


def parse_prowlarr_instance(name: str, config: dict[str, Any]) -> ProwlarrConfig:
    """Parse a Prowlarr instance configuration."""
    return ProwlarrConfig(
        name=name,
        base_url=config["base_url"],
        api_key=config["api_key"],
        indexers=config.get("indexers", {}).get("definitions", {}),
        applications=config.get("applications", {}).get("definitions", {}),
        download_clients=config.get("download_clients", {}).get("definitions", {}),
    )


def parse_bazarr_instance(name: str, config: dict[str, Any]) -> BazarrConfig:
    """Parse a Bazarr instance configuration."""
    return BazarrConfig(
        name=name,
        base_url=config["base_url"],
        api_key=config["api_key"],
        general=config.get("general"),
        sonarr=config.get("sonarr"),
        radarr=config.get("radarr"),
        providers=config.get("providers", {}),
        language_profiles=config.get("language_profiles", []),
    )


def parse_sabnzbd_instance(name: str, config: dict[str, Any]) -> SabnzbdConfig:
    """Parse a SABnzbd instance configuration."""
    return SabnzbdConfig(
        name=name,
        base_url=config["base_url"],
        api_key=config["api_key"],
        servers=config.get("servers", {}),
        categories=config.get("categories", {}),
        misc=config.get("misc"),
    )


def parse_config(config_path: Path) -> ConfigarrConfig:
    """Parse configarr.yml and return structured configuration.

    Supports ${VAR} environment variable substitution in all string values.
    Automatically loads .env file from the same directory as config file.

    Raises:
        pydantic.ValidationError: If required fields are missing or invalid
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML is malformed
    """
    # Load .env file from config directory if it exists
    env_path = config_path.parent / ".env"
    load_env_file(env_path)

    with open(config_path, "r") as f:
        raw_config = yaml.safe_load(f)

    # Expand environment variables in all config values
    raw_config = expand_env_vars(raw_config)

    # Parse each service type
    radarr_instances = []
    sonarr_instances = []
    prowlarr_instances = []
    bazarr_instances = []
    sabnzbd_instances = []

    if "radarr" in raw_config:
        for name, instance_config in raw_config["radarr"].get("instances", {}).items():
            radarr_instances.append(parse_arr_instance(name, instance_config))

    if "sonarr" in raw_config:
        for name, instance_config in raw_config["sonarr"].get("instances", {}).items():
            sonarr_instances.append(parse_arr_instance(name, instance_config))

    if "prowlarr" in raw_config:
        for name, instance_config in raw_config["prowlarr"].get("instances", {}).items():
            prowlarr_instances.append(parse_prowlarr_instance(name, instance_config))

    if "bazarr" in raw_config:
        for name, instance_config in raw_config["bazarr"].get("instances", {}).items():
            bazarr_instances.append(parse_bazarr_instance(name, instance_config))

    if "sabnzbd" in raw_config:
        for name, instance_config in raw_config["sabnzbd"].get("instances", {}).items():
            sabnzbd_instances.append(parse_sabnzbd_instance(name, instance_config))

    return ConfigarrConfig(
        radarr=radarr_instances,
        sonarr=sonarr_instances,
        prowlarr=prowlarr_instances,
        bazarr=bazarr_instances,
        sabnzbd=sabnzbd_instances,
    )
