"""Flight price store using YAML for local persistence."""

from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PriceRecord:
    """A single price record for a specific flight.

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
class FlightHistory:
    """Price history for a specific flight (unique by route+date+time+airline).

    Attributes:
        flight_id: Unique identifier (e.g., "BAQ-MDE_2026-08-14_18:30_LATAM").
        route: Route string (e.g., "BAQ-MDE").
        travel_date: Date of travel.
        departure_time: Time of departure (e.g., "18:30").
        airline: Airline name (e.g., "LATAM").
        records: List of price records over time.
    """

    flight_id: str
    route: str
    travel_date: date
    departure_time: str
    airline: str
    records: list[PriceRecord] = field(default_factory=list)

    @property
    def latest_price(self) -> int | None:
        """Get the most recent price."""
        if not self.records:
            return None
        return self.records[-1].price

    @property
    def latest_checked_at(self) -> datetime | None:
        """Get when the price was last checked."""
        if not self.records:
            return None
        return self.records[-1].checked_at

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

    def add_price(self, price: int) -> bool:
        """Add a new price record only if price changed.

        Args:
            price: New price to record.

        Returns:
            True if price was added (new or changed), False if skipped.
        """
        if self.latest_price == price:
            return False

        self.records.append(PriceRecord(price=price, checked_at=datetime.now()))
        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML."""
        return {
            "flight_id": self.flight_id,
            "route": self.route,
            "travel_date": self.travel_date.isoformat(),
            "departure_time": self.departure_time,
            "airline": self.airline,
            "records": [r.to_dict() for r in self.records],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FlightHistory":
        """Create from dictionary."""
        travel_date = data.get("travel_date")
        if isinstance(travel_date, str):
            travel_date = date.fromisoformat(travel_date)

        records = [PriceRecord.from_dict(r) for r in data.get("records", [])]

        return cls(
            flight_id=data.get("flight_id", ""),
            route=data.get("route", ""),
            travel_date=travel_date,
            departure_time=data.get("departure_time", "00:00"),
            airline=data.get("airline", "Unknown"),
            records=records,
        )

    @staticmethod
    def make_flight_id(
        route: str,
        travel_date: date,
        departure_time: str,
        airline: str,
    ) -> str:
        """Create a unique flight ID.

        Args:
            route: Route string (e.g., "BAQ-MDE").
            travel_date: Date of travel.
            departure_time: Time in HH:MM format.
            airline: Airline name.

        Returns:
            Unique flight ID string.
        """
        # Normalize airline name (remove spaces, uppercase)
        airline_clean = airline.upper().replace(" ", "_")
        return f"{route}_{travel_date.isoformat()}_{departure_time}_{airline_clean}"



class FlightPriceStore:
    """Store flight prices in YAML file with unique flight tracking.

    Each flight is uniquely identified by: route + date + departure_time + airline.
    Price history is only recorded when the price changes.
    """

    def __init__(self, path: Path | None = None):
        """Initialize the store.

        Args:
            path: Path to YAML file. Defaults to data/flight_prices.yaml.
        """
        if path is None:
            path = Path("data/flight_prices.yaml")
        self._path = Path(path)
        self._flights: dict[str, FlightHistory] = {}
        self._load()

    def _load(self) -> None:
        """Load history from YAML file."""
        if not self._path.exists():
            self._flights = {}
            return

        try:
            with open(self._path) as f:
                data = yaml.safe_load(f) or {}

            # Load new format (flights)
            self._flights = {}
            for key, entry in data.get("flights", {}).items():
                self._flights[key] = FlightHistory.from_dict(entry)

        except Exception:
            self._flights = {}

    def save(self) -> None:
        """Save history to YAML file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "updated_at": datetime.now().isoformat(),
            "flights": {fid: f.to_dict() for fid, f in self._flights.items()},
        }

        with open(self._path, "w") as f:
            yaml.dump(
                data, f, default_flow_style=False, allow_unicode=True, sort_keys=False
            )

    def set_flight_price(
        self,
        route: str,
        travel_date: date,
        departure_time: str,
        airline: str,
        price: int,
    ) -> bool:
        """Record a price for a specific flight.

        Args:
            route: Route string (e.g., "BAQ-MDE").
            travel_date: Date of travel.
            departure_time: Time in HH:MM format.
            airline: Airline name.
            price: Price in COP.

        Returns:
            True if price was recorded (new or changed), False if skipped.
        """
        flight_id = FlightHistory.make_flight_id(
            route, travel_date, departure_time, airline
        )

        if flight_id not in self._flights:
            self._flights[flight_id] = FlightHistory(
                flight_id=flight_id,
                route=route,
                travel_date=travel_date,
                departure_time=departure_time,
                airline=airline,
                records=[],
            )

        return self._flights[flight_id].add_price(price)

    def get_flight(
        self,
        route: str,
        travel_date: date,
        departure_time: str,
        airline: str,
    ) -> FlightHistory | None:
        """Get flight history by unique identifiers.

        Args:
            route: Route string.
            travel_date: Date of travel.
            departure_time: Time in HH:MM format.
            airline: Airline name.

        Returns:
            FlightHistory or None.
        """
        flight_id = FlightHistory.make_flight_id(
            route, travel_date, departure_time, airline
        )
        return self._flights.get(flight_id)

    def get_flight_by_id(self, flight_id: str) -> FlightHistory | None:
        """Get flight history by ID.

        Args:
            flight_id: Unique flight identifier.

        Returns:
            FlightHistory or None.
        """
        return self._flights.get(flight_id)

    def get_flights_for_route_date(
        self, route: str, travel_date: date
    ) -> list[FlightHistory]:
        """Get all tracked flights for a route and date.

        Args:
            route: Route string.
            travel_date: Date of travel.

        Returns:
            List of FlightHistory objects.
        """
        return [
            f
            for f in self._flights.values()
            if f.route == route and f.travel_date == travel_date
        ]

    def get_all_flights(self) -> list[FlightHistory]:
        """Get all tracked flights."""
        return list(self._flights.values())

    def get_flights_by_airline(self, airline: str) -> list[FlightHistory]:
        """Get all flights for a specific airline.

        Args:
            airline: Airline name (case-insensitive).

        Returns:
            List of FlightHistory objects.
        """
        airline_upper = airline.upper()
        return [f for f in self._flights.values() if airline_upper in f.airline.upper()]

    def cleanup_old_dates(self, before: date) -> int:
        """Remove flights for travel dates that have passed.

        Args:
            before: Remove flights with travel_date before this date.

        Returns:
            Number of flights removed.
        """
        keys_to_remove = [
            fid for fid, f in self._flights.items() if f.travel_date < before
        ]
        for key in keys_to_remove:
            del self._flights[key]

        return len(keys_to_remove)

    def get_lowest_prices(self) -> dict[str, int]:
        """Get lowest recorded price for each route."""
        lowest: dict[str, int] = {}
        for flight in self._flights.values():
            if flight.lowest_price:
                if (
                    flight.route not in lowest
                    or flight.lowest_price < lowest[flight.route]
                ):
                    lowest[flight.route] = flight.lowest_price
        return lowest
