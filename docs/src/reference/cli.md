# Command Line

configarr is a single command. It diffs your `configarr.yml` against every service
and, by default, **applies only what changed**. The flags control **what** is
processed, whether to **preview** instead of write, and whether to **prune**.

```text
configarr [OPTIONS]
```

## Options

| Flag | Argument | Description |
|---|---|---|
| `--config` | `PATH` | Path to the config file. Default: `./configarr.yml` (the current directory). |
| `--service` | `NAME` | Only process one service: `radarr`, `sonarr`, `prowlarr`, `bazarr`, or `sabnzbd`. |
| `--instance` | `NAME` | Only process the instance with this label. Combine with `--service` to disambiguate. |
| `--plan` / `--dry-run` | — | Preview the diff for **all** services, then exit without writing anything. The two flags are aliases. |
| `--check` | — | Validate the config **offline** — parse it, check the models, and resolve any TRaSH imports — then exit. Contacts **no** service, so it needs no reachable instances. For CI. |
| `--prune` | — | Also delete resources **configarr previously created** that the config no longer declares, for providers that support deletion. Ownership-scoped — never deletes resources you made by hand. Additive by default; combine with `--plan` to preview deletions first. |
| `--output` | `text\|json` | Output format for `--plan`. `json` emits a machine-readable diff for CI. Default: `text`. |
| `--strict` | — | Treat an unrecognized config key (likely a typo) as an error instead of a warning. |
| `--print-schema` | — | Print a JSON Schema for `configarr.yml` (for editor autocomplete/validation) and exit. Needs no config file. |
| `--debug` | — | Verbose debug logging for the whole run. Does **not** prevent writes. |
| `--version` | — | Print the configarr version and exit. |

Apply is the **default** — running with no flag writes the changes.

> [!NOTE]
> `--plan` / `--dry-run` is **universal**: it previews every service and writes
> nothing. There is no per-service dry-run and there is no `--verbose` flag. The
> only way to narrow a run is `--service` / `--instance`. See
> [Plan, Apply & Scoping](../concepts/dry-run-and-scoping.md).

> [!NOTE]
> `--prune` deletes for the providers that support it: **custom formats**,
> **indexers**, **applications**, **download clients** (Radarr/Sonarr and Prowlarr),
> and **notifications**. Singletons and set-only/config providers (naming, quality
> profiles/definitions, SABnzbd, Bazarr, delay/release profiles) stay additive even
> when `--prune` is passed.

> [!IMPORTANT]
> Prune is **ownership-scoped**. configarr records which resources it manages in a
> state file (`.configarr-state.json`, written next to your config after each apply)
> and only prunes resources it created that the config has since dropped — a custom
> format you made by hand is never deleted. On the very first apply the state is
> empty, so prune deletes nothing until configarr has recorded what it manages.
> Commit or ignore the state file as you see fit.
>
> The state also records each managed resource's service id, which makes matching
> **rename-tolerant**: if a resource configarr created (a custom format, indexer,
> download client, or notification) is renamed on the server, configarr recognizes
> it by that id and renames it back to match your config, instead of leaving the
> rename or creating a confusing duplicate.

> [!TIP]
> `--check` is not the same as `--plan`. `--plan` **contacts every service** to
> fetch current state and show a diff; `--check` contacts **nothing** — it only
> confirms the config parses, the models validate, and any TRaSH imports resolve.
> Use `--check` in CI to catch a broken config without needing reachable instances.

> [!TIP]
> **Editor autocomplete & validation.** `configarr --print-schema > configarr.schema.json`
> writes a JSON Schema for your config. Point your editor at it — e.g. with the YAML
> language server, add a first line to `configarr.yml`:
> `# yaml-language-server: $schema=./configarr.schema.json` — to get autocomplete of
> section keys and red squiggles on typos as you type. The same section-key check
> runs at load time: an unrecognized key is warned about (it's the usual cause of an
> edit that silently does nothing), and `--strict` turns that warning into an error.

## Examples

```bash
# Default: apply every change in ./configarr.yml
configarr

# Explicit config path
configarr --config /etc/configarr/configarr.yml

# Preview everything, write nothing
configarr --plan

# Validate the config in CI without any reachable instance
configarr --check

# Generate a JSON Schema for editor autocomplete/validation
configarr --print-schema > configarr.schema.json

# Only Radarr
configarr --service radarr

# Only the "uhd" Radarr instance
configarr --service radarr --instance uhd

# Preview, then include deletions
configarr --plan --prune

# Machine-readable diff for CI
configarr --plan --output json
```

## Exit codes

configarr's exit status is meaningful, which makes it safe to gate CI or a
scheduled job on it:

| Code | Meaning |
|---|---|
| `0` | Success — the plan/apply completed. |
| `1` | Config file missing, invalid YAML, a validation/config error, a TRaSH import error, or an apply error. |
| `2` | Bad scope: a `--service` with no configured instances, or an `--instance` name not found in scope. |

> [!TIP]
> The `2` vs `0` distinction matters: a mistyped `--service`/`--instance` exits `2`
> instead of silently doing nothing and exiting `0`, so a typo in automation fails
> loudly.

## Output

- **`--plan`** prints, per changed resource, an operation — `create`, `update`, or
  `delete` — with field-level `before -> after` lines for updates. Resources that
  are `unchanged` are not shown. With `--output json` the same diff is emitted as a
  stable JSON document (see [Plan, Apply & Scoping](../concepts/dry-run-and-scoping.md#machine-readable-plan-output-json)).
- **Apply** (the default) prints one line per provider that changed —
  `"<service>/<instance> — <label>: applied N change(s)"` — or `"No changes to
  apply."` when everything already matched. A write the API rejects stops the run
  (exit `1`); the error names where it aborted and lists the changes already applied
  before the failure (apply is not atomic).

The result vocabulary is explained in the
[Mental Model](../concepts/mental-model.md#idempotency-and-the-result-vocabulary).
