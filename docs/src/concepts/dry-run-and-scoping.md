# Dry-Run & Scoping

Before configarr writes to a live setup, it helps to know exactly how much a run
can touch — and how to limit it.

## Scoping a run

Two flags restrict which part of your config is processed:

```bash
configarr --config configarr.yml --service radarr
configarr --config configarr.yml --service radarr --instance uhd
```

- `--service <name>` limits the run to one service (`radarr`, `sonarr`,
  `prowlarr`, `bazarr`, `sabnzbd`).
- `--instance <name>` limits to one instance by its label. Combine with
  `--service` to disambiguate when the same label exists under multiple services.

> [!TIP]
> **Scoping is your main blast-radius control**
>
> For Radarr, Sonarr, Prowlarr, and SABnzbd there is **no true dry-run** (see
> below). `--service` / `--instance` are the practical way to limit what a run can
> change — iterate on one instance at a time.

A typo is caught rather than silently ignored: if you pass a `--service` with no
configured instances, or an `--instance` name that doesn't exist in scope,
configarr exits with status `2` instead of doing nothing and exiting `0`.

## Dry-run is Bazarr-only

> [!CAUTION]
> **--dry-run only simulates Bazarr**
>
> `--dry-run` simulates **Bazarr only**. Under `--dry-run`, Radarr, Sonarr,
> Prowlarr, and SABnzbd are **skipped entirely** — they are not dry-run-aware and
> running them would write to the live API. There is no way to preview changes for
> those four services.

So `--dry-run` answers "what would Bazarr do?" and nothing else. For the other
services, the safe pattern is: scope to one instance, run it, and read the
`CREATED` / `UPDATED` / `UNCHANGED` results.

Note that even under `--dry-run`, Bazarr provider and language-profile sync still
issue **read** (GET) requests to fetch current state; only the mutating writes are
skipped.

## Verbose and debug output

- `--verbose` logs full request payloads — **Bazarr-only**, like `--dry-run`.
- `--debug` enables verbose logging for the whole run. It does **not** prevent
  mutations; it only adds detail.

> [!WARNING]
> Neither `--debug` nor `--verbose` makes a run safe. Only `--dry-run` skips writes,
> and only for Bazarr.

## A safe first-run checklist

1. Start with `--service <one>` and `--instance <one>` to limit scope.
2. Read every result line. `CREATED`/`UPDATED` mean a write happened.
3. Re-run the same scope; healthy idempotent resources flip to `UNCHANGED`.
4. Widen scope once you trust the output.

See [Command Line](../reference/cli.md) for the full flag reference and exit
codes.
