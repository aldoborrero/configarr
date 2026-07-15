# TRaSH-Guides examples

These configs are the **expanded form** of [TRaSH-Guides](https://trash-guides.info)
quality profiles, written out by hand in the configarr schema: each custom-format's
specifications copied verbatim from the TRaSH-Guides data, each format's score set
to its TRaSH `default`, plus the standard **Unwanted Formats** set at negative
scores.

They are kept as a **reference** — a worked example of what a full TRaSH profile
looks like once it lands in configarr, and what the `trash:` import (below)
produces for you.

> [!TIP]
> For real setups, prefer the **`trash:` import** rather than these hand-written
> files. A single `trash_id` yields the same profile — with the correct quality
> groups and the group cutoff — and it tracks upstream changes automatically, with
> no hand-maintenance. See [`../trash.yml`](../trash.yml) and the
> [`trash` schema section](https://aldoborrero.github.io/configarr/reference/schema.html#trash-guides-import--trash).

## What's here

Two illustrative full profiles are kept, one per service:

| File | TRaSH profile |
|---|---|
| [`radarr/sqp-1-web-1080p.yml`](radarr/sqp-1-web-1080p.yml) | Radarr `[SQP] SQP-1 WEB (1080p)` |
| [`sonarr/web-1080p.yml`](sonarr/web-1080p.yml) | Sonarr `WEB-1080p` |

Each builds its quality group and sets the cutoff to the TRaSH quality **group**
name (`Bluray|WEB-1080p` for Radarr, `WEB 1080p` for Sonarr).

## Quality definitions (sizes)

TRaSH also recommends per-quality **size limits** (min / max / preferred MB per
minute). These are configured separately from the profiles, via
`profiles.quality_definitions`, and they are **instance-level** — pick the one
scheme that matches your primary profile.

| File | Scheme |
|---|---|
| [`radarr/quality-definitions-movie.yml`](radarr/quality-definitions-movie.yml) | Movie (default) |
| [`radarr/quality-definitions-anime.yml`](radarr/quality-definitions-anime.yml) | Anime |
| [`radarr/quality-definitions-sqp-streaming.yml`](radarr/quality-definitions-sqp-streaming.yml) | SQP Streaming |
| [`radarr/quality-definitions-sqp-uhd.yml`](radarr/quality-definitions-sqp-uhd.yml) | SQP UHD |
| [`sonarr/quality-definitions-series.yml`](sonarr/quality-definitions-series.yml) | Series (default) |
| [`sonarr/quality-definitions-anime.yml`](sonarr/quality-definitions-anime.yml) | Anime |

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

## Prefer the `trash:` import

These files are static snapshots. The maintained way to get the same result — and
to stay current as TRaSH updates a format's regex or score — is the `trash:`
import: point it at a local [TRaSH-Guides/Guides](https://github.com/TRaSH-Guides/Guides)
checkout and reference a profile by `trash_id`. configarr then builds the quality
groups, resolves the group cutoff, and scores every custom format the profile
uses, all from that single id.

See [`../trash.yml`](../trash.yml) for a runnable example, and the
[`trash` schema section](https://aldoborrero.github.io/configarr/reference/schema.html#trash-guides-import--trash)
for the full option list.

## Attribution

Custom-format definitions and scores are derived from
[TRaSH-Guides](https://trash-guides.info)
([TRaSH-Guides/Guides](https://github.com/TRaSH-Guides/Guides), MIT-licensed
data). All credit for the formats and the curation behind them belongs to the
TRaSH-Guides project and its contributors.
