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

        # Handle empty or null destinations
        if data is None:
            data = {"destinations": []}
        elif data.get("destinations") is None:
            data["destinations"] = []

        return cls.model_validate(data)

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

        # Handle empty or null activities
        if data is None:
            data = {"activities": []}
        elif data.get("activities") is None:
            data["activities"] = []

        return cls.model_validate(data)

    def get_normalized_activities(self) -> set[str]:
        """Get activities as lowercase set for matching.

        Returns:
            Set of lowercase activity descriptions.
        """
        return {a.lower().strip() for a in self.activities}


@dataclass
class BlacklistEntry:
    """An entry in the blacklist with reason.

    Attributes:
        destination: Destination name.
        reason: Why it's blacklisted (ya_fue, no_interesa, playa, etc.).
    """

    destination: str
    reason: str

    @property
    def destination_normalized(self) -> str:
        """Get lowercase destination for matching."""
        return self.destination.lower().strip()


class DestinationsConfig(BaseModel):
    """Configuration for destination filtering (blacklist-only approach).

    All activities are shown EXCEPT those matching the blacklist.
    Blacklist is organized by reason (ya_fue, playa, no_interesa, etc.).
    """

    blacklist: dict[str, list[str]] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> "DestinationsConfig":
        """Load destinations config from a YAML file.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            DestinationsConfig instance.
        """
        if not path.exists():
            return cls(blacklist={})

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if data is None:
            return cls(blacklist={})

        if data.get("blacklist") is None:
            data["blacklist"] = {}

        return cls.model_validate(data)

    def get_all_blacklisted(self) -> set[str]:
        """Get all blacklisted destinations as lowercase set.

        Returns:
            Set of lowercase destination names from all reasons.
        """
        result: set[str] = set()
        for destinations in self.blacklist.values():
            for dest in destinations:
                result.add(dest.lower().strip())
        return result

    def get_by_reason(self, reason: str) -> list[str]:
        """Get blacklisted destinations by reason.

        Args:
            reason: Reason key (ya_fue, playa, no_interesa, etc.).

        Returns:
            List of destinations for that reason.
        """
        return self.blacklist.get(reason, [])

    def is_blacklisted(self, text: str) -> tuple[bool, str | None, str | None]:
        """Check if text matches any blacklisted destination.

        Args:
            text: Text to check against blacklist.

        Returns:
            Tuple of (is_blacklisted, matched_destination, reason).
        """
        text_lower = text.lower()
        for reason, destinations in self.blacklist.items():
            for dest in destinations:
                if dest.lower().strip() in text_lower:
                    return True, dest, reason
        return False, None, None

    def add_to_blacklist(self, destination: str, reason: str = "ya_fue") -> None:
        """Add a destination to the blacklist.

        Args:
            destination: Destination name.
            reason: Reason for blacklisting.
        """
        if reason not in self.blacklist:
            self.blacklist[reason] = []
        if destination not in self.blacklist[reason]:
            self.blacklist[reason].append(destination)

    def save(self, path: Path) -> None:
        """Save config to YAML file.

        Args:
            path: Path to save the file.
        """
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Destinations Config - Blacklist Only\n")
            f.write(
                "# Recibes notificaciones de TODOS los planes EXCEPTO los que están aquí.\n\n"
            )
            yaml.dump(
                {"blacklist": self.blacklist},
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )
