# Feasibility study: a proper diffing engine for configarr

**Status:** Study / exploration (no implementation)
**Branch:** `diffing-engine`
**Goal:** Assess whether configarr can be evolved into a tool that configures *every*
aspect of any *arr app and applies changes with confidence that they "won't break" —
i.e. compute a real diff, show a plan, and apply it idempotently and safely.

This document is an assessment of feasibility and a proposed design. It deliberately
does **not** change runtime code.

---

## Status

Phase 0 (scaffolding) and the Phase 1 Radarr custom-format pilot are **implemented**.
The implementation lives under `configarr/diff/` — `model`, `normalize`, `engine`,
`providers/base`, `providers/radarr_custom_formats`, `render`, `runner`.

- A read-only `--plan` CLI flag previews Radarr custom-format changes before applying.
- Idempotency is confirmed by an apply-then-replan test (second plan is always empty);
  the full pytest suite runs in CI via `nix/checks/pytest.nix`.
- See the [implementation plan](./diffing-engine-plan.md) for the detailed phase design.
- Rolling the provider pattern out to the remaining resources and services is tracked as
  follow-up work (per the plan's "Follow-up plans" section).

---

## 1. What "won't break" actually means

Reading the goal precisely, a "proper diffing engine" needs four properties the
current tool only partially has:

1. **Completeness** — every user-facing field of every resource is representable and
   manageable, not just the subset each `sync_*` method happens to read.
2. **Diff accuracy** — the tool knows, per field, what will change before it writes,
   so re-running an unchanged config is a true no-op.
3. **Preview (plan) before apply** — a `--plan` view of exactly what would change,
   honored uniformly across all services.
4. **Safety** — no silent clobbering of fields the user didn't set, no orphaned
   resources, and a predictable answer to "what happens to things on the server that
   aren't in my config?"

---

## 2. Current architecture: a "sync-and-report" model

configarr today is a *sync-and-report* tool, not a diff engine. Per the codebase
survey (`configarr/sync.py`, `radarr.py`, `sonarr.py`, `prowlarr.py`, `sabnzbd.py`,
`bazarr/*`):

- Each `sync_*` method reads server state to **locate** a matching resource, then
  **writes unconditionally** (POST/PUT) and reports a status.
- `SyncStatus` is `{CREATED, UPDATED, UNCHANGED, FAILED}` — there is **no `DELETED`**;
  sync is purely **additive** (nothing on the server is ever pruned).
- Change detection is shallow and inconsistent. Some resources do partial field
  merges; many blind-write and always report `UPDATED`.
- `--dry-run` is **only** implemented inside the Bazarr client; Radarr/Sonarr/
  Prowlarr/SABnzbd ignore it entirely.

### 2.1 Matching strategy is per-resource and inconsistent

| Pattern | Where | Risk |
|---|---|---|
| Exact `name`, case-sensitive | most arr/prowlarr resources | rename ⇒ duplicate |
| Case-**insensitive** `name` | Prowlarr download clients only | collisions, inconsistent with siblings |
| `path` exact | root folders | fine |
| Tuple `(usenet_delay, torrent_delay, preferred_protocol)` | delay profiles | **cannot update** — changing a value creates a new profile |
| Singleton | naming, bazarr general/sonarr/radarr | n/a |

### 2.2 Update fidelity varies wildly

- **Field-merge (good-ish):** naming config, quality definitions, download clients,
  notifications — but they only overlay *configured* fields; unset schema fields fall
  back to **schema defaults**, not the resource's previous value (lossy).
- **Whole-object rebuild:** custom formats, quality profiles, prowlarr indexers/apps.
- **Write-once / cannot update:** Sonarr release profiles (returns `UNCHANGED` if a
  name match exists), delay profiles (value-tuple match).
- **Blind write, status meaningless:** SABnzbd servers & categories — the `create`
  and `update` branches call `set_config(...)` with identical arguments, so
  `CREATED`/`UPDATED` is not derived from any comparison.
- **Always `UPDATED`:** naming config and quality definitions report `UPDATED` even
  when nothing changed.

### 2.3 Consequences

- Re-running the same config is **not** a clean no-op in the logs (false `UPDATED`s).
- Logs can't tell an operator *what* changed.
- Config must be exhaustive or it silently resets fields to schema defaults.
- No preview, no prune, no rollback.

---

## 3. Target design: plan → apply

The central idea is to split today's monolithic `sync_*` into three composable stages
behind a uniform interface, so the diff logic lives in **one** place and each service
only supplies adapters.

```
desired  = build_desired(config)        # pure: YAML → normalized desired resources
current  = fetch_current()              # read server state, normalized the same way
plan     = diff(current, desired)       # per-field changes, per resource, + matches
report(plan)                            # --plan / dry-run: show it, change nothing
apply(plan)                             # execute only the resources that actually differ
```

### 3.1 Core abstractions

```python
class ResourceProvider(Protocol):
    kind: str                      # "radarr.quality_profile", ...
    def match_key(self, r) -> Hashable: ...     # ONE unified identity per kind
    def fetch_current(self) -> list[Resource]: ...
    def build_desired(self, cfg) -> list[Resource]: ...
    def normalize(self, r) -> dict: ...         # canonical, comparable shape
    def apply(self, action: Action) -> None: ... # CREATE | UPDATE(fields) | DELETE

@dataclass
class FieldDiff:    path: str; before: Any; after: Any
@dataclass
class ResourcePlan: kind: str; key: Hashable
                    op: Literal["create","update","unchanged","delete"]
                    field_diffs: list[FieldDiff]
@dataclass
class Plan:         resources: list[ResourcePlan]   # + summary counts
```

`diff()` is generic: match `current`↔`desired` by `match_key`, deep-compare the
`normalize()`d dicts, and emit `FieldDiff`s. No service-specific logic in the differ.

### 3.2 The hard part: three-way comparison (avoiding lossy merges)

A correct update needs **three** inputs, not two:

- `desired` — what the user wrote
- `current` — what's on the server
- `schema_default` — the API's default for unset fields

Rule: a field is only part of an update if the user **set it** *and* it differs from
`current`. Fields the user didn't set are **left at their current server value**, never
reset to `schema_default`. This directly fixes the current "lossy field merge" bug
(§2.2) and is the crux of "won't break."

### 3.3 Unified matching

Replace the ad-hoc per-resource matching with a declared identity per kind:
- Names matched case-insensitively **and** consistently everywhere (or a documented
  per-kind choice), with rename detection where the API exposes a stable id.
- Delay profiles must move from value-tuple identity to a stable id (or an explicit
  user-assigned name) so they become updatable instead of duplicating.

### 3.4 Plan/dry-run as a first-class, uniform mode

`--plan` builds the `Plan` and prints it; `apply` re-uses the same `Plan`. Dry-run
becomes "build plan, skip apply" — identical across all services, removing the
Bazarr-only special case.

### 3.5 Deletion / pruning (opt-in)

Introduce a `DELETED` status and an opt-in `--prune` (per kind / per instance) so the
config can optionally be the source of truth. Default stays additive for safety.

---

## 4. Feasibility per service

| Area | Difficulty | Why |
|---|---|---|
| Radarr/Sonarr custom formats, quality profiles | **Medium** | already read-then-write; need normalize + field diff + stable ids |
| Radarr/Sonarr download clients, notifications | **Medium** | fix lossy merge via three-way compare |
| Quality definitions, naming | **Easy** | already field-oriented; just add real comparison + correct status |
| Delay profiles | **Hard-ish** | identity model change (value-tuple → id); migration of existing dupes |
| Sonarr release profiles | **Medium** | currently write-once; needs an update path |
| Prowlarr indexers/apps/clients | **Medium** | unify case sensitivity; download-client uses raw HTTP (lib gap) |
| SABnzbd servers/categories | **Medium** | API is set-only; need a read+compare layer to make status meaningful |
| SABnzbd misc | **Easy** | already per-key |
| Bazarr general/sonarr/radarr | **Medium** | form-POST settings; need GET-current to compare; field names are passthrough |
| Bazarr providers | **Medium** | partial state read today; extend to provider-field compare |
| Bazarr language profiles | **Medium** | batch all-or-nothing; want per-profile diff + per-item status |

**No blockers found.** Every service exposes enough read API to compute a current
state; the work is uniformly "add a normalize + compare layer and a stable identity,"
not fighting the upstream APIs. The two genuinely awkward spots are (a) SABnzbd's
set-only config API (solved by reading full config and diffing client-side, which the
code already fetches) and (b) Bazarr's form-encoded settings with no allow-list
(solved by comparing against a GET of current settings).

---

## 5. Risks

1. **Normalization fidelity** — false diffs if server coerces types (bools→`1/0`,
   trailing slashes, ordering of lists). Mitigation: per-kind canonicalizers + golden
   tests that assert "config applied once ⇒ second plan is empty."
2. **Schema defaults vs. nulls** — Prowlarr already substitutes `None`→default to dodge
   a NullReferenceException; three-way compare must encode these quirks.
3. **Identity migration** — switching delay-profile identity can strand existing
   duplicates; needs a one-time reconciliation and clear messaging.
4. **Scope creep** — "configure every aspect" is unbounded; must be staged per resource
   behind the same engine rather than a big-bang rewrite.
5. **Test coverage gap** — there is currently **no test suite**. A diff engine without
   idempotency tests will regress; tests are a prerequisite, not an afterthought.

---

## 6. Proposed incremental path (no big-bang)

The engine can be introduced *alongside* the current code, one resource at a time:

1. **Phase 0 — scaffolding:** add `Plan`/`FieldDiff`/`ResourcePlan` types, a generic
   `diff()`, a plan renderer, and `--plan`/`--dry-run` plumbing in `sync.py`. Add
   `DELETED` to `SyncStatus`. No behavior change yet.
2. **Phase 1 — pilot:** convert one well-behaved resource (Radarr **custom formats**)
   to the provider interface; add idempotency tests proving second run = empty plan.
3. **Phase 2 — roll out** the provider interface to the remaining Radarr/Sonarr
   resources, then Prowlarr, SABnzbd, Bazarr — each gated by idempotency tests.
4. **Phase 3 — fix identity** (delay/release profiles) and add opt-in `--prune`.
5. **Phase 4 — completeness pass:** widen each provider to cover every documented
   field (the "configure every aspect" goal), driven by `reference/schema.md`.

Each phase is independently shippable and leaves the tool working.

---

## 7. Recommendation

**Feasible and worth doing, incrementally.** The current design is the main obstacle,
not the upstream APIs: change detection is shallow, matching is inconsistent, and
dry-run/plan is missing everywhere but Bazarr. A plan→apply engine with a three-way
(desired/current/default) field comparison and a unified identity model directly
delivers "configure every aspect" + "apply knowing it won't break."

Recommended first concrete step (a separate task, not this study): **Phase 0 + Phase 1
pilot on Radarr custom formats, with idempotency tests** — small, low-risk, and it
proves the engine end-to-end before committing to the full rollout.

### Open questions for the maintainer

- Should the config become the **source of truth** (prune by default) or stay additive
  with opt-in `--prune`?
- Is a human-readable plan enough, or is machine-readable (JSON) plan output wanted for
  GitOps/CI gating?
- Acceptable to change delay/release-profile identity (one-time reconciliation), or must
  existing setups be preserved exactly?
