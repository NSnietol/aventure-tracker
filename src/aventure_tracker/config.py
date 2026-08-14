"""Configuration management with dual environment support."""

import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment detection.

    Loads configuration from environment variables with .env file support
    for local development. Automatically detects CI environment for
    GitHub Actions execution.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment detection
    ci: bool = Field(default=False, description="CI environment flag (set by GitHub Actions)")
    app_env: str = Field(default="local", description="Application environment")

    # Telegram configuration
    telegram_bot_token: str = Field(
        default="",
        description="Telegram bot token from @BotFather",
    )
    telegram_chat_id: str = Field(
        default="",
        description="Telegram chat ID for notifications",
    )

    # Email configuration (Resend)
    resend_api_key: str = Field(
        default="",
        description="Resend API key for email notifications",
    )
    email_to: str = Field(
        default="",
        description="Recipient email address for notifications",
    )

    # GitHub Gist configuration
    gist_id: str = Field(
        default="",
        alias="GITHUB_GIST_ID",
        description="GitHub Gist ID for state persistence",
    )
    gist_token: str = Field(
        default="",
        alias="GITHUB_GIST_TOKEN",
        description="GitHub PAT with gist scope",
    )

    # Paths
    config_dir: Path = Field(
        default=Path("config"),
        description="Path to configuration directory",
    )

    # Scraping settings
    headless: bool = Field(
        default=True,
        description="Run browser in headless mode",
    )
    min_delay_ms: int = Field(
        default=1000,
        description="Minimum delay between actions (ms)",
    )
    max_delay_ms: int = Field(
        default=3000,
        description="Maximum delay between actions (ms)",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )

    @field_validator("ci", mode="before")
    @classmethod
    def parse_ci_flag(cls, v: str | bool) -> bool:
        """Parse CI flag from string or boolean."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return False

    @field_validator("config_dir", mode="before")
    @classmethod
    def parse_config_dir(cls, v: str | Path) -> Path:
        """Parse config directory from string or Path."""
        return Path(v) if isinstance(v, str) else v

    @property
    def is_ci(self) -> bool:
        """Check if running in CI environment (GitHub Actions).
        
        Uses GITHUB_ACTIONS which is ONLY set by GitHub Actions runner,
        never in local development.
        """
        return os.getenv("GITHUB_ACTIONS", "").lower() == "true"

    @property
    def is_configured(self) -> bool:
        """Check if all required settings are configured."""
        return bool(
            self.telegram_bot_token
            and self.telegram_chat_id
            and self.gist_id
            and self.gist_token
        )

    def get_routes_path(self) -> Path:
        """Get path to routes configuration file."""
        return self.config_dir / "routes.yaml"

    def get_accounts_path(self) -> Path:
        """Get path to Instagram accounts configuration file."""
        return self.config_dir / "accounts.yaml"

    def get_holidays_path(self) -> Path:
        """Get path to holidays configuration file."""
        return self.config_dir / "holidays.yaml"

    def get_done_path(self) -> Path:
        """Get path to done activities file."""
        return self.config_dir / "done.yaml"

    def get_wishlist_path(self) -> Path:
        """Get path to wishlist file."""
        return self.config_dir / "wishlist.yaml"

    def get_destinations_path(self) -> Path:
        """Get path to destinations (blacklist) configuration file."""
        return self.config_dir / "destinations.yaml"


# Global settings instance
settings = Settings()
