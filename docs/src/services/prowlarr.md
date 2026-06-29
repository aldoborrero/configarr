# Prowlarr

Prowlarr manages your indexers and pushes them to the *arr applications. configarr
manages three Prowlarr resource types, all nested under a `.definitions` map:
**indexers**, **applications**, and **download clients**. Path prefix:
`prowlarr.instances.<name>`.

> [!NOTE]
> For exact keys and defaults, see the
> [Prowlarr section of the schema](../reference/schema.md#prowlarr). This page shows
> how the pieces connect.

## Connect

```yaml
prowlarr:
  instances:
    main:
      base_url: http://localhost:9696
      api_key: ${PROWLARR_API_KEY}
```

## Indexers

Each indexer requires an `implementation` (often `Cardigann` for tracker
definitions). The `definition` key names the specific tracker schema; if omitted
it falls back to the `implementation` value. Tracker-specific fields go under
`settings`:

```yaml
indexers:
  definitions:
    mytracker:
      implementation: Cardigann
      definition: mytracker
      enable: true
      priority: 25
      settings:
        apikey: ${TRACKER_API_KEY}
```

## Applications

Applications are the *arr instances Prowlarr syncs indexers to. Each needs an
`implementation` (`Sonarr`, `Radarr`, …) and a `sync_level`. The connection
details — the app's URL and API key, plus the Prowlarr URL it should call back —
go under `settings`:

```yaml
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

> [!WARNING]
> **sync_level must be valid**
>
> `sync_level` must be a valid value (e.g. `fullSync`, `addOnly`, `disabled`). An
> invalid value raises an error rather than being ignored.

## Download clients

Same shape as the *arr download clients — a name, an `implementation`, and a
passthrough `settings` map:

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
```

Prowlarr download clients have a few quirks that differ from indexers and
applications:

> [!NOTE]
> **Prowlarr download-client quirks**
>
> - **Case-insensitive name matching** — an existing client is matched by lower-cased
>   name, so changing only the case updates it in place.
> - **`None` settings are replaced** with the schema field's default (or `""`) to
>   avoid a Prowlarr `NullReferenceException`.
> - **`categories` is hardcoded to empty** and is not user-settable.

## Full example

[`examples/prowlarr.yml`](https://github.com/aldoborrero/configarr/blob/main/examples/prowlarr.yml)
