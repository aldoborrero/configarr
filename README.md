# configarr

Configuration manager for *arr applications and SABnzbd. Declaratively manage your Radarr, Sonarr, Prowlarr, Bazarr, and SABnzbd instances from a single YAML file.

📖 **[Read the documentation](https://aldoborrero.github.io/configarr/)** — installation, core concepts, per-service guides, the full configuration schema, recipes, and troubleshooting.

## Features

- **Radarr/Sonarr**: Root folders, naming, quality profiles, download clients
- **Prowlarr**: Indexers, applications, download clients
- **Bazarr**: Language profiles, providers, Sonarr/Radarr connections
- **SABnzbd**: Servers, categories, misc settings
- **Multi-instance**: Configure multiple instances of each service
- **Environment variables**: `${VAR}` substitution in config values
- **Plan & apply**: preview the diff with `--plan`; sync applies only what changed, with opt-in `--prune` to remove unmanaged resources

## Usage

configarr diffs your `configarr.yml` against each service and applies only what
changed. Preview first with `--plan`, then run it for real:

```bash
# Preview the diff (no writes)
nix run github:aldoborrero/configarr -- --config configarr.yml --plan

# Apply the changes
nix run github:aldoborrero/configarr -- --config configarr.yml
```

### Docker

A multi-purpose image is published to the GitHub Container Registry. The
container's working directory is `/config` and configarr defaults to
`./configarr.yml`, so mounting your config there needs no extra arguments:

```bash
docker run --rm \
  -v "$PWD/configarr.yml:/config/configarr.yml" \
  ghcr.io/aldoborrero/configarr:latest
```

If you keep secrets in a `.env` next to the config, mount the whole directory
instead and configarr will load it automatically:

```bash
docker run --rm \
  -v "$PWD:/config" \
  ghcr.io/aldoborrero/configarr:latest --debug
```

### Options

```
--config PATH    Path to configarr.yml (default: ./configarr.yml)
--service NAME   Only process a specific service (radarr, sonarr, prowlarr, bazarr, sabnzbd)
--instance NAME  Only process a specific instance
--plan           Preview the diff without writing (alias: --dry-run)
--prune          Also delete unmanaged resources (sync is additive by default)
--debug          Enable debug logging
```

## Configuration

See the [`examples/`](examples/) folder for ready-to-adapt configs — a
[minimal](examples/minimal.yml) skeleton, one file per service, and a
[full](examples/full.yml) multi-instance example. Every supported key is
documented in the [schema reference](skills/configarr-config/references/schema.md).

## Claude Code skill

This repo ships a [Claude Code](https://claude.com/claude-code) skill that helps you
author and validate `configarr.yml`, backed by a source-verified reference for every
supported key. Install it with:

```
/plugin marketplace add aldoborrero/configarr
/plugin install configarr
```

Claude can then help you write quality profiles, custom formats, root folders,
download clients, indexers, Bazarr language profiles, SABnzbd servers, and more —
using the exact YAML keys configarr accepts.

## Development

```bash
nix develop
```

## License

Apache-2.0
