"""A single source of truth for the *shape* of a configarr.yml, feeding two things:

- ``build_json_schema`` — a JSON Schema editors can use for autocomplete and inline
  validation (emit it with ``configarr --print-schema``), and
- ``unknown_keys`` — a runtime check that warns on unrecognized section keys, the
  most common "I edited the config and nothing happened" cause (a typo like
  ``custom_format:`` for ``custom_formats:`` is otherwise silently ignored).

Most sections are passthrough (their inner keys aren't the *arr API keys and aren't
modelled), so the spec deliberately describes only the levels configarr itself
recognizes: the per-service instance sections and the container sub-keys where
typos actually bite (``definitions``, ``settings.media_management``, …). The strict
``trash:`` block is validated in full from its Pydantic model.
"""

from __future__ import annotations

from typing import Any

from configarr.models import TrashConfig

# Leaf markers used by the spec; a nested dict means "an object with known keys".
_STR = "string"
_OBJ = "object"  # a passthrough object (definitions maps, settings blocks, …)
_ARR = "array"
_TRASH = "trash"
_INCLUDE = "include"

_ARR_INSTANCE: dict[str, Any] = {
    "base_url": _STR,
    "api_key": _STR,
    "include": _INCLUDE,
    "trash": _TRASH,
    "custom_formats": {"definitions": _OBJ},
    "settings": {"media_management": _OBJ, "root_folders": _ARR},
    "profiles": {
        "quality_profiles": _OBJ,
        "quality_definitions": _OBJ,
        "delay_profiles": _ARR,
        "release_profiles": _OBJ,
    },
    "download_clients": {"definitions": _OBJ},
    "notifications": {"definitions": _OBJ},
    "import_lists": {"definitions": _OBJ},
}
_PROWLARR_INSTANCE: dict[str, Any] = {
    "base_url": _STR,
    "api_key": _STR,
    "include": _INCLUDE,
    "indexers": {"definitions": _OBJ},
    "applications": {"definitions": _OBJ},
    "download_clients": {"definitions": _OBJ},
}
_BAZARR_INSTANCE: dict[str, Any] = {
    "base_url": _STR,
    "api_key": _STR,
    "include": _INCLUDE,
    "general": _OBJ,
    "sonarr": _OBJ,
    "radarr": _OBJ,
    "subsync": _OBJ,
    "translator": _OBJ,
    "providers": _OBJ,
    "language_profiles": _ARR,
}
_SABNZBD_INSTANCE: dict[str, Any] = {
    "base_url": _STR,
    "api_key": _STR,
    "include": _INCLUDE,
    "servers": _OBJ,
    "categories": _OBJ,
    "misc": _OBJ,
}
_LINGARR_INSTANCE: dict[str, Any] = {
    "base_url": _STR,
    "api_key": _STR,
    "include": _INCLUDE,
    "translation": _OBJ,
    "integration": _OBJ,
}

SERVICES: dict[str, dict[str, Any]] = {
    "radarr": _ARR_INSTANCE,
    "sonarr": _ARR_INSTANCE,
    "prowlarr": _PROWLARR_INSTANCE,
    "bazarr": _BAZARR_INSTANCE,
    "sabnzbd": _SABNZBD_INSTANCE,
    "lingarr": _LINGARR_INSTANCE,
}
_REQUIRED = ("base_url", "api_key")


# --- unknown-key check ------------------------------------------------------


def unknown_keys(raw_config: dict[str, Any]) -> list[str]:
    """Return dotted paths of config keys configarr doesn't recognize (at the levels
    it models). An empty list means every section key is known."""
    findings: list[str] = []
    for service, spec in SERVICES.items():
        section = raw_config.get(service)
        if not isinstance(section, dict):
            continue
        instances = section.get("instances")
        if not isinstance(instances, dict):
            continue
        for name, inst in instances.items():
            if isinstance(inst, dict):
                _walk(inst, spec, f"{service}.instances.{name}", findings)
    return findings


def _walk(
    node: dict[str, Any], spec: dict[str, Any], path: str, out: list[str]
) -> None:
    for key, value in node.items():
        sub = spec.get(key)
        if sub is None:  # not a recognized key at this level
            out.append(f"{path}.{key}")
        elif isinstance(sub, dict) and isinstance(value, dict):
            _walk(value, sub, f"{path}.{key}", out)


# --- JSON Schema ------------------------------------------------------------


def build_json_schema() -> dict[str, Any]:
    """A draft-07 JSON Schema for configarr.yml, for editor autocomplete/validation.
    The ``trash:`` block is embedded from its Pydantic model."""
    defs: dict[str, Any] = {
        "include": {
            "type": "array",
            "items": {
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "properties": {"config": {"type": "string"}},
                        "required": ["config"],
                    },
                ]
            },
        }
    }
    trash_schema = TrashConfig.model_json_schema(ref_template="#/$defs/{model}")
    defs.update(trash_schema.pop("$defs", {}))
    defs["trash"] = trash_schema

    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "configarr configuration",
        "type": "object",
        "properties": {
            service: {
                "type": "object",
                "properties": {
                    "instances": {
                        "type": "object",
                        "additionalProperties": _object_schema(spec),
                    }
                },
                "additionalProperties": False,
            }
            for service, spec in SERVICES.items()
        },
        "additionalProperties": False,
        "$defs": defs,
    }


def _object_schema(spec: dict[str, Any]) -> dict[str, Any]:
    node: dict[str, Any] = {
        "type": "object",
        "properties": {key: _leaf_schema(sub) for key, sub in spec.items()},
        "additionalProperties": False,
    }
    required = [k for k in _REQUIRED if k in spec]
    if required:
        node["required"] = required
    return node


def _leaf_schema(sub: Any) -> dict[str, Any]:
    if isinstance(sub, dict):
        return _object_schema(sub)
    if sub == _STR:
        return {"type": "string"}
    if sub == _ARR:
        return {"type": "array"}
    if sub == _OBJ:
        return {"type": "object"}
    if sub == _INCLUDE:
        return {"$ref": "#/$defs/include"}
    if sub == _TRASH:
        return {"$ref": "#/$defs/trash"}
    return {}
