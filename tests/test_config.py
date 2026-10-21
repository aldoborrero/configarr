from configarr.config import _PARSERS, parse_config
from configarr.models import ConfigarrConfig
from configarr.schema import SERVICE_NAMES


def test_service_wiring_stays_in_lockstep():
    # Every service is defined once (schema.SERVICE_NAMES) and everything that
    # enumerates services derives from it. This guards the drift that let a service
    # be added to some spots but missed in others (e.g. the scope-validation dict).
    names = set(SERVICE_NAMES)
    assert set(_PARSERS) == names, "a service has no parser (or vice versa)"
    assert set(ConfigarrConfig.model_fields) == names, "model fields != service names"


def _write(directory, body):
    p = directory / "configarr.yml"
    p.write_text(body)
    return p


def test_parse_config_carries_bazarr_subsync_and_translator(tmp_path):
    # Regression: parse_bazarr_instance previously mapped only
    # general/sonarr/radarr/providers/language_profiles, silently dropping the
    # subsync and translator sections so they never reached the plan.
    _write(
        tmp_path,
        """
bazarr:
  instances:
    subs:
      base_url: http://bazarr.test
      api_key: k
      subsync:
        use_subsync: true
      translator:
        translator_type: lingarr
        lingarr_url: http://lingarr.test:9876
""",
    )

    config = parse_config(tmp_path / "configarr.yml")

    inst = config.bazarr[0]
    assert inst.subsync == {"use_subsync": True}
    assert inst.translator == {
        "translator_type": "lingarr",
        "lingarr_url": "http://lingarr.test:9876",
    }


def test_parse_config_carries_lingarr_sections(tmp_path):
    _write(
        tmp_path,
        """
lingarr:
  instances:
    main:
      base_url: http://lingarr.test:9876
      translation:
        service_type: localai
      integration:
        sonarr_url: http://sonarr.test:8989
""",
    )

    config = parse_config(tmp_path / "configarr.yml")

    inst = config.lingarr[0]
    assert inst.api_key == ""  # optional — AUTH_ENABLED=false
    assert inst.translation == {"service_type": "localai"}
    assert inst.integration == {"sonarr_url": "http://sonarr.test:8989"}


def test_parse_config_carries_cleanuparr_sections(tmp_path):
    _write(
        tmp_path,
        """
cleanuparr:
  instances:
    main:
      base_url: http://cleanuparr.test:11011/
      api_key: k
      queue_cleaner:
        enabled: true
      download_clients:
        SABnzbd:
          type: sabnzbd
      arr:
        sonarr:
          failed_import_max_strikes: 3
""",
    )

    config = parse_config(tmp_path / "configarr.yml")

    inst = config.cleanuparr[0]
    assert inst.base_url == "http://cleanuparr.test:11011"
    assert inst.queue_cleaner == {"enabled": True}
    assert inst.download_clients == {"SABnzbd": {"type": "sabnzbd"}}
    assert inst.arr == {"sonarr": {"failed_import_max_strikes": 3}}
    assert inst.general is None


def test_parse_config_carries_kavita_settings_and_libraries(tmp_path):
    _write(
        tmp_path,
        """
kavita:
  instances:
    main:
      base_url: https://kavita.test/
      api_key: k
      settings:
        enable_opds: true
        oidc:
          provider_name: Zitadel
      libraries:
        - name: Libros
          type: book
          folders: [/data/books]
""",
    )

    config = parse_config(tmp_path / "configarr.yml")

    inst = config.kavita[0]
    assert inst.base_url == "https://kavita.test"
    assert inst.settings == {"enable_opds": True, "oidc": {"provider_name": "Zitadel"}}
    assert inst.libraries == [
        {"name": "Libros", "type": "book", "folders": ["/data/books"]}
    ]


def test_parse_config_carries_kapowarr_sections(tmp_path):
    _write(
        tmp_path,
        """
kapowarr:
  instances:
    main:
      base_url: http://kapowarr.test:5656/
      api_key: k
      settings:
        flaresolverr_base_url: http://flaresolverr:8191
      root_folders:
        - path: /comics
      download_clients:
        Transmission:
          client_type: Transmission
          base_url: http://transmission:9091
      credentials:
        pixeldrain:
          api_key: pd
""",
    )

    config = parse_config(tmp_path / "configarr.yml")

    inst = config.kapowarr[0]
    assert inst.base_url == "http://kapowarr.test:5656"
    assert inst.settings == {"flaresolverr_base_url": "http://flaresolverr:8191"}
    assert inst.root_folders == [{"path": "/comics"}]
    assert inst.download_clients == {
        "Transmission": {
            "client_type": "Transmission",
            "base_url": "http://transmission:9091",
        }
    }
    assert inst.credentials == {"pixeldrain": {"api_key": "pd"}}


def test_parse_config_carries_tranga_sections(tmp_path):
    _write(
        tmp_path,
        """
tranga:
  instances:
    main:
      base_url: https://api.tranga.test/
      settings:
        download_language: es
      file_libraries:
        Manga:
          base_path: /Manga
      library_connectors:
        - type: kavita
          base_url: http://kavita:5000
          api_key: k
""",
    )

    config = parse_config(tmp_path / "configarr.yml")

    inst = config.tranga[0]
    assert inst.base_url == "https://api.tranga.test"
    assert inst.api_key == ""  # optional — Tranga's API has no auth
    assert inst.settings == {"download_language": "es"}
    assert inst.file_libraries == {"Manga": {"base_path": "/Manga"}}
    assert inst.library_connectors == [
        {"type": "kavita", "base_url": "http://kavita:5000", "api_key": "k"}
    ]
    assert inst.notification_connectors == {}
