# Kavita

configarr manages a [Kavita](https://www.kavitareader.com) instance under
`kavita.instances.<name>`: its **server settings** (including OIDC single sign-on
and SMTP) and its **libraries**. Libraries run before settings (see
[Sync Order](../concepts/sync-order.md)), so a setting can name a library created
in the same run.

Write keys in snake_case; configarr maps them onto Kavita's camelCase API fields
(`enable_folder_watching` → `enableFolderWatching`). Enums are written by name
(`type: light_novel`, `encode_media_as: webp`) in any case. The exact keys are in
the [schema reference](../reference/schema.md#kavita).

## Connect

Kavita has no API-key header. `api_key` is a Kavita **auth key** (from an admin's
account settings). configarr exchanges it for a session token with
`POST /api/plugin/authenticate` at the start of each run and sends that token as
`Authorization: Bearer …`. Use an admin's key: only admins can read and write
server settings, and libraries are listed per user.

```yaml
kavita:
  instances:
    main:
      base_url: https://kavita.example.com
      api_key: ${KAVITA_API_KEY}
```

## Server settings

`settings` mirrors Kavita's server settings. Kavita's API replaces the whole
settings object on every save, so configarr reads the current settings, overlays
your keys and writes it all back; everything you did not set keeps its value. A
plan lists each change as a dotted path, e.g. `oidcConfig.providerName`.

```yaml
settings:
  host_name: https://kavita.example.com
  logging_level: Information
  enable_opds: true
  enable_folder_watching: true
  oidc:
    authority: https://auth.example.com
    client_id: "kavita"
    secret: ${KAVITA_OIDC_SECRET}
    provision_accounts: true
    default_roles: [Login, Bookmark, Download, Change Password]
    default_libraries: [Libros]
    provider_name: Zitadel
  smtp:
    host: smtp.example.com
    port: 587
    password: ${KAVITA_SMTP_PASSWORD}
```

`oidc.default_libraries` takes library names (or ids). `oidc.enabled` can't be
set: Kavita derives it from `authority`, so OIDC is on whenever an authority is
set. To turn it off, set `authority: ""`.

> [!WARNING]
> Kavita builds its OIDC login handler only at startup. When a plan changes the
> OIDC `authority`, `client_id`, `secret` or `custom_scopes`, configarr warns that
> **Kavita must be restarted** after the apply. configarr itself never restarts
> it. A new `authority` also unlinks every user's existing OIDC login.

> [!NOTE]
> Kavita returns the OIDC secret masked, one `*` per character. configarr sends
> the configured secret, but a plan can only compare its **length**, so a rotated
> secret of the same length doesn't show up as a change. The SMTP password is
> compared by fingerprint. Neither value ever appears in a plan.

## Libraries

A list of libraries keyed by `name`. A new library needs `type` (`manga`, `comic`,
`comic_vine`, `book`, `image`, `light_novel`) and `folders`. Anything else you
leave out starts from the defaults Kavita's own dialog uses, including the file
types and metadata provider that fit the type. Changing an existing library's
`type` or folders makes Kavita rescan it.

```yaml
libraries:
  - name: Libros
    type: book
    folders: [/books]
    folder_watching: true
  - name: Manga
    type: manga
    folders: [/data/manga]
    file_group_types: [archive, images]
    exclude_patterns: ["**/@eaDir/**"]
```

Libraries not in the config are left alone unless you run with `--prune`.

> [!WARNING]
> Pruning a library deletes it and all of its series from Kavita's database,
> including reading progress tied to them. The files on disk are not touched.

Per-user library access and users themselves are not managed.
