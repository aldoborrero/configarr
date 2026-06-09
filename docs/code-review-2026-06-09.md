# configarr code review — bugs & pythonic smells

> Generated 2026-06-09 by a multi-agent audit (13 per-file + cross-cutting finders → independent adversarial verification of every finding → synthesis). Raw findings: 87; verified kept (confirmed/partial): 82; refuted/filtered: 5. Each item below survived an independent skeptic that re-read the source; the false positives are listed at the end for transparency.

## Summary

- **High:** 2
- **Medium:** 13
- **Low:** 13
- **Total verified groups:** 28  ·  **Refuted (not real):** 5

## Prioritized worklist

### 1. [HIGH · medium effort] Custom-format ID cache is treated as complete when only partially populated, silently dropping quality-profile format scores (Radarr + Sonarr)

get_custom_format_ids() only fetches the full server list when self._custom_format_ids is falsy, but sync_custom_format() incrementally writes single entries into that same dict as each configured format is synced. Because sync.py syncs all custom formats before quality profiles, by the time sync_quality_profile calls get_custom_format_ids() the dict is non-empty and contains ONLY the formats present in this run's config. Any custom_format_scores entry referencing a pre-existing server-side format not (re)synced this run is not found, hits the 'not found, skipping score assignment' branch, and silently drops the score. Identical bug in both clients (copy-paste).

**Fix:** Use a distinct sentinel for the 'fully fetched' state (e.g. self._custom_format_ids: dict | None = None, gate the full-list fetch on `is None`) instead of relying on dict emptiness. Merge incremental writes from sync_custom_format into the fully-loaded map rather than letting them satisfy the cache-fill guard. Fix once in a shared base class to avoid re-introducing the drift.

**Locations:**
- `configarr/radarr.py:201-206,236,241,314,320`
- `configarr/sonarr.py:252-257,287,292,354-358`

### 2. [HIGH · large effort] --dry-run silently performs live writes for Radarr/Sonarr/Prowlarr/SABnzbd

The CLI prints 'DRY RUN MODE - No changes will be made', but dry_run is only threaded into sync_bazarr. sync_arr(service_type, config), sync_prowlarr, and sync_sabnzbd take no dry_run argument and their underlying *Client.sync_* methods unconditionally call create_*/update_* against the live API. So --dry-run silently mutates Radarr, Sonarr, Prowlarr, and SABnzbd state, directly violating the user's explicit safety request. The flag's help text says '(Bazarr only)', but the runtime banner is unconditional and misleading.

**Fix:** Thread dry_run through sync_arr/sync_prowlarr/sync_sabnzbd and every underlying *Client.sync_* method, guarding all create_*/update_* calls exactly as BazarrClient already does. At minimum, refuse to run non-dry-aware syncs (exit with an error) when --dry-run is set, and fix the banner/help text so the scope is honest.

**Locations:**
- `configarr/sync.py:46 (sync_arr signature)`
- `configarr/__main__.py:82-83 (banner)`
- `configarr/__main__.py:116,125 (sync_arr calls)`
- `configarr/sync.py:280-291 (only sync_bazarr honors dry_run)`

### 3. [MEDIUM · small effort] Notification update branch drops tags (data loss vs create branch), in both clients

The create branch of sync_notification sets tags=config.get("tags", []), but the update branch updates name and on_* flags and field values yet never assigns found.tags from config. So configured tags apply on first creation but are silently ignored on every subsequent update and any tag drift is never reconciled. Contrast sync_download_client, whose update branch correctly sets found.tags. The two near-identical notification methods have drifted identically in radarr.py and sonarr.py.

**Fix:** Add `found.tags = config.get("tags", [])` to both notification update branches to match the create branch and the download-client update branch. Folds naturally into the shared ArrClientBase refactor.

**Locations:**
- `configarr/radarr.py:462-473 (update branch),485 (create),405 (download-client update)`
- `configarr/sonarr.py:491-503 (update branch),516 (create),433 (download-client update)`

### 4. [MEDIUM · small effort] Bazarr provider boolean fields sent with wrong casing (Python 'True'/'False')

sync_provider stringifies every provider config value with str(value) unconditionally, so a Python bool True becomes 'True' (capital T). The sibling _sync_settings_section explicitly lowercases bools to str(value).lower() because Bazarr's settings endpoint expects 'true'/'false'. Boolean provider options (enable/SSL/verify-style flags) are therefore silently sent with wrong casing and may be misinterpreted or rejected, causing silent provider misconfiguration. The two methods also duplicate the form-data build/POST/raise_for_status logic, which is the root cause of the drift.

**Fix:** Extract a shared _post_settings_fields(field_map) helper that performs the bool-aware coercion (isinstance(value, bool) -> str(value).lower()) and the POST/raise_for_status, and call it from both sync_provider and _sync_settings_section so the two paths cannot drift.

**Locations:**
- `configarr/bazarr/__init__.py:162-164 (sync_provider, no bool coercion)`
- `configarr/bazarr/__init__.py:95-104 (_sync_settings_section, lowercases bools)`

