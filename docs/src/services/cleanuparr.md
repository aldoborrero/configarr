# Cleanuparr

configarr manages a [Cleanuparr](https://github.com/Cleanuparr/Cleanuparr) instance
under `cleanuparr.instances.<name>`: its **settings sections** (general, queue
cleaner, download cleaner, malware blocker), its **download clients** and the
**\*arr instances** it cleans for (see [Sync Order](../concepts/sync-order.md) for
the order they run in).

Write keys in snake_case; configarr maps them onto Cleanuparr's camelCase API
fields (`failed_import.max_strikes` → `failedImport.maxStrikes`). Enum values can be
any case — `exclude` and `Exclude` are the same setting. The exact keys are in the
[schema reference](../reference/schema.md#cleanuparr).

## Connect

Cleanuparr requires authentication. Use the API key from its **Account** page; it is
sent as `X-Api-Key`.

```yaml
cleanuparr:
  instances:
    main:
      base_url: http://cleanuparr:11011
      api_key: ${CLEANUPARR_API_KEY}
```

## Settings sections

`general`, `queue_cleaner`, `download_cleaner` and `malware_blocker` mirror
Cleanuparr's own settings objects. Set only what you care about: Cleanuparr's API
replaces a whole section on every save, so configarr reads the current section,
overlays your keys and writes it back — everything you did not set keeps its
value. A plan lists each change as a dotted path, e.g.
`failedImport.maxStrikes: 0 -> 3`.

```yaml
general:
  dry_run: false
queue_cleaner:
  enabled: true
  failed_import:
    max_strikes: 3
download_cleaner:
  enabled: false
malware_blocker:
  enabled: true
  sonarr:
    enabled: true
```

Per-client download-cleaner settings live on the client itself — see
[Download clients](#download-clients).

## Download clients

Keyed by name. `type` is required when creating a client and cannot change later
(Cleanuparr locks it). Usenet support (`sabnzbd`) needs Cleanuparr 2.10.10 or later.

```yaml
download_clients:
  Transmission:
    type: transmission
    host: http://transmission:9091
    url_base: /transmission/
  SABnzbd:
    type: sabnzbd
    host: http://sabnzbd:8080
    api_key: ${SABNZBD_API_KEY}
```

### Per-client cleanup

Each download client can also carry its own download-cleaner settings:
`orphaned_files` (move files no job or \*arr claims into a quarantine folder),
`unlinked`, `dead_torrent`, and `seeding_rules` (when to remove finished torrents).
What a client supports depends on its type — SABnzbd only has `orphaned_files` —
and configarr rejects an unsupported one before touching anything.

```yaml
download_clients:
  Transmission:
    type: transmission
    host: http://transmission:9091
    seeding_rules:
      cleanup-imported-public:
        categories: [sonarr, radarr]
        privacy_type: both
        max_ratio: 1
        max_seed_time: 48 # hours
  SABnzbd:
    type: sabnzbd
    host: http://sabnzbd:8080
    api_key: ${SABNZBD_API_KEY}
    orphaned_files:
      enabled: true
      scan_directories: [/media/downloads/complete]
      orphaned_directory: /media/downloads/orphaned
      min_file_age_hours: 48
      purge_after_hours: 168
```

With `--prune`, seeding rules not listed are deleted — but only on clients that
declare `seeding_rules`; leave the key out to keep a client's rules untouched.

## \*arr instances

Group instances by arr type under `arr:`. A new instance needs `url`, `api_key`
and `version` (the major version, which picks Cleanuparr's API client).
`failed_import_max_strikes` is the per-arr strike limit (`-1` falls back to the
queue cleaner's).

```yaml
arr:
  sonarr:
    instances:
      Sonarr:
        url: http://sonarr:8989
        api_key: ${SONARR_API_KEY}
        version: 4
  radarr:
    failed_import_max_strikes: 3
    instances:
      Radarr:
        url: http://radarr:7878
        api_key: ${RADARR_API_KEY}
        version: 6
```

Download clients and \*arr instances not in the config are left alone unless you
run with `--prune`.

> [!WARNING]
> Cleanuparr never returns secrets (they come back as `••••••••`), so configarr
> cannot tell whether an `api_key` or `password` changed. It sends the configured
> secret whenever that client or instance is created or updated, but a changed
> secret on its own does not appear in a plan.
