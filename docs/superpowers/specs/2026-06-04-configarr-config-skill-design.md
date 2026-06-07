# Design: `configarr-config` Claude skill (in-repo plugin)

> Revised after an adversarial review (workflow) that cross-checked every claim
> against source. Key reversals from the first draft are called out inline.

## Goal

Ship a **publicly installable Claude Code plugin, hosted inside the configarr
repo**, containing one skill that helps a user (via Claude) **write, edit,
validate, and extend a `configarr.yml`**.

The skill exists because the configarr YAML schema is **entirely undocumented and
implicit**. It is defined by **three** code layers (the first draft missed the
middle one):

1. `configarr/config.py` `parse_*_instance` functions — read the *nested* YAML the
   user writes and **reshape/rename keys** (e.g. `upgrades_allowed` →
   `upgrade.allowed`).
2. `configarr/models.py` **Pydantic models** (`ArrServiceConfig`, `ProwlarrConfig`,
   `BazarrConfig`, `SabnzbdConfig`) — the **authoritative top-level contract**:
   which sections exist per instance and their defaults. `sync.py` reads these as
   typed attributes (`config.root_folders`, `config.naming_config`, …), *not* via
   `config.get`.
3. Each service client's `sync_*` methods — read the **inner per-resource dicts**
   via `config.get("key", default)`.

There is also no example config: the README links a `configarr.yml.example` that
does not exist in the repo. So the schema knowledge must be **bundled with the
skill** — installers will not have the configarr source checked out.

## Non-goals (explicitly out of scope)

- Creating/fixing the missing `configarr.yml.example` repo file. The skill's
  bundled recipes cover the gap. (Confirmed kept out of scope.)
- Changing any configarr runtime code or the YAML schema itself.
- Covering more than the five existing services. (But coverage **within** those
  five must be exhaustive — see Component 2.)

## Distribution & decisions (locked)

| Decision | Choice |
|---|---|
| Skill purpose | Author/validate/extend `configarr.yml` |
| Location | In-repo plugin, version-controlled with the code |
| Distribution | Plugin inside the configarr repo (marketplace + one plugin) |
| Schema delivery | **Exhaustive reference doc**, bundled as one file |
| Reference split | **Single `references/schema.md`** holding schema **and** the long-tail recipes; SKILL.md stays lean |
| Plugin namespace | `configarr` |
| Skill name | `configarr-config` (invocable as `/configarr:configarr-config`) |
| Capabilities | Authoring workflow + validation guidance + recipes + exhaustive schema |

## Architecture: structure added to the repo

Mirrors the proven working pattern of the user's own `nix-search-marketplace`
(a Python repo that also ships a skill). **Plugin at repo root; no `plugin.json`.**

```
.claude-plugin/
  marketplace.json            # one plugin entry; source "./"; explicit skills array
skills/
  configarr-config/
    SKILL.md                  # LEAN hub: model + workflow + validation + gotchas + 1-2 core recipes
    references/
      schema.md               # EXHAUSTIVE per-key reference (all 5 services) + Recipes section + "how to refresh" note
```

`marketplace.json` shape (verified against working examples — no nested `plugin/`
dir, no `plugin.json`):

```json
{
  "name": "configarr",
  "owner": { "name": "Aldo Borrero", "email": "aldo@aldoborrero.com" },
  "metadata": { "description": "...", "version": "1.0.0" },
  "plugins": [
    {
      "name": "configarr",
      "description": "...",
      "source": "./",
      "strict": false,
      "skills": ["./skills/configarr-config"]
    }
  ]
}
```

Notes / review reversals:
- **Dropped** the first draft's nested `plugin/` directory and `plugin.json`
  entirely — that layout diverged from every working marketplace on the machine
  and left `plugins[].source` unresolved. Repo-root + `source: "./"` is the proven
  shape.
- Marketplace name == plugin name (`configarr`) is **fine** (verified, not a
  conflict). Invocation is `/configarr:configarr-config`.
- `references/schema.md` is reachable from `SKILL.md` by relative link; with the
  repo-root layout the path is stable.

## Component 1 — `SKILL.md` (lean, always-loaded hub)

**Hard cap ~150-200 lines.** The first draft planned to fold *all* recipes inline;
the review showed that bloats always-loaded context. Long-tail recipes move to
`references/schema.md`; only 1-2 core recipes stay inline.

**Frontmatter** — real, `---`-fenced YAML (the nix-search file's heading-style
"frontmatter" is malformed; mirror only its *description wording*, never its
syntax):

```
---
name: configarr-config
description: "Use when writing, editing, validating, or extending a configarr.yml
  ... (trigger phrases) ... Targets the configarr YAML config specifically — not
  general Sonarr/Radarr/Prowlarr usage."
---
```

- Third-person/“Use when” trigger-rich; **under 1024 chars**.
- **Scoped to `configarr.yml`** to avoid over-triggering on generic *arr questions.
- `allowed-tools` unset — the skill reads, writes YAML, and runs configarr.