### 5. [MEDIUM · small effort] Dead, divergent Bazarr SettingsManager (settings.py) duplicates BazarrClient with a wrong API contract

The entire SettingsManager class is defined, imported, and re-exported in __all__ but never instantiated; the real work is done by BazarrClient, which independently re-implements sync_general/sync_sonarr/sync_radarr/sync_provider via requests form-data. Worse, SettingsManager's methods POST a typed SystemSettingsUpdate as a JSON body, which does NOT match the form-encoded settings-{section}-{field} contract Bazarr actually accepts — so if it were ever wired in it would be a silent no-op. It also has its own incidental defects (sync_general redundantly fetches all settings then ignores them; unused verbose param; dead self.base_url store passing raw host to Configuration). Two divergent settings implementations invite drift and mislead readers about which path is authoritative.

**Fix:** Delete configarr/bazarr/settings.py and its import/__all__ entry, since BazarrClient's form-data implementation is the authoritative one matching the Bazarr endpoint contract. (Only consolidate onto SettingsManager instead if you intend to migrate to the typed-client approach and first fix its JSON-vs-form-data contract.)

**Locations:**
- `configarr/bazarr/settings.py:18 (class)`
- `configarr/bazarr/settings.py:62-74,82-90,98-106 (wrong JSON contract + redundant fetch)`
- `configarr/bazarr/settings.py:26,28,30,32 (unused verbose, dead base_url store)`
- `configarr/bazarr/__init__.py:17,199 (import and __all__ entry)`

### 6. [MEDIUM · small effort] Required SABnzbd host is silently dropped, creating a broken hostless server

In sync_server, host is read with config.get("host") (no default), then the `{k: v for ... if v is not None}` filter drops the host key entirely when absent. No validation exists in models.py (servers is an unvalidated dict[str, Any]) or sync.py. SABnzbd's set_config is then called without a host, so a required field is treated as optional — either producing a broken non-functional server or surfacing an opaque RuntimeError, with the misconfiguration not clearly attributed.

**Fix:** Validate that host is present before calling set_config and raise a clear, named error if absent. Restrict the None-filter to genuinely optional fields rather than silently stripping a required one.

**Locations:**
- `configarr/sabnzbd.py:105 (host read),124 (None-filter)`

### 7. [MEDIUM · small effort] Unmatched --instance / --service filter reports success and exits 0

total_success and total_failure both start at 0. If --instance names a non-existent instance (or --service selects a category with no configured instances), every loop body is skipped via continue, nothing syncs, total_failure stays 0, and the CLI prints 'All operations completed successfully!' and exits 0. A typo'd instance name looks like a successful run while nothing was processed, silently masking a config mistake in CI/automation that keys on the exit code.

**Fix:** Track whether any instance was actually processed (or whether the --instance/--service filter matched anything). If a filter was given but matched nothing, print a warning and exit non-zero so the typo surfaces instead of being reported as success.

**Locations:**
- `configarr/__main__.py:157-162`
- `configarr/__main__.py:102-145 (filter loop)`

### 8. [MEDIUM · small effort] Prowlarr raw HTTP requests have no timeout and can hang the whole sync indefinitely

All three http_requests calls in the download-client path (GET existing list, PUT update, POST create) omit timeout=. The requests library defaults to no timeout, so a stalled/unresponsive Prowlarr blocks the sync loop forever with no recovery. The surrounding per-item try/except in sync.py would degrade gracefully if a finite timeout were set.

**Fix:** Pass an explicit timeout=(connect, read) to every http_requests.get/put/post call.

**Locations:**
- `configarr/prowlarr.py:216-219,229-233,238-242`

### 9. [MEDIUM · medium effort] Config parsing crashes with opaque errors on null/empty YAML sections

yaml.safe_load returns None for an empty/comment-only file and for any present-but-null section (e.g. `custom_formats:` or `radarr:` on its own line parses to None, not {}). The membership test `"radarr" in raw_config` then raises TypeError, and the pervasive chained `config.get("section", {}).get("definitions", {})` pattern raises AttributeError on `None.get(...)`. These surface only as a generic 'Configuration error' via the broad except at __main__.py:95, with no indication of which key, aborting the whole run on a common, easy-to-make YAML mistake. The fragile two-level .get().get() pattern is repeated throughout parse_arr_instance, parse_prowlarr_instance, parse_quality_profiles, and parse_config (including raw_config[section]).

**Fix:** After loading, coalesce with `raw_config = yaml.safe_load(f) or {}` (or raise a clear 'empty/invalid config' error if not a mapping). Apply a `(... or {})` guard between every chained .get() level and to `raw_config[section]`, and validate/skip non-dict profile_def values with a clear, key-named error message. Best done alongside the parse_config table refactor below so the coalescing lives in one place.

