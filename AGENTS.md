# AGENTS.md

Project-specific guidance for working in this repository. `CLAUDE.md` is a symlink
to this file.

## What this is

configarr is a Python CLI that declaratively syncs Radarr, Sonarr, Prowlarr,
Bazarr, and SABnzbd from a single `configarr.yml`. It talks to each app's HTTP API
and reconciles the live config toward what the file declares. Distributed as a Nix
flake and a Docker image on GHCR.

## Commands

This is a Nix flake (numtide/blueprint, sources under `nix/`). Prefer these:

- `nix run . -- --config configarr.yml` — run the CLI (args after `--`).
- `nix build` — build configarr (`.#default`). `nix build .#docs` — build the
  mdbook site. `nix build .#docker` — build the container image.
- `nix develop` — dev shell (python313, ruff, mypy, and the mdbook toolchain).
- `nix fmt` — format the tree with treefmt (nixfmt, ruff, yamlfmt). **Formatting is
  CI-enforced** via `treefmt --ci`; run it before committing.
- `nix flake check` — runs every check (treefmt, actionlint, the docs/mdbook
  build, and package builds). This is the full local gate.
- `mdbook serve docs` — live-preview the docs (from the dev shell).

Inside the dev shell the package is importable for quick validation, e.g.
`python -c "from pathlib import Path; from configarr.config import parse_config; parse_config(Path('configarr.yml'))"`
checks that a config passes the Pydantic models without syncing.

## Testing

The suite is mocked (`responses`) and runs offline under `nix flake check`. A
separate **live** integration suite in `tests/integration/` exercises the real
create → idempotent → prune → recreate round-trip against an actual Radarr; it is
**skipped** unless `CONFIGARR_IT_RADARR_URL` and `CONFIGARR_IT_RADARR_KEY` are set,
so it never affects the normal suite. Run it locally against a throwaway container:

```sh
docker run -d --name radarr -p 7878:7878 lscr.io/linuxserver/radarr:latest
# wait for it, then read the key: docker exec radarr cat /config/config.xml
CONFIGARR_IT_RADARR_URL=http://localhost:7878 CONFIGARR_IT_RADARR_KEY=<key> \
  nix develop --command python -m pytest tests/integration
```

CI runs the same thing on relevant PRs via `.github/workflows/integration.yml`
(it starts the container and captures the key automatically).

## Architecture

The config flows through three layers — keep this model when reading or changing
behavior:

1. **`configarr/config.py`** — `parse_*` functions read the nested YAML the user
   writes and **reshape/rename** keys (e.g. quality-profile `upgrades_allowed` →
   internal `upgrade.allowed`), and apply `${VAR}` substitution + `.env` loading.
2. **`configarr/models.py`** — Pydantic models are the authoritative top-level
   section contract and defaults per instance. Most sections are `dict[str, Any]`
   passthrough; only `TrashConfig` is strictly typed.
3. **`configarr/providers/*.py`** — one `ResourceProvider` per resource kind
   (custom formats, quality profiles, indexers, SABnzbd servers, Bazarr settings,
   …). Each reads the inner per-resource config and talks HTTP directly via
   `requests` — there are **no generated API clients** (the old per-service
   `sync.py`/`radarr.py`/`sonarr.py`/`bazarr/` modules and the `nix/packages/*-py`
   clients were deleted).

Orchestration is a generic plan→apply diffing engine, not per-service sync code:

- **`configarr/engine.py`** — the generic diff (current vs. desired → CREATE /
  UPDATE / DELETE / UNCHANGED per resource).
- **`configarr/registry.py`** — the `REGISTRY` list of provider registrations and
  `providers_for(...)`, which yields the providers to run for a config honoring the
  optional `--service`/`--instance` filters. `REGISTRY` order is fixed; the one
  real invariant is **custom formats before quality profiles** within an instance
  (FormatItems must reference CFs that already exist). SABnzbd is **not** first.
- **`configarr/runner.py`** — `run_plan` / `run_apply` drive the engine over those
  providers and format the report.
- **`configarr/__main__.py`** — the Click CLI.
- **`configarr/trash/`** — the TRaSH-Guides import pass.

Behavioral facts that are easy to get wrong (all documented in the book): YAML
keys are **not** the *arr API keys; `--plan`/`--dry-run` (aliases) is a
**universal** read-only preview across every service (there is **no `--verbose`
flag**); apply is the default (no flag); `--service`/`--instance` scope the run,
`--prune` also deletes unmanaged resources for providers that support it,
`--output text|json` selects the plan format; unknown keys are silently ignored.

## The schema reference is the single source of truth

`skills/configarr-config/references/schema.md` is the exhaustive, **source-verified**
reference for every YAML key. It is consumed in two places:

- the Claude Code skill `configarr-config` (this repo is also a plugin), and
- the docs book, whose `docs/src/reference/schema.md` chapter pulls it in verbatim
  via mdbook `{{#include ...:reference}}` (anchors hide the maintainer note).

**Do not duplicate this content.** When sync behavior or a key changes, update
`schema.md` by re-checking the three layers above (its maintainer note explains
how). Both the skill and the book pick up the change automatically.

## Docs (mdbook) notes

- Built with `mdbook` + `mdbook-mermaid` (diagrams) and the `mdbook-linkcheck2`
  backend, all pinned via `flake.lock`. The link check runs offline as part of
  `nix build .#docs` / `nix flake check`, so broken internal links fail CI.
- The linkcheck backend binary is `mdbook-linkcheck2`; `book.toml` sets
  `command = "mdbook-linkcheck2"` for the `[output.linkcheck]` backend.
- Callouts use **mdbook's native GitHub-style alerts** (`> [!NOTE]`, `> [!WARNING]`,
  …), not `mdbook-admonish` — the nixpkgs admonish is incompatible with mdbook
  0.5.x. Stick with native alerts.
- Deploys to GitHub Pages via `.github/workflows/docs.yml` on pushes to `main`
  touching docs sources.

## Releasing

The version lives in **one** place: `pyproject.toml`. `configarr.__version__` and
both Nix derivations read it from there, so never hardcode it elsewhere.

To cut a release:

1. Bump `version` in `pyproject.toml`.
2. In `CHANGELOG.md`, rename the `## [Unreleased]` section to `## [X.Y.Z] - <date>`
   and add the compare links at the bottom.
3. Commit, then tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.

The tag push triggers two workflows: `docker.yml` publishes the image to GHCR, and
`release.yml` publishes the GitHub Release. `release.yml` **fails if the tag does
not match `pyproject.toml`** (guarding the tag/version drift that broke 0.2.0) and
uses the matching `CHANGELOG.md` section as the release notes.

## Conventions

- GitHub Actions are pinned to commit SHAs, and nixpkgs is resolved from
  `flake.lock` in CI. Match this when editing workflows (actionlint gates them).
- Example configs live in `examples/` (per-service, `full.yml`, and
  `examples/trash-guides/` adapting TRaSH-Guides profiles + quality definitions).
- The repo ships as an in-repo Claude plugin (`.claude-plugin/`); the
  `configarr-config` skill is the user-facing way to author/validate configs.
