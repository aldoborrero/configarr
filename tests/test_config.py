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