**Locations:**
- `configarr/config.py:82-87 (parse_quality_profiles)`
- `configarr/config.py:115,117-123,133-135 (parse_arr_instance chains)`
- `configarr/config.py:181-211,194 (raw_config None and section access)`
- `configarr/__main__.py:95 (broad except masks key)`

### 10. [MEDIUM · medium effort] Bazarr language-profile sync mis-reports updated profiles and uses batch-wide counts as per-profile results

In languages.py, when a profile already exists it is rebuilt, added to all_profiles, and saved (i.e. updated), yet it is appended to `skipped` and never increments `success` — contradicting commit 35f6ecc ('update existing profiles instead of skipping them'). The single atomic _save_profiles call persists all profiles, but on success `success` undercounts updated profiles, and on failure it sets failure=len(profiles_config), success=0 while leaving `skipped` populated, so the returned tuple simultaneously claims items failed and were skipped. sync.py then derives each profile's printed label from the aggregate `f`: on a batch failure every non-skipped profile prints 'Failed to create', while existing/updated profiles in `skipped` unconditionally print 'Already exists' even when the save failed — so per-profile console messages reflect the whole batch, not the item. Functional sync is correct; only the reporting/accounting is wrong.

**Fix:** Count updated profiles as success (or add a distinct `updated` counter) and stop appending genuinely-saved profiles to `skipped`. Because the save is one atomic batch, derive counts after the save: on failure set failure=len(profiles_config), success=0, skipped=[]; on success set success=created+updated. Better, return per-profile statuses so sync.py reports each accurately and gate the 'Already exists' line on the failure state.

**Locations:**
- `configarr/bazarr/languages.py:205-216 (updated -> skipped, no success)`
- `configarr/bazarr/languages.py:223-228 (atomic save accounting)`
- `configarr/sync.py:341-354 (aggregate-derived per-profile labels)`

### 11. [MEDIUM · medium effort] Broad except Exception across Bazarr modules swallows failures, returns bool/empty, and loses tracebacks

Every Bazarr network/parse operation in BazarrClient, SettingsManager, and the language manager catches bare Exception, logs only str(e) (no exc_info), and returns False/None/[]. Programming errors (AttributeError/KeyError/TypeError from malformed responses) become indistinguishable from network failures, no traceback appears even with --debug, and get_profiles/get_languages returning [] on failure makes downstream logic (_get_next_profile_id, existing_by_name) treat 'fetch failed' as 'nothing exists' — risking duplicate-profile creation and loss of existing profiles. Failures reach sync.py as bare booleans with no exception detail, unlike the arr clients which surface {e}.

**Fix:** Narrow catches to requests.RequestException / json.JSONDecodeError / bazarr ApiException and let programming errors propagate; log with exc_info=True so tracebacks appear even when narrowed. Critically, distinguish 'fetch failed' from 'empty result' in get_profiles/get_languages so a read failure does not drive destructive create-everything sync behavior.

**Locations:**
- `configarr/bazarr/__init__.py:66,80,107,169`
- `configarr/bazarr/languages.py:71-73,83-85,177-179`
- `configarr/bazarr/settings.py:42-44,56-58,76-78,92-94,108-110`

### 12. [MEDIUM · medium effort] Per-resource catch-and-continue swallows programmer errors and actionable config errors with no traceback

Every resource loop in sync.py wraps the sync call in a bare `except Exception as e` that prints {e} and increments failure. This intended resilience also swallows ValueError raised for genuinely actionable misconfiguration (e.g. radarr.sync_download_client 'Missing implementation'/'Unknown implementation') and programming bugs (AttributeError/TypeError), presenting all of them as a one-line red message with no verbose/traceback path, so structural bugs are indistinguishable from server-side failures.

**Fix:** Narrow to the HTTP/API exception types raised by the generated clients (plus ValueError for config issues) and let unexpected exception types propagate, or surface a traceback under a verbose/--debug flag. Fold the repeated try/except into the shared _sync_collection helper described in the sync.py-duplication theme.

**Locations:**
- `configarr/sync.py:76,89,106,123,136,155,175,192,209,238,255,272,381,398,411`

### 13. [MEDIUM · medium effort] Pervasive sync.py reporting duplication with drifted/inconsistent SyncStatus handling

The 'iterate items; try sync_X; map CREATED/UPDATED/UNCHANGED to icon+counter; except -> Failed+failure' pattern is copy-pasted ~10x across sync_arr/sync_prowlarr/sync_sabnzbd. The blocks have drifted: some handle UNCHANGED but not UPDATED, others UPDATED but not UNCHANGED. The one genuine current silent gap is Misc Settings: sabnzbd.sync_misc_settings can return UNCHANGED but the handler only handles UPDATED, so that result is neither printed nor counted (empty section). Other drift is latent today only because the corresponding sync_X never returns the unhandled status. Also includes the naming/quality-definition UNCHANGED handlers that lack a branch, and the download-client/notification/indexer/application/server/category blocks that omit UNCHANGED entirely.

