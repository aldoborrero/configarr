from pathlib import Path

import pytest


@pytest.fixture
def guide_root() -> Path:
    """Root of the vendored fake TRaSH-Guides tree used across the trash tests."""
    return Path(__file__).parent / "fixtures" / "guide"
