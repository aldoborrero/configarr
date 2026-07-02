# TRaSH-Guides loader — design note

Status: **implemented (phases 1–3a):** the loader (`configarr/trash/`), the CLI
resolve pass, and import of custom formats + scores + quality definitions. Still
open: `source: git` (phase 4) and full quality-*profile* import (phase 3b, needs
custom quality-group support in the provider). Branch-local engineering note (not
part of the mdbook build).

**Decisions locked (see "Decisions needed" below):**
- **Source:** `local` checkout only in phase 1; runtime `git` fetch deferred to a
  later phase.
- **Merge point:** a **separate resolve pass** invoked by the CLI *after*
  `parse_config`; `parse_config` stays pure and offline.

## Goal

Let a `configarr.yml` pull custom formats, custom-format scores, quality
definitions, and (optionally) whole quality profiles directly from the
[TRaSH-Guides](https://github.com/TRaSH-Guides/Guides) repository by **`trash_id`**,
instead of hand-copying JSON into `examples/trash-guides/`. Keep the declarative,
idempotent model the diffing engine already provides.

## The one architectural decision

**TRaSH is a config-expansion concern, not a provider concern.**

The diffing engine's three layers (`config.py` reshape → `models.py` contract →
`<provider>.build_desired()`) already have exactly the seam we need. TRaSH resolution
is *another reshape step in `config.py`*: fetch guide data, expand the user's
`trash_id` references into the **same internal dicts** `parse_config` already produces
(`custom_formats`, `quality_profiles`, `quality_definitions`), then hand those to the
existing Pydantic models.

Consequence: **no provider changes, no engine changes, no new resource kinds.**
`CustomFormatProvider`, `QualityProfileProvider`, and `QualityDefinitionProvider`
never learn that TRaSH exists — they just receive a fuller config. Idempotency,
`--plan`, `--apply`, `--prune`, secret redaction: all unchanged and already tested.

```
configarr.yml ──parse_config (pure)──► user dicts ──┐
                                                     ├──CLI resolve pass──► expanded config ──► models ──► providers
TRaSH checkout ──resolve trash_ids──► expanded dicts ┘
```

`parse_config` stays network-/filesystem-free (the schema-validation smoke check keeps
working). The CLI runs `resolve_trash(config)` as an explicit step after parsing and
before planning; it deep-merges resolved dicts under the user's own definitions
(user-authored keys win).

## What TRaSH ships (verified against recyclarr's reader)

- **`metadata.json`** at repo root: per service (`radarr`/`sonarr`), lists *directory
  paths* for `custom_formats`, `qualities`, `naming`, `custom_format_groups`,
  `quality_profiles`, `quality_profile_groups`. Discovery is data-driven — glob
  `*.json` recursively under each listed dir. Never hardcode paths.
- **Custom-format JSON**: `{ trash_id, name, includeCustomFormatWhenRenaming,
  trash_scores: {<set>: int}, specifications: [...] }`. Each spec is
  `{ name, implementation, negate, required, fields }` where **`fields` is either an
  object `{"value": x}` or an array `[{name, value}]`** — must normalize to the array
  form. Field values are loosely typed (`"5"` vs `5`).
- **Quality-size JSON** (a.k.a. quality definitions): `{ type, qualities: [{quality,
  min, max, preferred}] }`, decimals.
- **Quality-profile JSON**: `{ trash_id, name, trash_score_set, upgradeAllowed,
  cutoff, minFormatScore, ..., items: [{name, allowed, items:[...]}], formatItems }`.
  `items` may nest child qualities → quality **groups**.

Identity is the stable **`trash_id`**, not the name (names change). Score sets let one
CF carry different scores for different intents; a profile selects one via
`trash_score_set`.

## Proposed module: `configarr/trash/`

Kept in its own package so the engine stays client-free and TRaSH stays optional.

