"""Flight-related data models."""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


from enum import Enum
from typing import Literal


class SearchDay(str, Enum):
    """Days of the week for flight search."""

    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"
    MONDAY = "monday"
    TUESDAY = "tuesday"


class AirlineRule(BaseModel):
    """Rule for a specific airline or group of airlines.

    Attributes:
        name: Airline name fragment to match (case-insensitive).
        max_price: Maximum price in COP to include this airline.
            If None, always include (same as priority).
    """

    name: str
    max_price: int | None = None

    def matches(self, airline: str) -> bool:
        """Check if this rule applies to the given airline name."""
        return self.name.upper() in airline.upper()


class AirlinePolicy(BaseModel):
    """Policy for which airlines to track and at what price thresholds.

    Decision logic (applied in order):
    1. If airline matches any priority_airlines → include if price ≤ route threshold
    2. If price ≤ bargain_threshold → include regardless of airline
    3. If airline matches any extra_airlines rule → include if price ≤ rule.max_price
    4. Otherwise → skip

    This model can be loaded from routes.yaml and overridden at runtime
    by calling add_airline() without restarting the process.

    Attributes:
        priority_airlines: Airlines always considered (e.g., LATAM for rewards).
        bargain_threshold: Any airline included if price ≤ this (COP).
        extra_airlines: Additional per-airline rules with custom thresholds.
    """

    priority_airlines: list[str] = Field(default_factory=lambda: ["LATAM"])
    bargain_threshold: int = Field(default=110000, gt=0)
    extra_airlines: list[AirlineRule] = Field(default_factory=list)

    def is_priority(self, airline: str) -> bool:
        """Check if airline is in the priority list."""
        upper = airline.upper()
        return any(p.upper() in upper for p in self.priority_airlines)

    def should_track(self, airline: str, price: int, route_threshold: int) -> tuple[bool, str]:
        """Decide if a flight should be tracked.

        Args:
            airline: Airline name from scraper.
            price: Flight price in COP.
            route_threshold: The price_threshold from the route config.

        Returns:
            Tuple of (should_track, reason) for logging.
        """
        # Rule 1: Priority airline within route threshold
        if self.is_priority(airline):
            if price <= route_threshold:
                return True, f"priority airline, price ${price:,} ≤ threshold ${route_threshold:,}"
            return False, f"priority airline but price ${price:,} > threshold ${route_threshold:,}"

        # Rule 2: Bargain — any airline below absolute floor
        if price <= self.bargain_threshold:
            return True, f"bargain price ${price:,} ≤ bargain_threshold ${self.bargain_threshold:,}"

        # Rule 3: Extra airline rules
        for rule in self.extra_airlines:
            if rule.matches(airline):
                if rule.max_price is None or price <= rule.max_price:
                    return True, f"extra rule for {rule.name}, price ${price:,}"
                return False, f"extra rule for {rule.name} but price ${price:,} > ${rule.max_price:,}"

        # Rule 4: Skip
        return False, f"not priority, price ${price:,} > bargain_threshold ${self.bargain_threshold:,}"

    def add_airline(self, name: str, max_price: int | None = None) -> None:
        """Add an airline rule at runtime without reloading config.

        Args:
            name: Airline name fragment (case-insensitive match).
            max_price: Max price in COP, or None to always include.
        """
        # Avoid duplicates
        for rule in self.extra_airlines:
            if rule.name.upper() == name.upper():
                rule.max_price = max_price
                return
        self.extra_airlines.append(AirlineRule(name=name, max_price=max_price))

    @classmethod
    def default(cls) -> "AirlinePolicy":
        """Return the default policy (LATAM priority + 110K bargain floor)."""
        return cls(
            priority_airlines=["LATAM"],
            bargain_threshold=110000,
            extra_airlines=[],
        )


class RouteConfig(BaseModel):
    """Configuration for a flight route to monitor.

    Attributes:
        origin: IATA airport code for departure (e.g., "BAQ").
        destination: IATA airport code for arrival (e.g., "MDE").
        price_threshold: Maximum price in COP to trigger notification.
        drop_percentage: Minimum price drop percentage to trigger notification.
        search_days: Days of the week to search for this route.
    """

    origin: str = Field(..., min_length=3, max_length=3, description="Origin airport IATA code")
    destination: str = Field(
        ..., min_length=3, max_length=3, description="Destination airport IATA code"
    )
    price_threshold: int = Field(..., gt=0, description="Maximum price in COP")
    drop_percentage: int = Field(
        ..., ge=0, le=100, description="Minimum drop percentage to notify"
    )
    search_days: list[SearchDay] = Field(
        default_factory=lambda: [SearchDay.FRIDAY],
        description="Days to search for flights (relative to weekend Friday)",
    )

    @field_validator("origin", "destination", mode="before")
    @classmethod
    def uppercase_airport_code(cls, v: str) -> str:
        """Convert airport codes to uppercase."""
        return v.upper() if isinstance(v, str) else v

    def get_route_key(self, travel_date: date) -> str:
        """Generate a unique key for this route and date combination.

        Args:
            travel_date: The date of travel.

        Returns:
            A unique string key like "BAQ-MDE-2025-03-15".
        """
        return f"{self.origin}-{self.destination}-{travel_date.isoformat()}"

    def __str__(self) -> str:
        """Return human-readable route string."""
        return f"{self.origin}→{self.destination}"


