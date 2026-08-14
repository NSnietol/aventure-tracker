"""Flight tracker service for monitoring flight prices."""

import logging
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path

from aventure_tracker.infrastructure.notifier import TelegramNotifier
from aventure_tracker.infrastructure.state_manager import StateManager
from aventure_tracker.models.flight import (
    FlightResult,
    RouteConfig,
    RoutesConfig,
    SearchDay,
)
from aventure_tracker.scrapers.google_flights import GoogleFlightsScraper
from aventure_tracker.services.flight_dates import FlightDateCalculator
from aventure_tracker.services.flight_price_store import FlightPriceStore
from aventure_tracker.services.holidays import HolidayService

logger = logging.getLogger(__name__)

# Airline priority configuration
PRIORITY_AIRLINE = "LATAM"
# Price threshold to consider non-priority airlines (in COP)
NON_PRIORITY_PRICE_THRESHOLD = 120000

# Time filters by day of week (based on requirements)
# Thursday: after 6PM (18:00)
# Friday: before 4PM (16:00)
# Sunday: after 2PM (14:00)
# Monday: before 10AM (10:00)
TIME_FILTERS: dict[SearchDay, tuple[time, time]] = {
    SearchDay.THURSDAY: (time(18, 0), time(23, 59)),  # 6PM - midnight
    SearchDay.FRIDAY: (time(0, 0), time(16, 0)),  # midnight - 4PM
    SearchDay.SATURDAY: (time(0, 0), time(23, 59)),  # all day
    SearchDay.SUNDAY: (time(14, 0), time(23, 59)),  # 2PM - midnight
    SearchDay.MONDAY: (time(0, 0), time(10, 0)),  # midnight - 10AM
}


@dataclass
class FlightFound:
    """A flight found during tracking.

    Attributes:
        flight_id: Unique identifier.
        route: Route string (e.g., "BAQ→MDE").
        travel_date: Date of travel.
        departure_time: Departure time (HH:MM).
        airline: Airline name.
        price: Price in COP.
        is_priority: Whether this is a priority airline flight.
    """

    flight_id: str
    route: str
    travel_date: date
    departure_time: str
    airline: str
    price: int
    is_priority: bool = False


@dataclass
class PriceAlert:
    """Price alert for a flight.

    Attributes:
        flight: The flight found.
        route_config: The route configuration.
        previous_price: Previous price (if tracked).
        price_change: Change from previous price (negative = drop).
        price_change_pct: Percentage change.
        is_below_threshold: Whether price is below threshold.
        is_significant_drop: Whether drop exceeds configured percentage.
    """

    flight: FlightFound
    route_config: RouteConfig
    previous_price: int | None
    price_change: int | None
    price_change_pct: float | None
    is_below_threshold: bool
    is_significant_drop: bool

    @property
    def should_notify(self) -> bool:
        """Check if this alert should trigger a notification."""
        return self.is_below_threshold or self.is_significant_drop


@dataclass
class FlightTrackerResult:
    """Result of a flight tracking run.

    Attributes:
        routes_checked: Number of routes checked.
        dates_checked: Number of dates checked.
        flights_found: Number of flights found.
        alerts_generated: Number of price alerts.
        notifications_sent: Number of notifications sent.
        prices_found: List of flights found during this run.
        errors: List of error messages.
    """

    routes_checked: int
    dates_checked: int
    flights_found: int
    alerts_generated: int
    notifications_sent: int
    prices_found: list[FlightFound]
    errors: list[str]


