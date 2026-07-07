from configarr.normalize import MASK, coerce_scalar, drop_secret_fields


def test_coerce_numeric_strings():
    assert coerce_scalar("5") == 5
    assert coerce_scalar("5.0") == 5.0
    assert coerce_scalar("true") is True
    assert coerce_scalar("keep") == "keep"


def test_coerce_inf_nan_guard():
    for s in ["inf", "+inf", "-inf", "infinity", "+infinity", "-infinity", "nan"]:
        assert coerce_scalar(s) == s


def test_coerce_preserves_numeric_looking_string_identity():
    # These only *look* numeric; coercing them would silently change identity and
    # mask a real string-vs-number drift. They must stay strings.
    for s in ["007", "1_000", "1e3", "0x10", "  1_0  ", "+", "1.2.3", "١٢٣"]:
        assert coerce_scalar(s) == s, s


def test_coerce_clean_numbers():
    assert coerce_scalar("0") == 0
    assert coerce_scalar("-3") == -3
    assert coerce_scalar("+3") == 3
    assert coerce_scalar("10") == 10
    assert coerce_scalar(".5") == 0.5
    assert coerce_scalar("-2.0") == -2.0


def test_drop_secret_fields_drops_mask_valued_only():
    fields = {"host": "h", "apiKey": MASK, "password": MASK, "port": 8080}
    assert drop_secret_fields(fields) == {"host": "h", "port": 8080}


def test_drop_secret_fields_drops_named_secrets_and_mask():
    fields = {"host": "h", "apiKey": "real", "token": MASK, "port": 8080}
    assert drop_secret_fields(fields, {"apiKey"}) == {"host": "h", "port": 8080}
