"""Helpers for building full desired objects (see diffing-engine-rollout §A5)."""

from __future__ import annotations

from typing import Any


def merge_full_replace(
    defaults: dict[str, Any],
    current: dict[str, Any] | None,
    desired: dict[str, Any],
) -> dict[str, Any]:
    """Overlay precedence desired > current > defaults for a full-replace resource.

    Full-replace apply PUTs the whole object, so the desired payload must carry every
    server-managed key from ``current``; otherwise the PUT resets them. Merging over
    current here keeps those keys, so the engine's current-only-key guard stays quiet.
    ``current`` is ``None`` on CREATE, where desired overlays defaults only.
    """
    return {**defaults, **(current or {}), **desired}
