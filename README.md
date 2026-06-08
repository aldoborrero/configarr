# configarr

Configuration manager for *arr applications and SABnzbd. Declaratively manage your Radarr, Sonarr, Prowlarr, Bazarr, and SABnzbd instances from a single YAML file.

## Features

- **Radarr/Sonarr**: Root folders, naming, quality profiles, download clients
- **Prowlarr**: Indexers, applications, download clients
- **Bazarr**: Language profiles, providers, Sonarr/Radarr connections
- **SABnzbd**: Servers, categories, misc settings
- **Multi-instance**: Configure multiple instances of each service
- **Environment variables**: `${VAR}` substitution in config values

## Usage

```bash
nix run github:aldoborrero/configarr -- --config configarr.yml
```

### Options

```
--config PATH    Path to configarr.yml (default: ./configarr.yml)
--service NAME   Only process specific service (radarr, sonarr, prowlarr, bazarr, sabnzbd)
--instance NAME  Only process specific instance
--dry-run        Show what would be done (Bazarr only)
--debug          Enable debug logging
```

## Configuration

See [configarr.yml.example](configarr.yml.example) for a full example.

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
