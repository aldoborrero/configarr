"""Human-readable rendering of a Plan."""

from __future__ import annotations

from typing import TypedDict

from rich.console import Console

from configarr.model import Op, Plan
from configarr.normalize import is_secret_name

_REDACTED = "***"
# Output-layer backstop over the shared secret-name policy (normalize.is_secret_name).
# Providers that echo secrets in clear text (Bazarr) fingerprint them in normalize, so
# the cleartext should not reach a FieldDiff — but rendering must never trust that, as
# a leaked secret in `--plan`/JSON output is the bug this guards against. Matching is
# by field *name* only: a secret under a non-secret-named key is not caught here.


def _redact(path: str, value: object) -> object:
    if is_secret_name(path):
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
