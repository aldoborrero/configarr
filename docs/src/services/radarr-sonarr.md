# Radarr & Sonarr

Radarr and Sonarr share the same configuration shape — one underlying model and
nearly identical clients — so they're documented together. Differences are called
out as they come up. The path prefix is `radarr.instances.<name>` or
`sonarr.instances.<name>`.

> [!NOTE]
> **Looking for the exact keys?**
>
> This guide is task-oriented. For every key, type, default, and accepted value, see
> the [Radarr / Sonarr section of the schema](../reference/schema.md). This page
> shows you how the pieces fit together.

## Connect

The minimum is a `base_url` and `api_key`:

```yaml
sonarr:
  instances:
    main:
      base_url: http://localhost:8989
      api_key: ${SONARR_API_KEY}
```

## Root folders and naming

Root folders go under `settings.root_folders` as a list of `{path: ...}` objects
(a bare string is rejected by validation). Naming lives under
`settings.media_management`:

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
          season_folder_format: "Season {season:00}"
          standard_episode_format: "{Series Title} - S{season:00}E{episode:00} - {Episode Title} {Quality Full}"
```

> [!NOTE]
> **Service-specific naming keys**
>
> The naming keys differ between the two: Radarr uses `rename_movies`,
> `standard_movie_format`, `movie_folder_format`; Sonarr uses `rename_episodes`,
> `multi_episode_style`, and the various episode/season formats. `colon_replacement`
> and `replace_illegal_characters` apply to both. Naming is **diffed** on the fields
> it manages: it reports `unchanged` when those already match, and only writes when
> they differ.

## Custom formats and quality profiles

This is the most common reason to use configarr. Define custom formats, then
reference them by name in a quality profile's `custom_format_scores`. Because
configarr syncs **custom formats before quality profiles**, formats defined in the
same file are available to the profile:

```yaml
radarr:
  instances:
    main:
      base_url: http://localhost:7878
      api_key: ${RADARR_API_KEY}

      custom_formats:
        definitions:
          x265:
            specifications:
              - name: x265
                implementation: ReleaseTitleSpecification
                fields:
                  value: "(x|h)265"

      profiles:
        quality_definitions:
          WEBDL-1080p:
            min: 5
            max: 200
            preferred: 95
        quality_profiles:
          definitions:
            HD:
              upgrades_allowed: true
              upgrade_until_quality: WEBDL-1080p
              upgrade_until_custom_format_score: 10000
              minimum_custom_format_score: 0
              language: Any        # Radarr-only; Sonarr ignores it
              qualities:
                - WEBDL-1080p
                - Bluray-1080p
              custom_format_scores:
                x265: 100
```

A few things worth knowing:

- **Write the configarr key names, not the API ones.** `upgrades_allowed`,
  `upgrade_until_quality`, `upgrade_until_custom_format_score`, and
  `minimum_custom_format_score` are renamed internally — see
  [Mental Model](../concepts/mental-model.md#yaml-keys-are-not-arr-api-keys).
- **Quality groups:** an entry under `qualities` can be a bare quality name, or a
  group `{name, qualities: [...], enabled}` that bundles several qualities at one
  rank.
- **`custom_format_scores`** maps a custom-format name to an integer score; the
  format must already exist (defined earlier in the file or pre-existing).
- **`language`** filters by language and is **Radarr-only**; Sonarr never reads
  it.

## Delay and release profiles

Delay profiles (`profiles.delay_profiles`) apply to both services. A profile's
identity is its **tag set** (the sorted list of tags it applies to, with the
built-in catch-all having no tags), not its delay values — so editing a delay
updates the existing profile instead of creating a duplicate:

```yaml
profiles:
  delay_profiles:
    - preferred_protocol: usenet
      usenet_delay: 0
      torrent_delay: 30
```

> [!WARNING]
> **Release profiles are Sonarr-only**
>
> `profiles.release_profiles` is **Sonarr-only**. If you put it on a Radarr
> instance, configarr ignores the section entirely.

```yaml
# Sonarr only
profiles:
  release_profiles:
    - enabled: true
      required:
        - x265
      ignored:
        - CAM
```

## Download clients and notifications

Both are maps under `.definitions`, keyed by a name you choose, and both require
an `implementation`. Anything under `settings` is passed through to that
implementation's own fields (use the *arr field names here — see the
[schema notes on `settings:` passthrough](../reference/schema.md)):

```yaml
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

notifications:
  definitions:
    discord:
      implementation: Discord
      on_download: true
      on_upgrade: true
      on_import_complete: true   # Sonarr-only flag
      settings:
        webHookUrl: ${DISCORD_WEBHOOK}
```

> [!CAUTION]
> **implementation is required**
>
> Omitting (or misspelling) `implementation` on a download client raises a
> `ValueError` when configarr tries to create it, which aborts the whole run (exit
> `1`) — there is no per-resource failure line.

## Import lists

Import lists auto-add movies or series from an external source (Trakt, IMDb,
another *arr, …). Like download clients they're a map under `.definitions` keyed by
a name you choose, each requiring an `implementation`, with `settings` passed
through to that implementation's own fields.

The **top-level** keys differ between Radarr and Sonarr — set whichever your
service uses; they're sent straight through as *arr field names. The
[import-lists schema reference](../reference/schema.md) lists the fields each
service accepts.

```yaml
# Radarr
import_lists:
  definitions:
    "Trakt Popular":
      implementation: TraktPopularImport
      enabled: true
      monitor: movieOnly
      qualityProfileId: 1
      rootFolderPath: /movies
      settings:
        traktListType: 0
```

```yaml
# Sonarr — note the different top-level keys
import_lists:
  definitions:
    "Trakt Popular":
      implementation: TraktPopularImport
      enableAutomaticAdd: true
      shouldMonitor: all
      seriesType: standard
      seasonFolder: true
      qualityProfileId: 1
      rootFolderPath: /tv
      settings:
        traktListType: 0
```

> [!NOTE]
> `qualityProfileId` is a numeric id (resolving it from a profile name may come
> later, like tag labels). `implementation` is required — the same
> abort-the-run rule as download clients applies. Import lists participate in
> `--prune` (ownership-scoped).

## Full examples

- [`examples/radarr.yml`](https://github.com/aldoborrero/configarr/blob/main/examples/radarr.yml)
- [`examples/sonarr.yml`](https://github.com/aldoborrero/configarr/blob/main/examples/sonarr.yml)
