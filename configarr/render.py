"""Human-readable rendering of a Plan."""

from __future__ import annotations

from typing import TypedDict

from rich.console import Console

from configarr.model import Op, Plan


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
                    console.print(f"    {d.path}: {d.before!r} -> {d.after!r}")
    return console.export_text()


def plan_resources_json(plan: Plan) -> list[ResourceJson]:
    """Changed resources of a plan as JSON-serializable dicts (for --output json)."""
    return [
        ResourceJson(
            key=r.key,
            op=r.op.value,
            field_diffs=[
                FieldDiffJson(path=d.path, before=d.before, after=d.after)
                for d in r.field_diffs
            ],
        )
        for r in plan.resources
        if r.changed
    ]
