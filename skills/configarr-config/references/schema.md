<!-- ANCHOR: reference -->
# configarr.yml schema reference

Exhaustive, source-verified reference for every YAML key configarr reads, plus
recipes. This documents the **user-facing keys you write** in `configarr.yml` —
not the post-parse / native *arr API shapes. configarr reshapes and renames many
keys before sending them, so guessing from the Sonarr/Radarr/Prowlarr/Bazarr API
will be wrong.

## Accuracy rule (three layers)

A key is real only if it traces to one of three code layers:

1. **`configarr/config.py`** `parse_*` functions — read the nested YAML you write
   and **reshape/rename** keys (e.g. quality-profile `upgrades_allowed` →
   internal `upgrade.allowed`). These also define which sub-keys (`.definitions`,
   `settings.`, `profiles.`) wrap each resource.
2. **`configarr/models.py`** Pydantic models — the authoritative **top-level
   section contract** per instance and their defaults. `sync.py` reads these as
   typed attributes (`config.root_folders`, `config.naming_config`, …), not via
   `config.get`.
3. **Each client's `sync_*` methods** (`radarr.py`, `sonarr.py`, `prowlarr.py`,
   `bazarr/*`, `sabnzbd.py`) — read the **inner per-resource dicts** via
   `config.get("key", default)` / `config["key"]`.

`settings:` maps are not enumerated key-by-key: every entry passes through to the
*arr API field of the **same name** (matched against the live schema; unknown
field names are silently ignored).

**The resource inventory is authoritative from `sync.py`.** Every
`_print_section(...)` block there is a section that must be documented. The full
list: Root Folders, Naming, Delay Profiles, Release Profiles, Quality
Definitions, Custom Formats, Quality Profiles, Download Clients, Notifications
(arr); Indexers, Applications, Download Clients (prowlarr); General Settings,
Sonarr Connection, Radarr Connection, Providers, Language Profiles (bazarr);
Servers, Categories, Settings (sabnzbd).

## Top-level conventions

- Every service nests under `<service>.instances.<name>`, where `<service>` is one
  of `radarr`, `sonarr`, `prowlarr`, `bazarr`, `sabnzbd`, and `<name>` is your
  chosen instance label.
- **`base_url` and `api_key` are REQUIRED on every instance.** `config.py` reads
  them with subscript access (`config["base_url"]`), so omitting either raises.
  `base_url` has a trailing slash stripped automatically.
- **`${VAR}` substitution** is applied to all string values. Missing variables
  are left literal (e.g. `${SONARR_KEY}` stays as-is if unset).
- A **`.env` file in the same directory as the config** is auto-loaded before
  expansion. Existing process env vars take precedence over `.env`.

```yaml
sonarr:
  instances:
    main:
      base_url: http://localhost:8989
      api_key: ${SONARR_API_KEY}
```

---

## Radarr / Sonarr

Radarr and Sonarr share one Pydantic model (`ArrServiceConfig`) and nearly
identical clients. Differences are called out per key. Path prefix:
`radarr.instances.<name>` or `sonarr.instances.<name>`.

Top-level sections (from `parse_arr_instance` + `ArrServiceConfig`):

| YAML path | wraps | notes |
|---|---|---|
| `base_url` | — | required |
| `api_key` | — | required |
| `settings.root_folders` | list of `{path: ...}` | root folders (string entries are rejected by the model) |
| `settings.media_management` | map | naming config |
| `profiles.delay_profiles` | list | |
| `profiles.release_profiles` | list | **Sonarr-only** (ignored by Radarr) |
| `profiles.quality_definitions` | map | keyed by quality name |
| `profiles.quality_profiles.definitions` | map | keyed by profile name |
| `custom_formats.definitions` | map | keyed by format name |
| `download_clients.definitions` | map | keyed by client name |
| `notifications.definitions` | map | keyed by connection name |
| `trash` | map | TRaSH-Guides import, resolved into `custom_formats` + `quality_definitions` |

### Root folders — `settings.root_folders`

A list whose entries are **`{path: ...}` objects**. Even though `sync.py` would
accept a bare string, the `ArrServiceConfig` Pydantic model types this field as
`list[dict[str, Any]]`, so a bare string path **fails validation at parse time**
(`Input should be a valid dictionary`). Always wrap each path in `path:`.
Creates the folder if absent; existing folders report `UNCHANGED`.

