"""State persistence models for shared storage."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FlightState(BaseModel):
    """State for a tracked flight route-date combination.

    Attributes:
        last_price: Last seen price in COP.
        last_notified: When the last notification was sent.
        price_history: Recent price history (last 10 prices).
    """

    last_price: int = Field(..., gt=0, description="Last seen price in COP")
    last_notified: datetime | None = Field(
        default=None, description="Last notification timestamp"
    )
    price_history: list[int] = Field(
        default_factory=list, description="Recent prices (max 10)"
    )

    def add_price(self, price: int) -> None:
        """Add a price to history, keeping only last 10.

        Args:
            price: Price to add to history.
        """
        self.price_history.append(price)
        if len(self.price_history) > 10:
            self.price_history = self.price_history[-10:]

    @property
    def average_price(self) -> float | None:
        """Calculate average price from history.

        Returns:
            Average price or None if no history.
        """
        if not self.price_history:
            return None
        return sum(self.price_history) / len(self.price_history)

    def calculate_drop_percentage(self, new_price: int) -> float:
        """Calculate percentage drop from last price.

        Args:
            new_price: New price to compare.

        Returns:
            Percentage drop (positive means price decreased).
        """
        if self.last_price <= 0:
            return 0.0
        return ((self.last_price - new_price) / self.last_price) * 100


class InstagramAccountState(BaseModel):
    """State for a monitored Instagram account.

    Attributes:
        last_post_id: ID of the last seen post.
        last_checked: When the account was last checked.
        seen_post_ids: Set of all seen post IDs.
    """

    last_post_id: str | None = Field(default=None, description="Last seen post ID")
    last_checked: datetime | None = Field(
        default=None, description="Last check timestamp"
    )
    seen_post_ids: list[str] = Field(
        default_factory=list, description="All seen post IDs"
    )

    def add_seen_post(self, post_id: str) -> None:
        """Mark a post as seen.

        Args:
            post_id: Post ID to mark as seen.
        """
        if post_id not in self.seen_post_ids:
            self.seen_post_ids.append(post_id)
            # Keep only last 100 post IDs to prevent unbounded growth
            if len(self.seen_post_ids) > 100:
                self.seen_post_ids = self.seen_post_ids[-100:]

    def is_seen(self, post_id: str) -> bool:
        """Check if a post has been seen.

        Args:
            post_id: Post ID to check.

        Returns:
            True if the post was already seen.
        """
        return post_id in self.seen_post_ids

    def get_seen_set(self) -> set[str]:
        """Get seen post IDs as a set for fast lookup.

        Returns:
            Set of seen post IDs.
        """
        return set(self.seen_post_ids)


class StateData(BaseModel):
    """Root state data structure for persistence.

    Attributes:
        version: Schema version for migrations.
        flights: Flight state by route-date key.
        instagram: Instagram account state by username.
    """

    version: int = Field(default=1, description="State schema version")
    flights: dict[str, FlightState] = Field(
        default_factory=dict, description="Flight states by route-date key"
    )
    instagram: dict[str, InstagramAccountState] = Field(
        default_factory=dict, description="Instagram states by username"
    )

    def get_flight_state(self, route_key: str) -> FlightState | None:
        """Get flight state for a route-date key.

        Args:
            route_key: Key like "BAQ-MDE-2025-03-15".

        Returns:
            FlightState if exists, None otherwise.
        """
        return self.flights.get(route_key)

    def set_flight_state(
        self,
        route_key: str,
        price: int,
        notified: bool = False,
    ) -> FlightState:
        """Set or update flight state for a route.

        Args:
            route_key: Key like "BAQ-MDE-2025-03-15".
            price: Current price.
            notified: Whether a notification was sent.

        Returns:
            Updated FlightState.
        """
        if route_key not in self.flights:
            self.flights[route_key] = FlightState(last_price=price)
        else:
            self.flights[route_key].last_price = price

        self.flights[route_key].add_price(price)

        if notified:
            self.flights[route_key].last_notified = datetime.now()

        return self.flights[route_key]

    def get_instagram_state(self, username: str) -> InstagramAccountState:
        """Get or create Instagram account state.

        Args:
            username: Instagram username.

        Returns:
            InstagramAccountState (creates new if not exists).
        """
        if username not in self.instagram:
            self.instagram[username] = InstagramAccountState()
        return self.instagram[username]

    def mark_post_seen(self, username: str, post_id: str) -> None:
        """Mark an Instagram post as seen.

        Args:
            username: Instagram username.
            post_id: Post ID to mark.
        """
        state = self.get_instagram_state(username)
        state.add_seen_post(post_id)
        state.last_post_id = post_id
        state.last_checked = datetime.now()

    def is_post_seen(self, username: str, post_id: str) -> bool:
        """Check if a post has been seen.

        Args:
            username: Instagram username.
            post_id: Post ID to check.

        Returns:
            True if the post was already seen.
        """
        if username not in self.instagram:
            return False
        return self.instagram[username].is_seen(post_id)

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the state.
        """
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StateData":
        """Create StateData from a dictionary.

        Args:
            data: Dictionary data (from JSON).

        Returns:
            StateData instance.
        """
        return cls.model_validate(data)

    @classmethod
    def empty(cls) -> "StateData":
        """Create an empty state.

        Returns:
            New empty StateData instance.
        """
        return cls()


@dataclass
class TrackerResult:
    """Result from a tracker run.

    Attributes:
        success: Whether the tracker completed without fatal errors.
        notifications_sent: Number of notifications sent.
        items_checked: Number of items (flights/posts) checked.
        errors: List of error messages encountered.
    """

    success: bool
    notifications_sent: int = 0
    items_checked: int = 0
    errors: list[str] = field(default_factory=list)

    def add_error(self, error: str) -> None:
        """Add an error message.

        Args:
            error: Error message to add.
        """
        self.errors.append(error)

    @property
    def has_errors(self) -> bool:
        """Check if any errors occurred."""
        return len(self.errors) > 0
