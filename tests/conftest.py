"""Shared pytest fixtures for Aventure Tracker tests."""

import pytest

from aventure_tracker.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Provide test settings configuration.

    Returns:
        A Settings instance configured for testing.
    """
    return Settings(
        app_name="Aventure Tracker Test",
        debug=True,
        log_level="DEBUG",
    )