```yaml
settings:
  root_folders:
    - path: /tv
    - path: /tv2
```

### Naming / media management — `settings.media_management`

A single map. Keys differ between services.

**Both services:**

| key | type | default | meaning |
|---|---|---|---|
| `replace_illegal_characters` | bool | `true` | replace illegal filename chars |
| `colon_replacement` | string | `smart` | one of `delete`, `dash`, `spaceDash`, `spaceDashSpace`, `smart` |

**Radarr only:**

| key | type | default | meaning |
|---|---|---|---|
| `rename_movies` | bool | `true` | rename on import |
| `standard_movie_format` | string | server current | movie file format |
| `movie_folder_format` | string | server current | movie folder format |

**Sonarr only:**

| key | type | default | meaning |
|---|---|---|---|
| `rename_episodes` | bool | `true` | rename on import |
| `multi_episode_style` | string | `range` | one of `extend`, `duplicate`, `repeat`, `scene`, `range`, `prefixedRange` |
| `standard_episode_format` | string | server current | standard episode format |
| `daily_episode_format` | string | server current | daily episode format |
| `anime_episode_format` | string | server current | anime episode format |
| `series_folder_format` | string | server current | series folder format |
| `season_folder_format` | string | server current | season folder format |
| `specials_folder_format` | string | server current | specials folder format |

Naming always reports `UPDATED` (it PUTs unconditionally).

### Delay profiles — `profiles.delay_profiles`

A **list** of maps. Idempotency is by matching `usenet_delay` + `torrent_delay` +
`preferred_protocol` against existing profiles; a match reports `UNCHANGED`,
otherwise a new profile is `CREATED`.

| key | type | default | meaning |
|---|---|---|---|
| `enable_usenet` | bool | `true` | |
| `enable_torrent` | bool | `true` | |
| `preferred_protocol` | string | `torrent` | matching key |
| `usenet_delay` | int | `0` | matching key |
| `torrent_delay` | int | `0` | matching key |
| `bypass_if_highest_quality` | bool | `true` | |
| `bypass_if_above_custom_format_score` | int | `0` | enables the bypass flag when `> 0` |
| `minimum_custom_format_score` | int | `0` | |
| `tags` | list | `[]` | |

### Release profiles — `profiles.release_profiles` (Sonarr-only)

A **list** of maps. Radarr ignores this section entirely (`sync.py` gates it on
`isinstance(client, SonarrClient)`).

| key | type | default | meaning |
|---|---|---|---|
| `enabled` | bool | `true` | |
| `required` | list | `[]` | required terms |
| `ignored` | list | `[]` | ignored terms |
| `indexer_id` | int | `0` | restrict to an indexer |
| `tags` | list | `[]` | |

### Quality definitions — `profiles.quality_definitions`

A **map** keyed by quality name (e.g. `WEBDL-1080p`), each value a map with any of
`min`, `max`, `preferred`. Only listed qualities are touched; each present key
sets the corresponding size. Always reports `UPDATED`.

| key | type | default | meaning |
|---|---|---|---|
| `min` | number | unchanged | minimum size (MB/min) |
| `max` | number | unchanged | maximum size (MB/min) |
| `preferred` | number | unchanged | preferred size (MB/min) |

```yaml
profiles:
  quality_definitions:
    WEBDL-1080p:
      min: 5
      max: 200
      preferred: 95
```

### Custom formats — `custom_formats.definitions`

A map keyed by format name. The parse layer passes each definition straight to
the client; the client reads:

| key | type | default | required | meaning |
|---|---|---|---|---|
| `include_when_renaming` | bool | `false` | no | include CF tag in renames |
| `specifications` | list | `[]` | no | the matching conditions |

Each entry in `specifications`:

| key | type | default | required | meaning |
|---|---|---|---|---|
| `name` | string | — | **yes** | spec name |
| `implementation` | string | — | **yes** | spec implementation (e.g. `ReleaseTitleSpecification`) |
| `negate` | bool | `false` | no | invert the match |
| `required` | bool | `true` | no | spec must match |
| `fields` | map | `{}` | no | field name → value, passthrough to the spec's fields |

