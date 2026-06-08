---
name: configarr-config
description: "Use when writing, editing, validating, debugging, or extending a configarr.yml — the single declarative YAML that configarr uses to manage Radarr, Sonarr, Prowlarr, Bazarr, and SABnzbd. Triggers when: (1) creating or changing a configarr.yml; (2) adding a quality profile, custom format, root folder, naming/media-management setting, delay or release profile, quality definition, download client, indexer, application, notification connection, Bazarr language profile or provider, or SABnzbd server/category/misc setting to a configarr config; (3) determining which YAML keys configarr accepts, or why a configarr run reports FAILED/UNCHANGED. Targets the configarr YAML schema specifically — not general Sonarr/Radarr/Prowlarr/Bazarr/SABnzbd usage or their native APIs."
---

## Overview

configarr reads a single `configarr.yml` and syncs Radarr, Sonarr, Prowlarr, Bazarr, and SABnzbd
from it. Every service is nested under `<service>.instances.<name>`, where `<name>` is an arbitrary
label you choose. For exact keys, accepted values, and defaults for every resource, consult
`references/schema.md`.

## Mental model

- **Secrets:** use `${VAR}` anywhere in string values. A `.env` file beside `configarr.yml` is
  loaded automatically. Missing variables are left as the literal `${VAR}` string — they are not
  errors at parse time.
- **YAML keys are not *arr API keys.** configarr renames and restructures them internally. Never
  guess key names from the Sonarr/Radarr/Prowlarr API docs — open `references/schema.md` for the
  keys that configarr actually accepts.
- **Ordering is controlled by the tool, not the file.** configarr always processes SABnzbd first
  (so categories exist before *arr apps need them), then Radarr, Sonarr, Prowlarr, Bazarr. Within
  each *arr instance, custom formats are synced before quality profiles. You cannot change this
  order via the YAML.

## Authoring workflow

1. Read the existing `configarr.yml`, or start from the skeleton in the Core recipes section below.
2. Identify the service (`radarr`, `sonarr`, `prowlarr`, `bazarr`, `sabnzbd`) and the resource
   type you need to add or change.
3. **Open `references/schema.md` for that resource before writing any keys.** Copy the exact
   nesting and key names shown there; do not guess.
4. Put secrets in `${VAR}` and add the variable to your `.env` file.
5. Write or merge the change into `configarr.yml`.

## Validation

**Scoping a run** — use `--service <name>` and/or `--instance <name>` to limit which services or
instances are touched. This is the only blast-radius control for non-Bazarr services.

**Dry-run and debug**

- `--dry-run` is **Bazarr-only**. For every other service, a run applies changes immediately.
- `--debug` enables verbose logging but does **not** prevent mutations for any service.
- There is no true dry-run for Radarr, Sonarr, Prowlarr, or SABnzbd.

**Result vocabulary** — CREATED / UPDATED / UNCHANGED / FAILED. SABnzbd servers and categories
always report CREATED or UPDATED; they never report UNCHANGED even when values match.

**Common errors**

- `missing implementation` — `implementation` is required for download clients, notifications,
  indexers, and applications; omitting it causes a FAILED result.
- Config parse error / `base_url` or `api_key` missing — both are required on every instance;
  omission raises a validation error before any sync runs.
- Literal `${VAR}` in a URL or key — the variable was not set in the environment or `.env` file.
- Unknown key silently ignored — configarr does not error on unrecognised keys; a resource that
  never appears in results was likely filed under a wrong key name. Check `references/schema.md`.

## Core recipes

### Minimal all-services skeleton

```yaml
radarr:
  instances:
    main:
      base_url: "${RADARR_URL}"
      api_key: "${RADARR_API_KEY}"

sonarr:
  instances:
    main:
      base_url: "${SONARR_URL}"
      api_key: "${SONARR_API_KEY}"

prowlarr:
  instances:
    main:
      base_url: "${PROWLARR_URL}"
      api_key: "${PROWLARR_API_KEY}"

bazarr:
  instances:
    main:
      base_url: "${BAZARR_URL}"
      api_key: "${BAZARR_API_KEY}"

sabnzbd:
  instances:
    main:
      base_url: "${SABNZBD_URL}"
      api_key: "${SABNZBD_API_KEY}"
```

### Sonarr quality profile and custom format

```yaml
sonarr:
  instances:
    main:
      base_url: "${SONARR_URL}"
      api_key: "${SONARR_API_KEY}"

      custom_formats:
        definitions:
          HDR:
            include_when_renaming: false
            specifications:
              - name: HDR
                implementation: ReleaseTitleSpecification
                negate: false
                required: true
                fields:
                  value: "\\bHDR\\b"

      profiles:
        quality_profiles:
          definitions:
            HD-1080p:
              upgrades_allowed: true
              upgrade_until_quality: WEBDL-1080p
              upgrade_until_custom_format_score: 10000
              minimum_custom_format_score: 0
              custom_format_scores:
                HDR: 10
              qualities:
                - WEBDL-1080p
                - name: WEB 1080p
                  qualities:
                    - WEBDL-1080p
                    - WEBRip-1080p
                  enabled: true
```

## Gotchas

- `release_profiles` is Sonarr-only; configarr ignores it on Radarr instances.
- Quality profile `qualities` entries are either a bare string (single quality) or an object with
  `name`, `qualities` (list), and `enabled` (for quality groups).
- `custom_format_scores` maps custom-format names to integer scores; the format must already exist
  (either defined earlier in the same file or pre-existing in the *arr instance) for scores to apply.
- `--verbose` (payload logging) is also Bazarr-only, like `--dry-run`.
- Full key reference and more recipes: `references/schema.md`.
