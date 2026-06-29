from configarr.diff.normalize import MASK, coerce_scalar, drop_masked_secrets


def test_coerce_numeric_strings():
    assert coerce_scalar("5") == 5
    assert coerce_scalar("5.0") == 5.0
    assert coerce_scalar("true") is True
    assert coerce_scalar("keep") == "keep"


def test_drop_masked_secrets():
    fields = {"host": "h", "apiKey": MASK, "password": MASK, "port": 8080}
    assert drop_masked_secrets(fields) == {"host": "h", "port": 8080}
