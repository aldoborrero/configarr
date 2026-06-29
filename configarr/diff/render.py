"""Human-readable rendering of a Plan."""

from __future__ import annotations

from rich.console import Console

from configarr.diff.model import Op, Plan


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