```yaml
custom_formats:
  definitions:
    x265:
      specifications:
        - name: x265
          implementation: ReleaseTitleSpecification
          fields:
            value: "(x|h)265"
```

### Quality profiles — `profiles.quality_profiles.definitions`

A map keyed by profile name. **Write the user-facing keys below.** `config.py`
`parse_quality_profiles` renames them internally (`upgrades_allowed` →
`upgrade.allowed`, `upgrade_until_quality` → `upgrade.until_quality`,
`upgrade_until_custom_format_score` → `upgrade.until_score`,
`minimum_custom_format_score` → `min_format_score`); do **not** write those
internal names.

| key | type | default | meaning |
|---|---|---|---|
| `qualities` | list | `[]` | enabled qualities; entries are quality-name strings, or a group `{name, qualities: [...], enabled}` |
| `upgrades_allowed` | bool | `true` | allow upgrades |
| `upgrade_until_quality` | string | `WEBDL-1080p` | cutoff quality name |
| `upgrade_until_custom_format_score` | int | `10000` | cutoff format score |
| `minimum_custom_format_score` | int | `0` | minimum format score |
| `custom_format_scores` | map | `{}` | custom-format name → score (CF must already exist) |
| `language` | string | unset | **Radarr-only** language filter (e.g. `Any`, `Original`); Sonarr never reads it |

