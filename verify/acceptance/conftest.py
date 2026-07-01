"""Black-box acceptance test fixtures — shared across all FR test files."""

import os

import pytest


@pytest.fixture
def api_base() -> str:
    """Base URL of the running application under test."""
    return os.environ.get("API_BASE_URL", "http://localhost:8000")
