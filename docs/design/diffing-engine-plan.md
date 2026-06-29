# Diffing Engine — Phase 0 + Radarr Custom-Formats Pilot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a plan→apply diffing engine as an isolated library and prove it end-to-end on one resource (Radarr custom formats) with idempotency tests, without changing any existing sync behavior.

**Architecture:** A new `configarr/diff/` package provides a generic, service-agnostic differ over normalized resources plus a `ResourceProvider` interface; each service supplies a provider (fetch current / build desired / normalize / apply). The pilot implements `RadarrCustomFormatProvider` using `/customformat/schema` as the default layer, name→id matching, and full-object PUT. A read-only `--plan` CLI flag renders the computed plan for custom formats; all other resources stay on the existing code path.

**Tech Stack:** Python 3.13, `requests` (existing API clients), `pydantic`, `rich` (plan rendering), `pytest` + `responses` (HTTP mocking) for tests, Nix devshell + a new `nix/checks/pytest.nix` so CI runs the suite.

**Companion docs:** [`diffing-engine-feasibility.md`](./diffing-engine-feasibility.md), [`diffing-engine-radarr-notes.md`](./diffing-engine-radarr-notes.md). Read the Radarr notes before Task 6 — they define the API constraints the provider must honor.

**Scope note:** This plan covers Phase 0 + the custom-formats pilot only. Rolling the provider interface out to the remaining Radarr/Sonarr resources, Prowlarr, SABnzbd, and Bazarr — plus opt-in `--prune` (`DELETED`) and apply-through-engine — are **separate follow-up plans**, each gated by its own idempotency tests.

---

## File Structure

**New package `configarr/diff/`:**
- `configarr/diff/__init__.py` — public exports (`Plan`, `diff`, `ResourceProvider`).
- `configarr/diff/model.py` — `Op` enum, `FieldDiff`, `ResourcePlan`, `Plan` dataclasses; pure data, no I/O.
- `configarr/diff/normalize.py` — canonicalization helpers (coerce numeric strings, compare-by-id, drop masked secrets, stable ordering) used by providers' `normalize()`.
- `configarr/diff/engine.py` — generic `diff(current, desired, *, match_key, normalize)` producing a `Plan`; no service-specific logic.
- `configarr/diff/render.py` — `render_plan(plan) -> str` using `rich` for human-readable output.
- `configarr/diff/providers/__init__.py`
- `configarr/diff/providers/base.py` — `ResourceProvider` Protocol + `Resource`/`Action` types.
- `configarr/diff/providers/radarr_custom_formats.py` — the pilot provider.

**Tests (new `tests/` tree):**
- `tests/conftest.py` — shared fixtures (sample CF config, schema/current JSON payloads).
- `tests/diff/test_model.py`, `tests/diff/test_normalize.py`, `tests/diff/test_engine.py`
- `tests/diff/test_render.py`
- `tests/providers/test_radarr_custom_formats.py` — provider unit + **idempotency** tests with `responses`.

**Modified:**
- `nix/devshell.nix` — add `pytest`, `responses` (and `rich` if not already pulled in).
- `nix/checks/pytest.nix` — **new** flake check running the suite in CI.
- `pyproject.toml` — add `[project.optional-dependencies] test = [...]`, `[tool.pytest.ini_options]`.
- `configarr/__main__.py` — add `--plan` flag and route Radarr custom-formats through the engine when set.

---

## Task 1: Test harness

**Files:**
- Modify: `nix/devshell.nix`
- Modify: `pyproject.toml`
- Create: `tests/__init__.py`, `tests/conftest.py`, `tests/test_smoke.py`

- [ ] **Step 1: Add test deps to the devshell**

In `nix/devshell.nix`, add to `packages`:
```nix
    python313Packages.pytest
    python313Packages.responses
    python313Packages.rich
```

- [ ] **Step 2: Add pytest config + test extra to pyproject.toml**

