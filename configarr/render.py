"""Human-readable rendering of a Plan."""

from __future__ import annotations

from typing import TypedDict

from rich.console import Console

from configarr.model import Op, Plan

_REDACTED = "***"
# Substrings marking a field name as secret. This output-layer redaction is a
# backstop: providers normally drop secrets from the diff (see normalize.MASK /
# drop_secret_fields), but Bazarr echoes provider passwords in clear text, so a real
# value can still reach a FieldDiff. Rendering must never trust that upstream dropped
# it — a leaked secret in `--plan` output is the bug this guards against.
#
# Matching is by field *name* only: a secret stored under a non-secret-named key, or a
# secret used as a resource match key, is NOT caught here — providers that hold
# cleartext secrets (Bazarr) should also drop them from the diff, not rely on this.
_SECRET_HINTS = (
    "password",
    "passkey",
    "apikey",
    "userkey",  # Pushover userKey — secret despite lacking password/apikey in the name
    "token",
    "secret",
    "cookie",
)


def _redact(path: str, value: object) -> object:
    leaf = path.rsplit(".", 1)[-1].replace("_", "").lower()
    if any(hint in leaf for hint in _SECRET_HINTS):
        return _REDACTED
    return value


class FieldDiffJson(TypedDict):
    path: str
    before: object
    after: object


class ResourceJson(TypedDict):
    key: object
    op: str
    field_diffs: list[FieldDiffJson]


def render_plan(plan: Plan) -> str:
    if not plan.has_changes:
        return "No changes."

    console = Console(record=True, width=100)
    for op in (Op.CREATE, Op.UPDATE, Op.DELETE):
        items = [r for r in plan.resources if r.op is op]
        if not items:
            continue
        console.print(f"[bold]{op.value.upper()}[/bold] ({len(items)})")
        for r in items:
            console.print(f"  {r.kind}/{r.key}")
            # Field-level diffs are only meaningful for UPDATE (CREATE diffs are
            # all before=None noise; DELETE has nothing to show).
            if r.op is Op.UPDATE:
                for d in r.field_diffs:
                    before = _redact(d.path, d.before)
                    after = _redact(d.path, d.after)
                    console.print(f"    {d.path}: {before!r} -> {after!r}")
    return console.export_text()


def plan_resources_json(plan: Plan) -> list[ResourceJson]:
    """Changed resources of a plan as JSON-serializable dicts (for --output json)."""
    return [
        ResourceJson(
            key=r.key,
            op=r.op.value,
            field_diffs=[
                FieldDiffJson(
                    path=d.path,
                    before=_redact(d.path, d.before),
                    after=_redact(d.path, d.after),
                )
                for d in r.field_diffs
            ],
        )
        for r in plan.resources
        if r.changed
    ]
