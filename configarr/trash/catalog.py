"""Index one service's TRaSH JSON so trash references resolve to configarr's own
internal shapes.

Custom formats are keyed by ``trash_id`` (the stable identity — names change),
quality sizes by ``type``. Loading is lazy and once. Two guide quirks are handled
here, both learned from recyclarr's reader (``.scratch/recyclarr``):

- ``specifications[].fields`` is usually an object ``{name: value}`` but historically
  can be an array ``[{name, value}]`` (``FieldsArrayJsonConverter``); both normalize
  to the ``{name: value}`` dict ``CustomFormatProvider`` consumes.
- on a duplicate ``trash_id`` across files, last-loaded wins (``GroupBy(id).Last()``).

Field *values* are left as-is: the diff already coerces both sides via
``CustomFormatProvider.normalize`` (``normalize.coerce_scalar``), so a resolved custom
format flows through exactly like a hand-written one.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TypedDict

from configarr.trash.errors import TrashError
from configarr.trash.metadata import ServicePaths


class TrashCustomFormat(TypedDict):
    """A guide custom format, plus the score sets needed to score it into profiles."""

    trash_id: str
    name: str
    include_when_renaming: bool
    specifications: list[dict[str, Any]]
    trash_scores: dict[str, int]


def _normalize_fields(fields: Any) -> dict[str, Any]:
    if isinstance(fields, dict):
        return dict(fields)
    if isinstance(fields, list):
        return {f["name"]: f.get("value") for f in fields}
    return {}


def _normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": spec.get("name"),
        "implementation": spec.get("implementation"),
        "negate": bool(spec.get("negate", False)),
        "required": bool(spec.get("required", False)),
        "fields": _normalize_fields(spec.get("fields")),
    }


class Catalog:
    """Lazily-loaded index over one service's guide directory tree."""

    def __init__(self, root: Path, paths: ServicePaths) -> None:
        self._root = root
        self._paths = paths
        self._custom_formats: dict[str, TrashCustomFormat] | None = None
        self._quality_sizes: dict[str, dict[str, Any]] | None = None

    def _iter_json(self, rel_dirs: list[str]) -> Iterator[dict[str, Any]]:
        for rel in rel_dirs:
            directory = self._root / rel
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*.json")):
                with path.open() as f:
                    yield json.load(f)

    def custom_formats(self) -> dict[str, TrashCustomFormat]:
        if self._custom_formats is None:
            index: dict[str, TrashCustomFormat] = {}
            for data in self._iter_json(self._paths.custom_formats):
                trash_id = data.get("trash_id")
                if not trash_id:
                    continue
                raw_scores = data.get("trash_scores") or {}
                index[trash_id] = TrashCustomFormat(
                    trash_id=trash_id,
                    name=data.get("name", ""),
                    include_when_renaming=bool(
                        data.get("includeCustomFormatWhenRenaming", False)
                    ),
                    specifications=[
                        _normalize_spec(s) for s in data.get("specifications", [])
                    ],
                    trash_scores={k: int(v) for k, v in raw_scores.items()},
                )
            self._custom_formats = index
        return self._custom_formats

    def custom_format(self, trash_id: str) -> TrashCustomFormat:
        formats = self.custom_formats()
        if trash_id not in formats:
            raise TrashError(f"custom format trash_id not found: {trash_id}")
        return formats[trash_id]

    def quality_sizes(self) -> dict[str, dict[str, Any]]:
        if self._quality_sizes is None:
            index: dict[str, dict[str, Any]] = {}
            for data in self._iter_json(self._paths.qualities):
                qtype = data.get("type")
                if qtype:
                    index[str(qtype)] = data
            self._quality_sizes = index
        return self._quality_sizes

    def quality_definition(self, type_name: str) -> dict[str, dict[str, Any]]:
        """A guide quality-size set as configarr ``quality_definitions``:
        ``{quality_name: {min?, max?, preferred?}}``."""
        sizes = self.quality_sizes()
        if type_name not in sizes:
            raise TrashError(f"quality definition type not found: {type_name}")
        result: dict[str, dict[str, Any]] = {}
        for quality in sizes[type_name].get("qualities", []):
            name = quality.get("quality")
            if not name:
                continue
            result[name] = {
                key: quality[key]
                for key in ("min", "max", "preferred")
                if key in quality
            }
        return result
