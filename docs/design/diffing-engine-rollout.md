# Diffing Engine — Rollout Plan (all services) — gnhf-ready

> **Status:** complete. All 17 work-list providers below are implemented and
> registered across Radarr, Sonarr, Prowlarr, SABnzbd, and Bazarr, each gated by an
> idempotency test (`configarr/diff/`, see [feasibility](./diffing-engine-feasibility.md),
> [pilot plan](./diffing-engine-plan.md), [Radarr API notes](./diffing-engine-radarr-notes.md)).
> Beyond the read-only `--plan` view, `--apply` executes plans in safe registry order
> and opt-in `--prune` emits `DELETE` for unmanaged resources (additive by default).
> Review findings A–E are fixed. The work-list below is retained as the per-provider
> recipe and an index of what shipped.

This plan is written to be executed either by **subagent-driven-development** (one
provider per task) or autonomously by **[gnhf](https://github.com/kunchenguid/gnhf)**
(loop-until-green). The work-list below is the per-iteration unit: each row = one
provider + its idempotency test.

---

## How to run it with gnhf

`gnhf` runs an agent in a loop, commits per successful iteration, rolls back failures,
and stops when a command succeeds. The test suite is the steering wheel, so the
`--stop-when` gate and the per-provider idempotency tests are what make it converge.

```bash
cd /home/aldo/Dev/aldoborrero/configarr-diffing   # the diffing-engine worktree

gnhf "Extend the configarr diffing engine to ALL services, following \
docs/design/diffing-engine-rollout.md. Phase 0 and the Radarr custom-format provider \
under configarr/diff/ are the template. FIRST complete Phase A (rollout enablers: \
provider registry, --service/--instance routing in the runner, a mypy conformance \
flake check, shared test fixtures, and the full-replace current-merge guard). THEN \
implement ONE provider per iteration from the work-list in that doc, in the listed \
order (custom formats before quality profiles). For each provider: build_desired \
(merging desired over CURRENT for full-replace resources, over /schema defaults for \
provider-Field resources), secret-skipping normalize, name->id matching, full-object \
apply, register it in the provider registry, and add a responses-mocked idempotency \
test (apply once, re-plan == empty). INVARIANTS: configarr/diff/* must never import \
the nix-only generated clients (radarr/sonarr/...) or configarr.sync; tests import \
only configarr.diff.* and configarr.config/models; follow TDD (failing test first); \
one provider per commit; keep every file treefmt-clean. After each iteration run \
'nix develop -c pytest -q' and 'nix flake check --all-systems' — both MUST pass." \
  --agent claude \
  --worktree \
  --max-iterations 60 \
  --max-tokens 40000000 \
  --stop-when "nix develop -c pytest -q && nix flake check --all-systems"
```

Notes:
- `--worktree` keeps each iteration isolated (other agents may be active in sibling checkouts).
- Verify flag names/semantics with `gnhf --help` first. If `--stop-when` only signals
  "good enough", back it with a completeness check (see **Done gate** below) so it can't
  stop with services missing.
- No `--push`: keep it local for review (the GHCR Docker workflow triggers on `v*` tags).
- For subagent-driven execution instead, treat each work-list row as one task and apply
  the two-stage review per the pilot.

---

## Phase A — rollout enablers (do these FIRST)

These remove the pilot's hardcoding and make every subsequent provider a drop-in. They
also resolve the two "Important" items from the pilot's final review.

### A1. Provider registry
- Create `configarr/diff/registry.py`: a mapping of `kind -> provider factory`, plus
  `providers_for(config, service, instance)` that yields the provider instances to plan,
  honoring optional `service`/`instance` filters.
- Each provider self-registers (decorator or explicit registration list).
- `runner.run_plan(config, service=None, instance=None)` iterates the registry instead of
  hardcoding Radarr custom formats.
- Test: registry returns the expected providers for a multi-service/multi-instance config,
  and filtering by `service`/`instance` narrows correctly.

### A2. CLI filter routing
- `configarr/__main__.py`: pass the existing `--service`/`--instance` values into
  `run_plan(...)` so `--plan --service radarr --instance uhd` works. Remove the
  "filters ignored" warning once honored.
- Test (client-free, via the runner): filters select the right providers.

### A3. Machine-checked provider conformance
- Add `nix/checks/mypy.nix` (mirror `nix/checks/pytest.nix`) running `mypy configarr/diff`
  with `types-requests`. Make `ResourceProvider` the typed seam the runner/registry depend
  on (not the concrete classes), so a divergent provider fails type-check in CI.
- Optionally mark `ResourceProvider` `@runtime_checkable` and add a test asserting each
  registered provider `isinstance`-conforms.

### A4. Shared test fixtures
- Move the duplicated `SCHEMA`/config/HTTP-mock helpers into `tests/conftest.py` so each
  new provider test reuses them (reduces drift as providers multiply).

### A5. Full-replace current-merge guard
- For full-replace resources (everything except where noted), `build_desired` MUST merge
  desired over **current** (then over `/schema` defaults), per
  [Radarr notes §1](./diffing-engine-radarr-notes.md). The custom-format pilot overlays
  schema-only because CF has no server-managed fields; do NOT copy that shortcut.
- Add an engine-level safeguard or per-provider test that surfaces **current-only keys**
  so a full-replace plan can't under-report "unchanged" while apply would reset fields.

**Phase A done gate:** registry-driven `--plan` works with filters; `nix/checks/mypy.nix`
green; conftest fixtures in use; `nix flake check --all-systems` passes.

---

## Universal per-provider recipe (every work-list row)

Each provider mirrors `RadarrCustomFormatProvider`:

1. **`kind`** = `"<service>.<resource>"`.
2. **`fetch_current()`** → GET the list endpoint.
3. **`_schema()`** (provider-Field resources only) → GET the `/schema` endpoint, cached,
   indexed by `implementation`.
4. **`build_desired()`** → from the parsed config section, build full objects:
   merge desired over current (full-replace kinds) and over schema defaults
   (provider-Field kinds); emit provider `fields` as `[{name,value}]`.
5. **`normalize()`** → canonical comparable shape: `coerce_scalar` values,
   `drop_masked_secrets`, compare enums/Quality/Language **by id**, drop server-echoed
   `name`/`label`, preserve semantic list order (quality `items`), sort unordered lists.
6. **`match_key`** → `name` (or the documented per-kind key); address by `id`.
7. **`to_action`/`apply`** → CREATE POST, UPDATE PUT `/{id}` with the full object;
   pass `?forceSave=true` for provider resources to skip the live connectivity test.
8. **Register** in `configarr/diff/registry.py`.
9. **Idempotency test** (the acceptance gate): mock current==desired → empty plan; and
   apply-then-replan → empty plan.

Keep `configarr/diff/*` free of generated-client imports; talk HTTP via `requests`.

---

## Work-list (one row = one provider = one iteration)

Ordering matters where noted (dependencies). Per-resource keys are drawn from
[schema.md](../../skills/configarr-config/references/schema.md) (user-facing YAML) and
[Radarr notes](./diffing-engine-radarr-notes.md) (API shapes).

### Radarr / Sonarr (`configarr/diff/providers/`)
| # | kind | config section | endpoint | match key | schema? | merge | notes |
|---|---|---|---|---|---|---|---|
| ✅ | `radarr.custom_format` | `custom_formats.definitions` | `/customformat` | name | yes | schema-overlay | DONE (pilot) |
| 1 | `*.quality_profile` | `profiles.quality_profiles.definitions` | `/qualityprofile` | name | `/qualityprofile/schema` | over current | **after custom formats**: `FormatItems` must list every CF on the instance; `items` order is semantic; cutoff by id |
| 2 | `*.quality_definition` | `profiles.quality_definitions` | `/qualitydefinition` | quality name | no | over current | only min/max/preferred per listed quality; fix "always UPDATED" |
| 3 | `*.naming` | `settings.media_management` | `/config/naming` | singleton id | no | over current | full-replace; Radarr vs Sonarr field sets differ |
| 4 | `*.root_folder` | `settings.root_folders` | `/rootfolder` | path | no | n/a | create-only is fine; no update semantics |
| 5 | `*.delay_profile` | `profiles.delay_profiles` | `/delayprofile` | **stable id** (see A) | no | over current | move OFF value-tuple identity so updates work (Radarr notes §3 / feasibility §3.3) |
| 6 | `sonarr.release_profile` | `profiles.release_profiles` | `/releaseprofile` | name | no | over current | **Sonarr-only**; today write-once — add real update path |
| 7 | `*.download_client` | `download_clients.definitions` | `/downloadclient` | name | `/downloadclient/schema` | over current | provider-Field; secret-skip apiKey/password; `forceSave` |
| 8 | `*.notification` | `notifications.definitions` | `/notifications` | name | `/notifications/schema` | over current | provider-Field; `on_import_complete` Sonarr-only |

> Radarr and Sonarr share `ProviderControllerBase`/`SchemaBuilder`, so each provider above
> should be parameterized by service (base path differs only by host); Sonarr deltas:
> series/season/episode naming fields, release profiles, quality set.

### Prowlarr
| # | kind | config section | endpoint | match key | schema? | notes |
|---|---|---|---|---|---|---|
| 9 | `prowlarr.indexer` | `indexers.definitions` | `/indexer` | name | `/indexer/schema` | provider-Field; `app_profile_id`, `redirect` indexer-only |
| 10 | `prowlarr.application` | `applications.definitions` | `/applications` | name | `/applications/schema` | `sync_level` must be a valid `ApplicationSyncLevel` |
| 11 | `prowlarr.download_client` | `download_clients.definitions` | `/downloadclient` | name (case-insensitive) | `/downloadclient/schema` | unify case handling; None→default substitution; `categories` hardcoded empty |

### SABnzbd
| # | kind | config section | endpoint | match key | notes |
|---|---|---|---|---|---|
| 12 | `sabnzbd.server` | `servers` | config API | name | API is set-only → GET full config, diff client-side to make status meaningful; bools→1/0 |
| 13 | `sabnzbd.category` | `categories` | config API | name | same set-only handling |
| 14 | `sabnzbd.misc` | `misc` | config API | singleton | only the allow-listed misc keys; bools→1/0 |

### Bazarr
| # | kind | config section | endpoint | match key | notes |
|---|---|---|---|---|---|
| 15 | `bazarr.general` / `bazarr.sonarr` / `bazarr.radarr` | `general`/`sonarr`/`radarr` | `/system/settings` | singleton per section | GET current settings to compare; form-POST `settings-<section>-<field>`; bools lower-cased |
| 16 | `bazarr.provider` | `providers` | `/system/settings` | provider name | `submate`→`whisperai` rename; `enabled_providers` additively managed |
| 17 | `bazarr.language_profile` | `language_profiles` | `/system/languages/profiles` | name | per-profile diff; rebuild listed, preserve unlisted; languages resolve by name→code |

---

## Apply-through-engine + prune (final phase)

After the providers exist (plan parity), wire **apply**:
- Add an `apply`/`--apply` path (or make the default sync route through the engine) that
  executes the plan's actions provider-by-provider, in the existing safe order (custom
  formats before quality profiles, etc.).
- Add **`DELETE` + opt-in `--prune`** (per kind/instance): surface server resources absent
  from config; default stays additive.
- Replace the legacy `sync_*` paths once each resource's engine provider is at parity, then
  delete the dead code.

---

## Done gate (overall completeness)

The rollout is complete when:
- Every work-list row has a registered provider with a passing idempotency test.
- `nix flake check --all-systems` passes (pytest + mypy + treefmt + actionlint + packages).
- `configarr --plan` (optionally `--service/--instance`) renders a plan for every service
  and performs zero writes.
- A second `--plan` immediately after an apply is empty for every resource (engine-wide
  idempotency).

A useful machine check for `gnhf --stop-when` / CI: a test that asserts the registry has a
provider for each `kind` in the `sync.py` `_print_section` inventory, each with a passing
idempotency test — so the loop can't stop with resources missing.
