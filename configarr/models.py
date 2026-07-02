"""Pydantic models for configarr configuration."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, field_validator


class TrashScoreTarget(BaseModel):
    """A quality profile that imported custom formats should be scored into.

    ``score`` overrides the guide value; otherwise the score comes from the custom
    format's ``score_set`` (default ``"default"``)."""

    profile: str
    score: int | None = None
    score_set: str | None = None


class TrashCustomFormatGroup(BaseModel):
    """A set of TRaSH custom formats to import, and where to score them."""

    trash_ids: list[str] = []
    assign_scores_to: list[TrashScoreTarget] = []


class TrashConfig(BaseModel):
    """Per-instance TRaSH-Guides import block. Resolved after parsing into the
    instance's own ``custom_formats`` / ``quality_definitions`` (see
    ``configarr.trash``). ``source: local`` reads an existing Guides checkout at
    ``path`` (relative paths resolve against the config file's directory)."""

    source: Literal["local"] = "local"
    path: str | None = None
    quality_definition: str | None = None
    custom_formats: list[TrashCustomFormatGroup] = []


class SyncStatus(StrEnum):
    """Status returned by sync operations."""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    FAILED = "failed"


class QualityProfileConfig(BaseModel):
    """Quality profile configuration from YAML."""

    name: str
    upgrades_allowed: bool = True
    upgrade_until_quality: str = "WEBDL-1080p"
    upgrade_until_custom_format_score: int = 10000
    minimum_custom_format_score: int = 0
    qualities: list[str | dict[str, Any]] = []


class ArrServiceConfig(BaseModel):
    """Base config for Radarr/Sonarr - they share identical APIs."""

    name: str
    base_url: str
    api_key: str
    custom_formats: dict[str, dict[str, Any]] = {}
    quality_profiles: list[dict[str, Any]] = []
    naming_config: dict[str, Any] | None = None
    delay_profiles: list[dict[str, Any]] | None = None
    release_profiles: list[dict[str, Any]] | None = None
    quality_definitions: dict[str, Any] | None = None
    root_folders: list[dict[str, Any]] | None = None
    download_clients: dict[str, dict[str, Any]] = {}
    notifications: dict[str, dict[str, Any]] = {}
    trash: TrashConfig | None = None

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        """Remove trailing slash from base_url."""
        return v.rstrip("/")


# Type aliases for clarity in code
RadarrConfig = ArrServiceConfig
SonarrConfig = ArrServiceConfig


class ProwlarrConfig(BaseModel):
    """Configuration for a Prowlarr instance."""

    name: str
    base_url: str
    api_key: str
    indexers: dict[str, dict[str, Any]] = {}
    applications: dict[str, dict[str, Any]] = {}
    download_clients: dict[str, dict[str, Any]] = {}

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        """Remove trailing slash from base_url."""
        return v.rstrip("/")


class BazarrConfig(BaseModel):
    """Configuration for a Bazarr instance."""

    name: str
    base_url: str
    api_key: str
    general: dict[str, Any] | None = None
    sonarr: dict[str, Any] | None = None
    radarr: dict[str, Any] | None = None
    providers: dict[str, dict[str, Any]] = {}
    language_profiles: list[dict[str, Any]] = []

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        """Remove trailing slash from base_url."""
        return v.rstrip("/")


class SabnzbdConfig(BaseModel):
    """Configuration for a SABnzbd instance."""

    name: str
    base_url: str
    api_key: str
    servers: dict[str, dict[str, Any]] = {}
    categories: dict[str, dict[str, Any]] = {}
    misc: dict[str, Any] | None = None

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        """Remove trailing slash from base_url."""
        return v.rstrip("/")


class ConfigarrConfig(BaseModel):
    """Root configuration containing all service instances."""

    radarr: list[ArrServiceConfig] = []
    sonarr: list[ArrServiceConfig] = []
    prowlarr: list[ProwlarrConfig] = []
    bazarr: list[BazarrConfig] = []
    sabnzbd: list[SabnzbdConfig] = []
