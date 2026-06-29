# TRaSH-Guides examples

These configs adapt [TRaSH-Guides](https://trash-guides.info) quality-profile
recommendations into the configarr schema. They are **complete, ready-to-run**
profiles: each custom-format's specifications are copied verbatim from the
TRaSH-Guides data, and each format's score is its TRaSH `default` score, plus the
standard **Unwanted Formats** set at negative scores.

Files are grouped by service. Pick the profile that matches the quality you want.

## Radarr — [`radarr/`](radarr/)

| File | TRaSH profile | Covers |
|---|---|---|
| [`hd-bluray-web.yml`](radarr/hd-bluray-web.yml) | HD Bluray + WEB | WEBDL 1080p, Bluray 720p/1080p |
| [`uhd-bluray-web.yml`](radarr/uhd-bluray-web.yml) | UHD Bluray + WEB | WEBDL/Bluray 2160p |
| [`remux-web-1080p.yml`](radarr/remux-web-1080p.yml) | Remux + WEB 1080p | Remux + WEBDL 1080p |
| [`remux-web-2160p.yml`](radarr/remux-web-2160p.yml) | Remux + WEB 2160p | Remux + WEBDL 2160p |
| [`remux-2160p-alternative.yml`](radarr/remux-2160p-alternative.yml) | Remux 2160p (Alternative) | Remux 2160p, alt scoring |
| [`remux-2160p-combined.yml`](radarr/remux-2160p-combined.yml) | Remux 2160p (Combined) | Remux 2160p, combined scoring |
| [`anime-remux-1080p.yml`](radarr/anime-remux-1080p.yml) | [Anime] Remux-1080p | Anime Remux/Bluray 1080p |
| [`sqp-1-1080p.yml`](radarr/sqp-1-1080p.yml) | [SQP] SQP-1 (1080p) | Streaming-Quality-Profile 1, 1080p |
| [`sqp-1-2160p.yml`](radarr/sqp-1-2160p.yml) | [SQP] SQP-1 (2160p) | SQP-1, 2160p |
| [`sqp-1-web-1080p.yml`](radarr/sqp-1-web-1080p.yml) | [SQP] SQP-1 WEB (1080p) | SQP-1 WEB, 1080p |
| [`sqp-1-web-2160p.yml`](radarr/sqp-1-web-2160p.yml) | [SQP] SQP-1 WEB (2160p) | SQP-1 WEB, 2160p |
| [`sqp-2.yml`](radarr/sqp-2.yml) | [SQP] SQP-2 | SQP tier 2 |
| [`sqp-3.yml`](radarr/sqp-3.yml) | [SQP] SQP-3 | SQP tier 3 |
| [`sqp-3-audio.yml`](radarr/sqp-3-audio.yml) | [SQP] SQP-3 (Audio) | SQP tier 3, audio-focused |
| [`sqp-4.yml`](radarr/sqp-4.yml) | [SQP] SQP-4 | SQP tier 4 |
| [`sqp-4-ma-hybrid.yml`](radarr/sqp-4-ma-hybrid.yml) | [SQP] SQP-4 (MA Hybrid) | SQP tier 4, MA hybrid |
| [`sqp-5.yml`](radarr/sqp-5.yml) | [SQP] SQP-5 | SQP tier 5 |

## Sonarr — [`sonarr/`](sonarr/)

| File | TRaSH profile | Covers |
|---|---|---|
| [`web-1080p.yml`](sonarr/web-1080p.yml) | WEB-1080p | WEBDL/WEBRip 1080p |
| [`web-1080p-alternative.yml`](sonarr/web-1080p-alternative.yml) | WEB-1080p (Alternative) | WEB 1080p, alt scoring |
| [`web-2160p.yml`](sonarr/web-2160p.yml) | WEB-2160p | WEBDL/WEBRip 2160p |
| [`web-2160p-alternative.yml`](sonarr/web-2160p-alternative.yml) | WEB-2160p (Alternative) | WEB 2160p, alt scoring |
| [`web-2160p-combined.yml`](sonarr/web-2160p-combined.yml) | WEB-2160p (Combined) | WEB 2160p, combined scoring |
| [`anime-remux-1080p.yml`](sonarr/anime-remux-1080p.yml) | [Anime] Remux-1080p | Anime Remux/Bluray 1080p |

## Quality definitions (sizes)

TRaSH also recommends per-quality **size limits** (min / max / preferred MB per
minute). These are configured separately from the profiles, via
`profiles.quality_definitions`, and they are **instance-level** — pick the one
scheme that matches your primary profile.

| File | Scheme | Pairs with |
|---|---|---|
| [`radarr/quality-definitions-movie.yml`](radarr/quality-definitions-movie.yml) | Movie (default) | HD/UHD Bluray + WEB, Remux + WEB |
| [`radarr/quality-definitions-anime.yml`](radarr/quality-definitions-anime.yml) | Anime | [Anime] Remux-1080p |
| [`radarr/quality-definitions-sqp-streaming.yml`](radarr/quality-definitions-sqp-streaming.yml) | SQP Streaming | SQP WEB profiles |
| [`radarr/quality-definitions-sqp-uhd.yml`](radarr/quality-definitions-sqp-uhd.yml) | SQP UHD | SQP UHD/Bluray profiles |
| [`sonarr/quality-definitions-series.yml`](sonarr/quality-definitions-series.yml) | Series (default) | WEB-1080p / WEB-2160p |
| [`sonarr/quality-definitions-anime.yml`](sonarr/quality-definitions-anime.yml) | Anime | [Anime] Remux-1080p |

Merge the chosen scheme's `profiles.quality_definitions` into the same instance
as your profile (configarr applies quality definitions before quality profiles),
or run the file standalone.

## Usage

```bash
cp ../.env.example .env   # then set RADARR_API_KEY / SONARR_API_KEY

# A profile, then its matching quality definitions, against the same instance:
configarr --config radarr/sqp-1-web-1080p.yml --service radarr
configarr --config radarr/quality-definitions-sqp-streaming.yml --service radarr

configarr --config sonarr/web-1080p.yml --service sonarr
configarr --config sonarr/quality-definitions-series.yml --service sonarr
```

Adjust `base_url` to point at your instance, and merge the `sonarr:`/`radarr:`
blocks into your main `configarr.yml` if you'd rather keep one file. Each file
configures a single `main` instance.

## How these differ from TRaSH / Recyclarr

configarr applies custom formats and scores like Recyclarr does, but its quality
model is simpler — worth knowing so the result matches your expectation:

- **No quality *groups* are created.** configarr enables or disables individual
  qualities; a `qualities:` group entry just enables its members. The grouping is
  for readability only.
- **The cutoff is an individual quality.** Many TRaSH profiles use a quality
  *group* as the cutoff (e.g. `WEB 1080p`, `Bluray|WEB-1080p`). configarr resolves
  cutoffs by quality name, so those are mapped to a concrete member (the header of
  each file notes when this happened).
- **Curated, faithful subset.** Each file includes the profile's own scored
  formats plus the standard Unwanted set. To add more — HDR, audio,
  streaming-service, or extra release-group formats — copy the corresponding
  entries from TRaSH-Guides into `custom_formats.definitions` and
  `custom_format_scores`. See the
  [configuration schema](https://aldoborrero.github.io/configarr/reference/schema.html#custom-formats--custom_formatsdefinitions).

> [!NOTE]
> The **SQP** profiles are advanced. These files reproduce each SQP profile's
> formats and scores; pair them with the matching SQP quality definitions
> (`quality-definitions-sqp-streaming.yml` or `quality-definitions-sqp-uhd.yml`,
> see below). For the complete setup, also add any additional optional formats
> from the TRaSH SQP guide.

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
