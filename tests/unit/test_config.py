"""Unit tests for configuration module."""

from aventure_tracker.config import Settings


class TestSettings:
    """Tests for the Settings class."""

    def test_settings_default_values(self) -> None:
        """Test that Settings has correct default values."""
        settings = Settings()

        assert settings.app_name == "Aventure Tracker"
        assert settings.log_level == "INFO"

    def test_settings_custom_values(self) -> None:
        """Test that Settings accepts custom values."""
        settings = Settings(
            app_name="Custom App",
            debug=True,
            log_level="DEBUG",
        )

        assert settings.app_name == "Custom App"
        assert settings.debug is True
        assert settings.log_level == "DEBUG"