Body sections (in order):

1. **Mental model**
   - One YAML file; every service nests under `<service>.instances.<name>`.
   - Secrets via `${VAR}` substitution; a `.env` next to the config is
     auto-loaded; missing vars are left literal.
   - **Two-/three-layer schema warning**: the YAML keys you write are not the API
     keys; `config.py` reshapes them and `models.py` defines the section contract.
     Always consult `references/schema.md` for exact key names/nesting — never
     guess from the *arr API.
   - **Ordering is handled by the tool, not by YAML key order.** configarr always
     processes SABnzbd first, then radarr/sonarr/prowlarr/bazarr, and within an
     *arr instance syncs custom formats before quality profiles. The user does
     **not** control this via ordering in the file. (Corrected — the first draft
     wrongly told users to order their YAML.)

2. **Authoring workflow** (numbered)
   1. Read the existing `configarr.yml` (or start from the skeleton recipe).
   2. Identify the service + resource to add/edit.
   3. **Open `references/schema.md` for that resource before writing any keys**;
      copy the exact nesting and key names. (Explicit instruction so Claude does
      not author from memory.)
   4. Put secrets (`api_key`, tokens, passwords) in `${VAR}`, never inline.
   5. Write/merge the YAML.

3. **Validation guidance** (inline)
   - Scope runs with `--service <name>` and `--instance <name>`.
   - **`--dry-run` is Bazarr-only.** For every other service a run **applies
     changes** — there is no true dry-run. `--debug` does **not** prevent
     mutations (corrected). The only blast-radius control for non-Bazarr services
     is `--service`/`--instance` scoping.
   - Reading results: `CREATED` / `UPDATED` / `UNCHANGED` / `FAILED`. Note SABnzbd
     servers/categories always write (never report `UNCHANGED`).
   - Common-errors mini-table: missing/unknown `implementation`; missing
     `base_url`/`api_key` (raises); unexpanded `${VAR}`.

4. **Core recipes (1-2 only, inline)**: the minimal all-services skeleton, and a
   Sonarr/Radarr quality profile + a custom format with `custom_format_scores`.
   Everything else lives in `references/schema.md` → Recipes.

5. **Gotchas + pointer** to `references/schema.md`.

## Component 2 — `references/schema.md` (core deliverable; schema + recipes)

### Accuracy rule (three layers)

Every documented key must trace to: a `parse_*` assignment in `config.py`, a
Pydantic field in `models.py`, **or** an inner-dict `config.get(...)`/`config[...]`
read in a client `sync_*`. Keys that cannot be traced are omitted, except
`settings:` maps which are explicitly documented as “passthrough to the *arr API
field of the same name.”

**Resource inventory is authoritative from `sync.py`**: every `_print_section`
block + the `config.<attr>` it reads is a section that MUST be documented. This
prevents silently dropping resource types.

### Per-service coverage (corrected & expanded from review)

For each service/resource: full YAML nesting path + a table of
**key · type · default · meaning · required?**, plus parse-layer renames and
quirks.

**Radarr / Sonarr** (`<svc>.instances.<name>`):
- `base_url`, `api_key` — **required** (subscript access raises).
- `settings.root_folders` — list of strings **or** `{path: ...}` objects.
- `settings.media_management` (naming): Sonarr uses `rename_episodes`,
  `multi_episode_style` (real; confirm allowed values/default),
  `standard_episode_format`, `daily_episode_format`, `anime_episode_format`,
  `series_folder_format`, `season_folder_format`, `specials_folder_format`;
  Radarr uses `rename_movies`, `standard_movie_format`, `movie_folder_format`.
  Both: `replace_illegal_characters`, `colon_replacement` (string set).
- `profiles.delay_profiles` — **list**; matching keys carry defaults that affect
  idempotency.
- `profiles.release_profiles` — **Sonarr-only** (ignored by Radarr); list.
- `profiles.quality_definitions` — **map** keyed by quality name → `min`/`max`/
  `preferred` (not a list).
- `profiles.quality_profiles.definitions.<name>` — document the **user-facing**
  keys (NOT the post-parse `upgrade.*`): `qualities` (strings or groups with
  nested `qualities` + `enabled`), `upgrades_allowed` (true),
  `upgrade_until_quality` (`WEBDL-1080p`), `upgrade_until_custom_format_score`
  (10000), `minimum_custom_format_score` (0), `custom_format_scores` (map),
  `language` (**Radarr-only**, ignored by Sonarr).
- `custom_formats.definitions.<name>` — `.definitions` sub-key; spec entries
  require `name` + `implementation`; `include_when_renaming` (false), `negate`
  (false), `required` (true).
- `download_clients.definitions.<name>` — `.definitions`; `implementation`
  **required**; `enable`/`priority`/`tags` + `settings` (passthrough field names).
- `notifications.definitions.<name>` — `.definitions`; `implementation`
  **required**; `on_download`/`on_upgrade`/`on_rename`, `on_import_complete`
  (**Sonarr-only**), `settings`, `tags`.

