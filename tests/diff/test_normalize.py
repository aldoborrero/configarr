from configarr.diff.normalize import MASK, coerce_scalar, drop_masked_secrets


def test_coerce_numeric_strings():
    assert coerce_scalar("5") == 5
    assert coerce_scalar("5.0") == 5.0
    assert coerce_scalar("true") is True
    assert coerce_scalar("keep") == "keep"


def test_coerce_inf_nan_guard():
    for s in ["inf", "+inf", "-inf", "infinity", "+infinity", "-infinity", "nan"]:
        assert coerce_scalar(s) == s


def test_drop_masked_secrets():
    fields = {"host": "h", "apiKey": MASK, "password": MASK, "port": 8080}
    assert drop_masked_secrets(fields) == {"host": "h", "port": 8080}
