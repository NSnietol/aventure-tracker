"""Configuration management for Aventure Tracker."""

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    """Application settings.

    Attributes:
        app_name: The name of the application.
        debug: Enable debug mode.
        log_level: Logging level.
    """

    app_name: str = "Aventure Tracker"
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


# Global settings instance
settings = Settings()
