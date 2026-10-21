import pytest
import responses

KV = "http://kavita.test"


@pytest.fixture
def kavita_auth():
    """Register the auth-key -> JWT exchange every Kavita session starts with."""
    responses.post(
        f"{KV}/api/plugin/authenticate", json={"token": "jwt", "username": "admin"}
    )
