# configarr-config Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a publicly installable Claude Code plugin inside the configarr repo containing one skill (`configarr-config`) that helps author/validate/extend `configarr.yml`, backed by an exhaustive, source-verified YAML schema reference.

**Architecture:** A single `.claude-plugin/marketplace.json` (repo root, `source: "./"`, explicit `skills` array, NO `plugin.json`) registers one plugin. The skill lives at `skills/configarr-config/SKILL.md` (lean hub) with `references/schema.md` beside it (exhaustive schema + recipes). Mirrors the proven layout of the user's `nix-search-marketplace`.

**Tech Stack:** Markdown (SKILL.md, schema.md), JSON (marketplace.json). Verification uses `python`/`jq`-equivalent JSON parsing, a YAML frontmatter parse, source cross-checks with `rg`, and a fresh-agent authoring trial.

**Authoritative source of content:** the revised spec at `docs/superpowers/specs/2026-06-04-configarr-config-skill-design.md` (post-adversarial-review). Component 2 of the spec is the verified key inventory; every key written into `schema.md` MUST be re-confirmed against the cited source file before inclusion (three layers: `config.py` nesting/renames, `models.py` section contract/defaults, client `sync_*` inner-dict reads, with `sync.py` `_print_section` as the resource inventory).

---

## Task 1: Feature branch

**Files:** none (git only)

- [ ] **Step 1: Create and switch to a feature branch**

Run:
```bash
cd /home/aldo/Dev/aldoborrero/configarr
git checkout -b configarr-config-skill
```
Expected: `Switched to a new branch 'configarr-config-skill'`

---

## Task 2: Marketplace manifest

**Files:**
- Create: `.claude-plugin/marketplace.json`

- [ ] **Step 1: Write `.claude-plugin/marketplace.json`**

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "configarr",
  "owner": {
    "name": "Aldo Borrero",
    "email": "aldo@aldoborrero.com"
  },
  "metadata": {
    "description": "Skill for authoring and validating configarr.yml configuration",
    "version": "1.0.0"
  },
  "plugins": [
    {
      "name": "configarr",
      "description": "Author, edit, validate, and extend configarr.yml — the declarative config for Radarr, Sonarr, Prowlarr, Bazarr, and SABnzbd.",
      "version": "1.0.0",
      "author": { "name": "Aldo Borrero", "email": "aldo@aldoborrero.com" },
      "homepage": "https://github.com/aldoborrero/configarr",
      "source": "./",
      "strict": false,
      "skills": ["./skills/configarr-config"]
    }
  ]
}
```

- [ ] **Step 2: Verify JSON parses and matches the working shape**

Run:
```bash
python -c "import json,sys; d=json.load(open('.claude-plugin/marketplace.json')); p=d['plugins'][0]; assert p['source']=='./' and p['skills']==['./skills/configarr-config'], 'source/skills wrong'; print('OK', d['name'], p['name'])" \
  || nix run nixpkgs#jq -- -e '.plugins[0] | (.source=="./") and (.skills==["./skills/configarr-config"])' .claude-plugin/marketplace.json
```
Expected: `OK configarr configarr` (or `true` from the jq fallback). Note `python` may not exist on this host — the `jq` fallback after `||` covers that. If neither exists, use `nix run nixpkgs#python3 -- -c ...`.

- [ ] **Step 3: Confirm no stray `plugin.json` / nested `plugin/` dir was created**