```toml
[project.optional-dependencies]
test = ["pytest>=8.0", "responses>=0.25"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 3: Write a smoke test** (`tests/test_smoke.py`)

```python
def test_package_imports():
    import configarr
    assert configarr.__version__
```

- [ ] **Step 4: Run it**

Run: `nix develop -c pytest tests/test_smoke.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add nix/devshell.nix pyproject.toml tests/
git commit -m "test: add pytest harness and devshell test deps"
```

---

## Task 2: Core diff model

**Files:**
- Create: `configarr/diff/__init__.py`, `configarr/diff/model.py`
- Test: `tests/diff/__init__.py`, `tests/diff/test_model.py`

- [ ] **Step 1: Write the failing test** (`tests/diff/test_model.py`)

```python
from configarr.diff.model import Op, FieldDiff, ResourcePlan, Plan


def test_resourceplan_is_changed():
    unchanged = ResourcePlan(kind="cf", key="x", op=Op.UNCHANGED, field_diffs=[])
    created = ResourcePlan(kind="cf", key="y", op=Op.CREATE, field_diffs=[])
    assert not unchanged.changed
    assert created.changed


def test_plan_summary_counts():
    plan = Plan(resources=[
        ResourcePlan("cf", "a", Op.CREATE, []),
        ResourcePlan("cf", "b", Op.UPDATE, [FieldDiff("score", 0, 100)]),
        ResourcePlan("cf", "c", Op.UNCHANGED, []),
    ])
    assert plan.summary() == {Op.CREATE: 1, Op.UPDATE: 1, Op.UNCHANGED: 1}
    assert plan.has_changes
