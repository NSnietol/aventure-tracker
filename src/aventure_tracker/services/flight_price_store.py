"""Flight price store using YAML for local persistence."""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PriceRecord:
    """A single price record for a flight route.

    Attributes:
        price: Price in COP.
        checked_at: When this price was recorded.
    """

    price: int
    checked_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML."""
        return {
            "price": self.price,
            "checked_at": self.checked_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PriceRecord":
        """Create from dictionary."""
        checked_at = data.get("checked_at")
        if isinstance(checked_at, str):
            checked_at = datetime.fromisoformat(checked_at)
        elif checked_at is None:
            checked_at = datetime.now()

        return cls(
            price=data.get("price", 0),
            checked_at=checked_at,
        )


@dataclass
class RouteHistory:
    """Price history for a specific route and date.

    Attributes:
        route: Route string (e.g., "BAQ-MDE").
        travel_date: Date of travel.
        records: List of price records over time.
    """

    route: str
    travel_date: date
    records: list[PriceRecord]

    @property
    def latest_price(self) -> int | None:
        """Get the most recent price."""
        if not self.records:
            return None
        return self.records[-1].price

    @property
    def previous_price(self) -> int | None:
        """Get the previous price (before latest)."""
        if len(self.records) < 2:
            return None
        return self.records[-2].price

    @property
    def lowest_price(self) -> int | None:
        """Get the lowest recorded price."""
        if not self.records:
            return None
        return min(r.price for r in self.records)

    @property
    def price_change(self) -> int | None:
        """Get change from previous to latest price."""
        if self.latest_price is None or self.previous_price is None:
            return None
        return self.latest_price - self.previous_price

    def add_price(self, price: int) -> None:
        """Add a new price record."""
        self.records.append(PriceRecord(price=price, checked_at=datetime.now()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML."""
        return {
            "route": self.route,
            "travel_date": self.travel_date.isoformat(),
            "records": [r.to_dict() for r in self.records],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RouteHistory":
        """Create from dictionary."""
        travel_date = data.get("travel_date")
        if isinstance(travel_date, str):
            travel_date = date.fromisoformat(travel_date)

        records = [PriceRecord.from_dict(r) for r in data.get("records", [])]

        return cls(
            route=data.get("route", ""),
            travel_date=travel_date,
            records=records,
        )


class FlightPriceStore:
    """Store flight prices in YAML file.

    Provides local persistence for flight price history without
    requiring external services like GitHub Gist.
    """

    def __init__(self, path: Path | None = None):
        """Initialize the store.

        Args:
            path: Path to YAML file. Defaults to data/flight_prices.yaml.
        """
        if path is None:
            path = Path("data/flight_prices.yaml")
        self._path = Path(path)
        self._history: dict[str, RouteHistory] = {}
        self._load()

    def _make_key(self, route: str, travel_date: date) -> str:
        """Create a unique key for route + date."""
        return f"{route}_{travel_date.isoformat()}"

    def _load(self) -> None:
        """Load history from YAML file."""
        if not self._path.exists():
            self._history = {}
            return

        try:
            with open(self._path) as f:
                data = yaml.safe_load(f) or {}

            self._history = {}
            for key, entry in data.get("routes", {}).items():
                self._history[key] = RouteHistory.from_dict(entry)

        except Exception:
            self._history = {}

    def save(self) -> None:
        """Save history to YAML file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "updated_at": datetime.now().isoformat(),
            "routes": {key: h.to_dict() for key, h in self._history.items()},
        }

        with open(self._path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def get_price(self, route: str, travel_date: date) -> int | None:
        """Get the latest price for a route and date.

        Args:
            route: Route string (e.g., "BAQ-MDE").
            travel_date: Date of travel.

        Returns:
            Latest price or None if not tracked.
        """
        key = self._make_key(route, travel_date)
        history = self._history.get(key)
        return history.latest_price if history else None

    def get_previous_price(self, route: str, travel_date: date) -> int | None:
        """Get the previous price for a route and date.

        Args:
            route: Route string.
            travel_date: Date of travel.

        Returns:
            Previous price or None.
        """
        key = self._make_key(route, travel_date)
        history = self._history.get(key)
        return history.previous_price if history else None

    def set_price(self, route: str, travel_date: date, price: int) -> None:
        """Record a new price for a route and date.

        Args:
            route: Route string.
            travel_date: Date of travel.
            price: Price in COP.
        """
        key = self._make_key(route, travel_date)

        if key not in self._history:
            self._history[key] = RouteHistory(
                route=route,
                travel_date=travel_date,
                records=[],
            )

        self._history[key].add_price(price)

    def get_history(self, route: str, travel_date: date) -> RouteHistory | None:
        """Get full price history for a route and date.

        Args:
            route: Route string.
            travel_date: Date of travel.

        Returns:
            RouteHistory or None.
        """
        key = self._make_key(route, travel_date)
        return self._history.get(key)

    def get_all_routes(self) -> list[RouteHistory]:
        """Get all tracked routes."""
        return list(self._history.values())

    def get_routes_for_date(self, travel_date: date) -> list[RouteHistory]:
        """Get all routes for a specific travel date."""
        return [h for h in self._history.values() if h.travel_date == travel_date]

    def get_lowest_prices(self) -> dict[str, int]:
        """Get lowest recorded price for each route (regardless of date)."""
        lowest: dict[str, int] = {}
        for history in self._history.values():
            route = history.route
            if history.lowest_price:
                if route not in lowest or history.lowest_price < lowest[route]:
                    lowest[route] = history.lowest_price
        return lowest

    def cleanup_old_dates(self, before: date) -> int:
        """Remove entries for travel dates that have passed.

        Args:
            before: Remove entries with travel_date before this date.

        Returns:
            Number of entries removed.
        """
        keys_to_remove = [
            key for key, h in self._history.items() if h.travel_date < before
        ]
        for key in keys_to_remove:
            del self._history[key]
        return len(keys_to_remove)
