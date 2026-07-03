"""Parse the TRaSH-Guides ``metadata.json`` for data-driven file discovery.

The guide repo ships ``metadata.json`` at its root, listing per service the
directory paths that hold each resource type's JSON. Reading it — instead of
hardcoding paths — keeps configarr working when the guide reorganizes its folders.
This mirrors recyclarr's ``RepoMetadata`` / ``TrashGuidesStrategy`` (see
``.scratch/recyclarr``); the guide's real key names are already snake_case, so the
Pydantic field names match verbatim and unknown keys (``naming``, ``conflicts``,
``$schema``, …) are ignored.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from configarr.trash.errors import TrashError


class ServicePaths(BaseModel):
    """Directory paths (relative to the guide root) for one service's resources."""

    custom_formats: list[str] = []
    qualities: list[str] = []
    quality_profiles: list[str] = []


class JsonPaths(BaseModel):
    radarr: ServicePaths = ServicePaths()
    sonarr: ServicePaths = ServicePaths()


class RepoMetadata(BaseModel):
    json_paths: JsonPaths = JsonPaths()


def load_metadata(root: Path) -> RepoMetadata:
    """Read and validate ``<root>/metadata.json``."""
    metadata_file = root / "metadata.json"
    if not metadata_file.is_file():
        raise TrashError(f"metadata.json not found in guide root: {root}")
    with metadata_file.open() as f:
        data = json.load(f)
    return RepoMetadata.model_validate(data)
