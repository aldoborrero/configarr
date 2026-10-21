# Kapowarr

configarr manages a [Kapowarr](https://github.com/Casvt/Kapowarr) instance under
`kapowarr.instances.<name>`: its **settings**, **root folders**, the external
**download clients** (torrent clients) it hands downloads to, and the
**credentials** for direct-download services (see
[Sync Order](../concepts/sync-order.md) for the order they run in). Checked
against Kapowarr 1.3.2. The exact keys are in the
[schema reference](../reference/schema.md#kapowarr).

## Connect

Use the API key from Kapowarr's **Settings → General** page. Kapowarr only
accepts it as an `api_key` query parameter, so configarr sends it that way;
configarr's own error messages never print the URL.

```yaml
kapowarr:
  instances:
    main:
      base_url: http://kapowarr:5656
      api_key: ${KAPOWARR_API_KEY}
```

If Kapowarr runs under a URL base, include it in `base_url`.

## Settings

`settings` takes Kapowarr's own setting names (the keys `GET /api/settings`
returns). Kapowarr's API saves settings partially, so configarr sends only the
keys that changed and leaves everything else alone.

```yaml
settings:
  comicvine_api_key: ${COMICVINE_API_KEY}
  flaresolverr_base_url: http://flaresolverr:8191
  download_folder: /downloads
  rename_downloaded_files: true
  format_preference: [CBZ]
```

Values compare the way Kapowarr stores them: a folder with or without its
trailing `/` is the same folder, and `flaresolverr_base_url` matches with or
without a trailing slash. A setting Kapowarr does not know is skipped with a
warning. `api_key` cannot be set this way, and Kapowarr checks some values
before it saves them: folders must exist in the container, the ComicVine key
must work, and FlareSolverr must be reachable.

> [!WARNING]
> Changing `host`, `port` or `url_base` restarts Kapowarr's web server, and so
> does changing a proxy setting.

`comicvine_api_key` comes back in clear text and is compared by fingerprint, so
a plan shows that it changed without printing it. `auth_username`,
`auth_password` and `proxy_password` come back masked, so configarr cannot tell
when they change. They are sent whenever another setting changes, but a change
to one of them alone never shows up in a plan.

## Root folders

A list of paths, as for Radarr/Sonarr. Each folder must exist inside the
Kapowarr container and may not sit inside the download folder or another root
folder.

```yaml
root_folders:
  - path: /comics
```

## Download clients

These are Kapowarr's external clients, keyed by title. `client_type` is
`Transmission` or `qBittorrent` (case-insensitive). A new client needs
`client_type` and `base_url`, and the type cannot change later.

```yaml
download_clients:
  Transmission:
    client_type: Transmission
    base_url: http://transmission:9091
    username: ${TRANSMISSION_USERNAME}
    password: ${TRANSMISSION_PASSWORD}
```

Kapowarr connects to the client on every create and update and refuses the save
if the connection fails. It also refuses to update or delete a client that
still has downloads in the queue. Passwords come back in clear text and are
compared by fingerprint, so a changed password shows up in a plan without being
printed.

## Credentials

Logins for the direct-download services, keyed by source: `mega` takes `email`
and `password`, `pixeldrain` takes `api_key`.

```yaml
credentials:
  mega:
    email: ${MEGA_EMAIL}
    password: ${MEGA_PASSWORD}
  pixeldrain:
    api_key: ${PIXELDRAIN_API_KEY}
```

Kapowarr's API cannot edit a credential, so a change creates the new one first
and then deletes the old one. If Kapowarr rejects the new login, the old one
stays. Mega passwords come back masked, so changing only the password does not
show up in a plan. Kapowarr allows several credentials per source, but configarr
manages one per source and stops with an error if the server already has two
for the same source.

Root folders, download clients and credentials that are not in the config are
left alone unless you run with `--prune`.
