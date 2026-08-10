"""Flight-related data models."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


class RouteConfig(BaseModel):
    """Configuration for a flight route to monitor.

    Attributes:
        origin: IATA airport code for departure (e.g., "BAQ").
        destination: IATA airport code for arrival (e.g., "MDE").
        price_threshold: Maximum price in COP to trigger notification.
        drop_percentage: Minimum price drop percentage to trigger notification.
    """

    origin: str = Field(..., min_length=3, max_length=3, description="Origin airport IATA code")
    destination: str = Field(
        ..., min_length=3, max_length=3, description="Destination airport IATA code"
    )
    price_threshold: int = Field(..., gt=0, description="Maximum price in COP")
    drop_percentage: int = Field(
        ..., ge=0, le=100, description="Minimum drop percentage to notify"
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
        outbound_date: Date for outbound flight.
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
