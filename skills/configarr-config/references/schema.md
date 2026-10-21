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
   section contract** per instance and their defaults. Most sections are
   `dict[str, Any]` passthrough (only `TrashConfig` is strictly typed); the
   registry reads them as typed attributes (`config.root_folders`,
   `config.naming_config`, …), not via `config.get`.
3. **The resource providers** (`configarr/providers/*.py`) — one `ResourceProvider`
   per resource kind reads the **inner per-resource dicts** via
   `config.get("key", default)` / `config["key"]` and talks HTTP directly via
   `requests` (there are no generated API clients).

`settings:` maps are not enumerated key-by-key: every entry passes through to the
*arr API field of the **same name** (matched against the live schema; unknown
field names are silently ignored).

**The resource inventory is authoritative from `configarr/registry.py`.** Every
`Registration` in `REGISTRY` is a resource that must be documented. The full list:
Custom Formats, Quality Profiles, Quality Definitions, Naming, Root Folders, Delay
Profiles, Release Profiles (Sonarr-only), Download Clients, Notifications (arr);
Indexers, Applications, Download Clients (prowlarr); Servers, Categories, Misc
Settings (sabnzbd); General/Sonarr/Radarr Settings, Providers, Language Profiles
(bazarr); Custom Formats, Quality Profiles, Metadata Profiles, Root Folders,
Naming, Delay Profiles, Download Clients (bookshelf). `REGISTRY` order is fixed; the one real invariant is **custom formats
before quality profiles** within an instance.

## Top-level conventions

- Every service nests under `<service>.instances.<name>`, where `<service>` is one
  of `radarr`, `sonarr`, `prowlarr`, `bazarr`, `sabnzbd`, `lingarr`,
  `cleanuparr`, `kavita`, `kapowarr`, `tranga`, `bookshelf`, and `<name>` is your
  chosen instance label.
- **`base_url` and `api_key` are REQUIRED on every instance** — except `tranga`,
  whose API has no authentication, so its `api_key` is optional. `config.py` reads
  them with subscript access (`config["base_url"]`), so omitting either raises.
  `base_url` has a trailing slash stripped automatically.
- **`${VAR}` substitution** is applied to all string values. Missing variables
  are left literal (e.g. `${SONARR_KEY}` stays as-is if unset).
- A **`.env` file in the same directory as the config** is auto-loaded before
  expansion. Existing process env vars take precedence over `.env`.
- **`include:` on an instance** merges shared partial-config files into it before
  anything else reads the config, so common blocks (custom formats, quality
  profiles, settings) can be factored out and reused across instances.
- **`tags:` accept labels or ids.** Anywhere a resource takes `tags:` (indexers,
  download clients, notifications, applications, delay/release profiles), list tag
  **labels** (strings) or numeric **ids**. Labels are resolved against the
  instance's existing tags; a label that doesn't exist is **created on apply**
  (during a read-only `--plan` it's warned about and skipped, since it would be
  created on apply). Numeric ids pass through unchanged.
- **Unrecognized section keys are warned about** at load time (a typo like
  `custom_format:` for `custom_formats:` is the usual cause of an edit that does
  nothing); `--strict` makes it an error. Generate an editor JSON Schema with
  `configarr --print-schema` for autocomplete and as-you-type validation. Deep
  `settings:`-style passthrough field names are still matched against the live API
  and dropped if unknown (see below).

```yaml
sonarr:
  instances:
    main:
      base_url: http://localhost:8989
      api_key: ${SONARR_API_KEY}
```

### Instance includes — `include`

