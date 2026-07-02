"""The resolved config must be indistinguishable from a hand-written one — feed an
imported custom format through the real CustomFormatProvider and assert it builds the
exact API shape (fields as a [{name, value}] list, schema defaults merged)."""

import responses

from configarr.models import ArrServiceConfig, ConfigarrConfig, TrashConfig
from configarr.providers.custom_formats import CustomFormatProvider
from configarr.trash import resolve_trash

BASE = "http://r.test"
SCHEMA = [
    {
        "name": "Release Title",
        "implementation": "ReleaseTitleSpecification",
        "negate": False,
        "required": False,
        "fields": [{"name": "value", "value": ""}],
    }
]


@responses.activate
def test_resolved_custom_format_builds_valid_api_shape(guide_root):
    inst = ArrServiceConfig(
        name="movies",
        base_url=BASE,
        api_key="k",
        trash=TrashConfig(
            source="local",
            path=str(guide_root),
            custom_formats=[{"trash_ids": ["aaa111"]}],
        ),
    )
    resolve_trash(ConfigarrConfig(radarr=[inst]), guide_root.parent)

    responses.get(f"{BASE}/api/v3/customformat/schema", json=SCHEMA)
    provider = CustomFormatProvider(
        inst.base_url, inst.api_key, inst.custom_formats, "radarr.custom_format"
    )
    built = {cf["name"]: cf for cf in provider.build_desired()}

    hdr = built["HDR10"]
    assert hdr["includeCustomFormatWhenRenaming"] is False
    # The imported {value: ...} dict became the API's [{name, value}] list, merged
    # over the schema default for that implementation.
    assert hdr["specifications"][0]["fields"] == [
        {"name": "value", "value": "\\bHDR10\\b"}
    ]