Run:
```bash
fd -H -t f 'plugin.json' . ; fd -H -t d '^plugin$' .
```
Expected: no output (the layout is repo-root, no `plugin.json`).

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin/marketplace.json
git commit -m "Add configarr plugin marketplace manifest"
```

---

## Task 3: SKILL.md frontmatter (valid YAML)

**Files:**
- Create: `skills/configarr-config/SKILL.md`

- [ ] **Step 1: Write the frontmatter block only**

Create the file beginning with a real `---`-fenced YAML block (NOT the nix-search heading style). The description must be `Use when…`, trigger-rich, **scoped to configarr.yml** (avoid over-triggering on generic *arr questions), and **under 1024 characters**:

```markdown
---
name: configarr-config
description: "Use when writing, editing, validating, debugging, or extending a configarr.yml — the single declarative YAML that configarr uses to manage Radarr, Sonarr, Prowlarr, Bazarr, and SABnzbd. Triggers when: (1) creating or changing a configarr.yml; (2) adding a quality profile, custom format, root folder, naming/media-management setting, delay or release profile, quality definition, download client, indexer, application, notification connection, Bazarr language profile or provider, or SABnzbd server/category/misc setting to a configarr config; (3) determining which YAML keys configarr accepts, or why a configarr run reports FAILED/UNCHANGED. Targets the configarr YAML schema specifically — not general Sonarr/Radarr/Prowlarr/Bazarr/SABnzbd usage or their native APIs."
---
```

- [ ] **Step 2: Verify the frontmatter parses as YAML with required keys**

Run:
```bash
nix run nixpkgs#python3 -- - <<'PY'
import re, sys
import importlib.util
text = open('skills/configarr-config/SKILL.md').read()
m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
assert m, "no ----fenced frontmatter"
fm = m.group(1)
# minimal YAML check without pyyaml: keys present + description length
assert re.search(r'^name:\s*configarr-config\s*$', fm, re.M), "name key missing/wrong"
desc = re.search(r'^description:\s*"(.*)"\s*$', fm, re.S | re.M)
assert desc, "description key missing or not double-quoted"
assert len(desc.group(1)) < 1024, f"description too long: {len(desc.group(1))}"
print("frontmatter OK; description length", len(desc.group(1)))
PY
```
Expected: `frontmatter OK; description length <N>` with N < 1024. (If `pyyaml` is available, prefer `yaml.safe_load(fm)`.)

- [ ] **Step 3: Commit**

```bash
git add skills/configarr-config/SKILL.md
git commit -m "Add configarr-config skill frontmatter"
```

---

## Task 4: SKILL.md body (lean hub, ≤200 lines)

**Files:**
- Modify: `skills/configarr-config/SKILL.md`

Content from spec Component 1. Keep it lean: mental model, authoring workflow, validation guidance, 1-2 core recipes only, gotchas. Long-tail recipes go in `schema.md` (Task 9), not here.

- [ ] **Step 1: Append the body sections**

Write, in order:
1. **Overview** (2-3 sentences): one YAML file; `<service>.instances.<name>`; consult `references/schema.md` for exact keys.
2. **Mental model** bullets:
   - Secrets via `${VAR}`; `.env` auto-loaded from the config's directory; missing vars left literal.
   - Three-layer schema warning: written YAML keys ≠ API keys (`config.py` renames; `models.py` defines sections); never guess from the *arr API — open `references/schema.md`.
   - **Ordering is handled by the tool, not YAML key order**: configarr always processes SABnzbd first, then radarr/sonarr/prowlarr/bazarr, and syncs custom formats before quality profiles within an *arr instance. Users do not control this via the file.
3. **Authoring workflow** (numbered): read existing config → identify service+resource → **open `references/schema.md` for that resource before writing keys** → put secrets in `${VAR}` → write/merge.
4. **Validation guidance**:
   - Scope with `--service <name>` / `--instance <name>`.
   - **`--dry-run` is Bazarr-only**; every other service applies changes on run; `--debug` does NOT prevent mutations; the only non-Bazarr blast-radius control is `--service`/`--instance` scoping.
   - Result vocabulary `CREATED/UPDATED/UNCHANGED/FAILED`; SABnzbd servers/categories always write (never `UNCHANGED`).
   - Common-errors mini-table: missing/unknown `implementation`; missing `base_url`/`api_key` (raises); unexpanded `${VAR}`.
5. **Core recipes (inline, only two)**:
   - Minimal all-services skeleton (instances with `base_url`/`api_key` via `${VAR}`).
   - A Sonarr (or Radarr) quality profile + a custom format with `custom_format_scores`, using the **user-facing** keys (`upgrades_allowed`, `upgrade_until_quality`, `upgrade_until_custom_format_score`, `minimum_custom_format_score`, `custom_format_scores`, `qualities`).
6. **Gotchas** quick list + "full reference & more recipes: `references/schema.md`".

- [ ] **Step 2: Verify length and the two recipes are valid YAML**

Run:
```bash
wc -l skills/configarr-config/SKILL.md   # expect <= ~200
# extract fenced ```yaml blocks and parse each (working nix invocation form)
nix shell --impure --expr 'with import <nixpkgs> {}; [(python3.withPackages (p: [p.pyyaml]))]' -c python3 - <<'PY'
import re
text=open('skills/configarr-config/SKILL.md').read()
import yaml
blocks=re.findall(r'```ya?ml\n(.*?)```', text, re.S)
assert blocks, "no yaml recipe blocks found"
for b in blocks:
    yaml.safe_load(b)