**Fix:** Extract a generic _sync_collection(title, items, sync_fn) helper that maps every SyncStatus member to an icon/counter (including UNCHANGED) and handles try/except uniformly, then drive all sections through a small declarative table. This kills the duplication and the drift, and fixes the Misc Settings empty-section gap in one place.

**Locations:**
- `configarr/sync.py:67-78,97-108,114-125,144-158,163-178,183-195,200-212,229-275,372-401,404-414`

### 14. [MEDIUM · large effort] Massive RadarrClient/SonarrClient duplication and the missing shared ArrClientBase abstraction

~80% of RadarrClient and SonarrClient are near-verbatim duplicate method bodies differing only by the SDK package and a few resource fields: _build_fields, _find_by_name/_find_by_path, the schema caches (_download_client_schemas, _notification_schemas) and get_*_schema methods, get_quality_definitions, sync_root_folder, sync_delay_profile, sync_custom_format, sync_download_client, and sync_quality_profile. This is the root cause that lets the high-severity custom-format-cache bug, the notification-tags bug, and the magic-value drift exist in two places at once and require double fixes. Also includes the _find_by_name/_find_by_path pair that differs only by attribute name.

**Fix:** Introduce a common ArrClientBase parameterized by the SDK module (or the constructed Api objects) holding _find_by_* (collapsed into one _find_by(resources, attr, value) helper), _build_fields, the schema caches, get_quality_definitions, and all non-divergent sync_* methods. Provide a hook (e.g. _apply_language) overridden only by Radarr for quality-profile language handling so the Sonarr-vs-Radarr difference is explicit. Note: notification schema cache is duplicated only across radarr/sonarr (twice), while the download-client schema/_build_fields pattern also appears in prowlarr (three times).

**Locations:**
- `configarr/radarr.py:72-94,116-128,159-198,201-243,260-355,358-432`
- `configarr/sonarr.py:82-94,126-138,185-224,252-294,297-383,386-460`

### 15. [MEDIUM · large effort] Sync operations are non-idempotent: always overwrite and report UPDATED, never UNCHANGED

Several sync paths never diff against current state. sync_quality_definitions mutates the cached resources in place and unconditionally PUTs, always returning UPDATED (also leaking mutated min/max sizes into the shared _quality_defs cache read by sync_quality_profile). sync_quality_profile, sync_custom_format, sync_download_client, and sync_notification always overwrite an existing resource and return UPDATED, never UNCHANGED. sync_delay_profile is worse: it matches existing profiles only by (usenet_delay, torrent_delay, preferred_protocol), so changing any other field is never applied, and changing a matched field creates a DUPLICATE profile instead of updating (no update API is ever called), letting repeated runs accumulate duplicates against Sonarr's default profile. Net effect: every run reports spurious 'Updated', issues unnecessary writes, and the elif UNCHANGED branches for quality profiles/custom formats are dead.

**Fix:** Track whether any field actually changed and return UNCHANGED + skip the write when nothing differs; operate on a copy rather than mutating the shared cache in sync_quality_definitions. For sync_delay_profile, match by a stable identity (name/tags) and call the update API when found and fields differ, mirroring sync_custom_format/sync_quality_profile, so it stops creating duplicates. Then either the UNCHANGED branches become live or are removed.

**Locations:**
- `configarr/radarr.py:93-113 (sync_quality_definitions),345-355 (sync_quality_profile),233-238 (custom format)`
- `configarr/sonarr.py:103-123 (sync_quality_definitions),185-224 (sync_delay_profile)`
- `configarr/sync.py:153-154,173-174 (dead UNCHANGED branches)`

### 16. [LOW · small effort] Prowlarr inconsistent name matching: case-sensitive for indexers/applications, case-insensitive for download clients

_find_by_name (used by sync_indexer and sync_application) matches with exact equality, while sync_download_client matches case-insensitively (commit 180d2a5 only applied the change to download clients). If a Prowlarr indexer/application name differs from the configured name only by case, _find_by_name returns None and a duplicate is CREATED instead of UPDATED, defeating idempotency. In practice this requires an out-of-band rename/manual creation, since configarr creates resources with the configured casing.

**Fix:** Normalize matching consistently across all three sync paths (compare name.casefold() == name.casefold() in _find_by_name and reuse it for download clients instead of a separate inline loop).

**Locations:**
- `configarr/prowlarr.py:91-96 (case-sensitive _find_by_name)`
- `configarr/prowlarr.py:222-225 (case-insensitive download clients)`

### 17. [LOW · small effort] Duplicated base-model fields and strip_trailing_slash validator across four config models

The identical strip_trailing_slash field_validator (same name/body/docstring) plus the name/base_url/api_key field declarations are copy-pasted into ArrServiceConfig, ProwlarrConfig, BazarrConfig, and SabnzbdConfig. A URL-normalization fix must be applied in four places and can drift.

**Fix:** Factor name/base_url/api_key and the strip_trailing_slash validator into a shared ServiceBase(BaseModel) that all four config models inherit, keeping the rstrip('/') behavior.

