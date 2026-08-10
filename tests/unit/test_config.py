"""Tests for configuration module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from aventure_tracker.config import Settings


class TestSettings:
    """Tests for Settings class."""

    def test_settings_loads_from_env_vars(self, mock_env_vars: dict[str, str]) -> None:
        """Test that settings loads values from environment variables."""
        # Arrange & Act
        settings = Settings()

        # Assert
        assert settings.telegram_bot_token == "test_bot_token"
        assert settings.telegram_chat_id == "test_chat_id"
        assert settings.gist_id == "test_gist_id"
        assert settings.gist_token == "test_gist_token"
        assert settings.app_env == "test"

    def test_settings_detects_ci_true(self, mock_ci_env_vars: dict[str, str]) -> None:
        """Test that settings correctly detects CI=true."""
        # Arrange & Act
        settings = Settings()

        # Assert
        assert settings.is_ci is True
        assert settings.ci is True

    def test_settings_detects_ci_false(self, mock_env_vars: dict[str, str]) -> None:
        """Test that settings correctly detects CI=false."""
        # Arrange & Act
        settings = Settings()

        # Assert
        assert settings.is_ci is False
        assert settings.ci is False

    def test_settings_ci_from_env_var_string(self) -> None:
        """Test CI detection from environment variable string."""
        with patch.dict(os.environ, {"CI": "true"}, clear=False):
            settings = Settings(
                telegram_bot_token="t",
                telegram_chat_id="c",
                gist_id="g",
                gist_token="t",
            )
            assert settings.is_ci is True

    def test_settings_default_values(self) -> None:
        """Test that settings has correct default values."""
        # Arrange - clear env vars
        with patch.dict(os.environ, {}, clear=True):
            # Act
            settings = Settings()

            # Assert
            assert settings.ci is False
            assert settings.app_env == "local"
            assert settings.headless is True
            assert settings.min_delay_ms == 1000
            assert settings.max_delay_ms == 3000
            assert settings.log_level == "INFO"
            assert settings.config_dir == Path("config")

    def test_settings_is_configured_true(self, mock_env_vars: dict[str, str]) -> None:
        """Test is_configured returns True when all required settings present."""
        # Arrange & Act
        settings = Settings()

        # Assert
        assert settings.is_configured is True

    def test_settings_is_configured_false_when_missing(self) -> None:
        """Test is_configured returns False when required settings missing."""
        # Arrange
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

            # Assert
            assert settings.is_configured is False

    def test_settings_path_methods(
        self, mock_env_vars: dict[str, str], temp_config_dir: Path
    ) -> None:
        """Test that path methods return correct paths."""
        # Arrange
        settings = Settings(config_dir=temp_config_dir)

        # Assert
        assert settings.get_routes_path() == temp_config_dir / "routes.yaml"
        assert settings.get_accounts_path() == temp_config_dir / "accounts.yaml"
        assert settings.get_holidays_path() == temp_config_dir / "holidays.yaml"
        assert settings.get_done_path() == temp_config_dir / "done.yaml"
        assert settings.get_wishlist_path() == temp_config_dir / "wishlist.yaml"

    def test_settings_config_dir_from_string(
        self, mock_env_vars: dict[str, str]
    ) -> None:
        """Test config_dir can be set from string."""
        # Arrange & Act
        settings = Settings(config_dir="custom/path")

        # Assert
        assert settings.config_dir == Path("custom/path")

    def test_settings_ci_parser_handles_various_inputs(self) -> None:
        """Test CI flag parser handles various input formats."""
        test_cases = [
            ("true", True),
            ("TRUE", True),
            ("True", True),
            ("1", True),
            ("yes", True),
            ("false", False),
            ("FALSE", False),
            ("0", False),
            ("no", False),
            ("", False),
        ]

        for input_val, expected in test_cases:
            with patch.dict(os.environ, {"CI": input_val}, clear=True):
                settings = Settings()
                assert settings.ci is expected, f"Failed for input: {input_val}"