class FlightTrackerService:
    """Service for tracking flight prices and sending alerts.

    Orchestrates the flight scraping, price comparison, and notification
    process for configured routes and upcoming weekends.

    Filters flights by:
    - Airline: LATAM has priority, others only if price <= 120,000 COP
    - Time: Based on day of week (Thursday >= 6PM, Friday < 4PM, etc.)
    """

    def __init__(
        self,
        routes_config_path: Path,
        holidays_config_path: Path | None = None,
        state_manager: StateManager | None = None,
        notifier: TelegramNotifier | None = None,
        scraper: GoogleFlightsScraper | None = None,
        weeks_ahead: int = 8,
        price_store_path: Path | None = None,
    ) -> None:
        """Initialize the flight tracker service.

        Args:
            routes_config_path: Path to routes.yaml.
            holidays_config_path: Path to holidays.yaml.
            state_manager: StateManager for persistence (optional).
            notifier: TelegramNotifier for alerts (optional).
            scraper: GoogleFlightsScraper instance (optional).
            weeks_ahead: Number of weeks to check ahead.
            price_store_path: Path to YAML price store (optional).
        """
        self._routes_config_path = routes_config_path
        self._holidays_config_path = holidays_config_path
        self._state_manager = state_manager
        self._notifier = notifier
        self._scraper = scraper
        self._weeks_ahead = weeks_ahead

        self._routes: RoutesConfig | None = None
        self._date_calculator: FlightDateCalculator | None = None

        # Initialize local price store
        self._price_store = FlightPriceStore(path=price_store_path)

    def _load_routes(self) -> RoutesConfig:
        """Load routes configuration."""
        if self._routes is None:
            self._routes = RoutesConfig.from_yaml(self._routes_config_path)
            logger.info(f"Loaded {len(self._routes.routes)} routes")
        return self._routes

    def _get_date_calculator(self) -> FlightDateCalculator:
        """Get or create the date calculator."""
        if self._date_calculator is None:
            holiday_service = HolidayService(config_path=self._holidays_config_path)
            self._date_calculator = FlightDateCalculator(
                holiday_service=holiday_service
            )
        return self._date_calculator

    def _get_scraper(self) -> GoogleFlightsScraper:
        """Get or create the scraper."""
        if self._scraper is None:
            self._scraper = GoogleFlightsScraper(headless=True)
        return self._scraper

    def _is_valid_time_for_day(self, departure_time: str, search_day: SearchDay) -> bool:
        """Check if departure time is valid for the search day.

        Args:
            departure_time: Time in HH:MM format.
            search_day: The day being searched.

        Returns:
            True if time is within valid window for that day.
        """
        if not departure_time:
            return True  # Accept if time not extracted

        try:
            hour, minute = map(int, departure_time.split(":"))
            flight_time = time(hour, minute)
        except (ValueError, AttributeError):
            return True  # Accept if parsing fails

        time_range = TIME_FILTERS.get(search_day)
        if not time_range:
            return True  # No filter for this day

        min_time, max_time = time_range
        return min_time <= flight_time <= max_time

    def _should_track_flight(self, flight: FlightResult) -> bool:
        """Determine if a flight should be tracked based on airline priority.

        Priority rules:
        - LATAM: Always track
        - Other airlines: Only if price <= 120,000 COP

        Args:
            flight: The flight result.

        Returns:
            True if flight should be tracked.
        """
        airline_upper = flight.airline.upper()

        # LATAM always has priority
        if PRIORITY_AIRLINE in airline_upper:
            return True

        # Other airlines only if price is very low
        return flight.price <= NON_PRIORITY_PRICE_THRESHOLD

    def _is_priority_airline(self, airline: str) -> bool:
        """Check if airline is the priority airline."""
        return PRIORITY_AIRLINE in airline.upper()

    async def track_flights(self) -> FlightTrackerResult:
        """Run the flight tracking process.

        Checks all configured routes for upcoming weekends and generates
        alerts for prices below threshold or significant drops.

        Returns:
            FlightTrackerResult with tracking statistics.
        """
        routes = self._load_routes()
        date_calculator = self._get_date_calculator()
        scraper = self._get_scraper()

        weekends = date_calculator.get_upcoming_weekends(weeks_ahead=self._weeks_ahead)

        result = FlightTrackerResult(
            routes_checked=0,
            dates_checked=0,
            flights_found=0,
            alerts_generated=0,
            notifications_sent=0,
            prices_found=[],
            errors=[],
        )

        for route in routes.routes:
            logger.info(f"Checking route: {route}")
            result.routes_checked += 1

            for weekend in weekends:
                # Get dates to check from route configuration
                for search_day in route.search_days:
                    travel_date = weekend.get_date_for_day(search_day)
                    result.dates_checked += 1

                    try:
                        # Use scrape() to get full flight details
                        flights = await scraper.scrape(route, travel_date)

                        if not flights:
                            logger.info(f"  {route} {travel_date} ({search_day.value}): No flights found")
                            continue

                        # Filter and process flights
                        for flight in flights:
                            # Check time filter
                            departure_time_str = flight.departure_time.strftime("%H:%M")
                            if not self._is_valid_time_for_day(departure_time_str, search_day):
                                logger.debug(
                                    f"    Skipping {flight.airline} {departure_time_str}: "
                                    f"outside time window for {search_day.value}"
                                )
                                continue

                            # Check airline priority
                            if not self._should_track_flight(flight):
                                logger.debug(
                                    f"    Skipping {flight.airline} ${flight.price:,}: "
                                    f"not priority and price > {NON_PRIORITY_PRICE_THRESHOLD:,}"
                                )
                                continue

                            # Create unique flight ID
                            route_str = f"{route.origin}-{route.destination}"
                            is_priority = self._is_priority_airline(flight.airline)

                            flight_found = FlightFound(
                                flight_id=f"{route_str}_{travel_date}_{departure_time_str}_{flight.airline}",
                                route=str(route),
                                travel_date=travel_date,
                                departure_time=departure_time_str,
                                airline=flight.airline,
                                price=flight.price,
                                is_priority=is_priority,
                            )

                            # Log the flight
                            priority_marker = "★" if is_priority else ""
                            logger.info(
                                f"  {route} {travel_date} {departure_time_str} "
                                f"{flight.airline}{priority_marker}: ${flight.price:,} COP"
                            )

                            result.flights_found += 1
                            result.prices_found.append(flight_found)

                            # Save to price store
                            self._price_store.set_flight_price(
                                route=route_str,
                                travel_date=travel_date,
                                departure_time=departure_time_str,
                                airline=flight.airline,
                                price=flight.price,
                            )

                            # Create alert and check if should notify
                            alert = self._create_alert(flight_found, route)
                            if alert.should_notify:
                                result.alerts_generated += 1
                                await self._send_notification(alert)
                                result.notifications_sent += 1

                    except Exception as e:
                        error_msg = f"Error checking {route} on {travel_date}: {e}"
                        logger.error(error_msg)
                        result.errors.append(error_msg)

        logger.info(
            f"Flight tracking complete: {result.routes_checked} routes, "
            f"{result.dates_checked} dates, {result.flights_found} flights, "
            f"{result.alerts_generated} alerts"
        )

        # Save prices to local YAML store
        self._price_store.save()
        logger.info("Flight prices saved to local store")

        return result

    def _create_alert(
        self,
        flight: FlightFound,
        route_config: RouteConfig,
    ) -> PriceAlert:
        """Create a price alert for a flight.

        Args:
            flight: The flight found.
            route_config: Route configuration.

        Returns:
            PriceAlert with comparison to previous price.
        """
        # Get previous price for this specific flight
        route_str = f"{route_config.origin}-{route_config.destination}"
        flight_history = self._price_store.get_flight(
            route=route_str,
            travel_date=flight.travel_date,
            departure_time=flight.departure_time,
            airline=flight.airline,
        )

        previous_price = flight_history.previous_price if flight_history else None

        price_change: int | None = None
        price_change_pct: float | None = None

        if previous_price is not None:
            price_change = flight.price - previous_price
            if previous_price > 0:
                price_change_pct = round((price_change / previous_price) * 100, 1)

        is_below_threshold = flight.price <= route_config.price_threshold
        is_significant_drop = (
            price_change_pct is not None
            and price_change_pct < 0
            and abs(price_change_pct) >= route_config.drop_percentage
        )

        return PriceAlert(
            flight=flight,
            route_config=route_config,
            previous_price=previous_price,
            price_change=price_change,
            price_change_pct=price_change_pct,
            is_below_threshold=is_below_threshold,
            is_significant_drop=is_significant_drop,
        )

    async def _send_notification(self, alert: PriceAlert) -> None:
        """Send notification for a price alert.

        Args:
            alert: Price alert to notify about.
        """
        flight = alert.flight

        if self._notifier is None:
            logger.info(
                f"Would notify: {flight.route} {flight.departure_time} "
                f"{flight.airline} at ${flight.price:,}"
            )
            return

        try:
            # Parse departure time to create datetime
            from datetime import datetime as dt
            hour, minute = map(int, flight.departure_time.split(":"))
            departure_dt = dt.combine(
                flight.travel_date,
                time(hour, minute)
            )

            self._notifier.send_flight_alert(
                route=flight.route,
                price=flight.price,
                airline=flight.airline,
                departure=departure_dt,
                link=f"https://www.google.com/travel/flights",  # Generic link
                prev_price=alert.previous_price,
            )
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    def get_upcoming_dates(self) -> list[date]:
        """Get list of upcoming travel dates to check.

        Returns:
            List of Friday dates for upcoming weekends.
        """
        date_calculator = self._get_date_calculator()
        weekends = date_calculator.get_upcoming_weekends(weeks_ahead=self._weeks_ahead)
        return [w.outbound_date for w in weekends]

    def get_bridge_weekends(self) -> list[date]:
        """Get list of upcoming bridge weekends (puentes).

        Returns:
            List of Friday dates that are bridge weekends.
        """
        date_calculator = self._get_date_calculator()
        bridges = date_calculator.get_bridge_weekends(weeks_ahead=self._weeks_ahead)
        return [w.outbound_date for w in bridges]

    async def save_state(self) -> None:
        """Save state to persistence."""
        if self._state_manager:
            await self._state_manager.save()
