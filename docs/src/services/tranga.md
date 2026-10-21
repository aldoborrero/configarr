# Tranga

configarr manages a [Tranga](https://github.com/C9Glax/tranga) v2 instance under
`tranga.instances.<name>`: its **settings**, its **file libraries**, the
**library connectors** (Kavita/Komga) it triggers scans on, and its
**notification connectors** (see [Sync Order](../concepts/sync-order.md) for the
order they run in). Manga subscriptions are data, not config, and are left alone.
The exact keys are in the [schema reference](../reference/schema.md#tranga).

## Connect

Point `base_url` at Tranga's **API** (the `tranga-api` container, which serves
`/v2/...` and `/swagger`), not the web UI. Tranga's API has no authentication, so
`api_key` is optional; when set it is sent as `X-Api-Key`, which is only useful
for an auth proxy in front of Tranga.

```yaml
tranga:
  instances:
    main:
      base_url: http://tranga-api:6531
```

> [!WARNING]
> Anyone who can reach Tranga's API can change it. Keep it on a private network.

## Settings

Set only what you care about; everything else keeps its value. Tranga has one
endpoint per setting, so apply makes one call for each setting that changed.

```yaml
settings:
  download_language: es
  flaresolverr_url: http://flaresolverr:8191
  image_compression: 40
  black_white_images: false
  chapter_naming_scheme: "%M - ?V(Vol.%V )Ch.%C?T( - %T)"
  library_refresh_setting: after_manga_finished
```

`flaresolverr_url: ""` clears the URL. `max_concurrent_downloads`,
`max_concurrent_workers` and `work_cycle_timeout_ms` cannot be set through the
API, and configuring one is an error.

## File libraries

Keyed by name, with the directory inside the Tranga container. A fresh Tranga has
one library called `Default FileLibrary`; use that name to manage it instead of
creating a second library on the same path.

```yaml
file_libraries:
  Default FileLibrary:
    base_path: /Manga
```

> [!CAUTION]
> Deleting a library (`--prune`) un-assigns every manga in it.

## Library connectors

A list of Kavita/Komga servers Tranga asks to rescan after downloads, matched by
`type` and `base_url`. `api_key` is the Kavita user's API key (or a Komga API
key), not a username/password. Tranga checks it on create and rejects a wrong one.

```yaml
library_connectors:
  - type: kavita
    base_url: http://kavita:5000
    api_key: ${TRANGA_KAVITA_API_KEY}
```

Tranga never returns the key and cannot update a connector, so an existing
connector always shows as unchanged. To rotate the key, remove the entry, run with
`--prune`, then add it back.

## Notification connectors

Keyed by name. Tranga stores every connector as a webhook (`url`, `http_method`,
`body`, `headers`); `%title` and `%text` are filled in when a notification is sent.
`type: gotify` is a shortcut that expands exactly like Tranga's own Gotify form.

```yaml
notification_connectors:
  gotify:
    type: gotify
    url: http://gotify
    app_token: ${GOTIFY_APP_TOKEN}
    priority: 5
  webhook:
    url: http://hooks.local/tranga
    body: '{"title": "%title", "text": "%text"}'
    headers:
      Authorization: Bearer ${HOOK_TOKEN}
```

Tranga has no update for connectors, so a changed one is deleted and recreated
under the same name. Header values show as fingerprints in a plan.