class RoutesConfig(BaseModel):
    """Container for multiple route configurations."""

    routes: list[RouteConfig] = Field(default_factory=list)
    airline_policy: AirlinePolicy = Field(default_factory=AirlinePolicy.default)

    @classmethod
    def from_yaml(cls, path: Path) -> "RoutesConfig":
        """Load routes configuration from a YAML file.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            RoutesConfig instance with loaded routes.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the YAML is invalid.
        """
        if not path.exists():
            raise FileNotFoundError(f"Routes config not found: {path}")

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls.model_validate(data or {"routes": []})


@dataclass
class FlightResult:
    """Result from a flight search.

    Attributes:
        price: Flight price in COP.
        airline: Airline name.
        departure_time: Departure datetime.
        arrival_time: Arrival datetime.
        duration: Flight duration.
        stops: Number of stops (0 for direct).
        booking_link: URL to book the flight.
    """

    price: int
    airline: str
    departure_time: datetime
    arrival_time: datetime
    duration: timedelta
    stops: int
    booking_link: str

    @property
    def is_direct(self) -> bool:
        """Check if this is a direct flight."""
        return self.stops == 0

    @property
    def departure_date(self) -> date:
        """Get the departure date."""
        return self.departure_time.date()

    @property
    def departure_time_only(self) -> time:
        """Get only the departure time."""
        return self.departure_time.time()

    def format_duration(self) -> str:
        """Format duration as human-readable string.

        Returns:
            String like "1h 30m".
        """
        total_minutes = int(self.duration.total_seconds() / 60)
        hours, minutes = divmod(total_minutes, 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"


@dataclass
class TimeRange:
    """A time range for valid flight departures.

    Attributes:
        start: Start time of the valid window.
        end: End time of the valid window.
    """

    start: time
    end: time

    def contains(self, t: time) -> bool:
        """Check if a time falls within this range.

        Args:
            t: Time to check.

        Returns:
            True if the time is within the range.
        """
        return self.start <= t <= self.end


@dataclass
class WeekendTrip:
    """Represents a weekend trip with valid travel dates.

    Attributes:
        outbound_date: Date for outbound flight (Friday).
        return_date: Date for return flight.
        is_bridge: Whether this is a bridge weekend (puente).
        outbound_times: Valid time ranges for outbound flights.
        return_times: Valid time ranges for return flights.
    """

    outbound_date: date
    return_date: date
    is_bridge: bool
    outbound_times: list[TimeRange]
    return_times: list[TimeRange]

    @property
    def thursday(self) -> date:
        """Get Thursday before this weekend (for evening departures)."""
        return self.outbound_date - timedelta(days=1)

    @property
    def friday(self) -> date:
        """Get Friday of this weekend (alias for outbound_date)."""
        return self.outbound_date

    @property
    def saturday(self) -> date:
        """Get Saturday of this weekend."""
        return self.outbound_date + timedelta(days=1)

    @property
    def sunday(self) -> date:
        """Get Sunday of this weekend (alias for return_date)."""
        return self.return_date

    @property
    def monday(self) -> date:
        """Get Monday after this weekend."""
        return self.return_date + timedelta(days=1)

    @property
    def tuesday(self) -> date:
        """Get Tuesday after this weekend.

        Used when the adventure ends on Monday in MDE and the user
        needs to fly back to BAQ the next morning.
        """
        return self.return_date + timedelta(days=2)

    def get_date_for_day(self, day: "SearchDay") -> date:
        """Get the date for a specific day of this weekend.

        Args:
            day: The day to get.

        Returns:
            The date for that day.
        """
        day_map = {
            SearchDay.THURSDAY: self.thursday,
            SearchDay.FRIDAY: self.friday,
            SearchDay.SATURDAY: self.saturday,
            SearchDay.SUNDAY: self.sunday,
            SearchDay.MONDAY: self.monday,
            SearchDay.TUESDAY: self.tuesday,
        }
        return day_map[day]

    def is_valid_outbound_time(self, t: time) -> bool:
        """Check if a time is valid for outbound flight.

        Args:
            t: Departure time to check.

        Returns:
            True if the time is within any valid outbound window.
        """
        return any(tr.contains(t) for tr in self.outbound_times)

    def is_valid_return_time(self, t: time) -> bool:
        """Check if a time is valid for return flight.

        Args:
            t: Departure time to check.

        Returns:
            True if the time is within any valid return window.
        """
        return any(tr.contains(t) for tr in self.return_times)
