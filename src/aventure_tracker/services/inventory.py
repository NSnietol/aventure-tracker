"""Inventory manager for tracking wishlist and completed activities."""

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from aventure_tracker.models.activity import (
    DoneConfig,
    InstagramPost,
    WishlistConfig,
)
from aventure_tracker.services.ocr import ExtractedActivity

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Result of matching an activity against inventory.

    Attributes:
        is_wishlist_match: Activity matches a wishlist destination.
        is_already_done: Activity has already been completed.
        matched_destination: The matching wishlist destination (if any).
        matched_done: The matching done activity (if any).
        match_score: Confidence score for the match (0-1).
    """

    is_wishlist_match: bool
    is_already_done: bool
    matched_destination: str | None = None
    matched_done: str | None = None
    match_score: float = 0.0


class InventoryManager:
    """Manager for wishlist destinations and completed activities.

    Handles loading, saving, and matching activities against the user's
    wishlist and done lists.

    Attributes:
        wishlist_path: Path to wishlist.yaml file.
        done_path: Path to done.yaml file.
    """

    def __init__(
        self,
        wishlist_path: Path | None = None,
        done_path: Path | None = None,
    ) -> None:
        """Initialize the inventory manager.

        Args:
            wishlist_path: Path to wishlist.yaml file.
            done_path: Path to done.yaml file.
        """
        self._wishlist_path = wishlist_path
        self._done_path = done_path
        self._wishlist: WishlistConfig | None = None
        self._done: DoneConfig | None = None

    def load(self) -> None:
        """Load wishlist and done configurations from files."""
        if self._wishlist_path:
            self._wishlist = WishlistConfig.from_yaml(self._wishlist_path)
            logger.info(
                f"Loaded {len(self._wishlist.destinations)} wishlist destinations"
            )
        else:
            self._wishlist = WishlistConfig(destinations=[])

        if self._done_path:
            self._done = DoneConfig.from_yaml(self._done_path)
            logger.info(f"Loaded {len(self._done.activities)} done activities")
        else:
            self._done = DoneConfig(activities=[])

    @property
    def wishlist(self) -> WishlistConfig:
        """Get the wishlist configuration."""
        if self._wishlist is None:
            self.load()
        return self._wishlist  # type: ignore

    @property
    def done(self) -> DoneConfig:
        """Get the done configuration."""
        if self._done is None:
            self.load()
        return self._done  # type: ignore

    def is_in_wishlist(self, text: str) -> tuple[bool, str | None]:
        """Check if text matches any wishlist destination.

        Uses case-insensitive partial matching.

        Args:
            text: Text to search for destinations.

        Returns:
            Tuple of (is_match, matched_destination).
        """
        text_lower = text.lower()
        for destination in self.wishlist.destinations:
            dest_lower = destination.lower()
            if dest_lower in text_lower:
                return True, destination
        return False, None

    def is_already_done(self, text: str) -> tuple[bool, str | None]:
        """Check if text matches any completed activity.

        Uses case-insensitive partial matching. Matches if:
        - The search text contains the done activity
        - The done activity contains the search text
        - They share a common destination keyword

        Args:
            text: Text to search for done activities.

        Returns:
            Tuple of (is_done, matched_activity).
        """
        text_lower = text.lower()

        for activity in self.done.activities:
            activity_lower = activity.lower()

            # Check direct containment both ways
            if activity_lower in text_lower or text_lower in activity_lower:
                return True, activity

            # Check for common keywords (split on common separators)
            activity_words = set(
                w.strip()
                for w in activity_lower.replace("-", " ").replace(",", " ").split()
                if len(w.strip()) > 3  # Skip short words like "de", "en"
            )
            text_words = set(
                w.strip()
                for w in text_lower.replace("-", " ").replace(",", " ").split()
                if len(w.strip()) > 3
            )

            # If they share significant words, consider it a match
            common = activity_words & text_words
            if common:
                return True, activity

        return False, None

    def match_activity(
        self,
        extracted: ExtractedActivity,
    ) -> MatchResult:
        """Match an extracted activity against inventory.

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

        # Check wishlist
        is_wishlist, matched_dest = self.is_in_wishlist(search_text)

        # Check done
        is_done, matched_done = self.is_already_done(search_text)

        # Calculate match score
        score = self._calculate_match_score(extracted, is_wishlist)

        return MatchResult(
            is_wishlist_match=is_wishlist,
            is_already_done=is_done,
            matched_destination=matched_dest,
            matched_done=matched_done,
            match_score=score,
        )

    def match_post(
        self,
        post: InstagramPost,
        extracted: ExtractedActivity | None = None,
    ) -> MatchResult:
        """Match an Instagram post against inventory.

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

        is_wishlist, matched_dest = self.is_in_wishlist(search_text)
        is_done, matched_done = self.is_already_done(search_text)

        score = 0.5 if is_wishlist else 0.0

        return MatchResult(
            is_wishlist_match=is_wishlist,
            is_already_done=is_done,
            matched_destination=matched_dest,
            matched_done=matched_done,
            match_score=score,
        )

    def _calculate_match_score(
        self,
        extracted: ExtractedActivity,
        is_wishlist: bool,
    ) -> float:
        """Calculate match score for an extracted activity.

        Args:
            extracted: Extracted activity information.
            is_wishlist: Whether it matches a wishlist destination.

        Returns:
            Match score from 0 to 1.
        """
        if not is_wishlist:
            return 0.0

        # Base score for wishlist match
        score = 0.5

        # Add OCR confidence
        score += extracted.confidence * 0.3

        # Bonus for having location extracted
        if extracted.location:
            score += 0.1

        # Bonus for having price
        if extracted.price:
            score += 0.1

        return min(score, 1.0)

    def add_to_done(self, activity: str) -> None:
        """Add an activity to the done list.

        Args:
            activity: Activity description to add.
        """
        if activity not in self.done.activities:
            self.done.activities.append(activity)
            logger.info(f"Added to done: {activity}")

    def add_to_wishlist(self, destination: str) -> None:
        """Add a destination to the wishlist.

        Args:
            destination: Destination to add.
        """
        if destination not in self.wishlist.destinations:
            self.wishlist.destinations.append(destination)
            logger.info(f"Added to wishlist: {destination}")

    def remove_from_wishlist(self, destination: str) -> bool:
        """Remove a destination from the wishlist.

        Args:
            destination: Destination to remove.

        Returns:
            True if removed, False if not found.
        """
        try:
            self.wishlist.destinations.remove(destination)
            logger.info(f"Removed from wishlist: {destination}")
            return True
        except ValueError:
            return False

    def save(self) -> None:
        """Save wishlist and done configurations to files."""
        if self._wishlist_path and self._wishlist:
            self._save_wishlist()

        if self._done_path and self._done:
            self._save_done()

    def _save_wishlist(self) -> None:
        """Save wishlist to YAML file."""
        data = {"destinations": self.wishlist.destinations}

        with open(self._wishlist_path, "w", encoding="utf-8") as f:  # type: ignore
            f.write("# Wishlist - Destinations of Interest\n")
            f.write("# Add destinations you want to be notified about.\n\n")
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

        logger.info(f"Saved wishlist to {self._wishlist_path}")

    def _save_done(self) -> None:
        """Save done activities to YAML file."""
        data = {"activities": self.done.activities}

        with open(self._done_path, "w", encoding="utf-8") as f:  # type: ignore
            f.write("# Done - Completed Activities\n")
            f.write("# Activities you've already done.\n\n")
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

        logger.info(f"Saved done to {self._done_path}")

    def get_stats(self) -> dict[str, int]:
        """Get inventory statistics.

        Returns:
            Dictionary with counts.
        """
        return {
            "wishlist_count": len(self.wishlist.destinations),
            "done_count": len(self.done.activities),
        }

    def filter_new_activities(
        self,
        posts: list[InstagramPost],
        extracted_activities: dict[str, ExtractedActivity] | None = None,
    ) -> list[tuple[InstagramPost, MatchResult]]:
        """Filter posts to find new wishlist-matching activities.

        Args:
            posts: List of Instagram posts to filter.
            extracted_activities: Optional dict mapping post IDs to extracted info.

        Returns:
            List of (post, match_result) tuples for new wishlist matches.
        """
        results: list[tuple[InstagramPost, MatchResult]] = []

        for post in posts:
            extracted = (
                extracted_activities.get(post.id) if extracted_activities else None
            )
            match = self.match_post(post, extracted)

            # Include if matches wishlist and not already done
            if match.is_wishlist_match and not match.is_already_done:
                results.append((post, match))

        # Sort by match score descending
        results.sort(key=lambda x: x[1].match_score, reverse=True)

        return results
