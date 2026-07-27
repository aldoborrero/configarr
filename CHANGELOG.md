# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/aldoborrero/configarr/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/aldoborrero/configarr/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/aldoborrero/configarr/releases/tag/v0.1.0