**Prowlarr** (`prowlarr.instances.<name>`, all under `.definitions`):
- `indexers` — `implementation` (required), `definition`, `enable`, `priority`
  (default **25**), `app_profile_id` (1, **indexer-only**), `redirect` (false,
  **indexer-only**), `settings`, `tags`.
- `applications` — `implementation` (required), `sync_level` (**application-only**,
  default `fullSync`; invalid value raises), `settings`, `tags`.
- `download_clients` — `implementation` (required), `enable`, `priority` (1),
  `settings`, `tags`. **Case-insensitive name matching** and **None-value
  substitution** apply **only here**. `categories` is hardcoded empty (not user-set).

**Bazarr** (`bazarr.instances.<name>`):
- Top-level keys: `base_url`, `api_key`, `general`, `sonarr`, `radarr`,
  `providers`, `language_profiles`.
- `general`/`sonarr`/`radarr` connections — POSTed as `settings-<section>-<field>`
  form fields; document them as sync'd sections (first draft under-covered these).
- `providers.<name>` — provider name map has **6 entries; only `submate`→
  `whisperai` renames**; all other names pass through verbatim. Present as a
  rename note + passthrough fallback, **NOT an allow-list**. `enabled_providers`
  is force-managed (additive, overwritten as a comma string).
- `language_profiles` — **CORRECTED**: listed profiles (new *or* existing) are
  written from config and **overwrite** the server copy; profiles on the server
  but absent from config are **preserved**. (The “create-only/never-updated”
  claim was fabricated.) Keys: `name`, `languages` (each a string or
  `{name|language, hi, forced, audio_exclude}`), `cutoff` (a language **name**
  that must appear in `languages` and resolve to a known code, else silently
  null), `must_contain`, `must_not_contain`, `original_format`.
- Dry-run aware, but **READ requests still hit the network** in provider/language
  sync.

**SABnzbd** (`sabnzbd.instances.<name>`):
- `servers.<name>` — `host` (**no default; silently dropped if omitted**), `port`
  (563), `ssl` (true), `ssl_verify` (2), **`ssl_ciphers` ("")**, **`username`
  ("")**, **`password` ("")**, `connections` (8), `priority` (0), `retention` (0),
  `timeout` (60), `enable` (true), `required`/`optional`/`send_group` (false),
  `notes` (""). (First draft omitted ssl_ciphers/username/password.)
- `categories.<name>` — `pp`, `script` (default literal `"None"`), `dir`,
  `newzbin`, `priority` (default `-100` = Default).
- `misc` — the `key_map` (~19 keys); document all and only those; booleans
  coerced to `1`/`0`; returns `UNCHANGED` when nothing set.
- `sync_server`/`sync_category` **always write** (never `UNCHANGED`).

### Top-level conventions
`base_url` + `api_key` required per instance; `${VAR}` expansion; `.env` auto-load.

### Recipes section (moved here from SKILL.md)
Download clients (qBittorrent / SABnzbd), a notification connection, Prowlarr
indexer + application, Bazarr language profile + provider, SABnzbd server +
category, root_folders + media_management, the `.env`/`${VAR}` pattern.

### Maintainer note
A **"How this schema was derived / how to refresh it"** note pointing at
`config.py` (nesting/renames), `models.py` (section contract/defaults), and each
client's `sync_*` (inner keys) + `sync.py` (`_print_section` inventory).

## Error handling / edge cases the skill must teach

- A run without `--dry-run` (non-Bazarr) mutates live services — scope it; there
  is no safe non-Bazarr preview.
- `implementation` is required for download clients, notifications, indexers,
  applications; unknown values raise.
- `base_url`/`api_key` omission raises.
- `${VAR}` left unexpanded ⇒ missing env var/`.env` entry.
- Bazarr language profiles overwrite server copies for listed names.
- SABnzbd `host` silently dropped if omitted.

## Verification plan (executed during implementation)

1. **JSON validity** — lint `marketplace.json`.
2. **Frontmatter validity** — parse SKILL.md frontmatter as YAML; assert `name` +
   `description` keys present and description < 1024 chars.
3. **Schema accuracy** — every key in `schema.md` cross-checked against the
   `config.py` / `models.py` / client source (the three layers).
4. **Coverage** — every `_print_section` in `sync.py` has a documented section.
5. **Fresh-agent dry run** — a subagent given *only* the installed skill authors a
   config for a scenario ("Sonarr instance with a root folder, a 1080p quality
   profile, and a qBittorrent client"); confirm the YAML matches what `config.py`
   + the clients accept. (Note: cannot be `--dry-run` validated for non-Bazarr.)
6. **Install shape** — confirm `marketplace.json` matches a known-good working
   example's structure (repo-root, `source: "./"`, `skills` array).

## Testing strategy

The repo has no test suite. This skill ships docs + one manifest, not runtime
code, so verification is the JSON/YAML lint + three-layer schema cross-check +
coverage check + fresh-agent authoring trial above, not a new pytest suite.
