# Bazarr

Bazarr handles subtitles. configarr manages its connections to Sonarr/Radarr, its
subtitle **providers**, and its **language profiles**. Path prefix:
`bazarr.instances.<name>`.

> [!NOTE]
> Exact keys live in the [Bazarr section of the schema](../reference/schema.md#bazarr).
> This page explains the behaviour, which is more nuanced than the other services.

## Connections — `general`, `sonarr`, `radarr`

These three are **flat passthrough maps**: every key you write is sent to the
Bazarr settings field of the same name, under that section. There is no allow-list,
so consult Bazarr's own settings field names for valid keys.

```yaml
bazarr:
  instances:
    main:
      base_url: http://localhost:6767
      api_key: ${BAZARR_API_KEY}

      general:
        use_sonarr: true
        use_radarr: true

      sonarr:
        ip: localhost
        port: 8989
        apikey: ${SONARR_API_KEY}

      radarr:
        ip: localhost
        port: 7878
        apikey: ${RADARR_API_KEY}
```

## Providers

`providers` is a map keyed by provider name; each value is a flat passthrough map
of that provider's fields.

```yaml
providers:
  opensubtitlescom:
    username: ${OST_USER}
    password: ${OST_PASSWORD}
```

Two behaviours to know:

> [!NOTE]
> **Provider names are used verbatim (with one exception)**
>
> configarr keeps a small rename map, but **only `submate` is renamed** (to Bazarr's
> `whisperai`). Every other provider name is used exactly as you write it — so this
> is a single rename plus passthrough, not an allow-list. Match Bazarr's own
> provider names.

> [!WARNING]
> **enabled_providers is force-managed**
>
> You do **not** set `enabled_providers` yourself. configarr reads Bazarr's current
> enabled list and **adds** each provider you configure (additive — it never removes
> others), then writes the combined list back.

## Language profiles

A **list** of profile maps. Their sync semantics are stronger than most resources:

> [!WARNING]
> **Listed profiles overwrite; unlisted profiles are preserved**
>
> A profile you list is **rebuilt from your config and overwrites** the server copy
> (whether it was new or already existed). A profile that exists on the server but is
> **absent from your config is left untouched**. The save is a single batch write,
> so the whole set succeeds or fails together.

```yaml
language_profiles:
  - name: English
    cutoff: English
    languages:
      - English
      - name: Spanish
        forced: true
    must_contain: []
    must_not_contain: []
```

Notes on the fields:

- **`languages`** entries are either a bare language **name** string, or a map with
  `name`/`language` plus optional `hi`, `forced`, `audio_exclude`. Entries whose
  name doesn't resolve to a known language code are dropped.
- **`cutoff`** must be a language name that also appears in `languages` and resolves
  to a known code; otherwise it is silently set to null.
- `must_contain` / `must_not_contain` / `original_format` map to Bazarr's
  `mustContain` / `mustNotContain` / `originalFormat`.

## Default profile

Bazarr only searches subtitles for series and movies that carry a language profile,
and its own `serie_default_profile` / `movie_default_profile` settings apply only to
items added **after** they are set. `default_profile` fills the gap: every series and
movie **with no profile** gets the named one.

```yaml
default_profile:
  series: Spanish + English
  movies: Spanish + English
```

- The value is a profile **name**, resolved against the server's profiles (including
  one created from `language_profiles` in the same run). An unknown name plans nothing.
- Only items whose profile is unset are changed. A profile chosen by hand is never
  overridden, and nothing is ever removed from Bazarr.
- Either key may be omitted to leave that library alone.
- To cover items Sonarr/Radarr add later, also set Bazarr's own defaults under
  `general` (`serie_default_enabled`, `serie_default_profile` with the profile id, and the
  `movie_` equivalents).

## Previewing changes

> [!TIP]
> `--plan` (alias `--dry-run`) works for Bazarr like every other service: it fetches
> current state with **read** (GET) requests, diffs it against your config, and
> prints what would change without writing. Bazarr settings are diffed, so a section
> whose managed fields already match reports `unchanged` and is not shown. See
> [Plan, Apply & Scoping](../concepts/dry-run-and-scoping.md).

## Full example

[`examples/bazarr.yml`](https://github.com/aldoborrero/configarr/blob/main/examples/bazarr.yml)
