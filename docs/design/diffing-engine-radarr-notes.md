# Radarr/Sonarr V3 API: notes for the diffing engine

Research notes from reading the Radarr source (cloned to `.claude/code/Radarr`, a
gitignored reference checkout). Sonarr's V3 API mirrors Radarr almost exactly (same
`RestController`, `ProviderControllerBase`, `SchemaBuilder`, Field model), so these
facts apply to both. Companion to [`diffing-engine-feasibility.md`](./diffing-engine-feasibility.md).

These are the upstream constraints that dictate how a client-side diff/apply engine
must behave.

## 1. PUT is a full-object replace (not a merge)

`RestController<TResource>.OnActionExecuting` (`src/Radarr.Http/REST/RestController.cs`)
only copies the route `id` onto the body when `Id == 0`; it never loads the existing
record to backfill omitted fields. Update handlers do `resource.ToModel()` →
`service.Update(model)` (e.g. `QualityProfileController.Update`,
`CustomFormatController.Update`, `NamingConfigController.UpdateNamingConfig`). Omitted
scalars deserialize to .NET defaults (`0`/`false`/`null`) and overwrite the stored value.

→ **Implication:** For every update the engine must **GET current → deep-merge desired
over current → PUT the complete object** (including `Id`). Never send a sparse patch.
"Field absent" means "reset to default," not "leave unchanged."

## 2. Providers are a flat `List<Field>`, with `/schema` as the default layer

Providers = download clients, indexers, notifications, import lists, metadata.
`ProviderResource<T>` carries `Name, Fields, Implementation, ConfigContract, Tags,
Presets, Id`. `Fields` is reflected from the settings POCO's `[FieldDefinition]`
properties via `SchemaBuilder.ToSchema` (nested objects flatten to `prefix.child`).
`GET /schema` (`ProviderControllerBase.GetTemplates`) returns one resource per
available implementation, each field's `Value` being the POCO's **default**.

→ **Implication:** Diff/merge providers at **field granularity keyed by `Field.Name`**,
not as opaque JSON. Use `GET /schema` (matched by `Implementation`/`ConfigContract`)
as the **default-value layer** for three-way comparison and for building new resources.
Always include `Implementation`, `ConfigContract`, and `Name` on writes.

## 3. Secret fields read back masked — the #1 false-diff source

`SchemaBuilder.ToSchema` replaces any non-empty `ApiKey`/`Password` field value with the
literal `"********"` (`PRIVATE_VALUE`). On write, `ReadFromSchema` sees an incoming
`"********"` and, **if an existing model is supplied**, restores the stored secret.
Field privacy/types live in `FieldDefinitionAttribute`
(`src/NzbDrone.Core/Annotations/FieldDefinitionAttribute.cs`):
`PrivacyLevel {Normal, Password, ApiKey, UserName}`, `FieldType {Textbox, Number,
Password, Checkbox, Select, Path, Tag, Url, ...}`.

→ **Implication:** Treat current secret values as **unknown** — exclude `Password`/
`ApiKey` from diffing. To keep a secret: omit it or send `"********"`. To change it:
send the real value (a real value always overwrites). Note: custom-format spec fields
do **not** get secret restoration (specs are assumed to have no privacy fields).

## 4. CustomFormat

`CustomFormatResource`: `Id` (always serialized), `Name`,
`IncludeCustomFormatWhenRenaming (bool?)`, `Specifications`. Each spec
(`CustomFormatSpecificationSchema`): `Name, Implementation (= C# type name),
Negate, Required, Fields`. On apply, specs are matched by `Implementation ==
GetType().Name` (throws if unknown). `GET /customformat/schema` lists all spec
implementations. Validators: **name unique**, ≥1 spec, non-empty spec names.

→ **Implication:** Address by `Id`, match across environments by **unique `Name`**.
Diff specifications by `Implementation` + `Name` + `Fields`. Always send `Id` and ≥1 spec.

## 5. QualityProfile

