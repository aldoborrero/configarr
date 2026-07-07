# Quick Start

This walks you from nothing to a working sync against a single Sonarr instance,
then shows how to grow the file. It assumes you can already reach your *arr apps
over HTTP and have their API keys.

## 1. Find your API keys

Each application exposes its API key under **Settings → General** in its web UI.
You'll need the `base_url` (the address you use to reach it) and that key for
every instance you manage.

## 2. Create a `.env`

Keep secrets out of the config file. configarr expands `${VAR}` in any string and
auto-loads a `.env` from the same directory as your config:

```bash
# .env
SONARR_API_KEY=your-real-key-here
```

> [!WARNING]
> **Don't commit secrets**
>
> Add `.env` to your `.gitignore`. The config file itself is safe to commit as long
> as every secret is a `${VAR}` reference.

## 3. Write `configarr.yml`

Start minimal — just a connection plus one thing to manage:

```yaml
sonarr:
  instances:
    main:
      base_url: http://localhost:8989
      api_key: ${SONARR_API_KEY}

      settings:
        root_folders:
          - path: /tv
```

Every instance **requires** `base_url` and `api_key`; everything else is
optional. `main` is just a label you choose — name instances however you like.

## 4. Run it

```bash
configarr --config configarr.yml
```

configarr connects to Sonarr, ensures `/tv` exists as a root folder, and prints one
line per provider that changed:

```text
sonarr/main — root folders: applied 1 change(s)
```

Run it again and there's nothing to do — most resources are idempotent, so the
second run prints `No changes to apply.`. Preview a run first with `--plan`, which
shows the per-resource ops (`create` / `update` / `delete`) without writing. The
[result vocabulary](../concepts/mental-model.md#idempotency-and-the-result-vocabulary)
is explained in Core Concepts.

## 5. Grow the file

Add resources under the same instance. Here's a quality profile with a custom
format:

```yaml
sonarr:
  instances:
    main:
      base_url: http://localhost:8989
      api_key: ${SONARR_API_KEY}

      settings:
        root_folders:
          - path: /tv

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
                - Bluray-1080p
              custom_format_scores:
                x265: 100
```

configarr always syncs **custom formats before quality profiles** within an
instance, so the `x265: 100` score above resolves to the format defined in the
same file. (See [Sync Order](../concepts/sync-order.md).)

## 6. Add more services

Each service is a top-level key with its own `instances`. Drop in only what you
run:

```yaml
radarr:
  instances:
    main:
      base_url: http://localhost:7878
      api_key: ${RADARR_API_KEY}

prowlarr:
  instances:
    main:
      base_url: http://localhost:9696
      api_key: ${PROWLARR_API_KEY}
```

## Where to go next

- Understand what configarr will and won't change: [Mental Model](../concepts/mental-model.md).
- Set up a specific service end to end: the [Service Guides](../services/radarr-sonarr.md).
- Copy ready-made configs: the [Cookbook](../cookbook/recipes.md) and the
  [`examples/`](https://github.com/aldoborrero/configarr/tree/main/examples) folder.
- Look up any key: the [Configuration Schema](../reference/schema.md).