| file | responsibility |
|---|---|
| `source.py` | Obtain the guide tree. `git` clone/pull into a cache dir **or** a user-pointed local checkout. Pin a ref. Returns a root `Path`. |
| `metadata.py` | Parse `metadata.json` → typed paths (mirror of recyclarr's `RepoMetadata`). |
| `catalog.py` | Load + index guide JSON by `trash_id` (CFs, quality sizes, profiles). Cache by path. Handle the `fields` object/array normalization here. Reuse `normalize.coerce_scalar` for loose scalars. |
| `resolve.py` | `resolve_trash(config)`: for each instance with a `trash:` block, emit the internal `custom_formats` / `quality_profiles` / `quality_definitions` dicts and deep-merge them under the user's own definitions (user-authored keys win). |

The CLI (`__main__.py`) calls `resolve_trash(config)` after `parse_config` and before
`run_plan`/`run_apply`. `parse_config` itself never touches TRaSH, keeping it pure.

## Proposed YAML surface

Declarative, mirrors recyclarr's intent but folds into configarr's existing sections:

```yaml
radarr:
  - name: movies
    base_url: ...
    api_key: ${RADARR_MOVIES_API_KEY}

    trash:
      # where the guide comes from; pinned for reproducibility
      source: git                 # git | local
      ref: master                 # branch/tag/sha (git only)
      path: /path/to/Guides       # local only

      quality_definition: movie   # apply a TRaSH quality-size set

      custom_formats:
        - trash_ids:
            - 570bc9e4... # HDR
            - e7c2fcae... # DV HDR10
          assign_scores_to:
            - profile: "HD Bluray + WEB"   # score into this managed profile
        - trash_ids: [ ... ]               # import CFs with no scoring (score 0)

      quality_profiles:
        - trash_id: <profile-trash-id>     # import a whole guide profile
          name: "HD Bluray + WEB"          # optional rename
          score_set: default               # which trash_score_set to use

    # user-authored CFs still work and take precedence on name conflicts
    custom_formats:
      My Custom CF:
        specifications: [ ... ]
```

The resolver turns the above into the shapes the providers already read:
- `trash.custom_formats[].trash_ids` → entries in the instance `custom_formats` dict.
- `assign_scores_to` → `formatItems` scores on the named managed quality profile.
- `quality_definition: movie` → the instance `quality_definitions`.
- `trash.quality_profiles[]` → full `quality_profiles` entries (qualities + groups +
  `formatItems` from the chosen score set).

## Parsing concerns to get right (recyclarr precedent in parentheses)

1. **`fields` object-or-array** — normalize object → `[{name, value}]`
   (`FieldsArrayJsonConverter`). configarr's `CustomFormatProvider._build_spec`
   currently assumes the dict form; the loader must hand it the normalized shape.
2. **Loose scalars** — `"5"` vs `5`; reuse `normalize.coerce_scalar`
   (recyclarr: `NumberHandling = AllowReadingFromString` + `FieldValue`).
3. **trash_id identity + dedup** — index by `trash_id`; last file wins on collision
   (`GroupBy(trash_id).Last()`). Quality sizes dedup by `type`, case-insensitive.
4. **Score sets** — resolve `assign_scores_to` / `score_set` against
   `trash_scores[<set>]`, default set `"default"`, missing → 0.
5. **Quality groups** — profile `items` nest child qualities; map straight onto the
   grouped structure `QualityProfileProvider` already builds.
6. **Name conflicts** — a user-authored CF/profile with the same name as a resolved
   TRaSH one: user wins, and we `log` the override (no silent shadowing).

Deferred to a later phase: custom-format **groups** and the **category markdown**
parser (`docs/*/…-collection-of-custom-formats.md`), media naming.

## Fetching, caching, reproducibility

- Runtime network is already the norm (the CLI talks to every *arr over HTTP), so a
  runtime `git` fetch is consistent — **but** default to a **pinned `ref`** and cache
  under a stable dir (respect `$XDG_CACHE_HOME`), refreshing only when the ref moves.
- Offer `source: local` pointing at an existing checkout (recyclarr's
  `LocalProviderLocation`) for fully offline / Nix-reproducible runs and for tests.
- The Nix package/flake and Docker image need **no** change: this is runtime CLI
  behavior, not build-time. Document that `--plan` may perform a one-time clone.

## Idempotency

Nothing new to prove. The resolver only *builds desired state*; the engine's existing
diff/normalize path decides changes and is already covered by the provider test
suites. A resolved config must satisfy: resolve → `--apply` → resolve → `--plan` is
empty. Add one end-to-end test asserting that against a fixture guide.

## Testing strategy

- Vendor a **tiny fake Guides tree** under `tests/trash/fixtures/` (a `metadata.json`,
  two CFs incl. one with object-form `fields` and one array-form, one quality-size
  set, one profile with a group). No network.
- Unit-test `metadata`, `catalog` (both `fields` forms, scalar coercion, trash_id
  dedup), and `resolve` (scores, groups, name-conflict precedence).
- One integration test: fixture guide + a `trash:` config → assert the expanded
  instance dicts match hand-written expected shapes, then feed them through the real
  providers with `responses`-mocked HTTP and assert a clean re-plan.

## Phased rollout

1. `source` (local only) + `metadata` + `catalog` with the `fields`/scalar/trash_id
   handling. No YAML surface yet — just the loader, unit-tested.
2. `resolve` for `custom_formats` + `assign_scores_to`, wired into the CLI resolve
   pass; YAML `trash.custom_formats`. Ship this — it's the 80% use case.
3. `quality_definition` + full `quality_profiles` import (groups, score sets).
4. `source: git` with ref pinning + cache.
5. (Later) CF groups, category markdown, media naming.

## Decisions

- **Fetch model** — ✅ **local checkout only in phase 1**; runtime `git` fetch + ref
  pinning + cache deferred to phase 4.
- **Where merge happens** — ✅ **separate resolve pass**, invoked by the CLI after a
  pure `parse_config`.
- **Scoping of `trash:`** — per-instance (matches the rest of the schema; simpler than
  a shared top-level block). Open to revisit if a shared block proves cleaner.
- **Schema reference** — this adds keys, so `skills/configarr-config/references/
  schema.md` (the single source of truth) must grow a `trash:` section when phase 2
  lands.