```

- [ ] **Step 2: Run to verify it fails**

Run: `nix develop -c pytest tests/diff/test_model.py -v`
Expected: FAIL (`ModuleNotFoundError: configarr.diff.model`).

- [ ] **Step 3: Implement** (`configarr/diff/model.py`)

```python
"""Service-agnostic diff data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Hashable


class Op(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    UNCHANGED = "unchanged"
    DELETE = "delete"


@dataclass(frozen=True)
class FieldDiff:
    path: str
    before: Any
    after: Any


@dataclass
class ResourcePlan:
    kind: str
    key: Hashable
    op: Op
    field_diffs: list[FieldDiff] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.op is not Op.UNCHANGED


@dataclass
class Plan:
    resources: list[ResourcePlan] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any(r.changed for r in self.resources)

    def summary(self) -> dict[Op, int]:
        counts: dict[Op, int] = {}
        for r in self.resources:
            counts[r.op] = counts.get(r.op, 0) + 1
        return counts
```

Create `configarr/diff/__init__.py` exporting these:
```python
from configarr.diff.model import Op, FieldDiff, ResourcePlan, Plan

__all__ = ["Op", "FieldDiff", "ResourcePlan", "Plan"]
```

- [ ] **Step 4: Run to verify it passes**

Run: `nix develop -c pytest tests/diff/test_model.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add configarr/diff/__init__.py configarr/diff/model.py tests/diff/
git commit -m "feat(diff): add core plan/diff data model"
```

---

## Task 3: Normalization helpers

**Files:**
- Create: `configarr/diff/normalize.py`
- Test: `tests/diff/test_normalize.py`

Implements the Radarr type-coercion rules from the notes: numeric-string coercion, "absent == default", and dropping masked secrets so they never produce false diffs.

- [ ] **Step 1: Write the failing test**

```python
from configarr.diff.normalize import coerce_scalar, drop_masked_secrets, MASK


def test_coerce_numeric_strings():
    assert coerce_scalar("5") == 5
    assert coerce_scalar("5.0") == 5.0
    assert coerce_scalar("true") is True
    assert coerce_scalar("keep") == "keep"


def test_drop_masked_secrets():
    fields = {"host": "h", "apiKey": MASK, "password": MASK, "port": 8080}
    assert drop_masked_secrets(fields) == {"host": "h", "port": 8080}
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** (`configarr/diff/normalize.py`)

```python
"""Canonicalization helpers to avoid false diffs (see diffing-engine-radarr-notes)."""

from __future__ import annotations

from typing import Any

MASK = "********"  # Radarr/Sonarr return ApiKey/Password fields masked


def coerce_scalar(value: Any) -> Any:
    """Coerce numeric/bool strings so '5' == 5 and 'true' == True."""
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "false"}:
            return low == "true"
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
    return value


def drop_masked_secrets(fields: dict[str, Any]) -> dict[str, Any]:
    """Remove fields whose value is the secret mask; their real value is unknown."""
    return {k: v for k, v in fields.items() if v != MASK}
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat(diff): add normalization helpers`.

---

## Task 4: Generic diff engine

**Files:**
- Create: `configarr/diff/engine.py`
- Test: `tests/diff/test_engine.py`

`diff()` matches current↔desired by `match_key`, deep-compares `normalize()`d dicts, and emits `ResourcePlan`s. Pure function, no I/O.

- [ ] **Step 1: Write the failing test**

```python
from configarr.diff.engine import diff
from configarr.diff.model import Op


def _norm(r):  # identity normalize for the test
    return r


def test_diff_detects_create_update_unchanged():
    current = [{"name": "a", "v": 1}, {"name": "b", "v": 1}]
    desired = [{"name": "a", "v": 1}, {"name": "b", "v": 2}, {"name": "c", "v": 9}]
    plan = diff("cf", current, desired,
                match_key=lambda r: r["name"], normalize=_norm)
    by_key = {r.key: r for r in plan.resources}
    assert by_key["a"].op is Op.UNCHANGED
    assert by_key["b"].op is Op.UPDATE
    assert [(d.path, d.before, d.after) for d in by_key["b"].field_diffs] == [("v", 1, 2)]
    assert by_key["c"].op is Op.CREATE


def test_diff_is_idempotent_on_equal_inputs():
    items = [{"name": "a", "v": 1}]
    plan = diff("cf", items, items, match_key=lambda r: r["name"], normalize=_norm)
    assert not plan.has_changes
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** (`configarr/diff/engine.py`)

```python
"""Generic, service-agnostic differ."""

from __future__ import annotations

from typing import Any, Callable, Hashable

from configarr.diff.model import FieldDiff, Op, Plan, ResourcePlan


def _field_diffs(before: dict, after: dict) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    # Only desired keys drive updates; absent desired keys are left to the
    # provider's build_desired (which already merged defaults/current).
    for key in after:
        if before.get(key) != after[key]:
            diffs.append(FieldDiff(path=key, before=before.get(key), after=after[key]))
    return diffs


def diff(
    kind: str,
    current: list[dict[str, Any]],
    desired: list[dict[str, Any]],
    *,
    match_key: Callable[[dict], Hashable],
    normalize: Callable[[dict], dict],
) -> Plan:
    cur_by_key = {match_key(r): r for r in current}
    plans: list[ResourcePlan] = []
    for d in desired:
        key = match_key(d)
        nd = normalize(d)
        if key not in cur_by_key:
            plans.append(ResourcePlan(kind, key, Op.CREATE, _field_diffs({}, nd)))
            continue
        nc = normalize(cur_by_key[key])
        fds = _field_diffs(nc, nd)
        plans.append(ResourcePlan(kind, key, Op.UPDATE if fds else Op.UNCHANGED, fds))
    return Plan(resources=plans)
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat(diff): add generic diff engine`.

---

## Task 5: ResourceProvider interface

**Files:**
- Create: `configarr/diff/providers/__init__.py`, `configarr/diff/providers/base.py`
- Test: `tests/providers/__init__.py` (no test needed — Protocol only; covered via the pilot)

- [ ] **Step 1: Implement** (`configarr/diff/providers/base.py`)

```python
"""Provider interface: each service/resource implements this."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Hashable, Protocol

