from configarr.config import parse_config


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
