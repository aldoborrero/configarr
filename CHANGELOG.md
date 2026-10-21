# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Kavita support: manage a Kavita instance under `kavita.instances.<name>` — its
  server `settings` (including `oidc` and `smtp`) and its `libraries` (name-keyed,
  prunable). `api_key` is a Kavita auth key, exchanged for a JWT via
  `/api/plugin/authenticate`. Settings are merged over the current DTO because
  Kavita's POST replaces it whole; enums are written by name. The OIDC secret is
  compared by length only (Kavita masks it) and the SMTP password by fingerprint,
  so neither appears in a plan; an OIDC authority/client/secret/scope change warns
  that Kavita must be restarted.
- Kapowarr support under `kapowarr.instances.<name>`: `settings` (partial PUT;
  only changed keys are sent), `root_folders`, `download_clients` (external
  Transmission/qBittorrent clients, keyed by title) and `credentials` (Mega,
  Pixeldrain; keyed by source). The collections are prunable. Clear-text
  secrets are compared by fingerprint, and masked ones are not diffed.

## [0.6.0] - 2026-10-16

### Fixed

- Lingarr: a configured `api_key` was never sent; it now goes out as `X-Api-Key`,
  so instances with authentication enabled can be managed.

### Added

- Lingarr `onboarding`: completes a fresh instance's first-run onboarding (plan
  shows `onboarded: False -> True`, apply POSTs it before any other group); until
  then the settings groups read as empty instead of failing.
- Lingarr `validation` group (`subtitle_validation_*`) and the
  `ai_context_use_translated` translation key (Lingarr 1.4).
- Lingarr `automation` group: manage scheduled file-mode translation
  (`automation_enabled`, `translation_schedule`, `max_translations_per_run`, the
  per-type schedules and age thresholds) under `lingarr.instances.<name>.automation`.

## [0.5.2] - 2026-10-16

### Fixed

- Bazarr providers: `enabled: false` never took effect — the plan showed the
  `enabled: True -> False` change, but apply always re-added the provider to
  `general.enabled_providers`. It is now removed from the list (other enabled
  providers untouched).

## [0.5.1] - 2026-10-15

### Added

- Cleanuparr per-client download-cleaner settings, declared on each
  `download_clients.<name>`: `orphaned_files`, `unlinked`, `dead_torrent` and
  `seeding_rules` (name-keyed, prunable per client). Settings a client type does
  not support (e.g. seeding rules on SABnzbd) are rejected at plan time.

### Fixed

- `--prune` with a state file never deleted resources whose match key is
  composite (Cleanuparr arr instances): the state stores keys as strings, and the
  ownership check compared the raw tuple. It now matches the stored string form.

## [0.5.0] - 2026-10-15

### Added

- Cleanuparr support: manage a Cleanuparr instance under
  `cleanuparr.instances.<name>` — its `general`, `queue_cleaner`,
  `download_cleaner` and `malware_blocker` settings, its `download_clients`
  (including SABnzbd, new in Cleanuparr 2.10.10) and its *arr instances and
  per-arr settings under `arr:`. Settings sections are merged over the current
  object because Cleanuparr's PUT is full-replace; download clients and arr
  instances are name-keyed and prunable. Keys are snake_case and mapped onto the
  API's camelCase fields; masked secrets are sent but not diffed.

## [0.4.2] - 2026-08-17

### Fixed

- A read-only `--plan` no longer drops a config `tags` label that doesn't exist on
  the instance yet: it is kept as its label (still warned) so the plan's tag set
  matches what apply writes. This stops a delay profile referencing an uncreated tag
  from crashing `--plan` (tag-set identities collapsing) and stops name-keyed
  resources (notifications/import lists/release profiles) from under-reporting the
  `tags` change.
- Root-folder paths are matched with the trailing slash stripped, so `/data/media/`
  in config matches the server's `/data/media` instead of reporting a phantom CREATE
  and a duplicate-path apply error.
- Quality definitions are matched case-insensitively (as quality profiles already
  are) and warn on an unmatched name, instead of silently applying nothing.
- A quality profile config with two quality groups sharing a name now errors clearly
  instead of shipping a PUT where both groups collide on one server id.

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

[Unreleased]: https://github.com/aldoborrero/configarr/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/aldoborrero/configarr/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/aldoborrero/configarr/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/aldoborrero/configarr/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/aldoborrero/configarr/compare/v0.4.2...v0.5.0
[0.4.2]: https://github.com/aldoborrero/configarr/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/aldoborrero/configarr/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/aldoborrero/configarr/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/aldoborrero/configarr/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/aldoborrero/configarr/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/aldoborrero/configarr/releases/tag/v0.1.0
