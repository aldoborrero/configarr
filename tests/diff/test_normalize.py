from configarr.diff.normalize import MASK, coerce_scalar, drop_secret_fields


def test_coerce_numeric_strings():
    assert coerce_scalar("5") == 5
    assert coerce_scalar("5.0") == 5.0
    assert coerce_scalar("true") is True
    assert coerce_scalar("keep") == "keep"


def test_coerce_inf_nan_guard():
    for s in ["inf", "+inf", "-inf", "infinity", "+infinity", "-infinity", "nan"]:
        assert coerce_scalar(s) == s


def test_drop_secret_fields_drops_mask_valued_only():
    fields = {"host": "h", "apiKey": MASK, "password": MASK, "port": 8080}
    assert drop_secret_fields(fields) == {"host": "h", "port": 8080}


def test_drop_secret_fields_drops_named_secrets_and_mask():
    fields = {"host": "h", "apiKey": "real", "token": MASK, "port": 8080}
    assert drop_secret_fields(fields, {"apiKey"}) == {"host": "h", "port": 8080}
