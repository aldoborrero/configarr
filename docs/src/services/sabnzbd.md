# SABnzbd

configarr manages SABnzbd's Usenet **servers**, download **categories**, and a set
of **misc** settings. Path prefix: `sabnzbd.instances.<name>`. SABnzbd is processed
**first** in every run so its categories exist before *arr download clients
reference them (see [Sync Order](../concepts/sync-order.md)).

> [!NOTE]
> Exact keys and defaults: the
> [SABnzbd section of the schema](../reference/schema.md#sabnzbd).

## Connect

```yaml
sabnzbd:
  instances:
    main:
      base_url: http://localhost:8080
      api_key: ${SABNZBD_API_KEY}
```

## Servers

A map keyed by server name. `host` is effectively required — if you omit it the
server is silently dropped (null values are filtered out). Booleans like `ssl` and
`enable` are coerced to `1`/`0` before sending.

```yaml
servers:
  news:
    host: news.example.com
    port: 563
    ssl: true
    username: ${USENET_USER}
    password: ${USENET_PASSWORD}
    connections: 20
    retention: 3000
```

## Categories

A map keyed by category name. A common pattern is one category per *arr app, so
downloads land in predictable folders:

```yaml
categories:
  sonarr:
    dir: sonarr
    priority: -100      # -100 = Default
  radarr:
    dir: radarr
    priority: -100
```

These category names are what you reference from a Sonarr/Radarr SABnzbd download
client (`tvCategory: sonarr`, `movieCategory: radarr`).

## Misc settings

A flat map. **Only a fixed set of keys is recognised** — anything else is ignored.
The recognised keys are directory paths, bandwidth limits, and a handful of
processing toggles (see the [schema](../reference/schema.md#sabnzbd) for the full
list). Booleans are coerced to `1`/`0`.

```yaml
misc:
  download_dir: /downloads/incomplete
  complete_dir: /downloads/complete
  bandwidth_max: 50M
  pre_check: true
```

## Always-write behaviour

> [!NOTE]
> **Servers and categories never report UNCHANGED**
>
> `sync_server` and `sync_category` always POST to SABnzbd's config API, so they
> report `CREATED` or `UPDATED` even when the values already match. Only
> `sync_misc_settings` reports `UNCHANGED`, and only when none of its keys are
> present.

## Full example

[`examples/sabnzbd.yml`](https://github.com/aldoborrero/configarr/blob/main/examples/sabnzbd.yml)