from configarr.diff.model import Op, ResourcePlan


@dataclass
class Action:
    op: Op
    key: Hashable
    payload: dict[str, Any]  # full object to POST/PUT


class ResourceProvider(Protocol):
    kind: str

    def match_key(self, resource: dict[str, Any]) -> Hashable: ...
    def fetch_current(self) -> list[dict[str, Any]]: ...
    def build_desired(self) -> list[dict[str, Any]]: ...
    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]: ...
    def to_action(self, plan: ResourcePlan,
                  current: dict | None, desired: dict | None) -> Action: ...
    def apply(self, action: Action) -> None: ...
```

- [ ] **Step 2: Commit** `feat(diff): add ResourceProvider interface`.

---

## Task 6: RadarrCustomFormatProvider

**Files:**
- Create: `configarr/diff/providers/radarr_custom_formats.py`
- Test: `tests/providers/test_radarr_custom_formats.py`

**Read [`diffing-engine-radarr-notes.md`](./diffing-engine-radarr-notes.md) first.** Honor: match by `name`; build spec fields over `/customformat/schema` defaults; full-object POST/PUT; always send `id` on update and ≥1 specification.

- [ ] **Step 1: Write failing tests** (use `responses` to mock the Radarr HTTP API)

```python
import responses
from configarr.diff.providers.radarr_custom_formats import RadarrCustomFormatProvider
from configarr.diff.engine import diff
from configarr.diff.model import Op

BASE = "http://radarr.test"

SCHEMA = [{"name": "Release Title", "implementation": "ReleaseTitleSpecification",
           "negate": False, "required": False,
           "fields": [{"name": "value", "value": ""}]}]


def _provider(config):
    return RadarrCustomFormatProvider(base_url=BASE, api_key="k", config=config)


@responses.activate
def test_create_when_absent():
    responses.get(f"{BASE}/api/v3/customformat", json=[])
    responses.get(f"{BASE}/api/v3/customformat/schema", json=SCHEMA)
    config = {"x265": {"specifications": [
        {"name": "x265", "implementation": "ReleaseTitleSpecification",
         "fields": {"value": "(x|h)265"}}]}}
    p = _provider(config)
    plan = diff(p.kind, p.fetch_current(), p.build_desired(),
                match_key=p.match_key, normalize=p.normalize)
    assert plan.resources[0].op is Op.CREATE


@responses.activate
def test_idempotent_after_apply():
    # current already equals desired → plan must be empty
    existing = [{"id": 7, "name": "x265", "includeCustomFormatWhenRenaming": False,
                 "specifications": [
                     {"name": "x265", "implementation": "ReleaseTitleSpecification",
                      "negate": False, "required": False,
                      "fields": [{"name": "value", "value": "(x|h)265"}]}]}]
    responses.get(f"{BASE}/api/v3/customformat", json=existing)
    responses.get(f"{BASE}/api/v3/customformat/schema", json=SCHEMA)
    config = {"x265": {"specifications": [
        {"name": "x265", "implementation": "ReleaseTitleSpecification",
         "fields": {"value": "(x|h)265"}}]}}
    p = _provider(config)
    plan = diff(p.kind, p.fetch_current(), p.build_desired(),
                match_key=p.match_key, normalize=p.normalize)
    assert not plan.has_changes, plan.resources
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** `RadarrCustomFormatProvider`

