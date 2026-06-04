# Design: `configarr-config` Claude skill (in-repo plugin)

## Goal

Ship a **publicly installable Claude Code plugin, hosted inside the configarr
repo**, containing one skill that helps a user (via Claude) **write, edit,
validate, and extend a `configarr.yml`**.

The skill exists because the configarr YAML schema is **entirely undocumented and
implicit**. It is defined by two code layers:

1. `configarr/config.py` `parse_*_instance` functions — which read the *nested*
   YAML the user writes and **reshape/rename keys** (e.g. `upgrades_allowed` →
   `upgrade.allowed`).
2. Each service client's `sync_*` methods — which read the post-parse dict via
   `config.get("key", default)`.

There is also no example config: the README links a `configarr.yml.example` that
does not exist in the repo. So the schema knowledge must be **bundled with the
skill** — installers will not have the configarr source checked out.

## Non-goals (explicitly out of scope)

- Creating/fixing the missing `configarr.yml.example` repo file. The skill's
  recipes cover the gap; fixing the repo file is a separate task.
- Changing any configarr runtime code or the YAML schema itself.
- Covering more than the five existing services.

## Distribution & decisions (locked)

| Decision | Choice |
|---|---|
| Skill purpose | Author/validate/extend `configarr.yml` |
| Location | In-repo plugin, version-controlled with the code |
| Distribution | Plugin inside the configarr repo (a marketplace + one plugin) |
| Schema delivery | **Exhaustive reference doc**, bundled as one file |
| Reference split | **Single `references/schema.md`**; workflow + validation + compact recipes folded into `SKILL.md` |
| Plugin namespace | `configarr` |
| Skill name | `configarr-config` (invocable as `/configarr:configarr-config`) |
| Capabilities | Authoring workflow + validation guidance + common recipes + exhaustive schema |

## Architecture: structure added to the repo

```
.claude-plugin/
  marketplace.json            # marketplace catalog; lists the one plugin
plugin/
  .claude-plugin/
    plugin.json               # plugin manifest (name, description, version, author, license)
  skills/
    configarr-config/
      SKILL.md                # lean hub: model + workflow + validation + compact recipes + gotchas
      references/
        schema.md             # EXHAUSTIVE per-key reference for all 5 services + "how to refresh" note
```

Notes:
- `marketplace.json` and the plugin live in the **same repo**. The exact
  `plugins[].source` syntax (pointing at the `plugin/` subdirectory) will be
  confirmed against a real, working marketplace example before finalizing, rather
  than trusting inferred field names.
- `.claude-plugin/` holds only manifest JSON. All component dirs (`skills/`) sit
  at the plugin root.
- Skill folder name is kebab-case. SKILL.md frontmatter `description` is
  third-person, trigger-rich, and under the 1024-char limit.

## Component 1 — `SKILL.md` (always-loaded hub, kept small)

Frontmatter:
- `name: configarr-config`
- `description:` third-person with concrete trigger phrases — writing/editing/
  validating a `configarr.yml`; "add a Sonarr quality profile", "configure a
  qBittorrent download client", "set up Bazarr language profiles", "why isn't my
  configarr config applying". No tool restriction (`allowed-tools` unset) — the
  skill reads, writes YAML, and runs configarr to validate.

Body sections (in order):

1. **Mental model**
   - One YAML file; every service nests under `<service>.instances.<name>`.
   - Secrets via `${VAR}` substitution; a `.env` next to the config is
     auto-loaded; missing vars are left literal.
   - **Two-layer schema warning**: the YAML keys you write are not the API keys.
     `config.py` reshapes them. Always consult `references/schema.md` for the
     exact key names and nesting — never guess from the *arr API.

2. **Authoring workflow** (numbered)
   1. Read the existing `configarr.yml` (or start from the skeleton recipe).
   2. Identify the service + resource to add/edit.
   3. Open `references/schema.md` for that resource; copy the exact nesting and
      key names.
   4. Put secrets (`api_key`, tokens, passwords) in `${VAR}`, never inline.
   5. Respect ordering: SABnzbd is processed first (categories must exist before
      *arr apps reference them); custom formats must be defined before quality
      profiles that score them.
   6. Write/merge the YAML.

