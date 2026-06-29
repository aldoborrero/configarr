# TRaSH-Guides examples

These configs adapt [TRaSH-Guides](https://trash-guides.info) quality-profile
recommendations into the configarr schema. They are **complete, ready-to-run**
profiles: the custom-format specifications are copied verbatim from the
TRaSH-Guides data, and each custom format's score is its TRaSH `default` score.

| File | Adapts | Covers |
|---|---|---|
| [`radarr-hd-bluray-web.yml`](radarr-hd-bluray-web.yml) | Radarr **"HD Bluray + WEB"** | WEBDL 1080p, Bluray 720p/1080p; release-group tiers; unwanted-source rejection |
| [`sonarr-web-1080p.yml`](sonarr-web-1080p.yml) | Sonarr **"WEB-1080p"** | WEBDL/WEBRip 1080p; WEB release-group tiers; unwanted-source rejection |

Each file defines, for a single instance:

- a `custom_formats` block — the release-group **tier** formats and the
  **Repack/Proper** formats the profile scores, plus the TRaSH **Unwanted Formats**
  set (BR-DISK, LQ, x265 HD transcodes, AV1, upscaled releases, …) at large
  negative scores; and
- one `quality_profiles` definition — the allowed qualities, cutoff, and the
  `custom_format_scores` map that wires every format to its TRaSH score.

## Usage

```bash
cp ../.env.example .env   # then set RADARR_API_KEY / SONARR_API_KEY
configarr --config radarr-hd-bluray-web.yml --service radarr
configarr --config sonarr-web-1080p.yml --service sonarr
```

Adjust `base_url` to point at your instance, and merge the `sonarr:`/`radarr:`
blocks into your main `configarr.yml` if you'd rather keep one file.

## How these differ from TRaSH / Recyclarr

configarr applies custom formats and scores like Recyclarr does, but its quality
model is simpler — worth knowing so the result matches your expectation:

- **No quality *groups* are created.** configarr enables or disables individual
  qualities; a `qualities:` group entry just enables its members. The grouping is
  for readability only.
- **The cutoff is an individual quality.** TRaSH's "WEB-1080p" profile uses the
  `WEB 1080p` quality *group* as its cutoff; configarr resolves cutoffs by quality
  name, so it is mapped to `WEBDL-1080p` here.
- **Only the listed formats are scored.** These files include a curated, faithful
  subset (the profile's own tier/repack formats plus the standard Unwanted set).
  To add more — HDR, audio, streaming-service, or release-group formats — copy the
  corresponding entries from TRaSH-Guides into the `custom_formats.definitions` and
  `custom_format_scores` blocks. See the
  [configuration schema](https://aldoborrero.github.io/configarr/reference/schema.html#custom-formats--custom_formatsdefinitions).

## Regenerating / staying current

The formats and scores were translated from the
[TRaSH-Guides/Guides](https://github.com/TRaSH-Guides/Guides) JSON
(`docs/json/{radarr,sonarr}/`). When TRaSH updates a format's regex or score,
re-copy the affected `specifications` / scores from that data.

## Attribution

Custom-format definitions and scores are derived from
[TRaSH-Guides](https://trash-guides.info)
([TRaSH-Guides/Guides](https://github.com/TRaSH-Guides/Guides), MIT-licensed
data). All credit for the formats and the curation behind them belongs to the
TRaSH-Guides project and its contributors.
