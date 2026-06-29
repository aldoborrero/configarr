# configarr

**configarr** is a configuration manager for *arr applications and SABnzbd. It lets
you declaratively manage [Radarr](https://radarr.video),
[Sonarr](https://sonarr.tv), [Prowlarr](https://prowlarr.com),
[Bazarr](https://www.bazarr.media), and [SABnzbd](https://sabnzbd.org) from a
single `configarr.yml` file.

Instead of clicking through each application's web UI — and re-doing it every time
you rebuild a container or stand up a new instance — you describe the desired
state once, in version-controlled YAML, and run one command to apply it.

```bash
configarr --config configarr.yml
```

## What it manages

| Service | Resources |
|---|---|
| **Radarr / Sonarr** | Root folders, naming, quality profiles, quality definitions, delay profiles, release profiles (Sonarr), custom formats, download clients, notifications |
| **Prowlarr** | Indexers, applications, download clients |
| **Bazarr** | General/Sonarr/Radarr connections, subtitle providers, language profiles |
| **SABnzbd** | Servers, categories, misc settings |

It also supports **multiple instances** of each service (for example a 1080p and a
4K Radarr side by side) and **`${VAR}` substitution** so secrets stay out of the
config file.

## How it works

configarr reads your YAML, talks to each application's HTTP API, and reconciles
the live configuration toward what you declared. Most resources are idempotent —
running twice is safe and the second run reports `UNCHANGED`. The
[Mental Model](concepts/mental-model.md) chapter explains the model in full.

> [!NOTE]
> **Declarative, but not a full diff engine**
>
> configarr **adds and updates** the resources you declare. With a few documented
> exceptions it does not delete resources you remove from the file, and it is not a
> two-way sync — your `configarr.yml` is the source of truth for the keys it
> manages, not a mirror of the entire application state. See
> [Mental Model](concepts/mental-model.md).

## Where to start

- New here? Read [Installation](getting-started/installation.md) then
  [Quick Start](getting-started/quick-start.md).
- Want to understand the behaviour before trusting it with a live setup? Read the
  [Core Concepts](concepts/mental-model.md).
- Looking up an exact key? Jump to the
  [Configuration Schema](reference/schema.md) — the exhaustive, source-verified
  reference.

> [!TIP]
> **Editing your config with Claude**
>
> This repository ships a [Claude Code](https://claude.com/claude-code) skill that
> helps you author and validate `configarr.yml`, backed by the same source-verified
> reference embedded in this book. See
> [Editing with the Claude skill](getting-started/installation.md#editing-with-the-claude-skill).
