# Bookshelf

[Bookshelf](https://github.com/pennydreadful/bookshelf) is a maintained revival of
Readarr. configarr manages its custom formats, quality profiles, **metadata
profiles**, root folders, naming, delay profiles and download clients. Path prefix:
`bookshelf.instances.<name>`.

Bookshelf speaks the Readarr API on `/api/v1`, one version below Radarr/Sonarr, so
configarr reuses the Radarr/Sonarr providers pointed at that path. The YAML reads
like a [Radarr/Sonarr](radarr-sonarr.md) instance with one extra section.

> [!NOTE]
> Exact keys and defaults: the
> [Bookshelf section of the schema](../reference/schema.md#bookshelf).

## Connect

```yaml
bookshelf:
  instances:
    main:
      base_url: http://localhost:8787
      api_key: ${BOOKSHELF_API_KEY}
```

## Profiles

Quality profiles work as in Radarr/Sonarr, but the qualities are book formats
(`EPUB`, `AZW3`, `MOBI`, `PDF`, `MP3`, `M4B`, `FLAC`, …). Always set
`upgrade_until_quality`: the `WEBDL-1080p` default does not exist in Bookshelf.

Metadata profiles decide which of an author's books Bookshelf brings in.
`allowed_languages` is a list of ISO 639 codes.

```yaml
profiles:
  quality_profiles:
    definitions:
      eBook:
        upgrade_until_quality: EPUB
        qualities: [EPUB, AZW3, MOBI]
  metadata_profiles:
    definitions:
      Standard:
        min_popularity: 0
        allowed_languages: [spa, eng]
        skip_missing_isbn: false
```

Metadata profiles are pruned under `--prune` like custom formats, except the
built-in `None` profile, which is never touched. Bookshelf refuses to delete a
profile that an author, import list or root folder still uses; configarr reports
which profile and why.

## Root folders

A Bookshelf root folder carries the defaults for authors added under it. Reference
the profiles **by name**; configarr resolves them to ids, and syncs both profile
kinds before root folders, so a profile created in the same run works. Changing a
default updates the folder in place.

```yaml
settings:
  root_folders:
    - name: Libros
      path: /hdd/books
      default_quality_profile: eBook
      default_metadata_profile: Standard
      default_monitor: all            # all, future, missing, existing, latest, first, none
      default_new_item_monitor: all   # all, none, new
```

## Naming

```yaml
settings:
  media_management:
    rename_books: true
    colon_replacement: smart
    author_folder_format: "{Author Name}"
```

## Download clients

Same as Radarr/Sonarr. Readarr inherited Lidarr's field names, so the category
field is `musicCategory`:

```yaml
download_clients:
  definitions:
    SABnzbd:
      implementation: Sabnzbd
      settings:
        host: sabnzbd
        apiKey: ${SABNZBD_API_KEY}
        musicCategory: books
```

## Prowlarr

Prowlarr syncs indexers to Bookshelf through its `Readarr` application:

```yaml
prowlarr:
  instances:
    main:
      applications:
        definitions:
          Bookshelf:
            implementation: Readarr
            settings:
              prowlarrUrl: http://prowlarr:9696
              baseUrl: http://bookshelf:8787
              apiKey: ${BOOKSHELF_API_KEY}
```

## Not supported

- **TRaSH-Guides import**: TRaSH publishes nothing for Readarr, so a `trash:` block
  on a Bookshelf instance is a configuration error.
- Release profiles, quality definitions, notifications and import lists are not
  managed yet: their Readarr fields differ from what the shared providers compare.
