# Mental Model

Understanding a few core ideas up front will save you surprises. configarr is
small and predictable once you know how it thinks.

## One file describes desired state

You write a single `configarr.yml`. It is organised as:

```text
<service>:
  instances:
    <name>:
      base_url: ...
      api_key: ...
      <resources...>
```

- `<service>` is one of `radarr`, `sonarr`, `prowlarr`, `bazarr`, `sabnzbd`.
- `<name>` is an arbitrary label you choose (`main`, `uhd`, `4k`, …). It only has
  to be unique within that service.
- `base_url` and `api_key` are **required on every instance**.

configarr connects to each instance's HTTP API and reconciles the live config
toward what you wrote.

## YAML keys are not *arr API keys

This is the single most important thing to internalise:

> [!CAUTION]
> **Don't guess keys from the *arr API docs**
>
> configarr reshapes and renames keys before sending them. For example, a quality
> profile's `upgrades_allowed` becomes the API's `upgrade.allowed`, and
> `minimum_custom_format_score` becomes `minFormatScore`. The keys you write are the
> **configarr keys** documented in the [Configuration Schema](../reference/schema.md),
> not the native Sonarr/Radarr/Prowlarr/Bazarr field names. Guessing from the API
> will silently not work.

When in doubt, open the [schema reference](../reference/schema.md) for the exact
key, nesting, type, and default.

## Add and update, not mirror

configarr is declarative but it is **not a full two-way diff engine**:

- It **creates** resources you declare that don't exist yet.
- It **updates** resources you declare that do exist.
- With documented exceptions, it does **not delete** resources you remove from the
  file. Removing a download client from `configarr.yml` does not remove it from
  Radarr.

So your config is the source of truth for the **keys it manages**, not a mirror of
the application's entire state. A couple of resources have stronger, documented
semantics — for instance, Bazarr **language profiles you list are rebuilt and
overwrite** the server copy, while profiles you don't list are left untouched.
Those cases are called out in the [service guides](../services/bazarr.md) and the
[schema](../reference/schema.md).

## Idempotency and the result vocabulary

configarr diffs desired state against the live service, so `--plan` reports one
operation per changed resource:

| Op | Meaning |
|---|---|
| `create` | Did not exist; configarr will create it. |
| `update` | Exists but differs; configarr will write the changed fields (shown as `before -> after`). |
| `delete` | Exists on the server but is absent from config — only with `--prune`. |
| `unchanged` | Exists and already matches. Not shown in the plan. |

Most resources are idempotent — running twice is safe and the second `--plan` is
empty. Apply (the default) writes only the resources that differ and prints one
line per provider that changed:
`"<service>/<instance> — <label>: applied N change(s)"`, or `"No changes to
apply."`.

There is **no** `FAILED` status. If the API rejects a write, that write **raises**,
the run stops (exit `1`), and the error names where it aborted and lists the changes
already applied before the failure — it does not keep going resource by resource.

> [!NOTE]
> A failed apply, a bad config, or a TRaSH import error all exit non-zero, which is
> what you want in CI. See [Command Line](../reference/cli.md#exit-codes).

## Unknown keys are silently ignored

configarr does **not** error on unrecognised keys. A resource that never shows up
in the results was most likely filed under a wrong or misspelled key — check it
against the [schema](../reference/schema.md). This is the most common "it didn't
do anything" cause. (`settings:` passthrough maps behave the same way: unknown
field names are matched against the live API schema and dropped if they don't
exist.)

## Multiple instances

Every service supports any number of instances. A common setup is a 1080p and a
4K Radarr:

```yaml
radarr:
  instances:
    main:
      base_url: http://localhost:7878
      api_key: ${RADARR_API_KEY}
    uhd:
      base_url: http://localhost:7879
      api_key: ${RADARR_4K_API_KEY}
```

Both are processed in one run. You can narrow a run to one service or instance —
see [Dry-Run & Scoping](dry-run-and-scoping.md).

## What's next

- The order things happen in — and why it matters:
  [Sync Order](sync-order.md).
- Keeping secrets out of the file: [Secrets & Environment](secrets-and-env.md).
- Limiting what a run touches: [Dry-Run & Scoping](dry-run-and-scoping.md).