print(f"{len(blocks)} yaml blocks parsed OK")
PY
```
Expected: line count ≤ ~200; all YAML blocks parse.

- [ ] **Step 3: Commit**

```bash
git add skills/configarr-config/SKILL.md
git commit -m "Write configarr-config skill body"
```

---

## Task 5: schema.md — header, accuracy rule, Radarr/Sonarr

**Files:**
- Create: `skills/configarr-config/references/schema.md`

Content authority: spec Component 2 → "Radarr / Sonarr" + "Accuracy rule". **Re-verify every key against source before writing it.**

- [ ] **Step 1: Re-derive the Radarr/Sonarr keys from source**

Run (use output as ground truth; do not trust memory):
```bash
rg -n "config\[|config\.get|def parse_arr_instance|def parse_quality_profiles" configarr/config.py
rg -n "config\.get|config\[" configarr/radarr.py
rg -n "config\.get|config\[" configarr/sonarr.py
rg -n "_print_section|config\." configarr/sync.py
sed -n '1,60p' configarr/models.py   # ArrServiceConfig fields/defaults
```
Confirm: user-facing quality-profile keys (renamed by `parse_quality_profiles`), `language` read only in `radarr.py` (absent in `sonarr.py`), Sonarr-only `release_profiles`/`on_import_complete`/`multi_episode_style`, `.definitions` sub-keys, required `base_url`/`api_key` + spec `name`/`implementation`.

- [ ] **Step 2: Write schema.md with: title, the three-layer Accuracy Rule, top-level conventions (`${VAR}`/`.env`, required `base_url`/`api_key`), and the full Radarr/Sonarr section**

Each resource: nesting path + a `key · type · default · meaning · required?` table. Mark Radarr-only (`language`, `rename_movies`, movie formats) and Sonarr-only (`release_profiles`, `on_import_complete`, `rename_episodes`, `multi_episode_style`, season/specials/series formats) keys explicitly. Document **user-facing** quality-profile keys, not `upgrade.*`.

- [ ] **Step 3: Verify the suspect keys are correctly attributed**

Run:
```bash
rg -n "language" configarr/sonarr.py || echo "OK: sonarr does NOT read language (Radarr-only) — correct"
rg -n "on_import_complete|multi_episode" configarr/sonarr.py
rg -n "on_import_complete|multi_episode" configarr/radarr.py || echo "OK: radarr does NOT read these"
```
Expected: sonarr.py has no `language`; the Sonarr-only keys appear only in sonarr.py.

- [ ] **Step 4: Commit**

```bash
git add skills/configarr-config/references/schema.md
git commit -m "Add schema reference: accuracy rule + Radarr/Sonarr"
```

---

## Task 6: schema.md — Prowlarr

**Files:**
- Modify: `skills/configarr-config/references/schema.md`

- [ ] **Step 1: Re-derive from source**

Run:
```bash
rg -n "config\.get|config\[|def sync_indexer|def sync_application|def sync_download_client|lower\(\)|app_profile_id|sync_level|redirect|priority" configarr/prowlarr.py
rg -n "def parse_prowlarr_instance" configarr/config.py
```
Confirm: `app_profile_id`/`redirect` indexer-only; `sync_level` application-only (default `fullSync`); priority default 25 (indexers) vs 1 (download clients); case-insensitive matching + None-substitution **download-clients only**.

- [ ] **Step 2: Append the Prowlarr section** (indexers / applications / download_clients, all under `.definitions`), scoping each key to the resource that actually reads it.

- [ ] **Step 3: Verify scoping**

Run:
```bash
rg -n "app_profile_id|redirect" configarr/prowlarr.py    # expect only within sync_indexer
rg -n "sync_level" configarr/prowlarr.py                 # expect only within sync_application
```
Expected: matches confined to the correct method.

- [ ] **Step 4: Commit**

```bash
git add skills/configarr-config/references/schema.md
git commit -m "Add schema reference: Prowlarr"
```

---

## Task 7: schema.md — Bazarr

**Files:**
- Modify: `skills/configarr-config/references/schema.md`

- [ ] **Step 1: Re-derive from source (the corrected language-profile semantics matter most)**

Run:
```bash
# PROVIDER_NAME_MAP and sync_provider live in __init__.py (NOT settings.py)
rg -n "PROVIDER_NAME_MAP|def sync_provider|enabled_providers|settings-" configarr/bazarr/__init__.py
rg -n "settings-|def _sync_settings_section" configarr/bazarr/settings.py
sed -n '181,230p' configarr/bazarr/languages.py     # sync_profiles: existing rebuilt+saved; absent preserved
rg -n "_build_profile_payload|mustContain|mustNotContain|originalFormat|cutoff|get_language_code|LANGUAGE_CODES" configarr/bazarr/languages.py
```
Confirm: PROVIDER_NAME_MAP has 6 entries, only `submate`→`whisperai` renames, others identity, unknown names pass through; language profiles **overwrite** listed names and **preserve** unlisted ones; keys `name/languages/cutoff/must_contain/must_not_contain/original_format`; cutoff is a language NAME that must be in the list + resolve to a code or it silently nulls.

- [ ] **Step 2: Append the Bazarr section** — top-level keys; `general`/`sonarr`/`radarr` connections (POSTed as `settings-<section>-<field>`); `providers` (rename note + passthrough, NOT an allow-list; `enabled_providers` force-managed); `language_profiles` with the **corrected overwrite/preserve semantics** and per-language string-or-dict form. Note dry-run still issues READ requests.

- [ ] **Step 3: Verify the corrected claims**

Run:
```bash
rg -n "skipped\.append|all_profiles\.append|preserve" configarr/bazarr/languages.py
rg -n "submate|whisperai" configarr/bazarr/__init__.py
```
Expected: confirms existing profiles are appended (rebuilt) and unlisted preserved; only `submate`→`whisperai` rename present.

- [ ] **Step 4: Commit**

```bash
git add skills/configarr-config/references/schema.md
git commit -m "Add schema reference: Bazarr"
```

---

## Task 8: schema.md — SABnzbd + maintainer note

**Files:**
- Modify: `skills/configarr-config/references/schema.md`

- [ ] **Step 1: Re-derive from source**

Run:
```bash
rg -n "config\.get|def sync_server|def sync_category|def sync_misc_settings|key_map|UNCHANGED|UPDATED" configarr/sabnzbd.py
```
Confirm: server keys include `ssl_ciphers`/`username`/`password`; `host` has no default (dropped if omitted); category `script` default `"None"`, `priority` default `-100`; `misc` key_map exact key set (~19); booleans → `1`/`0`; `sync_misc_settings` returns `UNCHANGED` when nothing set; `sync_server`/`sync_category` always write.

- [ ] **Step 2: Append the SABnzbd section** (servers/categories/misc with full keys + defaults) and the **maintainer "How this schema was derived / how to refresh it" note** pointing at `config.py` (nesting/renames), `models.py` (section contract/defaults), client `sync_*` (inner keys), and `sync.py` `_print_section` (inventory).

- [ ] **Step 3: Verify the misc key_map count matches what's documented**

Run:
```bash
rg -n '".*":\s*".*"' configarr/sabnzbd.py | rg -n "download_dir|complete_dir|key_map" 
# Manually count key_map entries and confirm schema.md lists exactly those.
```
Expected: documented misc keys == the actual `key_map` keys (no extras, none missing).

- [ ] **Step 4: Commit**

```bash
git add skills/configarr-config/references/schema.md
git commit -m "Add schema reference: SABnzbd + maintainer note"
```

---

## Task 9: schema.md — Recipes section

**Files:**
- Modify: `skills/configarr-config/references/schema.md`

- [ ] **Step 1: Append a Recipes section** (the long-tail, moved out of SKILL.md): download clients (qBittorrent / SABnzbd), a notification connection, Prowlarr indexer + application, Bazarr language profile + provider, SABnzbd server + category, root_folders + media_management, the `.env`/`${VAR}` pattern. Each recipe is a minimal, valid YAML snippet using only verified keys.

- [ ] **Step 2: Verify every recipe YAML parses and uses only documented keys**

Run:
```bash
nix shell --impure --expr 'with import <nixpkgs> {}; [(python3.withPackages (p: [p.pyyaml]))]' -c python3 - <<'PY'
import re, yaml
text=open('skills/configarr-config/references/schema.md').read()
blocks=re.findall(r'```ya?ml\n(.*?)```', text, re.S)
for b in blocks: yaml.safe_load(b)
print(f"{len(blocks)} recipe/schema YAML blocks parse OK")
PY
```
Expected: all blocks parse.

- [ ] **Step 3: Commit**

```bash
git add skills/configarr-config/references/schema.md
git commit -m "Add schema reference: recipes"
```

---

## Task 10: Coverage check (no silently-dropped resources)

**Files:** none (verification); fix prior files if gaps found

- [ ] **Step 1: Build the authoritative resource inventory from sync.py**

Run:
```bash
rg -n "_print_section\(" configarr/sync.py
```

- [ ] **Step 2: Confirm every `_print_section` resource is documented in schema.md**

For each section name printed in `sync.py`, grep `schema.md` for a matching heading/row. List any missing. Expected resources: root folders, naming, delay profiles, release profiles (Sonarr), quality definitions, custom formats, quality profiles, download clients, notifications (arr); indexers, applications, download clients (prowlarr); general settings, sonarr/radarr connections, providers, language profiles (bazarr); servers, categories, settings/misc (sabnzbd).

- [ ] **Step 3: If any section is undocumented, add it (amend the relevant Task 5-8 section) and commit**

```bash
git add skills/configarr-config/references/schema.md
git commit -m "Fill schema coverage gaps from sync.py inventory"
```

---

## Task 11: Fresh-agent authoring trial (end-to-end validation)

**Files:** none (validation); fix skill/schema if the trial reveals errors

- [ ] **Step 1: Dispatch a subagent given ONLY the skill files**

Use the Agent tool (general-purpose). Provide it the contents of `skills/configarr-config/SKILL.md` and `skills/configarr-config/references/schema.md` (NOT the configarr source). Task: "Author a `configarr.yml` for a Sonarr instance named `main` with one root folder `/tv`, a quality profile `HD` that allows WEBDL-1080p with a custom format scored, and a qBittorrent download client. Use `${VAR}` for secrets."

- [ ] **Step 2: Validate the produced YAML against the real parser/models**

Run:
```bash
# Save the agent's YAML to /tmp/trial.yml, then:
nix shell --impure --expr 'with import <nixpkgs> {}; [(python3.withPackages (p: [p.pyyaml]))]' -c python3 - <<'PY'
import yaml
raw=yaml.safe_load(open('/tmp/trial.yml'))
# structural checks mirroring config.py expectations:
inst=raw['sonarr']['instances']['main']
assert 'base_url' in inst and 'api_key' in inst, "missing required base_url/api_key"
qp=inst['profiles']['quality_profiles']['definitions']
assert qp, "no quality profile definitions under profiles.quality_profiles.definitions"
prof=next(iter(qp.values()))
assert 'qualities' in prof, "quality profile missing qualities"
# must use USER-FACING keys, not the post-parse shape:
assert not any(k in prof for k in ('upgrade','min_format_score','until_quality','allowed')), \
    "used post-parse keys (upgrade.*/min_format_score) instead of user-facing"
