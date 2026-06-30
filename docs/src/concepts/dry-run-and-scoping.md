# Plan, Apply & Scoping

configarr diffs your `configarr.yml` against each service and applies **only what
changed**. You can preview that diff before anything is written, limit which part
of your config a run touches, and opt in to deleting resources the config no
longer declares.

## Plan vs. apply

```bash
# Preview the diff — reads only, writes nothing
configarr --config configarr.yml --plan

# Apply it — creates/updates only what differs
configarr --config configarr.yml
```

- `--plan` (alias `--dry-run`) computes the diff against every service and prints
  it, then exits **without writing**. This is a true, universal preview — it works
  for Radarr, Sonarr, Prowlarr, Bazarr, and SABnzbd alike.
- With no flag, configarr **applies** the plan: it writes only the resources that
  actually differ, so re-running an unchanged config is a no-op.

> [!TIP]
> **Preview, then apply**
>
> `--plan` is the safe way to see exactly what a run will change. Because the
> engine is idempotent, applying a plan and immediately re-planning yields an empty
> plan.

## Scoping a run

Two flags restrict which part of your config is processed:

```bash
configarr --config configarr.yml --plan --service radarr
configarr --config configarr.yml --service radarr --instance uhd
```

- `--service <name>` limits the run to one service (`radarr`, `sonarr`,
  `prowlarr`, `bazarr`, `sabnzbd`).
- `--instance <name>` limits to one instance by its label. Combine with
  `--service` to disambiguate when the same label exists under multiple services.

A typo is caught rather than silently ignored: if you pass a `--service` with no
configured instances, or an `--instance` name that doesn't exist in scope,
configarr exits with status `2` instead of doing nothing and exiting `0`.

## Pruning unmanaged resources

By default sync is **additive** — it never deletes anything. To make the config a
source of truth, opt in with `--prune`:

```bash
# Preview what would be deleted (plus the usual creates/updates)
configarr --config configarr.yml --plan --prune

# Apply, including deletions
configarr --config configarr.yml --prune
```

`--prune` emits `DELETE` for resources present on the server but absent from your
config, for the providers that support deletion. Always preview it with `--plan`
first. Pruning respects `--service` / `--instance`, so you can scope deletions to
one instance.

## Machine-readable plan (`--output json`)

For CI / GitOps drift gating, render the plan as JSON:

```bash
configarr --config configarr.yml --plan --output json
```

stdout is pure JSON (the human chrome is suppressed in this mode):

```json
{
  "has_changes": true,
  "providers": [
    {
      "service": "radarr",
      "instance": "main",
      "kind": "radarr.custom_format",
      "label": "custom formats",
      "resources": [
        { "key": "x265", "op": "create", "field_diffs": [] }
      ]
    }
  ]
}
```

A pipeline can fail on drift by checking `has_changes`:

```bash
configarr --config configarr.yml --plan --output json \
  | jq -e '.has_changes | not' > /dev/null
```

## Debug output

`--debug` enables verbose logging for the whole run. It adds detail; it does
**not** make a run safe — only `--plan` avoids writes.

See [Command Line](../reference/cli.md) for the full flag reference and exit
codes.
