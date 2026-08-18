"""Inventory manager for activity filtering using blacklist-only approach."""

import logging
from dataclasses import dataclass
from pathlib import Path

from aventure_tracker.models.activity import (
    DestinationsConfig,
    InstagramPost,
)
from aventure_tracker.services.events.ocr import ExtractedActivity

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Result of matching an activity against inventory.

    Attributes:
        is_blacklisted: Activity matches a blacklisted destination.
        matched_blacklist: The matching blacklisted destination (if any).
        blacklist_reason: Why it's blacklisted (ya_fue, playa, etc.).
        match_score: Confidence score for the match (0-1).
    """

    is_blacklisted: bool = False
    matched_blacklist: str | None = None
    blacklist_reason: str | None = None
    match_score: float = 1.0

    @property
    def should_notify(self) -> bool:
        """Check if this match should trigger a notification."""
        return not self.is_blacklisted


class InventoryManager:
    """Manager for activity filtering using blacklist-only approach.

    All activities are shown EXCEPT those matching the blacklist.
    No wishlist needed - you get everything that's not blocked.

    Attributes:
        destinations_path: Path to destinations.yaml file.
    """

    def __init__(
        self,
        destinations_path: Path | None = None,
        # Legacy params for backward compatibility
        wishlist_path: Path | None = None,
        done_path: Path | None = None,
        blacklist_path: Path | None = None,
    ) -> None:
        """Initialize the inventory manager.

        Args:
            destinations_path: Path to destinations.yaml file (preferred).
            wishlist_path: DEPRECATED - ignored.
            done_path: DEPRECATED - ignored.
            blacklist_path: DEPRECATED - use destinations_path instead.
        """
        self._destinations_path = destinations_path
        self._destinations: DestinationsConfig | None = None

        # Log deprecation warnings
        if wishlist_path:
            logger.warning("wishlist_path is deprecated, use destinations_path")
        if done_path:
            logger.warning("done_path is deprecated, use destinations_path")
        if blacklist_path:
            logger.warning("blacklist_path is deprecated, use destinations_path")

    def load(self) -> None:
        """Load destinations configuration from file."""
        if self._destinations_path:
            self._destinations = DestinationsConfig.from_yaml(self._destinations_path)
            logger.info(
                f"Loaded {len(self._destinations.get_all_blacklisted())} blacklisted destinations"
            )
        else:
            self._destinations = DestinationsConfig(blacklist={})

    @property
    def destinations(self) -> DestinationsConfig:
        """Get the destinations configuration."""
        if self._destinations is None:
            self.load()
        return self._destinations  # type: ignore

    @property
    def blacklist(self) -> DestinationsConfig:
        """Alias for destinations (for compatibility)."""
        return self.destinations

    def is_blacklisted(self, text: str) -> tuple[bool, str | None, str | None]:
        """Check if text matches any blacklisted destination.

        Args:
            text: Text to search for blacklisted destinations.

        Returns:
            Tuple of (is_blacklisted, matched_destination, reason).
        """
        return self.destinations.is_blacklisted(text)

    def match_activity(
        self,
        extracted: ExtractedActivity,
    ) -> MatchResult:
        """Match an extracted activity against blacklist.

        Args:
            extracted: Activity information extracted from OCR.

        Returns:
            MatchResult with matching details.
        """
        # Build search text from extracted info
        search_parts = [extracted.raw_text]
        if extracted.activity_name:
            search_parts.append(extracted.activity_name)
        if extracted.location:
            search_parts.append(extracted.location)

        search_text = " ".join(search_parts)

        # Check blacklist
        is_blocked, matched_blacklist, reason = self.is_blacklisted(search_text)

        return MatchResult(
            is_blacklisted=is_blocked,
            matched_blacklist=matched_blacklist,
            blacklist_reason=reason,
            match_score=extracted.confidence if not is_blocked else 0.0,
        )

    def match_post(
        self,
        post: InstagramPost,
        extracted: ExtractedActivity | None = None,
    ) -> MatchResult:
        """Match an Instagram post against blacklist.

        Args:
            post: Instagram post to match.
            extracted: Optional extracted activity info from OCR.

        Returns:
            MatchResult with matching details.
        """
        # If we have OCR results, use those
        if extracted:
            return self.match_activity(extracted)

        # Otherwise, just use the caption
        search_text = post.caption

        is_blocked, matched_blacklist, reason = self.is_blacklisted(search_text)

        return MatchResult(
            is_blacklisted=is_blocked,
            matched_blacklist=matched_blacklist,
            blacklist_reason=reason,
            match_score=1.0 if not is_blocked else 0.0,
        )

    def add_to_blacklist(self, destination: str, reason: str = "ya_fue") -> None:
        """Add a destination to the blacklist.

        Args:
            destination: Destination name to blacklist.
            reason: Reason for blacklisting.
        """
        self.destinations.add_to_blacklist(destination, reason)
        logger.info(f"Added to blacklist ({reason}): {destination}")

    def save(self) -> None:
        """Save destinations configuration to file."""
        if self._destinations_path and self._destinations:
            self._destinations.save(self._destinations_path)
            logger.info(f"Saved destinations to {self._destinations_path}")

    def get_stats(self) -> dict[str, int]:
        """Get inventory statistics.

        Returns:
            Dictionary with counts.
        """
        return {
            "blacklist_count": len(self.destinations.get_all_blacklisted()),
            "ya_fue_count": len(self.destinations.get_by_reason("ya_fue")),
            "playa_count": len(self.destinations.get_by_reason("playa")),
            "no_interesa_count": len(self.destinations.get_by_reason("no_interesa")),
        }

    def filter_new_activities(
        self,
        posts: list[InstagramPost],
        extracted_activities: dict[str, ExtractedActivity] | None = None,
    ) -> list[tuple[InstagramPost, MatchResult]]:
        """Filter posts to find activities that should be notified.

        Args:
            posts: List of Instagram posts to filter.
            extracted_activities: Optional dict mapping post IDs to extracted info.

        Returns:
            List of (post, match_result) tuples for non-blacklisted activities.
        """
        results: list[tuple[InstagramPost, MatchResult]] = []

        for post in posts:
            extracted = (
                extracted_activities.get(post.id) if extracted_activities else None
            )
            match = self.match_post(post, extracted)

            # Include if should notify (not blacklisted)
            if match.should_notify:
                results.append((post, match))

        # Sort by match score descending
        results.sort(key=lambda x: x[1].match_score, reverse=True)

        return results