# and should positively use at least one user-facing upgrade key when upgrades are configured:
print("user-facing upgrade keys present:",
      [k for k in ('upgrades_allowed','upgrade_until_quality','upgrade_until_custom_format_score') if k in prof])
print("trial config matches the documented schema shape")
PY
```
Expected: passes. If the agent produced wrong nesting or post-parse keys, the skill/schema is unclear — fix it and re-run the trial.

- [ ] **Step 3: Optionally run the real parser if configarr is importable**

Run (best-effort; needs the configarr deps/env):
```bash
nix develop -c python -c "from configarr.config import parse_config; from pathlib import Path; print(parse_config(Path('/tmp/trial.yml')))" 2>&1 | tail -5 || echo "skipped: configarr env not available"
```
Expected: parses without error, or a clear skip.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A && git commit -m "Refine skill/schema after fresh-agent authoring trial" || echo "no fixes needed"
```

---

## Task 12: README install instructions

**Files:**
- Modify: `README.md`

Serves the "publicly installable" goal — users need to know how to install. Small, additive section; does not touch runtime code.

- [ ] **Step 1: Add an install section to README.md**

Add under a new heading (e.g. after Usage):
```markdown
## Claude Code skill

This repo ships a Claude Code skill that helps you author and validate
`configarr.yml`. Install it with:

\```
/plugin marketplace add aldoborrero/configarr
/plugin install configarr
\```

Then Claude can help write quality profiles, custom formats, download clients,
indexers, language profiles, and more, using the bundled schema reference.
```

