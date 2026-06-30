# gnhf objective — diffing engine: adversarial review, cleanup, strict typing

You are hardening the configarr diffing engine on branch `diffing-engine`. The feature is
functionally COMPLETE and CI-green (engine, registry, runner, `--plan`/`--apply`/opt-in
`--prune`, 27 providers across Radarr/Sonarr/Prowlarr/SABnzbd/Bazarr, all under
`configarr/diff/`). This objective is a QUALITY pass: adversarially find bugs, fix the
open review findings, cut duplication, and raise the typing/lint bar to best-practice
Python. **Do NOT add new features and do NOT change observable behavior** — every existing
test must stay green at every step.

Read first: `docs/design/diffing-engine-rollout.md`, `docs/design/diffing-engine-radarr-notes.md`,
`docs/design/cleanup-objective.md` (this file). Template: `configarr/diff/providers/radarr_custom_formats.py`.

Work the phases IN ORDER, one logical change per iteration/commit, TDD throughout
(behaviour-preserving refactors: rely on the existing tests as the safety net; add tests
before changing behaviour).

## Phase 1 — raise the tooling bar (establish the quality gate first)

- **mypy `--strict`.** Change `nix/checks/mypy.nix` to run `mypy --strict configarr/diff`.
  Fix EVERY resulting error: annotate all functions, remove `: Any` where a real type
  exists, eliminate `# type: ignore` (or justify each with a specific error code), and
  give the registry factory a precise type (not `Callable[[Any], ResourceProvider]`).
- **Real ruff lint ruleset.** Add a `[tool.ruff.lint]` section to `pyproject.toml` selecting
  a strong set — at least `E,F,I,UP,B,SIM,RUF,PTH,RET,C4` — and wire a `ruff check` lint gate
  (extend the treefmt config or add `nix/checks/ruff.nix`) so lint (not just import-sort) is
  enforced in CI. Fix every violation. Do not blanket-ignore rules; justify any per-line
  `noqa` locally.
- Both new/changed gates must pass: `nix flake check --all-systems`.

## Phase 2 — fix the open review findings

- **`_secret_names` ordering (I2):** in the provider-Field providers, `normalize()` reads
  `self._secret_names`, which is populated lazily by `build_desired()`. Make this
  self-enforcing — a lazy property / `_ensure_secret_names()` — so `normalize()` is correct
  even if called before `build_desired()`. Add a test that calls `normalize()` first.
- **Dedupe-count tests (I3):** add an HTTP-call-count test (`responses` `call_count == 1`
  for the list endpoint per plan) for ALL providers that call `fetch_current()` inside
  `build_desired()` (notifications, indexers, quality_profiles, bazarr_language_profiles,
  …), not just download_clients — so a B-regression can't slip back in.
- **Apply-payload secret test:** add a test that, on an UPDATE with an unchanged secret,
  asserts the PUT body carries the `"********"` mask sentinel (the server's "keep existing"
  protocol) rather than an empty string or omission — locking in the highest-risk path.
- **`run_apply` double `build_desired()`:** capture desired from the plan computation (or
  document why the second call is safe) so apply doesn't re-`build_desired()` and risk a
  TOCTOU gap.
- **DELETE `to_action` guard:** add `assert current is not None` (clear message) on the
  DELETE branch in providers that support prune.
- **Stale counts / docstrings:** fix the conformance test's hardcoded "26 providers" (it's
  27); remove other stale counts; verify `bazarr_providers` mask handling matches Bazarr's
  actual sentinel (it is a Python app — confirm vs the legacy `configarr/bazarr/*`).

## Phase 3 — adversarial bug-hunt

Each iteration, pick ONE subsystem (an engine function, the runner, or a provider family)
and act as a hostile reviewer: enumerate edge cases that could break it, write a test that
EXPOSES the weakness (red), then fix it (green). Probe at least: empty/None config sections;
servers returning unexpected/extra fields; secret fields with privacy but no value; enum/id
vs name coercion (Quality/Language); list-order-sensitive resources; prune safety (never
deletes a matched/managed resource, never runs without `--prune`); apply ordering
dependencies (CF before QP); idempotency under value-type drift ("5" vs 5, true vs 1).
Record each probe and its outcome in the gnhf notes. If a probe finds no bug, note that and
move on. Do not fabricate fixes for non-bugs.

## Phase 4 — DRY / best-practice refactor (behaviour-preserving)

Duplication is heavy: `to_action` in 19 files, `raise_for_status` in 18, `X-Api-Key` in 12,
`_schema` in 7, `_overlay_fields` in 5. Extract shared abstractions WITHOUT changing
behaviour — one small extraction per commit, full suite green after each:
- A base `HttpProvider` (session + `X-Api-Key`, `_url`, `_get/_post/_put` with
  `raise_for_status`) that all providers use.
- A `ProviderFieldMixin` for the repeated `/schema` fetch+cache, `_overlay_fields`,
  schema-privacy secret handling, and `forceSave` write — used by download_clients,
  notifications, indexers, applications, prowlarr_download_clients.
- A shared `to_action` default on the base where the boilerplate is identical.
Keep each provider a thin, readable specialization. Do NOT collapse genuinely
service-specific logic into the base. Aim to materially cut the 2,651-line provider total
while keeping every test green.

## Phase 5 — consistency & docs

Unify the two masked-secret helpers (`drop_masked_secrets` vs `drop_secret_fields`) into one
clear API; add concise docstrings to each public provider/class; remove dead code; ensure
error messages are uniform and name the offending resource. Update the design-doc Status
sections to reflect the quality pass.

## Invariants (every iteration)

- `configarr/diff/*` MUST NOT import the nix-only generated clients (`radarr`/`sonarr`/…) or
  `configarr.sync`; HTTP via `requests`. Tests import only `configarr.diff.*` and
  `configarr.config`/`configarr.models`.
- Behaviour-preserving: no existing test may be weakened or deleted to make a refactor pass.
  TDD for new tests (red first). One logical change per commit; keep every file treefmt-clean.
- After each iteration, ALL must pass before committing: `nix develop -c pytest -q`,
  `nix flake check --all-systems` (which now includes `mypy --strict` and the ruff lint gate).

## Done when

`mypy --strict configarr/diff` is clean; the ruff lint gate is green with a real ruleset;
all open review findings (Phase 2) are fixed with tests; the adversarial probes (Phase 3)
are documented in the notes with no open bugs; provider duplication is materially reduced via
shared base/mixins with the full suite still green; and `nix flake check --all-systems` passes.