**Locations:**
- `configarr/models.py:45-49,67-71,86-90,103-107`

### 18. [LOW · small effort] Dead QualityProfileConfig model with quality-profile defaults duplicated as literals in config.py

QualityProfileConfig in models.py is defined with fields, defaults, and a qualities normalization intent but is never imported or instantiated; quality-profile input is typed as list[dict[str, Any]] and parsed manually. Its defaults (upgrades_allowed=True, upgrade_until_quality='WEBDL-1080p', upgrade_until_custom_format_score=10000, minimum_custom_format_score=0) and the str->{'name': q} normalization are re-implemented as literals in config.py:parse_quality_profiles, so the two can silently drift and the model gives a false impression that this input is validated. (The earlier claim of 'three call sites incl. radarr.py/sonarr.py' was wrong — those are unrelated DelayProfileResource defaults.)

**Fix:** Either delete QualityProfileConfig as dead code, or wire it into parse_quality_profiles so parsing validates input and the defaults live in exactly one place.

**Locations:**
- `configarr/models.py:18-26`
- `configarr/config.py:88,93-99`

### 19. [LOW · small effort] Magic values in quality-profile construction: min_upgrade_format_score=1 and cutoff_id=3 fallback (both clients)

min_upgrade_format_score is hardwired to 1 in both clients' QualityProfileResource with no config knob and no comment, unlike the adjacent min_format_score/cutoff_format_score read from config. The cutoff fallback to literal 3 (when neither configured until_quality nor any enabled quality resolves) is an unexplained magic id not guaranteed to be in the profile's allowed set, so Radarr/Sonarr may reject the profile or apply an unexpected cutoff. Both appear in the copy-pasted methods (sonarr.py:334 has a '# Default fallback' comment, radarr.py:296 does not — drift).

**Fix:** Read min_upgrade_format_score from config (upgrade_config.get('min_upgrade_format_score', 1)) and document why 1 is the default. Fall back the cutoff to the id of the first allowed/enabled quality actually built for the profile (or raise a clear error) instead of a hardcoded 3. Resolve once in the shared ArrClientBase.

**Locations:**
- `configarr/radarr.py:296,331`
- `configarr/sonarr.py:334,369`

### 20. [LOW · small effort] Root-folder dict missing 'path' key passes the whole dict downstream as the path

folder.get("path", folder) defaults to the entire folder dict when 'path' is missing/misspelled, so client.sync_root_folder(<dict>) is called where a str path is expected, producing a confusing downstream error (caught by try/except and reported as a generic failure) instead of a clear 'missing path' message. The `if isinstance(folder, dict) else folder` guard and the `, folder` default are dead branches given root_folders is typed list[dict[str, Any]].

**Fix:** Use path = folder.get("path") and raise/skip with a clear, named error when missing; drop the dead isinstance branch since the model guarantees a dict.

**Locations:**
- `configarr/sync.py:68`
- `configarr/models.py:41 (typed dict)`

### 21. [LOW · small effort] SABnzbd duplicated identical create/update branches and bool-coercion split across layers

In sync_server and sync_category the `if existing:` and else branches call self.set_config(...) with identical arguments, differing only in returned SyncStatus and log message (the existence lookup still legitimately distinguishes CREATED vs UPDATED, but the duplicated call is redundant). Separately, bool->int coercion lives only in the high-level sync_* methods; set_misc/set_config/_call pass values straight to the query string, so any future caller that forgets to pre-coerce would send 'True'/'False' strings SABnzbd does not interpret. del_config is also dead code, and key_map in sync_misc_settings is a misleading identity mapping.

**Fix:** Collapse to a single set_config call: status = UPDATED if existing else CREATED. Centralize bool->int coercion inside set_misc/set_config (or _call) so every path produces 1/0. Remove del_config (or wire it into a prune flow) and replace the identity key_map with a plain tuple of key names.

**Locations:**
- `configarr/sabnzbd.py:126-133,151-158 (duplicated branches)`
- `configarr/sabnzbd.py:189-190 vs 57-67 (split bool coercion)`
- `configarr/sabnzbd.py:69-77 (dead del_config)`
- `configarr/sabnzbd.py:163-183 (identity key_map)`

### 22. [LOW · small effort] Bazarr dead initialization and unused imports across __init__.py and languages.py

