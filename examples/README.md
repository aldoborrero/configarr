# Examples

Sample `configarr.yml` files. Every key here is part of configarr's documented
schema — see [`skills/configarr-config/references/schema.md`](../skills/configarr-config/references/schema.md)
for the exhaustive, source-verified reference.

| File | What it shows |
|---|---|
| [`minimal.yml`](minimal.yml) | Bare connections to every service (`base_url` + `api_key` only). |
| [`radarr.yml`](radarr.yml) | Radarr: root folders, naming, quality, custom formats, download clients, notifications. |
| [`sonarr.yml`](sonarr.yml) | Sonarr: episode naming, release profiles, quality, download clients. |
| [`prowlarr.yml`](prowlarr.yml) | Prowlarr: indexers, applications, download clients. |
| [`bazarr.yml`](bazarr.yml) | Bazarr: Sonarr/Radarr connections, providers, language profiles. |
| [`sabnzbd.yml`](sabnzbd.yml) | SABnzbd: servers, categories, misc settings. |
| [`full.yml`](full.yml) | Every service in one file, including a multi-instance setup. |
| [`.env.example`](.env.example) | Secrets referenced by the examples via `${VAR}`. |
| [`trash-guides/`](trash-guides/) | Ready-to-run quality profiles adapting [TRaSH-Guides](https://trash-guides.info) custom formats and scores for Radarr and Sonarr. |

## Usage

Pick a file, fill in your URLs, and supply secrets through environment
variables. configarr expands `${VAR}` in any string value and auto-loads a
`.env` file from the config's directory:

```bash
cp examples/.env.example .env   # then edit
nix run github:aldoborrero/configarr -- --config examples/full.yml
```

Process a single service or instance while iterating:

```bash
configarr --config examples/full.yml --service radarr
configarr --config examples/full.yml --service radarr --instance uhd
```
