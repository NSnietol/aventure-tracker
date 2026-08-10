"""Activity-related data models for Instagram tracking."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


@dataclass
class InstagramPost:
    """Represents an Instagram post from a monitored account.

    Attributes:
        id: Unique post identifier (shortcode).
        url: Full URL to the Instagram post.
        image_urls: List of image URLs in the post.
        caption: Post caption text (may be empty).
        timestamp: When the post was created.
    """

    id: str
    url: str
    image_urls: list[str]
    caption: str
    timestamp: datetime

    @property
    def has_images(self) -> bool:
        """Check if the post has any images."""
        return len(self.image_urls) > 0

    @property
    def first_image_url(self) -> str | None:
        """Get the first image URL if available."""
        return self.image_urls[0] if self.image_urls else None


class InstagramAccountConfig(BaseModel):
    """Configuration for an Instagram account to monitor.

    Attributes:
        username: Instagram username (without @).
        name: Human-readable name for the account.
        enabled: Whether to monitor this account.
    """

    username: str = Field(..., min_length=1, description="Instagram username")
    name: str = Field(..., min_length=1, description="Display name")
    enabled: bool = Field(default=True, description="Whether to monitor this account")

    @property
    def profile_url(self) -> str:
        """Get the full Instagram profile URL."""
        return f"https://www.instagram.com/{self.username}/"


class AccountsConfig(BaseModel):
    """Container for Instagram account configurations."""

    accounts: list[InstagramAccountConfig] = Field(default_factory=list)

    @property
    def enabled_accounts(self) -> list[InstagramAccountConfig]:
        """Get only enabled accounts."""
        return [acc for acc in self.accounts if acc.enabled]

    @classmethod
    def from_yaml(cls, path: Path) -> "AccountsConfig":
        """Load accounts configuration from a YAML file.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            AccountsConfig instance with loaded accounts.

        Raises:
            FileNotFoundError: If the file doesn't exist.
        """
        if not path.exists():
            raise FileNotFoundError(f"Accounts config not found: {path}")

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls.model_validate(data or {"accounts": []})


class WishlistConfig(BaseModel):
    """Configuration for desired destinations."""

    destinations: list[str] = Field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: Path) -> "WishlistConfig":
        """Load wishlist from a YAML file.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            WishlistConfig instance.
        """
        if not path.exists():
            return cls(destinations=[])

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls.model_validate(data or {"destinations": []})

    def get_normalized_destinations(self) -> set[str]:
        """Get destinations as lowercase set for matching.

        Returns:
            Set of lowercase destination names.
        """
        return {d.lower().strip() for d in self.destinations}


class DoneConfig(BaseModel):
    """Configuration for completed activities."""

    activities: list[str] = Field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: Path) -> "DoneConfig":
        """Load done activities from a YAML file.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            DoneConfig instance.
        """
        if not path.exists():
            return cls(activities=[])

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls.model_validate(data or {"activities": []})

    def get_normalized_activities(self) -> set[str]:
        """Get activities as lowercase set for matching.

        Returns:
            Set of lowercase activity descriptions.
        """
        return {a.lower().strip() for a in self.activities}
