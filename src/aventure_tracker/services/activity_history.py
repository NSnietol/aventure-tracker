"""Activity history manager for tracking seen Instagram posts."""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

MAX_CHECK_COUNT = 3  # Maximum times to check a post before ignoring


@dataclass
class ActivityRecord:
    """Record of a seen Instagram post/activity.

    Attributes:
        post_id: Instagram post ID (shortcode).
        event_id: Unique identifier based on date + event name.
        event_name: Human-readable event name.
        event_date: Date of the event (if extracted).
        first_seen: When we first saw this post.
        times_checked: How many times we've processed this post.
        matched_wishlist: Whether it matched a wishlist destination.
        destination: Matched destination name (if any).
    """

    post_id: str
    event_id: str
    event_name: str
    event_date: str | None = None
    first_seen: str = field(default_factory=lambda: date.today().isoformat())
    times_checked: int = 1
    matched_wishlist: bool = False
    destination: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "event_id": self.event_id,
            "event_name": self.event_name,
            "event_date": self.event_date,
            "first_seen": self.first_seen,
            "times_checked": self.times_checked,
            "matched_wishlist": self.matched_wishlist,
            "destination": self.destination,
        }

    @classmethod
    def from_dict(cls, post_id: str, data: dict[str, Any]) -> "ActivityRecord":
        """Create from dictionary."""
        return cls(
            post_id=post_id,
            event_id=data.get("event_id", ""),
            event_name=data.get("event_name", ""),
            event_date=data.get("event_date"),
            first_seen=data.get("first_seen", date.today().isoformat()),
            times_checked=data.get("times_checked", 1),
            matched_wishlist=data.get("matched_wishlist", False),
            destination=data.get("destination"),
        )


class ActivityHistoryManager:
    """Manages the history of seen Instagram activities.

    Persists activity records to a YAML file and provides methods
    to check if a post should be processed and to record checks.

    Attributes:
        history_path: Path to the activity_history.yaml file.
        max_checks: Maximum times to check a post (default: 3).
    """

    def __init__(
        self,
        history_path: Path | None = None,
        max_checks: int = MAX_CHECK_COUNT,
    ) -> None:
        """Initialize the history manager.

        Args:
            history_path: Path to history YAML file. Defaults to data/activity_history.yaml.
            max_checks: Maximum times to check a post before ignoring.
        """
        if history_path is None:
            history_path = Path("data/activity_history.yaml")

        self._history_path = history_path
        self._max_checks = max_checks
        self._records: dict[str, dict[str, ActivityRecord]] = {}  # account -> post_id -> record
        self._loaded = False

    @property
    def history_path(self) -> Path:
        """Get the history file path."""
        return self._history_path

    def load(self) -> None:
        """Load history from YAML file."""
        self._records = {}

        if not self._history_path.exists():
            logger.info(f"History file not found, starting fresh: {self._history_path}")
            self._loaded = True
            return

        try:
            with open(self._history_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if data and "posts" in data:
                for account, posts in data["posts"].items():
                    if posts is None:
                        continue
                    self._records[account] = {}
                    for post_id, record_data in posts.items():
                        self._records[account][post_id] = ActivityRecord.from_dict(
                            post_id, record_data
                        )

            logger.info(f"Loaded history: {self.total_records} records")
            self._loaded = True

        except Exception as e:
            logger.error(f"Error loading history: {e}")
            self._records = {}
            self._loaded = True

    def save(self) -> None:
        """Save history to YAML file."""
        # Ensure directory exists
        self._history_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to serializable format
        data = {"posts": {}}

        for account, posts in self._records.items():
            data["posts"][account] = {}
            for post_id, record in posts.items():
                data["posts"][account][post_id] = record.to_dict()

        try:
            with open(self._history_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

            logger.info(f"Saved history: {self.total_records} records")

        except Exception as e:
            logger.error(f"Error saving history: {e}")
            raise

    @property
    def total_records(self) -> int:
        """Get total number of records across all accounts."""
        return sum(len(posts) for posts in self._records.values())

    def should_check(self, account: str, post_id: str) -> bool:
        """Check if a post should be processed.

        Returns False if the post has been checked max_checks times.

        Args:
            account: Instagram account username.
            post_id: Post ID (shortcode).

        Returns:
            True if the post should be checked, False if it should be skipped.
        """
        if not self._loaded:
            self.load()

        if account not in self._records:
            return True

        if post_id not in self._records[account]:
            return True

        record = self._records[account][post_id]
        return record.times_checked < self._max_checks

    def get_check_count(self, account: str, post_id: str) -> int:
        """Get the number of times a post has been checked.

        Args:
            account: Instagram account username.
            post_id: Post ID (shortcode).

        Returns:
            Number of times checked (0 if never seen).
        """
        if not self._loaded:
            self.load()

        if account not in self._records:
            return 0

        if post_id not in self._records[account]:
            return 0

        return self._records[account][post_id].times_checked

    def get_record(self, account: str, post_id: str) -> ActivityRecord | None:
        """Get the record for a post.

        Args:
            account: Instagram account username.
            post_id: Post ID (shortcode).

        Returns:
            ActivityRecord or None if not found.
        """
        if not self._loaded:
            self.load()

        if account not in self._records:
            return None

        return self._records[account].get(post_id)

    def record_check(
        self,
        account: str,
        post_id: str,
        event_id: str,
        event_name: str,
        event_date: str | None = None,
        matched_wishlist: bool = False,
        destination: str | None = None,
    ) -> ActivityRecord:
        """Record that a post was checked.

        Creates a new record or updates an existing one.

        Args:
            account: Instagram account username.
            post_id: Post ID (shortcode).
            event_id: Unique event identifier.
            event_name: Human-readable event name.
            event_date: Date of the event.
            matched_wishlist: Whether it matched wishlist.
            destination: Matched destination.

        Returns:
            The created or updated ActivityRecord.
        """
        if not self._loaded:
            self.load()

        if account not in self._records:
            self._records[account] = {}

        if post_id in self._records[account]:
            # Update existing record
            record = self._records[account][post_id]
            record.times_checked += 1
            record.matched_wishlist = matched_wishlist
            if destination:
                record.destination = destination
        else:
            # Create new record
            record = ActivityRecord(
                post_id=post_id,
                event_id=event_id,
                event_name=event_name,
                event_date=event_date,
                matched_wishlist=matched_wishlist,
                destination=destination,
            )
            self._records[account][post_id] = record

        logger.debug(f"Recorded check: @{account}/{post_id} (count: {record.times_checked})")
        return record

    def get_account_history(self, account: str) -> list[ActivityRecord]:
        """Get all records for an account.

        Args:
            account: Instagram account username.

        Returns:
            List of ActivityRecord for the account.
        """
        if not self._loaded:
            self.load()

        if account not in self._records:
            return []

        return list(self._records[account].values())

    def get_skipped_count(self, account: str) -> int:
        """Get number of posts that will be skipped for an account.

        Args:
            account: Instagram account username.

        Returns:
            Number of posts with times_checked >= max_checks.
        """
        if not self._loaded:
            self.load()

        if account not in self._records:
            return 0

        return sum(
            1 for r in self._records[account].values()
            if r.times_checked >= self._max_checks
        )

    def clear_account(self, account: str) -> None:
        """Clear all records for an account.

        Args:
            account: Instagram account username.
        """
        if account in self._records:
            del self._records[account]
            logger.info(f"Cleared history for @{account}")

    def clear_all(self) -> None:
        """Clear all records."""
        self._records = {}
        logger.info("Cleared all history")
