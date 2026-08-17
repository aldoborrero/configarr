# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Internal: providers are grouped into family subpackages
  (`providers/{arr,prowlarr,bazarr,sabnzbd,lingarr}/`) reflecting that the *arr
  providers are shared by radarr and sonarr, and the plan/diff types moved from
  `model.py` to `plan.py` to disambiguate them from the config `models.py`. No
  behaviour or configuration change.

## [0.4.0] - 2026-08-17

### Added

- Lingarr support: manage a Lingarr instance's `translation` backend and `arr`
  `integration` settings declaratively under `lingarr.instances.<name>`. Two
  provider groups (`lingarr.translation`, `lingarr.integration`) over its flat
  `/api/setting` store; secret keys are fingerprinted so they stay out of the plan;
  a key outside its group's known set is warned about rather than written blindly.

### Fixed

- Bazarr `enabled_providers` is now written as one repeated form field per
  provider instead of a comma-joined value, which Bazarr stored as a single
  malformed list entry that matched — and thus enabled — no provider.
- Rename reconciliation now looks up managed ids through the provider's
  `match_key`, so a case-insensitive provider (Prowlarr download clients) whose
  config name has any uppercase no longer misses its stored id and creates a
  duplicate after a server-side rename.
- SABnzbd `misc`/`servers`/`categories` config keys outside the managed
  allow-list, and a `profiles.quality_profiles` block missing its `definitions:`
  layer, now emit a warning instead of being silently dropped from the plan.
- TRaSH `git` source now accepts a commit SHA as `ref` (documented but previously
  broken — `git clone --branch` rejects a SHA); a SHA pin is fetched explicitly and
  checked out detached.
- A `POST` (resource create) is now retried on `429`/`503` — where the server
  declined to process it, so nothing was created — instead of failing hard; it is
  still never retried on connection errors or `5xx` that may have taken effect.
- Duplicate-identity errors now name the resource kind and distinguish a repeated
  name from two nameless resources, instead of a bare `duplicate key` message.
- Ownership state is now persisted even when an apply fails mid-run, so the
  `.configarr-state.json` record of resources already written (by completed
  providers, and by a provider that aborted partway through) is no longer lost.
## [0.3.0] - 2026-07-28

### Added

- Import list management for Radarr and Sonarr (#23).
- Live integration-test harness that exercises the create → idempotent → prune →
  recreate round-trip against a real Radarr container (#24).
- Config JSON Schema output via `--print-schema`, plus unknown-key warnings and a
  `--strict` mode that turns them into errors (#20).
- Instance-level `include:` for sharing config across instances (#17).
- Ownership state (`.configarr-state.json`) so `--prune` only removes resources
  configarr created, never hand-made ones (#15).
- `git` source for TRaSH-Guides imports (#14).
- `--check` flag for offline config validation (#13).
- `--version` flag (#21).

### Changed

- Auto-create missing tags on apply instead of failing (#22).
- `--prune` now also covers indexers, applications, download clients, and
  notifications (#19).
- Tag labels are resolved to ids across every tag-carrying provider (#18).
- Rename-tolerant matching via stored service ids, extended to prunable
  field-based providers (#16, #21).
- HTTP requests now use timeouts and bounded retries (#12).
- The package version is single-sourced from `pyproject.toml`; the Nix
  derivations and `configarr.__version__` derive from it (#25).

### Security

- Bazarr secrets (which its settings API returns in clear text) are fingerprinted
  before they enter a plan, so a rotated password or apikey no longer appears in
  `--plan`/`--output json`. Change detection and apply are unaffected.

## [0.2.0] - 2026-07-17

### Added

- mdbook user guide, deployed to GitHub Pages.
- TRaSH-Guides import pass with example configs for Radarr and Sonarr, including
  quality definitions (sizes) and the English/SQP profiles.

### Changed

- Replaced the per-service sync modules with a generic plan → apply diffing
  engine (#8).

### Fixed

- Engine, CLI, and TRaSH import defects plus documentation drift surfaced by the
  configuration audit (#9, #10).

## [0.1.0] - 2026-06-29

### Added

- Initial release: declaratively sync Radarr, Sonarr, Prowlarr, Bazarr, and
  SABnzbd from a single `configarr.yml`. Distributed as a Nix flake and a Docker
  image on GHCR.

[Unreleased]: https://github.com/aldoborrero/configarr/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/aldoborrero/configarr/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/aldoborrero/configarr/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/aldoborrero/configarr/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/aldoborrero/configarr/releases/tag/v0.1.0
