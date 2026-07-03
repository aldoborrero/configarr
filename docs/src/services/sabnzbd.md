# SABnzbd

configarr manages SABnzbd's Usenet **servers**, download **categories**, and a set
of **misc** settings. Path prefix: `sabnzbd.instances.<name>` (see
[Sync Order](../concepts/sync-order.md) for where SABnzbd falls in a run).

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

A map keyed by server name. `host` is **required** — a server entry without one is
a hard error that aborts the run (exit `1`), not a silent drop. Booleans like `ssl`
and `enable` are coerced to `1`/`0` before sending.

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

## Diffing behaviour

> [!NOTE]
> **SABnzbd is diffed like everything else**
>
> SABnzbd's config API is set-only (no per-object id, no full-document PUT), so
> configarr GETs the current config and diffs it client-side. Servers, categories,
> and misc settings that already match report `unchanged` and are skipped —
> re-running an in-sync config writes nothing.

## Full example

[`examples/sabnzbd.yml`](https://github.com/aldoborrero/configarr/blob/main/examples/sabnzbd.yml)
