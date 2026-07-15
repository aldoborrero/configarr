"""Configuration parsing for configarr."""

import logging
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

log = logging.getLogger("configarr.config")

# Re-export for backwards compatibility
__all__ = [
    "BazarrConfig",
    "ConfigarrConfig",
    "ProwlarrConfig",
    "RadarrConfig",
    "SabnzbdConfig",
    "SonarrConfig",
    "expand_env_vars",
    "load_env_file",
    "parse_config",
]


def load_env_file(env_path: Path) -> None:
    """Load environment variables from a .env file."""
    if not env_path.exists():
        return

    with env_path.open() as f:
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


def expand_env_vars(value: Any, _unresolved: set[str] | None = None) -> Any:
    """Recursively expand environment variables in config values.

    Supports ${VAR} syntax. A missing variable is left as the literal ``${VAR}``;
    its name is collected into ``_unresolved`` (when provided) so the caller can warn
    — otherwise a literal ``${API_KEY}`` silently reaches an API payload and surfaces
    as a confusing 401 far from the cause.
    """
    if isinstance(value, str):

        def replace_env(match: re.Match[str]) -> str:
            var_name = match.group(1)
            if var_name not in os.environ:
                if _unresolved is not None:
                    _unresolved.add(var_name)
                return match.group(0)
            return os.environ[var_name]

        return re.sub(r"\$\{([^}]+)\}", replace_env, value)
    if isinstance(value, dict):
        return {k: expand_env_vars(v, _unresolved) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env_vars(item, _unresolved) for item in value]
    return value


def parse_quality_profiles(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse quality profiles from nested YAML structure to flat list."""
    quality_profiles = []
    profiles = config.get("profiles") or {}
    quality_profiles_section = profiles.get("quality_profiles") or {}
    profiles_config = quality_profiles_section.get("definitions") or {}

    for profile_name, profile_def in profiles_config.items():
        if not isinstance(profile_def, dict):
            raise ValueError(
                f"Quality profile '{profile_name}' must be a mapping of settings"
            )
        qualities_raw = profile_def.get("qualities", [])
        qualities = [{"name": q} if isinstance(q, str) else q for q in qualities_raw]

        quality_profiles.append(
            {
                "name": profile_name,
                "upgrade": {
                    "allowed": profile_def.get("upgrades_allowed", True),
                    "until_quality": profile_def.get(
                        "upgrade_until_quality", "WEBDL-1080p"
                    ),
                    "until_score": profile_def.get(
                        "upgrade_until_custom_format_score", 10000
                    ),
                },
                "min_format_score": profile_def.get("minimum_custom_format_score", 0),
                "custom_format_scores": profile_def.get("custom_format_scores", {}),
                "quality_sort": "top",
                "qualities": qualities,
                "language": profile_def.get("language"),
            }
        )

    return quality_profiles


def parse_arr_instance(name: str, config: dict[str, Any]) -> ArrServiceConfig:
    """Parse a Radarr or Sonarr instance configuration."""
    return ArrServiceConfig(
        name=name,
        base_url=config["base_url"],
        api_key=config["api_key"],
        custom_formats=(config.get("custom_formats") or {}).get("definitions", {}),
        quality_profiles=parse_quality_profiles(config),
        naming_config=(config.get("settings") or {}).get("media_management"),
        delay_profiles=(config.get("profiles") or {}).get("delay_profiles"),
        release_profiles=(config.get("profiles") or {}).get("release_profiles"),
        quality_definitions=(config.get("profiles") or {}).get("quality_definitions"),
        root_folders=(config.get("settings") or {}).get("root_folders"),
        download_clients=(config.get("download_clients") or {}).get("definitions", {}),
        notifications=(config.get("notifications") or {}).get("definitions", {}),
        # Carried through as-is; TRaSH resolution is a separate, IO-performing pass
        # (configarr.trash.resolve_trash) so parse_config stays pure.
        trash=config.get("trash"),
    )


def parse_prowlarr_instance(name: str, config: dict[str, Any]) -> ProwlarrConfig:
    """Parse a Prowlarr instance configuration."""
    return ProwlarrConfig(
        name=name,
        base_url=config["base_url"],
        api_key=config["api_key"],
        indexers=(config.get("indexers") or {}).get("definitions", {}),
        applications=(config.get("applications") or {}).get("definitions", {}),
        download_clients=(config.get("download_clients") or {}).get("definitions", {}),
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
        providers=config.get("providers") or {},
        language_profiles=config.get("language_profiles") or [],
    )


def parse_sabnzbd_instance(name: str, config: dict[str, Any]) -> SabnzbdConfig:
    """Parse a SABnzbd instance configuration."""
    return SabnzbdConfig(
        name=name,
        base_url=config["base_url"],
        api_key=config["api_key"],
        servers=config.get("servers") or {},
        categories=config.get("categories") or {},
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

    with config_path.open() as f:
        raw_config = yaml.safe_load(f)

    # An empty or comment-only file parses to None; treat it as an empty config.
    if raw_config is None:
        raw_config = {}
    if not isinstance(raw_config, dict):
        raise ValueError(
            "Configuration file must contain a YAML mapping at the top level, "
            f"got {type(raw_config).__name__}"
        )

    # Expand environment variables in all config values, warning about any that were
    # left unresolved (they'd otherwise flow into API payloads as literal ${VAR}).
    unresolved: set[str] = set()
    raw_config = expand_env_vars(raw_config, unresolved)
    if unresolved:
        log.warning(
            "unresolved ${VAR} left literal (set them in .env or the environment): %s",
            ", ".join(sorted(unresolved)),
        )

    # The `or {}` at each level keeps a present-but-null section (e.g. `radarr:`
    # with no body, or `instances:` left blank) from crashing instead of being
    # read as "no instances".
    def instances(section: str) -> dict[str, Any]:
        return (raw_config.get(section) or {}).get("instances") or {}

    return ConfigarrConfig(
        radarr=[
            parse_arr_instance(name, cfg or {})
            for name, cfg in instances("radarr").items()
        ],
        sonarr=[
            parse_arr_instance(name, cfg or {})
            for name, cfg in instances("sonarr").items()
        ],
        prowlarr=[
            parse_prowlarr_instance(name, cfg or {})
            for name, cfg in instances("prowlarr").items()
        ],
        bazarr=[
            parse_bazarr_instance(name, cfg or {})
            for name, cfg in instances("bazarr").items()
        ],
        sabnzbd=[
            parse_sabnzbd_instance(name, cfg or {})
            for name, cfg in instances("sabnzbd").items()
        ],
    )
