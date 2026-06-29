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
> and `replace_illegal_characters` apply to both. Naming always reports `UPDATED` —
> it is written unconditionally.

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

Delay profiles (`profiles.delay_profiles`) apply to both services and are matched
for idempotency on `usenet_delay` + `torrent_delay` + `preferred_protocol`:

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
> Omitting `implementation` on a download client or notification produces a
> `FAILED` result. An unknown implementation value is also rejected.

## Full examples

- [`examples/radarr.yml`](https://github.com/aldoborrero/configarr/blob/main/examples/radarr.yml)
- [`examples/sonarr.yml`](https://github.com/aldoborrero/configarr/blob/main/examples/sonarr.yml)