`QualityProfileResource`: `Name, UpgradeAllowed, Cutoff (int → quality OR group id),
Items (ordered), MinFormatScore, CutoffFormatScore, MinUpgradeFormatScore, FormatItems
(custom-format scores), Language`. Quality groups are items with `Id >= 1000` and child
`Items`; leaves carry `Quality {id,name,...}`. `GET /qualityprofile/schema` builds a
default profile (qualities grouped by weight, all `Allowed=false`, one `FormatItem` per
existing custom format with `Score=0`). Validators: `FormatItems` must list **exactly
every existing custom format id** (none missing/extra); `MinUpgradeFormatScore >= 1`;
cutoff/items valid; `MinFormatScore` satisfiable. Name uniqueness is **by convention**
(only NotEmpty validated).

→ **Implication:** Match by `Name`. **Fetch all custom formats first** and emit a
`FormatItem` for every one (default score 0) or the PUT is rejected. `Items` order is
**semantic** (priority) — build from `/qualityprofile/schema`, preserve order, diff
structurally keying qualities/cutoff by `id`.

## 6. NamingConfig — singleton

`config/naming` is a fixed-id singleton (no create/delete); GET then PUT the whole
object. Radarr fields: `RenameMovies, ReplaceIllegalCharacters, ColonReplacementFormat
(enum), StandardMovieFormat, MovieFolderFormat`. Sonarr has series/season/episode
formats instead. Format strings are validated server-side.

→ **Implication:** GET-merge-PUT with the same `Id`; include all format fields
(full-replace).

## 7. Identity & validation to pre-empt

Stable identity is the integer `Id` (`RestResource.Id`), omitted from JSON when 0
(except `CustomFormatResource`, which always emits it). Name uniqueness is
**validator-enforced** for providers and custom formats, **by convention** for quality
profiles. Pre-empt locally: unique names; ≥1 spec with non-empty names; FormatItems
completeness; MinFormatScore satisfiability; MinUpgradeFormatScore≥1; valid naming
formats. Provider create/update runs a **live connectivity `Test()`** when `Enable=true`
— pass `?forceSave=true` to apply without the server probing the external service.

→ **Implication:** Key by `Id` once known; resolve desired-by-`Name`. Validate locally
before apply. Support `forceSave` for bulk/offline reconciliation.

## 8. Type-coercion hazards (normalize before comparing)

- Secrets masked as `"********"` (§3).
- Provider select-field values serialize as **ints**; `Field.Value` is untyped
  (`JsonElement` on read). `Field.IsFloat` distinguishes double vs int; `"5"` == `5`
  server-side but differ as raw JSON.
- Top-level enums serialize as ints (`ColonReplacementFormat`); `Language` and `Quality`
  are objects `{id,name,...}` — compare by **`id`**, not the echoed `name`/`label`.
- **List order is semantic** for quality profile `Items`; do not sort before diffing.
  `Fields` come back sorted by `Order` (cosmetic) — normalize order before comparing.
- Absent scalar == server default (full-replace), not "unchanged".
- Nested `Id`s dropped when 0 — absence isn't a diff.
- URLs not normalized server-side — normalize trailing slashes client-side.

→ **Implication:** Canonicalize before comparison: coerce numeric strings, compare
enums/Quality/Language by id, ignore server-derived label echoes, preserve semantic
list order, treat absent == default.

## How this updates the engine design

These facts confirm and sharpen the §3 design in the feasibility study:

1. The **three-way comparison** (desired / current / default) is not optional — it's
   forced by full-replace PUT. The **default layer must come from the live `/schema`
   endpoints**, not hardcoded constants, because defaults are per-implementation.
2. The `ResourceProvider.normalize()` step must implement the §8 canonicalization, and
   the per-kind comparison must **skip masked secret fields** entirely.
3. `build_desired()` for quality profiles must **depend on a prior fetch of custom
   formats** (FormatItems completeness) — i.e. providers have an ordering dependency the
   engine must encode (custom formats → quality profiles), which matches configarr's
   existing "custom formats before quality profiles" rule.
4. Identity is `Id`, but cross-environment matching is by `Name`; the matcher registry
   should resolve name→id against current state before producing the apply action.
5. Apply should expose a `forceSave`-style option for providers so reconciliation
   doesn't fail when a target service is briefly unreachable.

Sonarr deltas to verify when extending: series/season/episode naming fields, release
profiles (Sonarr-only), and any quality definition differences — but the REST/provider
machinery is identical, so the engine abstractions carry over unchanged.
