# Troubleshooting

A field guide to the things that actually go wrong, and what they mean.

## A resource I configured never appears

configarr does **not** error on unrecognised keys — it silently ignores them. If a
resource never shows up in the output, it was almost certainly filed under a
**wrong or misspelled key**, or at the wrong nesting level.

- Check the exact key, nesting, and `.definitions` wrapper against the
  [Configuration Schema](reference/schema.md).
- Remember that **configarr keys are not *arr API keys** — don't copy field names
  from the native API docs. See
  [Mental Model](concepts/mental-model.md#yaml-keys-are-not-arr-api-keys).
- The same applies inside `settings:` passthrough maps: an unknown field name is
  matched against the live API schema and dropped if it doesn't exist.

## Literal `${VAR}` in output

If a URL or key shows up as the literal string `${SOMETHING}`, the variable was
**not set**. configarr leaves unresolved references untouched rather than failing,
so this usually surfaces later as an **authentication failure**.

- Confirm the variable is exported, or present in a `.env` **next to the config**.
- Remember process environment variables override `.env`.
- See [Secrets & Environment](concepts/secrets-and-env.md).

## `FAILED` results

A `FAILED` line means the application's API rejected the operation. Common causes:

- **Missing `implementation`.** Download clients, notifications, indexers, and
  applications all require `implementation`; omitting it fails the resource. An
  unknown implementation value also fails.
- **Bad credentials / unreachable host.** Check `base_url` and `api_key`, and that
  the address is reachable from where configarr runs (see the container note
  below).
- **Invalid enum value.** For example, a Prowlarr application `sync_level` that
  isn't a valid value raises.

Re-run with `--debug` for more detail.

## Config won't load at all

These exit with status `1` before any sync runs:

- **File not found** — the path passed to `--config` (default `./configarr.yml`)
  doesn't exist.
- **Invalid YAML** — a syntax error; the message points at the location.
- **Validation error** — most often a missing `base_url` or `api_key` (both are
  required on every instance), or a `root_folders` entry written as a bare string
  instead of `{path: ...}`.

## `--service` or `--instance` does nothing / exits 2

Exit code `2` means the scope didn't match anything: a `--service` with no
configured instances, or an `--instance` label that doesn't exist in scope. Check
the spelling against your file. (This is deliberate — a typo fails loudly instead
of silently no-opping.)

## `--dry-run` changed something / skipped everything

`--dry-run` only simulates **Bazarr**. The other four services are **skipped** under
`--dry-run`, so:

- If you expected Radarr/Sonarr/Prowlarr/SABnzbd to be previewed, they weren't —
  there is no dry-run for them.
- For those services, scope tightly with `--service` / `--instance` and read the
  `CREATED`/`UPDATED` results instead. See
  [Dry-Run & Scoping](concepts/dry-run-and-scoping.md).

## A SABnzbd server silently disappeared

A SABnzbd server with no `host` is **dropped** (null values are filtered out before
sending). Make sure every server entry has a `host`.

## SABnzbd always says CREATED/UPDATED, never UNCHANGED

That's expected. SABnzbd servers and categories always write, so they never report
`UNCHANGED` even when nothing changed. Only misc settings can report `UNCHANGED`.
See [SABnzbd](services/sabnzbd.md#always-write-behaviour).

## I can't reach my apps from inside Docker

Inside a container, `http://localhost:PORT` is the container itself, not your host
or other containers. Use a Docker network alias (`http://sonarr:8989`), the host
gateway (`host.docker.internal` with `--add-host`), or a LAN IP. See
[Installation](getting-started/installation.md#run-with-docker).