The `qualities` list defines both the **enabled set and the priority order** (first
= highest). Qualities you don't list are appended **disabled** at the bottom, so the
profile stays complete. For a quality **group**, a member entry may be a map with
`name`, a nested `qualities` list of quality names, and `enabled` (default `true`) —
this **creates a custom group** (e.g. merging `WEBDL-1080p` + `Bluray-1080p` under
one name), and `upgrade_until_quality` may name that group. A bare string enables a
single quality. (Group ids are assigned the way Radarr's UI does; reusing the
server's existing group id keeps re-syncs idempotent.)

```yaml
profiles:
  quality_profiles:
    definitions:
      HD:
        upgrades_allowed: true
        upgrade_until_quality: WEBDL-1080p
        upgrade_until_custom_format_score: 10000
        minimum_custom_format_score: 0
        qualities:
          - WEBDL-1080p
          - Bluray-1080p
        custom_format_scores:
          x265: 100
```

Note: configarr always syncs **custom formats before quality profiles** within an
instance, so `custom_format_scores` referencing a CF defined in the same file
resolves correctly. A score referencing an unknown CF is skipped with a warning.

### TRaSH-Guides import — `trash`

Imports custom formats, their scores, and quality definitions from a local
[TRaSH-Guides](https://github.com/TRaSH-Guides/Guides) checkout by `trash_id`,
instead of hand-writing them. It is resolved by a separate pass **after** parsing
(a pure `parse_config` never touches the filesystem), and merged into this
instance's own `custom_formats.definitions`, `profiles.quality_profiles.definitions`,
and `profiles.quality_definitions`, so **user-authored definitions always win** on a
name conflict.

| key | type | default | meaning |
|---|---|---|---|
| `source` | string | `local` | only `local` is supported today |
| `path` | string | — | path to a Guides checkout; **required** for `local`. Relative paths resolve against the config file's directory |
| `quality_definition` | string | unset | a guide quality-size `type` (e.g. `movie`, `anime`) to import as `profiles.quality_definitions` |
| `custom_formats` | list | `[]` | groups of custom formats to import and score |
| `quality_profiles` | list | `[]` | whole guide quality profiles to import by `trash_id` |

Each entry under `custom_formats`:

| key | type | default | meaning |
|---|---|---|---|
| `trash_ids` | list | `[]` | guide `trash_id`s to import as custom formats |
| `assign_scores_to` | list | `[]` | quality profiles to score these CFs into |

Each entry under `assign_scores_to`:

| key | type | default | meaning |
|---|---|---|---|
| `profile` | string | — | name of a profile under `profiles.quality_profiles.definitions` |
| `score_set` | string | `default` | which of the CF's `trash_scores` sets to use |
| `score` | int | unset | explicit score, overriding the guide's score set |

Score precedence is `score` > the CF's `trash_scores[score_set]` (matched
case-insensitively) > the CF's `trash_scores.default` > `0`; each fallback logs a
warning. An unknown `trash_id` is a hard error. Scoring into a `profile` that isn't
defined (by you or by a `quality_profiles` import) logs a warning and is dropped
(the CF is still imported).

Each entry under `quality_profiles` imports a **whole** guide quality profile —
its quality grouping/order, upgrade settings, and **every custom format it scores**
(pulled automatically from the profile's `formatItems`, scored via its score set):

| key | type | default | meaning |
|---|---|---|---|
| `trash_id` | string | — | the guide quality profile to import |
| `name` | string | guide name | rename the imported profile |
| `score_set` | string | the profile's `trash_score_set` | which `trash_scores` set to score its CFs from |

The profile becomes a normal entry under `profiles.quality_profiles.definitions`
(custom groups and all), so it diffs and applies like a hand-written one. If you
already define a profile with the same name, **your** definition wins and the import
is skipped entirely.

```yaml
radarr:
  instances:
    movies:
      base_url: ${RADARR_URL}
      api_key: ${RADARR_API_KEY}
      trash:
        source: local
        path: ./Guides # a `git clone` of TRaSH-Guides/Guides
        quality_definition: movie
        # Import a whole guide profile — its grouping + all its custom formats.
        quality_profiles:
          - trash_id: 9c0fb2ba1... # e.g. SQP-1 (2160p)
            score_set: sqp-1-web-2160p
        # ...and/or import specific CFs and score them into a profile you define.
        custom_formats:
          - trash_ids:
              - 570bc9e4ff7... # HDR10
            assign_scores_to:
              - profile: HD Bluray + WEB
      profiles:
        quality_profiles:
          definitions:
            HD Bluray + WEB:
              qualities: [Bluray-1080p, WEBDL-1080p]
```

### Download clients — `download_clients.definitions`

A map keyed by client name.

| key | type | default | required | meaning |
|---|---|---|---|---|
| `implementation` | string | — | **yes** | client implementation (e.g. `QBittorrent`, `Sabnzbd`); missing or unknown raises locally (the engine validates before any write, so an omitted value fails fast instead of yielding an opaque server 422) |
| `enable` | bool | `true` | no | |
| `priority` | int | `1` | no | |
| `tags` | list | `[]` | no | |
| `settings` | map | `{}` | no | field name → value, passthrough to the client's schema fields |

### Notifications / connections — `notifications.definitions`

A map keyed by connection name.

| key | type | default | required | meaning |
|---|---|---|---|---|
| `implementation` | string | — | **yes** | notification implementation; missing or unknown raises locally (validated before any write) |
| `on_download` | bool | `true` | no | |
| `on_upgrade` | bool | `true` | no | |
| `on_rename` | bool | `true` | no | |
| `on_import_complete` | bool | `true` | no | **Sonarr-only** (Radarr never reads it) |
| `tags` | list | `[]` | no | |
| `settings` | map | `{}` | no | field name → value, passthrough to the connection's schema fields |

---

## Prowlarr

Path prefix `prowlarr.instances.<name>`. All three resources nest under a
`.definitions` sub-key (from `parse_prowlarr_instance`):
`indexers.definitions`, `applications.definitions`,
`download_clients.definitions`.

### Indexers — `indexers.definitions`

A map keyed by indexer name.

| key | type | default | required | meaning |
|---|---|---|---|---|
| `implementation` | string | — | **yes** | indexer implementation; missing or unknown raises locally (validated before any write) |
| `definition` | string | unset | no | indexer definition/schema name (e.g. the tracker slug); falls back to `implementation` |
| `enable` | bool | `true` | no | |
| `priority` | int | `25` | no | |
| `app_profile_id` | int | `1` | no | **indexer-only** |
| `redirect` | bool | `false` | no | **indexer-only** |
| `tags` | list | `[]` | no | |
| `settings` | map | `{}` | no | passthrough to the indexer's schema fields |

### Applications — `applications.definitions`

A map keyed by application name.

| key | type | default | required | meaning |
|---|---|---|---|---|
| `implementation` | string | — | **yes** | application implementation; missing or unknown raises locally (validated before any write) |
| `sync_level` | string | `fullSync` | no | **application-only**; must be a valid `ApplicationSyncLevel` (e.g. `fullSync`, `addOnly`, `disabled`) — an invalid value raises |
| `tags` | list | `[]` | no | |
| `settings` | map | `{}` | no | passthrough to the application's schema fields |

### Download clients — `download_clients.definitions`

A map keyed by client name.

| key | type | default | required | meaning |
|---|---|---|---|---|
| `implementation` | string | — | **yes** | client implementation; missing or unknown raises locally (validated before any write) |
| `enable` | bool | `true` | no | |
| `priority` | int | `1` | no | |
| `tags` | list | `[]` | no | |
| `settings` | map | `{}` | no | passthrough to the client's schema fields |

Quirks specific to Prowlarr download clients (not indexers/applications):

- **Case-insensitive name matching**: an existing client is matched by
  lower-cased name, so renaming only by case updates in place.
- **None-value substitution**: a setting that resolves to `None` is replaced by
  the schema field's default value (or `""`), to avoid a Prowlarr
  NullReferenceException.
- `categories` is **hardcoded to an empty list** and is not user-settable.

---

## Bazarr

Path prefix `bazarr.instances.<name>`. Top-level keys (from
`parse_bazarr_instance` + `BazarrConfig`): `base_url`, `api_key`, `general`,
`sonarr`, `radarr`, `providers`, `language_profiles`.

`--dry-run` is supported for Bazarr, but **provider and language-profile sync
still issue READ (GET) requests** to fetch current state even in a dry run; only
the mutating POSTs are skipped.

### Connections — `general`, `sonarr`, `radarr`

Each is a flat map of fields. configarr POSTs them to
`/api/system/settings` as form fields named `settings-<section>-<field>` (section
= `general` / `sonarr` / `radarr`). Booleans are sent lower-cased
(`true`/`false`); everything else is stringified. There is no allow-list — **every
key passes through to the Bazarr settings field of the same name** under that
section. Consult Bazarr's own settings field names for valid keys.

```yaml
general:
  use_sonarr: true
sonarr:
  ip: localhost
  port: 8989
  apikey: ${SONARR_API_KEY}
```

### Providers — `providers`

A map keyed by provider name; each value is a flat map of that provider's fields
(passthrough — sent as `settings-<provider>-<field>`).

Provider name handling: configarr keeps a small `PROVIDER_NAME_MAP`, but **only
`submate` is renamed (to `whisperai`)**. Every other name — whether or not it
appears in the map — is used **verbatim** as the Bazarr provider name. So this is
a single rename plus passthrough, not an allow-list.

`enabled_providers` is **force-managed**: configarr reads the current enabled
list and **adds** each provider you configure (additive — it does not remove
others), then writes it back as a comma-separated string. You do not set
`enabled_providers` yourself.

```yaml
providers:
  opensubtitlescom:
    username: ${OST_USER}
    password: ${OST_PASSWORD}
  submate: {}   # configured as Bazarr's "whisperai" provider
```

### Language profiles — `language_profiles`

A **list** of profile maps. Semantics (`languages.py` `sync_profiles`):

- Profiles you **list** (whether new or already on the server) are **rebuilt from
  your config and overwrite** the server copy.
- Profiles present on the server but **absent from your config are preserved**.

Per-profile keys (snake_case in YAML; renamed to camelCase
`mustContain`/`mustNotContain`/`originalFormat` internally):

| key | type | default | meaning |
|---|---|---|---|
| `name` | string | — | profile name (the match key) |
| `languages` | list | `[]` | each entry a language **name** string, or a map (see below) |
| `cutoff` | string | null | a language **name** that must appear in `languages` and resolve to a known code, else it is silently null |
| `must_contain` | list | `[]` | → `mustContain` |
| `must_not_contain` | list | `[]` | → `mustNotContain` |
| `original_format` | bool/null | null | → `originalFormat` |

Each `languages` entry is either a bare language name string, or a map:

| key | type | default | meaning |
|---|---|---|---|
| `name` or `language` | string | — | language name (resolved to a code; entries that don't resolve are dropped) |
| `hi` | bool | `false` | hearing-impaired |
| `forced` | bool | `false` | forced subtitles |
| `audio_exclude` | bool | `false` | exclude if audio already in language |

```yaml
language_profiles:
  - name: English
    cutoff: English
    languages:
      - English
      - name: Spanish
        forced: true
    must_contain: []
    must_not_contain: []
```

---

## SABnzbd

Path prefix `sabnzbd.instances.<name>`. Top-level keys (from
`parse_sabnzbd_instance` + `SabnzbdConfig`): `base_url`, `api_key`, `servers`,
`categories`, `misc`.

Legacy `sync_server` and `sync_category` write blindly (POST to SABnzbd's
config API) and so report `CREATED`/`UPDATED` — never `UNCHANGED`. The diffing
engine (`configarr/diff/`) instead GETs the full config and diffs servers and
categories client-side, so an instance already matching config reports
`UNCHANGED`; only genuine changes are written. `sync_misc_settings` (legacy) and
the engine's `sabnzbd.misc` provider both report `UNCHANGED` when none of the
managed keys differ.

### Servers — `servers`

A map keyed by server name. Booleans are coerced to `1`/`0` before sending.

| key | type | default | meaning |
|---|---|---|---|
| `host` | string | **none** | server host; **silently dropped if omitted** (None values are filtered out) |
| `port` | int | `563` | |
| `ssl` | bool | `true` | sent as `1`/`0` |
| `ssl_verify` | int | `2` | |
| `ssl_ciphers` | string | `""` | |
| `username` | string | `""` | |
| `password` | string | `""` | |
| `connections` | int | `8` | |
| `priority` | int | `0` | |
| `retention` | int | `0` | |
| `timeout` | int | `60` | |
| `enable` | bool | `true` | sent as `1`/`0` |
| `required` | bool | `false` | sent as `1`/`0` |
| `optional` | bool | `false` | sent as `1`/`0` |
| `send_group` | bool | `false` | sent as `1`/`0` |
| `notes` | string | `""` | |

### Categories — `categories`

A map keyed by category name.

| key | type | default | meaning |
|---|---|---|---|
| `pp` | string | `""` | post-processing: `""`, `"0"`, `"1"`, `"2"`, `"3"` |
| `script` | string | `"None"` | post-processing script (literal `"None"` = none) |
| `dir` | string | `""` | category folder |
| `newzbin` | string | `""` | indexer category |
| `priority` | int | `-100` | `-100` = Default |

### Misc settings — `misc`

A flat map. Only the keys below are recognized (each maps to the SABnzbd API key
of the same name); booleans are coerced to `1`/`0`. Unlisted keys are ignored.

`download_dir`, `complete_dir`, `nzb_backup_dir`, `scripts_dir`, `log_dir`,
`bandwidth_max`, `bandwidth_perc`, `cache_limit`, `pause_on_post_processing`,
`auto_sort`, `enable_all_par`, `enable_recursive`, `par_option`, `nice`,
`ionice`, `pre_check`, `auto_disconnect`, `flat_unpack`, `safe_postproc`.

```yaml
misc:
  download_dir: /downloads/incomplete
  complete_dir: /downloads/complete
  bandwidth_max: 50M
  pre_check: true
```

---

## Recipes

Minimal, valid snippets using only verified keys. Each block is a fragment of a
single `configarr.yml`; merge the ones you need under the same top-level keys.

### All-services skeleton

```yaml
radarr:
  instances:
    main:
      base_url: http://localhost:7878
      api_key: ${RADARR_API_KEY}
sonarr:
  instances:
    main:
      base_url: http://localhost:8989
      api_key: ${SONARR_API_KEY}
prowlarr:
  instances:
    main:
      base_url: http://localhost:9696
      api_key: ${PROWLARR_API_KEY}
bazarr:
  instances:
    main:
      base_url: http://localhost:6767
      api_key: ${BAZARR_API_KEY}
sabnzbd:
  instances:
    main:
      base_url: http://localhost:8080
      api_key: ${SABNZBD_API_KEY}
```

### `.env` / `${VAR}` pattern

Place a `.env` next to `configarr.yml`:

```
RADARR_API_KEY=abc123
SONARR_API_KEY=def456
```

Reference with `${VAR}` anywhere a string is expected (`api_key`, provider
passwords, etc.). Unset variables are left literal, which surfaces as an auth
failure rather than a parse error.

### Root folders + media management (Sonarr)

```yaml
sonarr:
  instances:
    main:
      base_url: http://localhost:8989
      api_key: ${SONARR_API_KEY}
      settings:
        root_folders:
          - path: /tv
        media_management:
          rename_episodes: true
          multi_episode_style: range
          colon_replacement: smart
          series_folder_format: "{Series TitleYear}"
```

### qBittorrent download client (Radarr/Sonarr)

```yaml
radarr:
  instances:
    main:
      base_url: http://localhost:7878
      api_key: ${RADARR_API_KEY}
      download_clients:
        definitions:
          qbittorrent:
            implementation: QBittorrent
            enable: true
            priority: 1
            settings:
              host: localhost
              port: 8080
              username: admin
              password: ${QBIT_PASSWORD}
              category: radarr
```

### SABnzbd as an arr download client

```yaml
sonarr:
  instances:
    main:
      base_url: http://localhost:8989
      api_key: ${SONARR_API_KEY}
      download_clients:
        definitions:
          sabnzbd:
            implementation: Sabnzbd
            settings:
              host: localhost
              port: 8080
              apiKey: ${SABNZBD_API_KEY}
              tvCategory: sonarr
```

### Notification connection (Sonarr)

```yaml
sonarr:
  instances:
    main:
      base_url: http://localhost:8989
      api_key: ${SONARR_API_KEY}
      notifications:
        definitions:
          discord:
            implementation: Discord
            on_download: true
            on_upgrade: true
            on_import_complete: true
            settings:
              webHookUrl: ${DISCORD_WEBHOOK}
```

### Prowlarr indexer + application

```yaml
prowlarr:
  instances:
    main:
      base_url: http://localhost:9696
      api_key: ${PROWLARR_API_KEY}
      indexers:
        definitions:
          mytracker:
            implementation: Cardigann
            definition: mytracker
            priority: 25
            settings:
              apikey: ${TRACKER_API_KEY}
      applications:
        definitions:
          sonarr:
            implementation: Sonarr
            sync_level: fullSync
            settings:
              baseUrl: http://localhost:8989
              apiKey: ${SONARR_API_KEY}
              prowlarrUrl: http://localhost:9696
```

### Bazarr language profile + provider

```yaml
bazarr:
  instances:
    main:
      base_url: http://localhost:6767
      api_key: ${BAZARR_API_KEY}
      providers:
        opensubtitlescom:
          username: ${OST_USER}
          password: ${OST_PASSWORD}
      language_profiles:
        - name: English
          cutoff: English
          languages:
            - English
```

### SABnzbd server + category

```yaml
sabnzbd:
  instances:
    main:
      base_url: http://localhost:8080
      api_key: ${SABNZBD_API_KEY}
      servers:
        news:
          host: news.example.com
          port: 563
          ssl: true
          username: ${USENET_USER}
          password: ${USENET_PASSWORD}
          connections: 20
      categories:
        sonarr:
          dir: sonarr
          priority: -100
```

<!-- ANCHOR_END: reference -->

---

## Maintainer note: how this schema was derived / how to refresh it

This reference is reconstructed from source, not from external docs. To refresh
it after a code change, re-check the three layers and the inventory:

- **`configarr/config.py`** — the `parse_*` functions define the YAML **nesting**
  (`settings.`, `profiles.`, `.definitions`) and **renames** (especially
  `parse_quality_profiles`, which maps the user-facing quality-profile keys to the
  internal `upgrade.*` / `min_format_score` shape). `base_url`/`api_key` are read
  by subscript here (hence required).
- **`configarr/models.py`** — the Pydantic models
  (`ArrServiceConfig`, `ProwlarrConfig`, `BazarrConfig`, `SabnzbdConfig`) are the
  top-level **section contract and defaults**; `sync.py` reads these as attributes.
- **Client `sync_*` methods** (`radarr.py`, `sonarr.py`, `prowlarr.py`,
  `bazarr/__init__.py`, `bazarr/languages.py`, `bazarr/settings.py`,
  `sabnzbd.py`) — the **inner per-resource keys** via `config.get(...)`, their
  defaults, and which keys are service-specific.
- **`configarr/sync.py`** — every `_print_section(...)` is the **authoritative
  list of resources**; if a new one appears, add a section here.

