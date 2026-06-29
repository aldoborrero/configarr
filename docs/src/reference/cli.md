# Command Line

configarr is a single command. Everything it does is driven by `configarr.yml`;
the flags only control **what** is processed and **how much** it logs.

```text
configarr [OPTIONS]
```

## Options

| Flag | Argument | Description |
|---|---|---|
| `--config` | `PATH` | Path to the config file. Default: `./configarr.yml` (the current directory). |
| `--service` | `NAME` | Only process one service: `radarr`, `sonarr`, `prowlarr`, `bazarr`, or `sabnzbd`. |
| `--instance` | `NAME` | Only process the instance with this label. Combine with `--service` to disambiguate. |
| `--dry-run` | — | Simulate **Bazarr only**. The other four services are skipped (they are not dry-run-aware). |
| `--verbose` | — | Log full request payloads (**Bazarr-only**). |
| `--debug` | — | Verbose debug logging for the whole run. Does **not** prevent writes. |

> [!WARNING]
> `--dry-run` and `--verbose` affect Bazarr only. For Radarr/Sonarr/Prowlarr/SABnzbd,
> the only blast-radius control is `--service` / `--instance`. See
> [Dry-Run & Scoping](../concepts/dry-run-and-scoping.md).

## Examples

```bash
# Default: process every service in ./configarr.yml
configarr

# Explicit config path
configarr --config /etc/configarr/configarr.yml

# Only Radarr
configarr --service radarr

# Only the "uhd" Radarr instance
configarr --service radarr --instance uhd

# Preview Bazarr changes
configarr --service bazarr --dry-run --verbose
```

## Exit codes

configarr's exit status is meaningful, which makes it safe to gate CI or a
scheduled job on it:

| Code | Meaning |
|---|---|
| `0` | All operations completed successfully. |
| `1` | At least one resource `FAILED`, or the config could not be loaded (missing file, invalid YAML, validation error). |
| `2` | Bad scope: a `--service` with no configured instances, or an `--instance` name not found in scope. |

> [!TIP]
> The `2` vs `0` distinction matters: a mistyped `--service`/`--instance` exits `2`
> instead of silently doing nothing and exiting `0`, so a typo in automation fails
> loudly.

## Output

For each instance, configarr prints a header, then one section per resource type
with a result per item — `CREATED` / `UPDATED` / `UNCHANGED` / `FAILED` — and ends
with a summary of total successes and failures. The meaning of each result is
covered in the [Mental Model](../concepts/mental-model.md#idempotency-and-the-result-vocabulary).