Responsibilities (complete implementation in this step):
- `__init__(base_url, api_key, config)` — store, build a `requests.Session` with `X-Api-Key`.
- `kind = "radarr.custom_format"`.
- `match_key(r) -> r["name"]`.
- `fetch_current()` — GET `/api/v3/customformat`, return list as-is.
- `_schema()` — GET `/api/v3/customformat/schema`, cache; index by `implementation`.
- `build_desired()` — for each `name -> definition` in config, construct the resource: `{"name", "includeCustomFormatWhenRenaming": def.get(..., False), "specifications": [...]}`; for each spec, start from the schema template for its `implementation`, set `negate`/`required`, and overlay `fields` (dict → list of `{"name","value"}` merged over schema defaults).
- `normalize(r)` — canonical comparable shape: `{"includeCustomFormatWhenRenaming": bool, "specifications": [sorted/normalized specs]}` where each spec is `{"implementation", "negate", "required", "fields": {name: coerce_scalar(value)}}`; **exclude `id`, server-echoed `name`/`label` on fields, and any masked secrets** (`drop_masked_secrets`). Spec list compared as a set keyed by spec `name`+`implementation` to ignore order.
- `to_action(plan, current, desired)` — CREATE → payload = desired (no id); UPDATE → payload = `{**desired, "id": current["id"]}`.
- `apply(action)` — CREATE: POST `/api/v3/customformat`; UPDATE: PUT `/api/v3/customformat/{id}`. Raise on non-2xx.

- [ ] **Step 4: Run → PASS** (both tests).
- [ ] **Step 5: Commit** `feat(diff): add Radarr custom-format provider`.

---

## Task 7: Apply-then-replan idempotency test (the north star)

**Files:**
- Test: `tests/providers/test_radarr_custom_formats.py` (add)

- [ ] **Step 1: Write the test** — mock an empty instance, run plan (CREATE), call `provider.apply(action)` (mock POST returning the created object with an `id`), then mock GET to return that object and re-run `diff` → assert `not plan.has_changes`.

```python
@responses.activate
def test_apply_then_replan_is_noop():
    created = {"id": 7, "name": "x265", "includeCustomFormatWhenRenaming": False,
              "specifications": [{"name": "x265",
                  "implementation": "ReleaseTitleSpecification",
                  "negate": False, "required": False,
                  "fields": [{"name": "value", "value": "(x|h)265"}]}]}
    responses.get(f"{BASE}/api/v3/customformat", json=[])
    responses.get(f"{BASE}/api/v3/customformat/schema", json=SCHEMA)
    responses.post(f"{BASE}/api/v3/customformat", json=created, status=201)
    config = {"x265": {"specifications": [
        {"name": "x265", "implementation": "ReleaseTitleSpecification",
         "fields": {"value": "(x|h)265"}}]}}
    p = _provider(config)
    plan = diff(p.kind, p.fetch_current(), p.build_desired(),
                match_key=p.match_key, normalize=p.normalize)
    for rp in plan.resources:
        if rp.changed:
            p.apply(p.to_action(rp, None, {d["name"]: d for d in p.build_desired()}[rp.key]))
    # Second run: instance now returns the created CF
    responses.reset()
    responses.get(f"{BASE}/api/v3/customformat", json=[created])
    responses.get(f"{BASE}/api/v3/customformat/schema", json=SCHEMA)
    plan2 = diff(p.kind, p.fetch_current(), p.build_desired(),
                 match_key=p.match_key, normalize=p.normalize)
    assert not plan2.has_changes, plan2.resources
```

- [ ] **Step 2: Run → adjust `normalize`/`build_desired` until it PASSES.** This test is the acceptance gate for the whole architecture.
- [ ] **Step 3: Commit** `test(diff): prove custom-format apply is idempotent`.

---

## Task 8: Plan renderer

**Files:**
- Create: `configarr/diff/render.py`
- Test: `tests/diff/test_render.py`

- [ ] **Step 1: Write the failing test** — `render_plan(plan)` returns a string containing the counts and, for an UPDATE, a `field: before -> after` line.

