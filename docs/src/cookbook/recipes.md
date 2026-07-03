# Recipes

End-to-end scenarios that combine several services in one `configarr.yml`. For
single-resource snippets (one download client, one indexer, …), the
[Configuration Schema](../reference/schema.md#recipes) has a focused recipe per
resource; this page is about wiring a whole setup together.

> [!TIP]
> **Copy-paste starting points**
>
> Every snippet here uses only verified keys. The repository's
> [`examples/`](https://github.com/aldoborrero/configarr/tree/main/examples) folder
> has the same configs as complete, runnable files — including
> [`full.yml`](https://github.com/aldoborrero/configarr/blob/main/examples/full.yml),
> the kitchen-sink reference.

## A complete Usenet media stack

SABnzbd + Sonarr + Radarr + Prowlarr, wired together. The pieces that connect:

- SABnzbd defines `sonarr` / `radarr` **categories**.
- Sonarr/Radarr each add a **SABnzbd download client** that targets its category.
- Prowlarr adds **applications** pointing at Sonarr and Radarr, so indexers sync to
  them.

An *arr SABnzbd download client just references a category by name, so the whole
stack wires up from one file in a single run regardless of
[sync order](../concepts/sync-order.md).

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
        sonarr: { dir: sonarr, priority: -100 }
        radarr: { dir: radarr, priority: -100 }

sonarr:
  instances:
    main:
      base_url: http://localhost:8989
      api_key: ${SONARR_API_KEY}
      settings:
        root_folders:
          - path: /tv
      download_clients:
        definitions:
          sabnzbd:
            implementation: Sabnzbd
            settings:
              host: localhost
              port: 8080
              apiKey: ${SABNZBD_API_KEY}
              tvCategory: sonarr

radarr:
  instances:
    main:
      base_url: http://localhost:7878
      api_key: ${RADARR_API_KEY}
      settings:
        root_folders:
          - path: /movies
      download_clients:
        definitions:
          sabnzbd:
            implementation: Sabnzbd
            settings:
              host: localhost
              port: 8080
              apiKey: ${SABNZBD_API_KEY}
              movieCategory: radarr

prowlarr:
  instances:
    main:
      base_url: http://localhost:9696
      api_key: ${PROWLARR_API_KEY}
      applications:
        definitions:
          sonarr:
            implementation: Sonarr
            sync_level: fullSync
            settings:
              baseUrl: http://localhost:8989
              apiKey: ${SONARR_API_KEY}
              prowlarrUrl: http://localhost:9696
          radarr:
            implementation: Radarr
            sync_level: fullSync
            settings:
              baseUrl: http://localhost:7878
              apiKey: ${RADARR_API_KEY}
              prowlarrUrl: http://localhost:9696
```

## Separate 1080p and 4K Radarr

Run two Radarr instances from one file — a common "two libraries, two quality
targets" setup. Each instance is just another entry under `instances`:

```yaml
radarr:
  instances:
    main:
      base_url: http://localhost:7878
      api_key: ${RADARR_API_KEY}
      settings:
        root_folders:
          - path: /movies
      profiles:
        quality_profiles:
          definitions:
            HD:
              upgrades_allowed: true
              upgrade_until_quality: WEBDL-1080p
              qualities:
                - WEBDL-1080p
                - Bluray-1080p

    uhd:
      base_url: http://localhost:7879
      api_key: ${RADARR_4K_API_KEY}
      settings:
        root_folders:
          - path: /movies-4k
      profiles:
        quality_profiles:
          definitions:
            UHD:
              upgrades_allowed: true
              upgrade_until_quality: Bluray-2160p
              qualities:
                - WEBDL-2160p
                - Bluray-2160p
```

Iterate on one at a time with `--instance`:

```bash
configarr --service radarr --instance uhd
```

## Custom format with a score

Define a format once and weight it in a profile. configarr syncs custom formats
before quality profiles, so the score resolves within the same file:

```yaml
sonarr:
  instances:
    main:
      base_url: http://localhost:8989
      api_key: ${SONARR_API_KEY}
      custom_formats:
        definitions:
          x265:
            specifications:
              - name: x265
                implementation: ReleaseTitleSpecification
                fields:
                  value: "(x|h)265"
      profiles:
        quality_profiles:
          definitions:
            HD:
              upgrades_allowed: true
              upgrade_until_quality: WEBDL-1080p
              qualities:
                - WEBDL-1080p
              custom_format_scores:
                x265: 100
```

## Subtitles with Bazarr

Connect Bazarr to your Sonarr/Radarr and set up an English profile with a forced
Spanish track:

```yaml
bazarr:
  instances:
    main:
      base_url: http://localhost:6767
      api_key: ${BAZARR_API_KEY}
      general:
        use_sonarr: true
        use_radarr: true
      sonarr:
        ip: localhost
        port: 8989
        apikey: ${SONARR_API_KEY}
      radarr:
        ip: localhost
        port: 7878
        apikey: ${RADARR_API_KEY}
      providers:
        opensubtitlescom:
          username: ${OST_USER}
          password: ${OST_PASSWORD}
      language_profiles:
        - name: English
          cutoff: English
          languages:
            - English
            - name: Spanish
              forced: true
```

Preview it before applying — `--plan` works for every service, so you can scope it
to Bazarr:

```bash
configarr --service bazarr --plan
```

## More

- Per-resource recipes: [schema reference](../reference/schema.md#recipes).
- Runnable files: [`examples/`](https://github.com/aldoborrero/configarr/tree/main/examples).
