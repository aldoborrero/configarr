from configarr.normalize import (
    fingerprint_secret,
    is_secret_name,
    redact_secret_fields,
)


def test_is_secret_name_matches_common_credential_fields():
    for name in ("password", "apiKey", "api_key", "user_key", "botToken", "cookies"):
        assert is_secret_name(name), name


def test_is_secret_name_ignores_ordinary_fields():
    for name in ("username", "endpoint", "timeout", "use_hash", "port", "seriesType"):
        assert not is_secret_name(name), name


def test_is_secret_name_uses_leaf_segment():
    assert is_secret_name("settings.opensubtitles.password")
    assert not is_secret_name("password.enabled")  # leaf is "enabled"


def test_fingerprint_is_stable_and_hides_value():
    fp = fingerprint_secret("hunter2")
    assert fp == fingerprint_secret("hunter2")  # deterministic
    assert "hunter2" not in fp
    assert fp.startswith("secret:")


def test_fingerprint_changes_with_value():
    assert fingerprint_secret("a") != fingerprint_secret("b")


def test_fingerprint_unset_marker():
    assert fingerprint_secret(None) == "secret:unset"
    assert fingerprint_secret("") == "secret:unset"


def test_redact_secret_fields_only_touches_secrets():
    out = redact_secret_fields({"username": "user", "password": "pw", "port": 8080})
    assert out["username"] == "user"
    assert out["port"] == 8080
    assert out["password"] == fingerprint_secret("pw")
    assert "pw" not in str(out)