3. **Validation guidance** (folded in here, no separate file)
   - Scope runs with `--service <name>` and `--instance <name>`.
   - **`--dry-run` is Bazarr-only** — called out loudly; for other services a run
     applies changes. Recommend `--service`/`--instance` scoping + `--debug` to
     preview safely.
   - Reading results: `CREATED` / `UPDATED` / `UNCHANGED` / `FAILED`.
   - Common-errors mini-table: missing/unknown `implementation`, missing
     `base_url`/`api_key`, unexpanded `${VAR}`.

4. **Common recipes** (compact, folded in here)
   - Minimal all-services skeleton.
   - Sonarr/Radarr quality profile + a custom format with `custom_format_scores`.
   - A download client (qBittorrent / SABnzbd).
   - A notification connection.
   - Prowlarr indexer + application.
   - Bazarr language profile + provider.
   - SABnzbd server + category.
   - The `.env` / `${VAR}` pattern.

5. **Gotchas + pointer** to `references/schema.md` for the full reference.

## Component 2 — `references/schema.md` (the core deliverable)

Per service (radarr, sonarr, prowlarr, bazarr, sabnzbd), and per resource within
each, document:

- The **full YAML nesting path** (e.g.
  `sonarr.instances.<name>.profiles.quality_profiles.definitions.<profile>`).
- A table of **key · type · default · meaning · required?**, derived from the
  actual `config.get(...)` / `config[...]` calls and `parse_*` functions.
- The **parse-layer key transformations** (notably quality profiles:
  `upgrades_allowed`→`upgrade.allowed`, `upgrade_until_quality`→
  `upgrade.until_quality`, `upgrade_until_custom_format_score`→
  `upgrade.until_score`).
- **Service-specific quirks**:
  - Sonarr-only `release_profiles` (ignored by Radarr).
  - Prowlarr case-insensitive name matching and `None`-value stripping.
  - Bazarr provider-name mapping and **language profiles are create-only — never
    updated**; settings POSTed as `settings-<section>-<field>` form fields;
    dry-run aware.
  - SABnzbd booleans coerced to `1`/`0`; create and update use the same call.
- Top-level conventions: `base_url` + `api_key` required per instance; `${VAR}`
  expansion; `.env` auto-load.

End with a **"How this schema was derived / how to refresh it"** maintainer note
pointing at `config.py` and each client's `sync_*` methods, so the in-repo
reference stays honest as the code evolves.

**Accuracy rule:** every documented key must trace to a real `config.get`/
`config[...]` read or a `parse_*` assignment. Keys that cannot be confirmed in
code are omitted (or explicitly marked "passes through to the *arr API field of
the same name" where the client forwards arbitrary `settings`). The earlier
exploratory extraction inferred a few keys (e.g. Sonarr `multi_episode_style`,
`on_import_complete`, quality-profile `language`); each is re-verified against
the source during implementation before inclusion.

## Error handling / edge cases the skill must teach

- A run without `--dry-run` (non-Bazarr) mutates live services — scope it.
- `implementation` is required for download clients, notifications, indexers,
  applications; an unknown value raises.
- `${VAR}` left unexpanded means the env var/`.env` entry is missing.
- Custom-format-before-quality-profile and SABnzbd-first ordering.

## Verification plan (executed during implementation)

1. **JSON validity** — lint `marketplace.json` and `plugin.json`.
2. **Schema accuracy** — every key in `schema.md` cross-checked against the
   client/parser source.
3. **Fresh-agent dry run** — dispatch a subagent given *only* the installed skill
   and a scenario ("add a Sonarr instance with a 1080p quality profile and a
   qBittorrent client"); confirm the YAML it produces matches what `config.py` +
   the clients actually accept.
4. **Install smoke test** — confirm the marketplace/plugin manifests are
   structurally loadable (validate against a known-good real example's shape).

## Testing strategy

The repo currently has no test suite. This skill ships docs + manifests, not
runtime code, so verification is the JSON lint + schema cross-check + fresh-agent
authoring trial above, not a new pytest suite.
