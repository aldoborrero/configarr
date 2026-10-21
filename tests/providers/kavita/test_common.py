import pytest
import responses
from responses import matchers

from configarr.providers.kavita.common import (
    LIBRARY_TYPES,
    enum_name,
    enum_value,
    kavita_session,
)

KV = "http://kavita.test"


@responses.activate
def test_auth_key_is_exchanged_once_for_a_bearer_token():
    responses.post(
        f"{KV}/api/plugin/authenticate",
        json={"token": "jwt-1"},
        match=[
            matchers.query_param_matcher({"apiKey": "key", "pluginName": "configarr"})
        ],
    )
    responses.get(
        f"{KV}/api/settings",
        json={},
        match=[matchers.header_matcher({"Authorization": "Bearer jwt-1"})],
    )
    session = kavita_session(KV, "key")
    session.get(f"{KV}/api/settings")
    session.get(f"{KV}/api/settings")
    auth_calls = [c for c in responses.calls if "authenticate" in c.request.url]
    assert len(auth_calls) == 1


@responses.activate
def test_rejected_auth_key_is_a_clear_error():
    responses.post(f"{KV}/api/plugin/authenticate", status=401)
    session = kavita_session(KV, "bad")
    with pytest.raises(ValueError, match="rejected the auth key"):
        session.get(f"{KV}/api/settings")


def test_enum_value_accepts_names_loosely_and_ints():
    assert enum_value(LIBRARY_TYPES, "light_novel", "type") == 4
    assert enum_value(LIBRARY_TYPES, "LightNovel", "type") == 4
    assert enum_value(LIBRARY_TYPES, "Comic Vine", "type") == 5
    assert enum_value(LIBRARY_TYPES, 2, "type") == 2
    with pytest.raises(ValueError, match="unknown type"):
        enum_value(LIBRARY_TYPES, "novel", "type")
    with pytest.raises(ValueError):
        enum_value(LIBRARY_TYPES, 9, "type")
    assert enum_name(LIBRARY_TYPES, 2) == "book"
