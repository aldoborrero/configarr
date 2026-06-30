# gnhf objective — diffing engine: harden, complete, add apply

You are continuing work on the configarr diffing engine on branch `diffing-engine`. The
plan phase is already largely built under `configarr/diff/` (engine, registry, runner,
the read-only `--plan` CLI, and 16 providers across Radarr/Sonarr/Prowlarr/SABnzbd/Bazarr).
This objective HARDENS and COMPLETES it — do not rebuild what exists.

Read first: `docs/design/diffing-engine-rollout.md` (work-list + per-provider recipe),
`docs/design/diffing-engine-radarr-notes.md` (API contract), `docs/design/diffing-engine-feasibility.md`,
`skills/configarr-config/references/schema.md` (user-facing keys), and the legacy
implementations `configarr/{radarr,sonarr,prowlarr,sabnzbd}.py`, `configarr/bazarr/*`.
Use `configarr/diff/providers/radarr_custom_formats.py` as the provider template.

Work the tasks IN ORDER, one logical change per iteration/commit, TDD throughout.

## 1. Fix the review findings

- **A. Secret detection from schema, not a static name list.** `configarr/diff/normalize.py`
  uses a fixed `SECRET_FIELD_NAMES` allowlist, so provider-Field secrets not named
  `apiKey`/`password`/`passKey` (e.g. Telegram `botToken`, Pushover `userKey`, webhook
  secrets) produce a **perpetual false UPDATE** — desired keeps the real value while
  current comes back masked `"********"`. Derive secret-ness from the `/schema` field
  **privacy** metadata so any privacy=apiKey/password field is skipped in `normalize`.
  Add a regression test using a schema secret field NOT named apiKey/password.
- **B. Remove the double-fetch / TOCTOU.** Many providers call `self.fetch_current()`
  inside `build_desired()` while the runner ALSO calls `fetch_current()` → 2× GETs per
  plan (4× in the apply harness), and plan vs apply can observe different state.
  Refactor so current state is fetched ONCE and reused (cache on the provider, invalidated
  after `apply()`, or threaded through). Keep the `ResourceProvider` contract coherent;
  update `runner.py` and `tests/conftest.py` helpers to fetch once.
- **C. Validate `implementation` locally.** Provider-Field providers (radarr/sonarr
  `download_clients` & `notifications`; prowlarr `indexers`/`applications`/`download_clients`)
  currently send a `None` implementation when config omits it, yielding an opaque server
  422. Raise a clear `ValueError` naming the resource, matching the legacy behavior.
- **D. quality_profiles must honor `language`.** `configarr/diff/providers/quality_profiles.py`
  silently ignores the user `language` config key (Radarr-only). Resolve it as the legacy
  does (language name → Language id/object) and include it in the built profile; add a test.
- **E. Conformance test must cover all services.** `tests/diff/test_conformance.py` feeds
  only a Radarr config, so 18 of 26 registered providers are never isinstance-checked.
  Extend the config fixture to include one instance of every service (radarr, sonarr,
  prowlarr, sabnzbd, bazarr) so all registered providers are verified.

## 2. Implement the missing provider — `bazarr.language_profile` (work-list #17)

Per `docs/design/diffing-engine-rollout.md` #17 and the legacy `configarr/bazarr/languages.py`:
profiles listed in config are rebuilt and overwrite the server copy; profiles only on the
server are preserved; languages resolve by name→code (drop unknown); `cutoff` must be a
listed language. Match by profile `name`. Build the provider, register it, and add a
genuine responses-mocked idempotency test (current==desired → empty plan; apply-then-replan
→ empty).

## 3. Apply + prune phase

- Add an **apply path** (e.g. an `--apply` flag, or route the default sync through the
  engine) that executes a plan's actions provider-by-provider in the existing safe order
  (custom formats before quality profiles, etc.), using each provider's `apply()`.
- Add **`DELETE` + opt-in `--prune`**: providers expose deletion (DELETE endpoint); the
  engine emits `DELETE` for current resources absent from desired; gated behind `--prune`
  (per kind/instance). Default stays **additive** (no deletion). This also resolves the
  delay-profile orphan risk.
- Add round-trip tests: apply a plan → re-plan is empty; prune removes only unmanaged
  resources and leaves managed ones intact.

## 4. Docs

Update `skills/configarr-config/references/schema.md` where it now misstates behavior
(SABnzbd servers/categories are no longer "always UPDATED"; `implementation` is validated
locally). Update the Status sections of `docs/design/diffing-engine-feasibility.md` and
`diffing-engine-rollout.md` as phases complete.

## Invariants (every iteration)

- `configarr/diff/*` MUST NOT import the nix-only generated clients (`radarr`/`sonarr`/…)
  or `configarr.sync`; talk HTTP via `requests`. Tests import only `configarr.diff.*` and
  `configarr.config`/`configarr.models` — never `configarr.sync`/`configarr.__main__`.
- TDD: write the failing test first. One logical change per commit. Keep every file
  treefmt-clean (run `nix fmt`).
- After each iteration, BOTH must pass before committing:
  `nix develop -c pytest -q` and `nix flake check --all-systems`.

## Done when

All 17 work-list providers (including `bazarr.language_profile`) are registered with
passing idempotency tests; review findings A–E are fixed; `--apply` and opt-in `--prune`
work with round-trip tests; `nix flake check --all-systems` passes; the docs above are
consistent with the implementation.