BazarrClient imports json and GeneralSettings/RadarrSettings/SonarrSettings that are never referenced (only SystemSettingsUpdate is used, at line 77), and constructs self.languages_api/self.profiles_api (SystemLanguagesApi/SystemLanguagesProfilesApi) that are never used — all language/profile work goes through self._language_manager. The language manager likewise builds languages_api/profiles_api but talks to Bazarr via raw requests, leaving those attributes dead. This dead surface misleads readers about which code path is real. (The earlier claim that languages.py's `bazarr` import is unused is incorrect — it is used.)

**Fix:** Remove the unused json/GeneralSettings/RadarrSettings/SonarrSettings imports (keep SystemSettingsUpdate) and the dead languages_api/profiles_api attributes (and their now-unused API-class imports), or use the generated clients instead of raw requests.

**Locations:**
- `configarr/bazarr/__init__.py:3,11-13 (unused imports),54-55 (unused api instances)`
- `configarr/bazarr/languages.py:60-61 (unused languages_api/profiles_api)`

### 23. [LOW · small effort] Bazarr language profile silently drops unresolved language names and cutoff

In _build_profile_payload, items only gains entries where lang_code is truthy, so if get_language_code returns None for an unknown/typo'd language name that language is silently omitted (possibly yielding an empty items list), and cutoff_id stays None if the cutoff language never resolves — silently producing a profile with no cutoff. No logging surfaces these unresolved names.

**Fix:** Log a warning whenever get_language_code returns None for a configured language or for the cutoff, so unresolved/typo language names are not silently swallowed.

**Locations:**
- `configarr/bazarr/languages.py:123,128-157`

### 24. [LOW · small effort] Unresolved ${VAR} references and INFO-level diagnostics silently lost

Two CLI-diagnostics smells. replace_env returns the literal ${VAR} text when an env var is unset, so a typo'd/unset api_key flows downstream as the string '${API_KEY}', accepted by Pydantic as a valid str and failing only later as an opaque auth error far from the root cause. Separately, logging.basicConfig is called only inside `if debug:`, so without --debug no handler/format is configured; in practice there are no log.info calls and WARNING/ERROR still reach stderr via the last-resort handler, but with Python's bare default format rather than the configured timestamped one.

**Fix:** Fail fast (or log a warning) when a referenced ${VAR} is unset instead of passing the literal placeholder downstream. Call logging.basicConfig unconditionally with the format and set level=logging.DEBUG if debug else logging.INFO/WARNING so non-debug runs have a consistently configured handler.

**Locations:**
- `configarr/config.py:67-71 (silent ${VAR} passthrough)`
- `configarr/__main__.py:68-73 (logging only on --debug)`

### 25. [LOW · medium effort] Prowlarr N+1 list fetches and divergent/duplicated field-building and error handling

Each existing-resource list is re-fetched once per configured item (sync_indexer/list_indexer, sync_application/list_applications, sync_download_client HTTP GET) inside the sync.py loops, while only schema lists are cached — an avoidable N+1. Separately, build_fields (indexers/applications) leaves field.value unset for missing values while the download-client path coerces None to '' (a deliberate Prowlarr NullReferenceException workaround) — duplicated field-building logic with divergent null policy. Invalid sync_level raises a bare ValueError lacking application/key context unlike sibling validations. And _find_by_name uses an unbounded generic T plus a hasattr guard that silently yields None on wrong-typed input.

**Fix:** Cache each existing-resource list once on the client (like the schema caches) and look up by name in memory, updating the cache after create/update. Factor field-building into one helper with a documented null-handling policy. Wrap the ApplicationSyncLevel conversion to re-raise with application/key context. Bound the _find_by_name generic with a Protocol exposing .name so misuse surfaces loudly.

**Locations:**
- `configarr/prowlarr.py:122,156,216 (N+1 list fetches)`
- `configarr/prowlarr.py:82-88 vs 197-201 (divergent field-building)`
- `configarr/prowlarr.py:144-145 (opaque sync_level ValueError)`
- `configarr/prowlarr.py:93-95 (unbounded generic + hasattr guard)`

### 26. [LOW · medium effort] Duplicated five-block dispatch/parse structure in __main__.py and config.py

Two parallel five-way repetitions: parse_config has five near-identical instance-parsing blocks (radarr/sonarr/prowlarr/bazarr/sabnzbd) differing only by section key/target/parser, and __main__.py has five service-dispatch blocks repeating the same `service.lower()` + `if instance and cfg.name != instance: continue` filter and success/failure accumulation. The repetition makes the null-handling and silent-no-match bugs easy to introduce inconsistently and forces fixes in five places.

**Fix:** Drive parse_config from a small table mapping section name -> parser and build each list via a comprehension that coalesces None once. Extract a __main__ helper taking the service key, instance list, and a per-instance sync callable that applies the service/instance filter once and returns aggregated (success, failure).

**Locations:**
- `configarr/config.py:193-211`
- `configarr/__main__.py:102-145`

### 27. [LOW · medium effort] Bazarr provider/profile sync re-fetches state over HTTP repeatedly with no caching

sync_provider does a full GET of system settings to read enabled_providers, appends one provider, then POSTs — called once per provider in sync.py, so it re-reads and re-writes enabled_providers N times. Within configarr's sequential loop this accumulates correctly, but it is N redundant GET/POST round-trips and opens a lost-update window if any external writer modifies enabled_providers between this call's GET and POST. Separately, the language manager's get_language_code calls get_languages() (HTTP GET) on every cache-miss, and sync_profiles fetches get_profiles() at line 194 and again indirectly via _get_next_profile_id — none memoized, plus a membership test rebuilds a list inside the existing-profile loop (O(n*m)).

**Fix:** Compute enabled_providers once for all configured providers and write per-provider fields without re-touching the global list (or read it once and pass it in). Memoize get_languages()/get_profiles() on the manager instance and precompute config_names = {p.get('name') for p in profiles_config} once before the loop.

**Locations:**
- `configarr/bazarr/__init__.py:132-168 (per-provider re-fetch of enabled_providers)`
- `configarr/bazarr/languages.py:103,111,194,199 (uncached re-fetches)`
- `configarr/bazarr/languages.py:219-220 (list rebuilt in loop)`

### 28. [LOW · medium effort] Cosmetic/typing/idiom cleanups in arr clients and sync.py

A cluster of low-impact consistency nits, mostly duplicated across radarr/sonarr. _resolve_language lazily creates self._language_cache via a hasattr guard instead of declaring it in __init__ like the other caches (and needlessly rebuilds Language(id=..., name=...)). _build_fields re-imports ContractField locally despite the module-level import, and uses over-broad bare `list`/`list | None` hints instead of list[ContractField]. COLON_REPLACEMENT_MAP in radarr.py is an identity map that only serves to whitelist values with a 'smart' fallback (could be a set membership check), unlike Sonarr's meaningful str->int map. sync.py wedges the ArrClient = Union[...] alias mid-import-block (should sit with ServiceType and use `RadarrClient | SonarrClient`), and _print_header/_print_section lack `-> None`. Pydantic models use literal mutable [] / {} defaults (safe in v2 but non-idiomatic; prefer default_factory).

**Fix:** Declare self._language_cache: list[Language] | None = None in __init__, gate on `is None`, and return lang directly. Remove the local ContractField re-imports and annotate _build_fields as -> list[ContractField] with a concrete element type. Replace COLON_REPLACEMENT_MAP with a set membership check (or the radarr ColonReplacementFormat enum). Move the ArrClient alias below imports next to ServiceType and use `RadarrClient | SonarrClient`. Add `-> None` to _print_header/_print_section, unify update_* id coercion, and switch Pydantic literal defaults to Field(default_factory=...). Best absorbed into the ArrClientBase refactor.

**Locations:**
- `configarr/radarr.py:38-44,72-84,246-258,369-373`
- `configarr/sonarr.py:397-411,401,438-439,501-503`
- `configarr/sync.py:11-14,34,41`
- `configarr/models.py:26,35-43,63-65,83-84,99-101,113-117`

## Refuted findings (verified NOT to be real issues)

These were raised by a finder but an independent verifier disproved them against the source — recorded so they are not re-investigated:

- **bypass_if_above_custom_format_score discards the configured threshold** (`configarr/sonarr.py:207-217`) — The claim's factual reading of sonarr.py:207-217 is accurate (bypass_score is collapsed to bypass_score > 0), but its premise that a "threshold is silently dropped" is wrong. The upstream Sonarr API model defines bypass_if_above_custom_format_score as a StrictBool toggle and minimum_custom_format_score as a separate StrictInt threshold (delay_profile_resource.py:37-38). The configarr config schema documents bypass_if_above_custom_format_score as an int whose meaning is explicitly "enables the bypass flag when > 0" (references/schema.md:145), with the actual threshold provided by the independent minimum_custom_format_score key (schema.md:146), which the code passes through verbatim (sonarr.py:217). So 50 vs 1 producing the same toggle is documented, intended behavior, not a dropped value. There is no separate threshold associated with this key to transmit. The claim's recommendation (derive minimum_custom_format_score from the bypass value) would actually corrupt the independently-configured minimum_custom_format_score. This is at most a naming/UX ambiguity, not a bug.
- **Boolean flags coerced to Python str ('True'/'False') instead of real booleans** (`configarr/bazarr/languages.py:136-147`) — The code at /home/aldo/Dev/aldoborrero/configarr/configarr/bazarr/languages.py:136-138 does coerce hi/forced/audio_exclude via str(bool) -> "True"/"False", and lines 145-147 default to the literal "False". The literal evidence holds. However the claim's premise — that Bazarr's API expects JSON booleans and these strings flip semantics — is false. Bazarr's API contract genuinely requires Python-style boolean strings for these exact fields. Bazarr's frontend types (frontend/src/types/api.d.ts) declare Language.ProfileItem.{hi,forced,audio_exclude} as the custom type PythonBoolean, and Bazarr's own conversion helper (frontend/src/utilities/index.ts:62-67) defines: fromPython(value: PythonBoolean): boolean and toPython(value: boolean): PythonBoolean { return value ? "True" : "False"; }. So PythonBoolean === "True" | "False" string literals, and emitting "True"/"False" is exactly correct. The defaults "False" are correct, not a truthy bug — Bazarr parses them with fromPython back to real booleans. There is no semantic flip. The only residual nit is that str() is mildly fragile if a config supplies a non-bool (e.g. YAML string "false" would pass through as "false" rather than "False"), but that is a different, lower-severity concern than the claimed bug and the recommendation (emit real bools) would actually break the API. Claim refuted.
- **Inconsistent id type passed to update calls: download client uses found.id, notification wraps it in int()** (`configarr/radarr.py:411 vs radarr.py:472 (same in sonarr.py:439 vs 502)`) — The factual observations are accurate: radarr.py:411 calls update_download_client(found.id), radarr.py:472 calls update_notification(int(found.id)), and update_custom_format (radarr.py:235) / update_quality_profile (radarr.py:347) use str(found.id) (same pattern in sonarr.py:439/502/286/375). But the claim's core thesis — that these are arbitrary, trial-and-error coercions of "the same kind of identifier" posing a latent 422/400 risk — is refuted by the actual SDK contract (radarr-py 1.2.0). The generated SDK declares two distinct pydantic-typed signatures: update_download_client(id: StrictInt) and update_notification(id: StrictInt) vs update_custom_format(id: StrictStr) and update_quality_profile(id: StrictStr) (verified at download_client_api.py:2671, notification_api.py:2133, custom_format_api.py:1858, quality_profile_api.py:1077). On all resources .id is Optional[StrictInt] (download_client_resource.py:32, notification_resource.py:31, custom_format_resource.py:30), i.e. an int at runtime. Therefore the coercions are deliberate and correct: download_client passes the already-int .id to a StrictInt param (raw is correct); custom_format/quality_profile MUST wrap in str() because StrictStr would reject an int; notification's int(found.id) is redundant (int of an int) but harmless. The "three different coercions" reduce to two SDK signatures, each handled correctly — there is no latent HTTP-error risk. The only residual issue is purely cosmetic: notification redundantly wraps an already-int value in int() while download_client does not, a stylistic inconsistency with no behavioral impact. Severity none.
- **Batch language-profile save: partial config failure zeroes out already-counted successes and overcounts failures** (`configarr/bazarr/languages.py:224-229`) — The claim mischaracterizes the save mechanism and the success/failure semantics. (1) "Partial config failure": there is no partial failure. _save_profiles (languages.py:163-179) does a SINGLE atomic POST of the entire all_profiles list to /api/system/settings. If raise_for_status fails, NOTHING is persisted — it's all-or-nothing. (2) "Zeroes out already-counted successes / counts SKIPPED profiles as successes": false. In the loop, success is incremented ONLY in the create branch (languages.py:216). Updated/existing profiles are appended to `skipped` (line 210) and are NEVER added to success. So success holds only the created-profile count. On save failure, setting success = 0 (line 227) is correct because nothing was written. (3) "Failure count too high / overcounts": failure = len(profiles_config) (line 226). Since the POST is atomic and failed, every configured profile (created + updated) genuinely failed to persist, so counting all of them as failures is defensible, not an overcount. If anything it UNDERcounts relative to all_profiles (it excludes the preserved existing-but-not-in-config profiles appended at lines 219-221), the opposite of the claim. There is a real but minor inconsistency, and it is NOT at the cited lines: in the reporting layer (sync.py:343-352), on failure the skipped profiles are still printed as "Already exists" (lines 351-352) even though they were aggregated into the failure total — a cosmetic display/aggregate mismatch, not the data-corruption bug the claim describes. The cited evidence (languages.py:224-229) does not support the stated high-severity bug.
- **sync_misc_settings filters falsy/None via `if config_key in config` but not None values, and bool→int may corrupt intended strings** (`configarr/sabnzbd.py:186-193`) — The central evidence claim is factually wrong. At sabnzbd.py:187-191 a YAML null does pass the `if config_key in config` check and `set_misc(api_key, None)` is called, but the claim that this "gets sent as the string 'None' via the API layer, silently writing a bad value" is incorrect. The value flows to `set_misc` (sabnzbd.py:57-67), which puts it into `params["value"]` and passes `params` directly to `requests.get(..., params=params, ...)` in `_call` (sabnzbd.py:21-30). There is no string-coercion layer. I empirically tested `requests`' query serialization (PreparedRequest.prepare_url): a `None` param value is DROPPED entirely from the query string — `{'value': None, 'keyword': 'bandwidth_max'}` produces `?keyword=bandwidth_max` with no `value` at all. It does NOT produce `value=None`. So the described failure mode (writing the string 'None') does not occur. At worst SABnzbd receives a set_config call with no value and ignores/rejects it — not a silent bad write.\n\nThe bool→int concern is also a non-issue: the `1 if value else 0` conversion only fires on actual Python `bool` (sabnzbd.py:189), which is exactly what's needed since `requests` would otherwise serialize `True`/`False` to the strings 'True'/'False' (confirmed in the same test). A YAML value 'intended as a string' only becomes a Python bool if the user literally writes an unquoted boolean keyword, in which case treating it as a boolean setting is correct. No realistic corruption path exists.\n\nThe only kernel of truth is that None values aren't explicitly skipped, but the consequence described is refuted, and the practical impact is negligible (param omitted, not corrupted).
