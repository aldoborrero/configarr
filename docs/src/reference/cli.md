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
| `--prune` | — | Also delete unmanaged resources (present on the server, absent from config) for providers that support deletion. Additive by default; combine with `--plan` to preview deletions first. |
| `--output` | `text\|json` | Output format for `--plan`. `json` emits a machine-readable diff for CI. Default: `text`. |
| `--debug` | — | Verbose debug logging for the whole run. Does **not** prevent writes. |

Apply is the **default** — running with no flag writes the changes.

> [!NOTE]
> `--plan` / `--dry-run` is **universal**: it previews every service and writes
> nothing. There is no per-service dry-run and there is no `--verbose` flag. The
> only way to narrow a run is `--service` / `--instance`. See
> [Plan, Apply & Scoping](../concepts/dry-run-and-scoping.md).

> [!NOTE]
> `--prune` currently affects only custom formats — the one provider that supports
> deletion today. Other providers stay additive even when `--prune` is passed.

## Examples

```bash
# Default: apply every change in ./configarr.yml
configarr

# Explicit config path
configarr --config /etc/configarr/configarr.yml

# Preview everything, write nothing
configarr --plan

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