`include` is a list of partial-config files merged into the instance. Each entry is
a path (relative to the config file's directory) or a `{config: path}` mapping.
Files are merged in order, then the instance's own keys are merged on top, so **the
instance always wins** on a conflict. Mappings deep-merge key by key (so
`custom_formats.definitions` from several files are unioned by name); a scalar or
list replaces. Included files may themselves have an `include:` (nested, resolved
relative to that file, cycle-guarded). A missing or non-mapping include file is an
error.

```yaml
radarr:
  instances:
    hd:
      base_url: http://localhost:7878
      api_key: ${RADARR_API_KEY}
      include:
        - shared/custom-formats.yml   # defines custom_formats.definitions
        - shared/quality-profiles.yml
      # instance-specific overrides win over the included files
      settings:
        root_folders:
          - path: /movies
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
| `import_lists.definitions` | map | keyed by list name |
| `trash` | map | TRaSH-Guides import, resolved into `custom_formats` + `quality_definitions` |

### Root folders — `settings.root_folders`

A list whose entries are **`{path: ...}` objects**. The `ArrServiceConfig`
Pydantic model types this field as `list[dict[str, Any]]`, so a bare string path
**fails validation at parse time** (`Input should be a valid dictionary`). Always
wrap each path in `path:`. Creates the folder if absent; existing folders report
`UNCHANGED`.

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

Naming is diffed against the live config (the provider merges the keys you set
over the current settings and normalizes both sides), so it reports `UNCHANGED`
when your values already match and `UPDATED` only on a genuine change.

### Delay profiles — `profiles.delay_profiles`

A **list** of maps. Idempotency identity is the profile's **sorted tag-set**: a
config entry is matched to the existing profile carrying the same set of tags (the
built-in catch-all has empty tags), so editing delay values updates that profile in
place rather than creating a duplicate. A matched profile keeps its current field
values with only your configured settings overlaid; an unmatched tag-set is
`CREATED` from the defaults below.

| key | type | default | meaning |
|---|---|---|---|
| `enable_usenet` | bool | `true` | |
| `enable_torrent` | bool | `true` | |
| `preferred_protocol` | string | `torrent` | |
| `usenet_delay` | int | `0` | |
| `torrent_delay` | int | `0` | |
| `bypass_if_highest_quality` | bool | `true` | |
| `bypass_if_above_custom_format_score` | int | `0` | enables the bypass flag when `> 0` |
| `minimum_custom_format_score` | int | `0` | |
| `tags` | list | `[]` | |

### Release profiles — `profiles.release_profiles` (Sonarr-only)

A **list** of maps. Radarr ignores this section entirely — `release_profile` is
only registered for Sonarr in `REGISTRY`.

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
sets the corresponding size. Each quality is diffed individually, so one whose
sizes already match reports `UNCHANGED` and only genuinely-changed qualities are
`UPDATED`. A listed quality that doesn't exist on the instance is skipped.

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
| `required` | bool | `false` | no | spec must match |
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
| `source` | string | `local` | `local` (an existing checkout) or `git` (clone/update one into a cache) |
| `path` | string | — | path to a Guides checkout; **required** for `local`, rejected for `git`. Relative paths resolve against the config file's directory |
| `url` | string | official TRaSH-Guides repo | **`git` only.** Guides repo to clone. Rejected for `local` |
| `ref` | string | the repo's default branch | **`git` only.** Branch or tag to check out. Rejected for `local` |
| `quality_definition` | string | unset | a guide quality-size `type` (e.g. `movie`, `anime`) to import as `profiles.quality_definitions` |
| `custom_formats` | list | `[]` | groups of custom formats to import and score |
| `quality_profiles` | list | `[]` | whole guide quality profiles to import by `trash_id` |

With `source: git`, configarr shallow-clones `url` at `ref` into a per-(url, ref)
cache under `$XDG_CACHE_HOME/configarr/guides` (default `~/.cache/...`) and
fetches+resets it on later runs. If the network is unavailable but a cache
already exists, the cached checkout is used with a warning. `git` must be on
`PATH` (the Nix package bundles it).

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
(custom groups and all), so it diffs and applies like a hand-written one. If you set
`name` (or the guide name) to a profile **you already define**, the guide's custom
formats and scores are **merged into your profile** instead — your structure
(`qualities`, `upgrade`, `language`) and any scores you set win, and the guide's
remaining CF scores layer in. That's recyclarr's include-then-override: keep a
profile tuned to your own custom formats while pulling in a whole TRaSH score set.

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

### Import lists — `import_lists.definitions`

A map keyed by list name. Like download clients/notifications it's a provider-Field
resource (schema-driven `fields` via `settings`), but its **top-level** attributes
differ between Radarr and Sonarr, so they are **passed straight through** to the API
(camelCase, matching the arr field names). Set whichever your service uses.

| key | type | required | meaning |
|---|---|---|---|
| `implementation` | string | **yes** | list implementation (e.g. `TraktPopularImport`, `ImdbListImport`); missing/unknown raises locally |
| `settings` | map | no | field name → value, passthrough to the list's schema fields |
| `tags` | list | no | labels or ids (see conventions) |
| *top-level API fields* | — | no | any other key is sent through verbatim: **Radarr** `enabled`, `enableAuto`, `monitor`, `qualityProfileId`, `rootFolderPath`, `searchOnAdd`, `minimumAvailability`; **Sonarr** `enableAutomaticAdd`, `shouldMonitor`, `monitorNewItems`, `seriesType`, `seasonFolder`, `searchForMissingEpisodes`, `qualityProfileId`, `rootFolderPath` |

`qualityProfileId` is a numeric id today (resolving it from a profile **name** is a
possible future addition, like tag labels). Participates in `--prune` (ownership-scoped).

```yaml
radarr:
  instances:
    main:
      import_lists:
        definitions:
          "Trakt Popular":
            implementation: TraktPopularImport
            enabled: true
            qualityProfileId: 1
            rootFolderPath: /movies
            monitor: movieOnly
            settings:
              traktListType: 0
```

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

`--plan`/`--dry-run` previews Bazarr like every other service: the providers still
issue READ (GET) requests to fetch current state and diff against config, but no
mutating writes happen.

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

A **list** of profile maps. Semantics (`providers/bazarr/language_profiles.py`):

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

SABnzbd's config API is set-only (no per-object id, no full-document PUT), so each
provider GETs the whole config (`mode=get_config`) and diffs servers, categories,
and misc settings **client-side**. An instance already matching config reports
`UNCHANGED`; only genuine changes are written back via `mode=set_config`, which
touches only the keys it is given. The `sabnzbd.misc` provider likewise reports
`UNCHANGED` when none of the managed keys differ.

### Servers — `servers`

A map keyed by server name. Booleans are coerced to `1`/`0` before sending.

| key | type | default | meaning |
|---|---|---|---|
| `host` | string | **none** | server host; **required** — a server missing `host` raises `ValueError` and aborts the run |
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

## Cleanuparr

Path prefix `cleanuparr.instances.<name>`. Top-level keys (from
`parse_cleanuparr_instance` + `CleanuparrConfig`): `base_url`, `api_key` (the key
from Cleanuparr's *Account* page, sent as `X-Api-Key`), `general`,
`queue_cleaner`, `download_cleaner`, `malware_blocker`, `download_clients`, `arr`.

Keys are written **snake_case** and mapped onto Cleanuparr's camelCase API fields
by a loose match against what the server returns (`rolling_size_mb` →
`rollingSizeMB`); a key the server does not return is sent as plain camelCase.
Enum values may be written in any case (`exclude` == `Exclude`); the server's
spelling is kept, so they do not diff.

Secrets (`api_key`, `password`) come back masked (`••••••••`) and are **not
diffed**: they are sent on create and on any update of their object, and an update
without one configured keeps the stored value. A changed secret alone does not
show in a plan.

### Sections — `general`, `queue_cleaner`, `download_cleaner`, `malware_blocker`

Free-form nested maps over Cleanuparr's own settings objects
(`GET/PUT /api/configuration/<section>`). Cleanuparr's PUT is **full-replace** —
an omitted field is reset to its default — so configarr merges the configured keys
over the current object and writes the whole result back: unset settings keep
their current values. Plans list changes as dotted paths
(`failedImport.maxStrikes: 0 -> 3`). The download cleaner's per-client sub-configs
(seeding rules, unlinked/dead-torrent/orphaned-files settings) are separate
endpoints and are **not** managed.

```yaml
queue_cleaner:
  enabled: true
  failed_import:
    max_strikes: 3
    pattern_mode: exclude
malware_blocker:
  enabled: true
  sonarr:
    enabled: true
```

### Download clients — `download_clients`

A map keyed by client name (CRUD, prunable under `--prune`).

| key | type | meaning |
|---|---|---|
| `type` | string | **required for a new client**: `qbittorrent`, `deluge`, `transmission`, `utorrent`, `rtorrent`, `sabnzbd`. Cleanuparr locks it after creation — a different `type` for an existing client raises |
| `enabled` | bool | default `true` for a new client |
| `host` | string | client URL |
| `username` / `password` | string | secret `password` (see above) |
| `api_key` | string | secret; SABnzbd and API-key qBittorrent |
| `url_base` | string | e.g. `/transmission/` |
| `external_url` | string | link shown in the UI |
| `download_directory_source` / `download_directory_target` | string | path mapping |
| `orphaned_files` / `unlinked` / `dead_torrent` | map | per-client download-cleaner settings (below) |
| `seeding_rules` | map | per-client seeding rules (below) |

#### Per-client download cleaner — `download_clients.<name>.{orphaned_files,unlinked,dead_torrent}`

One settings object each per client (`PUT /api/{orphaned-files,unlinked,dead-torrent}-config/{clientId}`),
merged over the current object like the sections. Support depends on the client
type (Cleanuparr's capability table) and an unsupported setting raises at plan
time: usenet (`sabnzbd`) supports only `orphaned_files`; `dead_torrent` needs a
seeders-capable torrent client (not `rtorrent`).

| setting | keys |
|---|---|
| `orphaned_files` | `enabled`, `scan_directories` (list), `orphaned_directory`, `exclude_patterns` (list), `min_file_age_hours` (default 24), `purge_after_hours` |
| `unlinked` | `enabled`, `target_category` (default `cleanuparr-unlinked`), `use_tag`, `ignored_root_dirs` (list), `categories` (list) |
| `dead_torrent` | `enabled`, `target_category` (default `cleanuparr-dead`), `use_tag`, `max_strikes`, `categories` (list) |

#### Seeding rules — `download_clients.<name>.seeding_rules`

A map keyed by rule name (CRUD; under `--prune`, rules not listed are deleted —
only on clients that declare `seeding_rules`, so `seeding_rules: {}` removes a
client's rules and omitting the key leaves them alone). Torrent clients only.

| key | default | meaning |
|---|---|---|
| `categories` | `[]` | client categories the rule applies to |
| `tracker_patterns` / `tags_any` / `tags_all` | `[]` | further filters |
| `priority` | next free | evaluation order; must be unique per client |
| `privacy_type` | `public` | `public`, `private` or `both` |
| `max_ratio` / `max_seed_time` (hours) / `max_inactive_days` | `-1` | limits; `-1` = no limit |
| `min_seed_time` (hours) / `min_seeders` | `0` | |
| `delete_source_files` | `true` | |
| `action` | `delete` | what to do when a limit is hit |

### Arr — `arr`

A map keyed by arr type: `sonarr`, `radarr`, `lidarr`, `readarr`, `whisparr`,
`sportarr`, `lazylibrarian` (anything else raises).

| key | type | meaning |
|---|---|---|
| `failed_import_max_strikes` | int | the per-arr setting (`-1` = use the queue cleaner's) |
| `instances` | map | instances keyed by name (CRUD, prunable): `url`, `api_key` (secret), `version` (number, e.g. `4` for Sonarr v4), `enabled` (default `true`), `external_url`. A new instance needs `url`, `api_key` and `version` |

Cleanuparr stores `url` with a trailing slash; URLs compare without one.

---

## Kavita

Path prefix `kavita.instances.<name>`. Top-level keys (from
`parse_kavita_instance` + `KavitaConfig`): `base_url`, `api_key` (a Kavita **auth
key**, exchanged for a JWT with `POST /api/plugin/authenticate?apiKey=…&pluginName=configarr`
and sent as `Authorization: Bearer …`; use an admin's), `settings`, `libraries`.

Keys are written **snake_case** and mapped onto Kavita's camelCase fields by a loose
match against what the server returns. Kavita serializes enums as integers;
configarr takes them **by name** (case, `_`, `-` and spaces ignored) or as the raw
integer, and plans show names.

### Server settings — `settings`

A free-form map over Kavita's `ServerSettingDto` (`GET /api/settings`,
`POST /api/settings`). The POST takes the **whole** DTO, so configarr merges the
configured keys over the current object and posts the result: unset settings keep
their values. Plans list dotted paths (`oidcConfig.providerName`).

| key | type | meaning |
|---|---|---|
| `host_name` | string | public URL (Kavita drops a trailing slash) |
| `logging_level` | string | `Trace`, `Debug`, `Information`, `Warning`, `Critical` |
| `enable_opds` / `enable_folder_watching` / `allow_stat_collection` | bool | |
| `task_scan` / `task_backup` / `task_cleanup` / `task_cbl_sync` | string | `daily`, `weekly`, `disabled` or a cron expression |
| `total_backups` / `total_logs` | int | 1–30 |
| `on_deck_progress_days` / `on_deck_update_days` | int | |
| `cache_size` | int | MB |
| `encode_media_as` | enum | `png`, `webp`, `avif` |
| `cover_image_size` | enum | `default`, `medium`, `large`, `xlarge` |
| `pdf_render_resolution` | enum | `default`, `high`, `ultra` |
| `base_url` / `bookmarks_directory` / `port` / `ip_addresses` | | passed through (Kavita ignores port/IPs in Docker) |
| `smtp` (or `smtp_config`) | map | `sender_address`, `sender_display_name`, `user_name`, `password`, `host`, `port`, `enable_ssl`, `size_limit`, `customized_templates` |
| `oidc` (or `oidc_config`) | map | see below |

`oidc` keys: `authority`, `client_id`, `secret`, `provision_accounts`,
`require_verified_email`, `sync_user_settings`, `roles_prefix`, `roles_claim`,
`custom_scopes` (list), `default_roles` (list), `default_libraries` (list of library
names or ids; names resolve against the instance's libraries),
`default_age_restriction` (enum: `unknown`, `everyone`, `teen`, `mature`, …, or
the int), `default_include_unknowns`, `auto_login`,
`disable_password_authentication`, `provider_name`. `enabled` is **derived** by
Kavita from `authority` and is ignored (with a warning if it contradicts it).

Read-only keys (`cache_directory`, `install_version`, `install_id`,
`first_install_*`, `stats_api_hits`) are ignored with a warning.

Secrets: `oidc.secret` comes back as `"*" * len(secret)` and Kavita keeps the stored
secret when it gets that mask back. configarr sends the configured secret, or the
mask when none is configured, and compares **lengths only**. `smtp.password` comes
back in clear text and is compared by fingerprint. Neither enters a plan. Changing
the OIDC `authority`, `client_id`, `secret` or `custom_scopes` logs a warning that
**Kavita must be restarted** (its OIDC handler is built at startup), and a new
authority unlinks every user's OIDC login.

### Libraries — `libraries`

A list keyed by `name` (create/update, prunable under `--prune`; a delete drops the
library's series from Kavita's DB, not the files). Create is `POST /api/library/create`,
update is `POST /api/library/update` (both take the full `UpdateLibraryDto`) and
delete is `DELETE /api/library/delete?libraryId=`.

| key | type | meaning |
|---|---|---|
| `name` | string | identity |
| `type` | enum | **required for a new library**: `manga`, `comic` (flexible), `comic_vine`, `book`, `image`, `light_novel` |
| `folders` | list | **required for a new library**; compared as a set |
| `file_group_types` | list | `archive`, `epub`, `pdf`, `images`; default by type (manga: archive+images, comic: archive, book: epub+pdf, light novel: epub, image: images) |
| `exclude_patterns` | list | globs; compared as a set |
| `folder_watching` / `include_in_dashboard` / `include_in_search` | bool | default `true` |
| `manage_collections` / `manage_reading_lists` | bool | default `false` |
| `allow_scrobbling` / `allow_metadata_matching` / `enable_metadata` | bool | default `true` (`allow_scrobbling` defaults `false` for `comic`) |
| `remove_prefix_for_sort_name` / `inherit_web_links_from_first_chapter` | bool | default `false` |
| `default_language` | string | |
| `metadata_provider` | enum | `hardcover`, `mangabaka`, `comic_book_roundup`; must suit the type (an invalid one raises). It defaults to the first valid one, and is reset to that when a type change invalidates the current one |

A create is followed by an update with the same body, because Kavita's create
ignores some fields.

---

## Kapowarr

Path prefix `kapowarr.instances.<name>`. Top-level keys (from
`parse_kapowarr_instance` + `KapowarrConfig`): `base_url` (include any URL base),
`api_key` (Settings → General; sent as the `api_key` **query parameter**, the only
form Kapowarr accepts), `settings`, `root_folders`, `download_clients`,
`credentials`. Source-verified against Kapowarr V1.3.2 (`frontend/api.py`).

Secrets: values Kapowarr echoes in **clear text** (`comicvine_api_key`, client
`password`/`api_token`, Pixeldrain `api_key`) are compared by fingerprint, so a
change shows in a plan without the value. Values echoed **masked** (`********`:
settings `auth_username`, `auth_password`, `proxy_password`; Mega `password`) are
never diffed.

### Settings — `settings`

A flat map of Kapowarr's own setting names (the keys of `GET /api/settings`, e.g.
`comicvine_api_key`, `flaresolverr_base_url`, `download_folder`,
`rename_downloaded_files`, `volume_folder_naming`, `file_naming`, `convert`,
`format_preference` (list), `seeding_handling` (`copy`/`complete`),
`concurrent_direct_downloads`, `proxy_type`, …). `PUT /api/settings` is
**partial**: only keys whose value differs are sent (plus any configured masked
key). A key the server does not return is skipped with a warning; `api_key` raises
(Kapowarr only regenerates it). Comparison follows Kapowarr's storage: folders with
a trailing `/`, `flaresolverr_base_url` without one (and `http://` added),
`url_base` `/`-prefixed. Kapowarr validates on save (folders must exist, ComicVine
key and FlareSolverr are tested); `host`/`port`/`url_base` or proxy changes restart
its server.

### Root folders — `root_folders`

A list of `{path: ...}` (`POST`/`DELETE /api/rootfolder`), matched by path ignoring
a trailing slash; create/delete only, prunable. The folder must exist and may not
overlap the download folder or another root folder.

### Download clients — `download_clients`

Kapowarr's external clients (`/api/externalclients`), a map keyed by **title**;
prunable. `PUT` is full-replace, so an update carries current values for every key
not set.

| key | type | meaning |
|---|---|---|
| `client_type` | string | **required for a new client**: `Transmission` or `qBittorrent` (any case). Cannot change afterwards (raises) |
| `base_url` | string | **required for a new client**; compared without trailing slash, `http://` added if missing |
| `enabled` | bool | default `true` for a new client |
| `username` / `password` | string | client login (`password` fingerprinted) |
| `api_token` | string | fingerprinted; unused by the V1.3.2 clients |

Kapowarr tests the connection on every create/update and refuses a client with
queued downloads to be updated or deleted.

### Credentials — `credentials`

Download-service logins (`/api/credentials`), a map keyed by **source**; prunable.
`mega`: `email` + `password` (both required); `pixeldrain`: `api_key` (required).
Any other source raises. No update endpoint: a change POSTs the new credential,
then DELETEs the old one. One credential per source is managed; two on the server
for the same source is an identity clash error.

```yaml
kapowarr:
  instances:
    main:
      base_url: http://kapowarr:5656
      api_key: ${KAPOWARR_API_KEY}
      settings:
        comicvine_api_key: ${COMICVINE_API_KEY}
        flaresolverr_base_url: http://flaresolverr:8191
      root_folders:
        - path: /comics
      download_clients:
        Transmission:
          client_type: Transmission
          base_url: http://transmission:9091
          username: ${TRANSMISSION_USERNAME}
          password: ${TRANSMISSION_PASSWORD}
      credentials:
        mega:
          email: ${MEGA_EMAIL}
          password: ${MEGA_PASSWORD}
```

---

## Tranga

Path prefix `tranga.instances.<name>` (Tranga v2, `/v2/...` API). Top-level keys
(from `parse_tranga_instance` + `TrangaConfig`): `base_url` (the **API** URL, not
the web UI), `api_key` (**optional** — Tranga's API has no authentication; when set
it is sent as `X-Api-Key`, for an auth proxy in front of it), `settings`,
`file_libraries`, `library_connectors`, `notification_connectors`. Manga
subscriptions are data, not config, and are not managed.

Tranga creates with `PUT`, which is not idempotent there, so creates are sent
**once, without retries**.

### Settings — `settings`

Over-current singleton read from `GET /v2/Settings`. Tranga has no bulk write: each
setting has its own endpoint, and apply makes one call per setting that changed.

| key | API field | write |
|---|---|---|
| `user_agent` | `userAgent` | `PATCH /v2/Settings/UserAgent` (JSON string) |
| `image_compression` | `imageCompression` | `PATCH /v2/Settings/ImageCompressionLevel/{1..100}`; outside 1..100 raises |
| `black_white_images` | `blackWhiteImages` | `PATCH /v2/Settings/BWImages/{bool}` |
| `flaresolverr_url` | `flareSolverrUrl` | `PATCH /v2/Settings/FlareSolverr/Url`; `""` clears it (`DELETE`) |
| `chapter_naming_scheme` | `chapterNamingScheme` | `PATCH /v2/Settings/ChapterNamingScheme` (placeholders `%M %V %C %T %A %I %i %Y`, `?X(...)` conditionals) |
| `download_language` | `downloadLanguage` | `PATCH /v2/Settings/DownloadLanguage/{lang}` (e.g. `en`, `es`) |
| `library_refresh_setting` | `libraryRefreshSetting` | `AfterAllFinished`, `AfterMangaFinished`, `AfterEveryChapter`, `WhileDownloading` (any case, `_` ignored); `PATCH /v2/Settings/LibraryRefresh` |
| `refresh_library_while_downloading_every_minutes` | `refreshLibraryWhileDownloadingEveryMinutes` | int; written together with `library_refresh_setting` |

`max_concurrent_downloads`, `max_concurrent_workers` and `work_cycle_timeout_ms` are
returned but have no write endpoint: configuring one **raises**. Other unknown keys
are warned about and ignored.

### File libraries — `file_libraries`

A map keyed by library name (CRUD, prunable): `base_path` (directory inside the
Tranga container; required for a new library). A path change is a `PATCH` in place.
Tranga ships with one library named `Default FileLibrary` — key your entry by that
name to manage it rather than creating a second one. **Deleting a library
un-assigns its manga** (Tranga sets their library to null), so prune with care.

### Library connectors — `library_connectors`

A **list** of Kavita/Komga servers Tranga asks to rescan after downloads, keyed by
`(type, base_url)` (create/delete only, prunable).

| key | meaning |
|---|---|
| `type` | `kavita` or `komga` (any case) |
| `base_url` | server URL as Tranga reaches it; trailing `/` ignored |
| `api_key` | **required for a new connector**: the Kavita user's API key (Kavita: *User settings → API key*; Tranga authenticates via `/api/Plugin/authenticate`) or a Komga API key (`X-API-Key`). Not username/password |

Tranga never returns the key and has no update endpoint, so an existing connector
is always `UNCHANGED`; a changed key is not detected. To rotate it, remove the
entry, apply with `--prune`, and add it back. Tranga tests the credentials on
create and answers `401` when they are wrong.

### Notification connectors — `notification_connectors`

A map keyed by connector name (CRUD, prunable). Tranga stores every connector as a
generic webhook; `%title` and `%text` in `url`, `body` and header values are
replaced when a notification is sent.

| key | meaning |
|---|---|
| `type` | `generic` (default) or `gotify` |
| `url` | required |
| `http_method` | generic; default `POST` |
| `body` | generic; required |
| `headers` | generic; map of header → value |
| `app_token` / `priority` | gotify; `priority` default `5` |

`type: gotify` is expanded the same way Tranga's own Gotify endpoint does
(`<url>/message`, `X-Gotify-Key` header), so a connector created in the UI diffs
clean against it. Header values are fingerprinted in plans (they usually carry the
credential). There is no update endpoint: a changed connector is **deleted and
recreated** under the same name.

---

## Bookshelf

[Bookshelf](https://github.com/pennydreadful/bookshelf) is a maintained revival
of Readarr. It serves the Readarr API on **`/api/v1`** (Radarr/Sonarr are on
`/api/v3`); configarr drives it with the same arr providers plus a Readarr-only
metadata-profile provider. Path prefix `bookshelf.instances.<name>`.

Top-level sections (from `parse_bookshelf_instance` + `BookshelfConfig`):

| YAML path | wraps | notes |
|---|---|---|
| `base_url` | — | required |
| `api_key` | — | required |
| `custom_formats.definitions` | map | as for Radarr/Sonarr |
| `profiles.quality_profiles.definitions` | map | as for Radarr/Sonarr, with Readarr's qualities |
| `profiles.metadata_profiles.definitions` | map | **Bookshelf-only**, keyed by profile name |
| `profiles.delay_profiles` | list | as for Radarr/Sonarr |
| `settings.root_folders` | list | richer than Radarr/Sonarr (below) |
| `settings.media_management` | map | naming config (book keys below) |
| `download_clients.definitions` | map | as for Radarr/Sonarr |

Not available: `trash` (TRaSH-Guides publishes nothing for Readarr; a `trash:`
block is a **parse error**), `profiles.release_profiles` (Readarr's have no name to
match on), `profiles.quality_definitions`, `notifications`, `import_lists`
(their Readarr field sets differ from what the shared providers compare).

Sync order within an instance: custom formats, quality profiles, metadata
profiles, root folders, naming, delay profiles, download clients. Both profile
kinds come before root folders because a root folder references them by name.

### Custom formats, quality profiles, delay profiles, download clients

Same keys and behaviour as the Radarr/Sonarr sections above. Differences:

- **Qualities** are book formats: `Unknown Text`, `PDF`, `MOBI`, `EPUB`, `AZW3`,
  `Unknown Audio`, `MP3`, `M4B`, `FLAC`. Set `upgrade_until_quality` to one of
  them (or a group you define); the `WEBDL-1080p` default does not exist here, so
  it falls back to the server's default cutoff.
- `language` on a quality profile is Radarr-only and ignored.
- Download-client category fields are named `musicCategory` /
  `musicImportedCategory` in Readarr's schema (a Lidarr inheritance), e.g.
  `settings: {musicCategory: books}`.

### Metadata profiles — `profiles.metadata_profiles.definitions`

A map keyed by profile name (create, update, prunable under `--prune`). A new
profile starts from `/metadataprofile/schema`; an existing one keeps its server
values for keys you do not set.

| key | type | server default | meaning |
|---|---|---|---|
| `min_popularity` | number | `0` | minimum popularity |
| `min_pages` | int | `0` | minimum page count |
| `allowed_languages` | list or comma string | `eng` | ISO 639 codes; compared as a set |
| `skip_missing_date` | bool | `false` | skip books without a release date |
| `skip_missing_isbn` | bool | `false` | skip books without an ISBN |
| `skip_parts_and_sets` | bool | `false` | skip "Part 1 of …" and box sets |
| `skip_series_secondary` | bool | `false` | skip secondary series entries |
| `ignored` | list | `[]` | terms whose matching books are ignored |

The built-in `None` profile is reserved: it is never planned or pruned, and naming
a profile `None` is an error. Bookshelf refuses to delete a profile still used by
an author, an import list or a root folder's default; a prune that hits one fails
with that reason and the profile name.

### Root folders — `settings.root_folders`

A list matched by `path` (trailing slash ignored). Unlike Radarr/Sonarr, an
existing folder is **updated in place** when its defaults change (Readarr has
`PUT /rootfolder/{id}`). Not prunable.

| key | type | default | meaning |
|---|---|---|---|
| `path` | string | — | **required**; the folder's identity, cannot change |
| `name` | string | last path component | display name |
| `default_quality_profile` | string or id | — | **required to create**; quality profile name |
| `default_metadata_profile` | string or id | — | **required to create**; metadata profile name |
| `default_monitor` | string | `all` | books monitored for a new author: `all`, `future`, `missing`, `existing`, `latest`, `first`, `none` |
| `default_new_item_monitor` | string | `all` | books added later: `all`, `none`, `new` |
| `default_tags` | list | `[]` | tag labels or ids |

Profile names are resolved to ids on the instance. A name that does not exist yet
(a profile the same config creates) is shown by name in a plan and must resolve
on apply. Calibre-library settings are not managed; an existing folder keeps them.

### Naming — `settings.media_management`

| key | type | meaning |
|---|---|---|
| `rename_books` | bool | rename on import |
| `replace_illegal_characters` | bool | replace illegal filename chars |
| `colon_replacement` | string | `delete`, `dash`, `spaceDash`, `spaceDashSpace`, `smart` |
| `standard_book_format` | string | book file format |
| `author_folder_format` | string | author folder format |

```yaml
bookshelf:
  instances:
    main:
      base_url: https://bookshelf.example.com
      api_key: ${BOOKSHELF_API_KEY}
      profiles:
        quality_profiles:
          definitions:
            eBook:
              upgrade_until_quality: EPUB
              qualities: [EPUB, AZW3, MOBI]
        metadata_profiles:
          definitions:
            Standard:
              min_popularity: 0
              allowed_languages: [spa, eng]
              skip_missing_isbn: false
      settings:
        root_folders:
          - name: Libros
            path: /hdd/books
            default_quality_profile: eBook
            default_metadata_profile: Standard
        media_management:
          rename_books: true
          standard_book_format: "{Book Title}"
          author_folder_format: "{Author Name}"
      download_clients:
        definitions:
          SABnzbd:
            implementation: Sabnzbd
            settings:
              host: sabnzbd
              apiKey: ${SABNZBD_API_KEY}
              musicCategory: books
```

Prowlarr syncs indexers to Bookshelf through its **`Readarr`** application:

```yaml
prowlarr:
  instances:
    main:
      applications:
        definitions:
          Bookshelf:
            implementation: Readarr
            settings:
              prowlarrUrl: http://prowlarr:9696
              baseUrl: http://bookshelf:8787
              apiKey: ${BOOKSHELF_API_KEY}
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
  top-level **section contract and defaults** (mostly `dict[str, Any]` passthrough;
  only `TrashConfig` is strict); the registry reads these as attributes.
- **`configarr/providers/*.py`** — each `ResourceProvider` reads the **inner
  per-resource keys** via `config.get(...)`, their defaults, and which keys are
  service-specific, and drives its own diff/apply against the HTTP API.
- **`configarr/registry.py`** — every `Registration` in `REGISTRY` is the
  **authoritative list of resources** and fixes their order; if a new one appears,
  add a section here.