```python
from configarr.diff.render import render_plan
from configarr.diff.model import Plan, ResourcePlan, Op, FieldDiff

def test_render_shows_changes():
    plan = Plan([ResourcePlan("radarr.custom_format", "x265", Op.UPDATE,
                              [FieldDiff("score", 0, 100)])])
    out = render_plan(plan)
    assert "x265" in out and "score" in out and "100" in out
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `render_plan` using `rich` (Console with `record=True` → `export_text()`), grouping by `op`, showing `kind/key` and indented `FieldDiff`s. Empty plan → "No changes.".
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat(diff): add plan renderer`.

---

## Task 9: CLI `--plan` wiring (read-only)

**Files:**
- Modify: `configarr/__main__.py`
- Test: `tests/test_cli_plan.py`

- [ ] **Step 1: Write the failing test** — invoke the CLI with `--plan` via click's `CliRunner`, a temp config with one Radarr instance + one custom format, and `responses`-mocked endpoints; assert exit 0 and that rendered output mentions the CF name and "create". Assert **no POST/PUT** was issued (plan is read-only).

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — add `@click.option("--plan", is_flag=True, ...)`. When set: for each parsed Radarr instance, build `RadarrCustomFormatProvider`, compute the plan via `diff(...)`, print `render_plan(...)`, and **return before** the existing sync runs (no writes anywhere). When not set: existing behavior, untouched.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat(cli): add read-only --plan for Radarr custom formats`.

---

## Task 10: CI — run the test suite as a flake check

**Files:**
- Create: `nix/checks/pytest.nix`
- Test: `nix flake check`

- [ ] **Step 1: Implement** `nix/checks/pytest.nix` — a `runCommandLocal` that copies `${inputs.self}` to a writable dir and runs `pytest` with a Python env containing the runtime deps + `pytest` + `responses` (build via `python313.withPackages`). Pattern mirrors `nix/checks/treefmt.nix`.

```nix
{ pkgs, inputs, ... }:
let
  py = pkgs.python313.withPackages (ps: with ps; [
    click pydantic pyyaml requests rich pytest responses
  ]);
in
pkgs.runCommandLocal "pytest-check" { } ''
  cp -r ${inputs.self} src
  chmod -R u+w src
  export HOME=$(mktemp -d)
  cd src
  ${py}/bin/pytest -q
  touch $out
''
```

> Note: the runtime API-client deps (`radarr-py` etc.) are not on PyPI; the pilot's tests mock HTTP and import only `configarr.diff.*`, so they don't import the generated clients. Keep `configarr/diff/` import-clean of the generated clients (the provider uses `requests` directly) so this check needs no custom packages.

- [ ] **Step 2: Run** `nix build .#checks.x86_64-linux.pytest -L` → success; then `nix flake check --all-systems` → all pass.
- [ ] **Step 3: Commit** `ci: run pytest as a flake check`.

---

## Task 11: Document the engine

**Files:**
- Modify: `docs/design/diffing-engine-feasibility.md` (mark Phase 0 + pilot done; link the plan)
- Optionally add a short `docs/src/concepts/` page later (out of scope here — book pages are user-facing).

- [ ] **Step 1:** Add a "Status" note to the feasibility doc pointing at the implemented `configarr/diff/` package and `--plan`.
- [ ] **Step 2: Commit** `docs: record diffing-engine pilot status`.

---

## Acceptance criteria

- `nix develop -c pytest` → all green; **`test_apply_then_replan_is_noop` passes** (idempotency proven).
- `nix flake check --all-systems` → all pass (incl. new pytest check, treefmt, actionlint).
- `configarr --plan --config <cfg>` prints a custom-formats plan and performs **zero writes**.
- No change to any existing sync code path when `--plan` is absent.

## Follow-up plans (not this document)

1. Apply-through-engine for custom formats (`--plan`/apply parity) + `DELETED`/`--prune`.
2. Remaining Radarr/Sonarr resources (quality profiles depend on custom formats — enforce ordering).
3. Prowlarr, SABnzbd, Bazarr providers.
4. `--output json` plan for CI/GitOps gating.
