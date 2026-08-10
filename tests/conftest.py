"""Shared pytest fixtures for Adventure Tracker tests."""

import os
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with sample files."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create sample routes.yaml
    routes_yaml = config_dir / "routes.yaml"
    routes_yaml.write_text(
        """
routes:
  - origin: BAQ
    destination: MDE
    price_threshold: 150000
    drop_percentage: 15
"""
    )

    # Create sample accounts.yaml
    accounts_yaml = config_dir / "accounts.yaml"
    accounts_yaml.write_text(
        """
accounts:
  - username: testaccount
    name: Test Account
    enabled: true
"""
    )

    # Create sample wishlist.yaml
    wishlist_yaml = config_dir / "wishlist.yaml"
    wishlist_yaml.write_text(
        """
destinations:
  - Guatapé
  - Jardín
"""
    )

    # Create sample done.yaml
    done_yaml = config_dir / "done.yaml"
    done_yaml.write_text(
        """
activities:
  - "Bungee Medellín"
"""
    )

    # Create sample holidays.yaml
    holidays_yaml = config_dir / "holidays.yaml"
    holidays_yaml.write_text(
        """
holidays:
  2025:
    - date: "2025-08-18"
      name: "Asunción de la Virgen"
      type: moved_monday
"""
    )

    return config_dir


@pytest.fixture
def mock_env_vars() -> Generator[dict[str, str], None, None]:
    """Mock environment variables for testing."""
    env_vars = {
        "TELEGRAM_BOT_TOKEN": "test_bot_token",
        "TELEGRAM_CHAT_ID": "test_chat_id",
        "GITHUB_GIST_ID": "test_gist_id",
        "GITHUB_GIST_TOKEN": "test_gist_token",
        "APP_ENV": "test",
        "CI": "false",
    }

    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars


@pytest.fixture
def mock_ci_env_vars() -> Generator[dict[str, str], None, None]:
    """Mock CI environment variables for testing."""
    env_vars = {
        "TELEGRAM_BOT_TOKEN": "ci_bot_token",
        "TELEGRAM_CHAT_ID": "ci_chat_id",
        "GITHUB_GIST_ID": "ci_gist_id",
        "GITHUB_GIST_TOKEN": "ci_gist_token",
        "APP_ENV": "ci",
        "CI": "true",
    }

    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars
