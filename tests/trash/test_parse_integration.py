import textwrap

from configarr.config import parse_config
from configarr.models import TrashConfig


def test_parse_config_carries_and_validates_trash_block(tmp_path, guide_root):
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(
        textwrap.dedent(f"""
        radarr:
          instances:
            movies:
              base_url: http://r.test
              api_key: k
              trash:
                source: local
                path: "{guide_root}"
                quality_definition: movie
                custom_formats:
                  - trash_ids: [aaa111]
                    assign_scores_to:
                      - profile: HD
        """)
    )
    config = parse_config(cfg)
    inst = config.radarr[0]
    assert isinstance(inst.trash, TrashConfig)
    assert inst.trash.quality_definition == "movie"
    assert inst.trash.custom_formats[0].trash_ids == ["aaa111"]
    assert inst.trash.custom_formats[0].assign_scores_to[0].profile == "HD"
    # parse_config is pure: nothing is resolved/imported yet.
    assert inst.custom_formats == {}
    assert inst.quality_definitions is None


def test_no_trash_block_is_none(tmp_path):
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(
        "radarr:\n  instances:\n    movies:\n"
        "      base_url: http://r.test\n      api_key: k\n"
    )
    config = parse_config(cfg)
    assert config.radarr[0].trash is None


def test_trash_block_rejects_unknown_keys(tmp_path):
    # The trash models are strict (extra="forbid") so a typo is a hard error, not a
    # silently-dropped key like the passthrough sections elsewhere.
    import pytest
    from pydantic import ValidationError

    cfg = tmp_path / "configarr.yml"
    cfg.write_text(
        "radarr:\n  instances:\n    movies:\n"
        "      base_url: http://r.test\n      api_key: k\n"
        "      trash:\n        source: local\n        path: /x\n"
        "        custom_formats:\n"
        "          - trash_id: [aaa]\n"  # typo: should be trash_ids
    )
    with pytest.raises(ValidationError):
        parse_config(cfg)
