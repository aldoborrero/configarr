# Seerr

configarr manages the **Radarr and Sonarr instances a [Seerr](https://github.com/seerr-team/seerr)
registers** — the servers it dispatches approved requests to — keyed under
`seerr.instances.<name>` (see [Sync Order](../concepts/sync-order.md) for where Seerr
falls in a run).

This is the wiring you would otherwise click through Seerr's settings UI and which
lives only in its config afterwards. Declaring it here makes it reproducible: a
rebuilt Seerr is re-wired by an apply instead of by hand.

## Connect

Seerr's `X-Api-Key` resolves to user id 1 — the owner account. Until Seerr's setup
wizard has created that account, every `/api/v1/settings/*` route answers `403`;
configarr surfaces that as a clear error rather than completing the wizard itself
(a plan stays read-only).

```yaml
seerr:
  instances:
    main:
      base_url: http://seerr:5055
      api_key: ${SEERR_API_KEY}
```

## Radarr / Sonarr instances — `radarr`, `sonarr`

Each key is the instance **name** as it appears in Seerr, which is also the identity
configarr diffs on (Seerr assigns the numeric `id` on create).

Seerr stores a quality profile by **id and by name** and validates neither. You give
the profile's name, and configarr resolves it through
`POST /api/v1/settings/<kind>/test` — the same connection probe Seerr's own dialog
uses, which reports the target \*arr's quality profiles, root folders and tags.
Asking Seerr rather than the \*arr directly is deliberate: what has to reach the
\*arr is Seerr. Root folders and tag labels are checked against the same response,
so a typo fails the plan instead of surfacing much later as a request that never
lands.

> [!NOTE]
> Seerr's write routes cast the request body and persist it verbatim, so a
> misspelled field is stored and then ignored by everything that reads it.
> configarr therefore builds every key from its own allow-list and **rejects** an
> unknown setting, or a value outside an enum's options, instead of forwarding it.
>
> For the same reason, don't reach for Seerr's published OpenAPI spec (or the
> generated `seerr` PyPI client) as the reference: it lags the code and is missing
> `tags`, `tagRequests`, `seriesType`, `animeSeriesType`, `animeTags` and
> `monitorNewItems`.

| Key | Seerr field | Default | Notes |
|---|---|---|---|
| `hostname` | `hostname` | — | required |
| `port` | `port` | 7878 / 8989 | |
| `api_key` | `apiKey` | — | required — the \*arr's key |
| `quality_profile` | `activeProfileId` + `activeProfileName` | — | required; resolved by name |
| `root_folder` | `activeDirectory` | — | required; must exist on the \*arr |
| `use_ssl` | `useSsl` | `false` | |
| `base_url` | `baseUrl` | `""` | the \*arr's URL base, when it has one |
| `is_4k` | `is4k` | `false` | |
| `is_default` | `isDefault` | `false` | clears the previous default of the same `is_4k` |
| `external_url` | `externalUrl` | `""` | link shown in Seerr's UI |
| `sync_enabled` | `syncEnabled` | `false` | |
| `prevent_search` | `preventSearch` | `false` | |
| `tags` | `tags` | `[]` | tag labels or ids |
| `tag_requests` | `tagRequests` | `false` | tag each item with the requesting user |

Radarr only — `minimum_availability` (`announced`, `inCinemas`, `released`; default
`released`).

Sonarr only:

| Key | Seerr field | Default | Options |
|---|---|---|---|
| `season_folders` | `enableSeasonFolders` | `false` | |
| `series_type` | `seriesType` | `standard` | `standard`, `daily` |
| `monitor_new_items` | `monitorNewItems` | `all` | `all`, `none` |
| `anime_quality_profile` | `activeAnimeProfileId` + `activeAnimeProfileName` | unset | |
| `anime_root_folder` | `activeAnimeDirectory` | unset | |
| `anime_series_type` | `animeSeriesType` | `anime` | `anime`, `standard` |
| `anime_tags` | `animeTags` | unset | labels or ids |

Set the anime keys to send anime to a different profile and library within the same
Sonarr. Routing anime to a **separate** Sonarr instance is a different feature —
Seerr's override rules — and is not managed here.

```yaml
seerr:
  instances:
    main:
      base_url: http://seerr:5055
      api_key: ${SEERR_API_KEY}
      radarr:
        radarr:
          hostname: radarr
          api_key: ${RADARR_API_KEY}
          quality_profile: WEB-1080p
          root_folder: /media/movies
          is_default: true
      sonarr:
        sonarr:
          hostname: sonarr
          api_key: ${SONARR_API_KEY}
          quality_profile: WEB-1080p
          root_folder: /media/tv
          season_folders: true
          anime_quality_profile: Anime-1080p
          anime_root_folder: /media/anime/shows
          is_default: true
```
