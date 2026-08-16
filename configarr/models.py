"""Pydantic models for configarr configuration."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# The TRaSH import block is the one part of the config with a tight, fully-modelled
# contract, so it forbids unknown keys — a typo (`trash_id` vs `trash_ids`,
# `assign_score_to`) is a hard error instead of being silently dropped like the
# passthrough sections elsewhere.
_STRICT = ConfigDict(extra="forbid")


class TrashScoreTarget(BaseModel):
    """A quality profile that imported custom formats should be scored into.

    ``score`` overrides the guide value; otherwise the score comes from the custom
    format's ``score_set`` (default ``"default"``)."""

    model_config = _STRICT
    profile: str
    score: int | None = None
    score_set: str | None = None


class TrashCustomFormatGroup(BaseModel):
    """A set of TRaSH custom formats to import, and where to score them."""

    model_config = _STRICT
    trash_ids: list[str] = []
    assign_scores_to: list[TrashScoreTarget] = []


class TrashQualityProfileImport(BaseModel):
    """A whole TRaSH quality profile to import by ``trash_id`` — its quality
    grouping, upgrade settings, and every custom format it scores (pulled from the
    profile's ``score_set``). ``name`` optionally renames it."""

    model_config = _STRICT
    trash_id: str
    name: str | None = None
    score_set: str | None = None


class TrashConfig(BaseModel):
    """Per-instance TRaSH-Guides import block. Resolved after parsing into the
    instance's own ``custom_formats`` / ``quality_profiles`` / ``quality_definitions``
    (see ``configarr.trash``).

    - ``source: local`` reads an existing Guides checkout at ``path`` (relative
      paths resolve against the config file's directory).
    - ``source: git`` clones/updates a Guides repo into a local cache. ``url``
      defaults to the official TRaSH-Guides repo; ``ref`` pins a branch/tag (the
      repo's default branch when unset)."""

    model_config = _STRICT
    source: Literal["local", "git"] = "local"
    path: str | None = None
    url: str | None = None
    ref: str | None = None
    quality_definition: str | None = None
    custom_formats: list[TrashCustomFormatGroup] = []
    quality_profiles: list[TrashQualityProfileImport] = []

    @model_validator(mode="after")
    def _check_source_fields(self) -> "TrashConfig":
        # Fail fast on a misused field instead of silently ignoring it: local needs
        # a path and rejects git-only keys; git rejects the local-only path.
        if self.source == "local":
            if not self.path:
                raise ValueError("trash source 'local' requires 'path'")
            if self.url or self.ref:
                raise ValueError("'url'/'ref' are only valid with trash source 'git'")
        elif self.source == "git" and self.path:
            raise ValueError("'path' is only valid with trash source 'local'")
        return self


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
    import_lists: dict[str, dict[str, Any]] = {}
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
    subsync: dict[str, Any] | None = None
    translator: dict[str, Any] | None = None
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