- [ ] **Step 2: Verify the README link to the (still missing) example is not newly relied upon**

Run:
```bash
rg -n "configarr.yml.example" README.md
```
Expected: the pre-existing reference is unchanged (creating the example file is out of scope; we did not add new dependencies on it).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document Claude Code skill install in README"
```

---

## Task 13: Finalize

- [ ] **Step 1: Final structural sanity check**

Run:
```bash
fd -H . .claude-plugin skills   # show the created tree
nix run nixpkgs#jq -- -e '.plugins[0].skills[0]=="./skills/configarr-config"' .claude-plugin/marketplace.json
test -f skills/configarr-config/SKILL.md && test -f skills/configarr-config/references/schema.md && echo "files present"
```
Expected: tree as designed; `true`; `files present`.

- [ ] **Step 2: Use superpowers:finishing-a-development-branch** to choose merge / PR / cleanup for the `configarr-config-skill` branch.

---

## Notes for the executor

- `python` is not guaranteed on this host. For plain Python use `nix run nixpkgs#python3 -- ...`. When a library is needed (e.g. `pyyaml`), `nix run nixpkgs#python3.withPackages` does NOT work — use `nix shell --impure --expr 'with import <nixpkgs> {}; [(python3.withPackages (p: [p.pyyaml]))]' -c python3 - <<'PY' ... PY`. For pure JSON/YAML checks, `nix run nixpkgs#jq` and `nix run nixpkgs#yq` (3.4.3) are available.
- Do NOT create a `plugin.json` or a nested `plugin/` directory — the layout is repo-root.
- Use real `---`-fenced YAML frontmatter in SKILL.md; the nix-search skill's heading-style frontmatter is malformed and must not be copied.
- Every schema key must be re-verified against source (the `rg`/`sed` steps) before it is written — do not transcribe the spec on faith.
