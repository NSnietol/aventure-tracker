"""Flight tracker service for monitoring flight prices."""

import logging
from dataclasses import dataclass
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
from aventure_tracker.services.flights.dates import FlightDateCalculator
from aventure_tracker.services.flights.price_store import FlightPriceStore
from aventure_tracker.services.shared.holidays import HolidayService

logger = logging.getLogger(__name__)

# Time filters by day of week
# IMPORTANT: These filters run BEFORE _build_weekend_pairs().
# - SUNDAY is intentionally absent: whether a Sunday return is valid
#   depends on the adventure context (saturday-only vs multi-day).
#   That decision is made in _build_weekend_pairs(), not here.
# - SATURDAY is absent: not a valid search day per business rules.
# - TUESDAY uses a wide early-morning window to cover the case where
#   the adventure ends Monday in MDE and the user flies home Tuesday.
TIME_FILTERS: dict[SearchDay, tuple[time, time]] = {
    SearchDay.THURSDAY: (time(18, 0), time(23, 59)),
    SearchDay.FRIDAY: (time(0, 0), time(16, 0)),
    SearchDay.MONDAY: (time(0, 0), time(10, 0)),
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
class ReturnOption:
    """A return flight option for a weekend pair.

    Attributes:
        flight: The return flight.
        is_recommended: Whether this is the recommended option.
            True for the best match given outbound airline and price rules.
        savings_vs_priority: COP saved vs the priority airline return (if any).
            Negative means this option is more expensive than priority.
    """

    flight: FlightFound
    is_recommended: bool = False
    savings_vs_priority: int | None = None


@dataclass
class WeekendPair:
    """Outbound flight paired with return options for a specific weekend.

    Rules applied:
    - If events fall on Sunday → return must be Monday (not Sunday)
    - If outbound is priority airline → prefer same for return unless
      another airline is ≥100K cheaper
    - Always expose top 3 return options sorted by price

    Attributes:
        window_start: First day of the weekend window (Thursday).
        window_end: Last day of the window (Monday).
        outbound: The cheap outbound flight that triggered the alert.
        return_options: Up to 3 return flight options, sorted by price.
            First entry is the recommended one (is_recommended=True).
        events: Agency events available this weekend.
        sunday_adventure: Whether events fall on Sunday (forces Monday return).
    """

    window_start: date
    window_end: date
    outbound: FlightFound
    return_options: list[ReturnOption]
    events: list  # list[MatchedEvent] — imported at runtime to avoid circular
    sunday_adventure: bool = False
    return_only: bool = (
        False  # True when only return flight is cheap (no cheap outbound)
    )

    @property
    def recommended_return(self) -> ReturnOption | None:
        """The recommended return option (first in list)."""
        return self.return_options[0] if self.return_options else None

    @property
    def alternative_returns(self) -> list[ReturnOption]:
        """Non-recommended return options (2nd and 3rd)."""
        return self.return_options[1:]

    @property
    def total_price(self) -> int | None:
        """Total price for outbound + recommended return."""
        if self.recommended_return:
            return self.outbound.price + self.recommended_return.flight.price
        return None

    @property
    def has_return(self) -> bool:
        """Whether at least one return option was found."""
        return len(self.return_options) > 0

    @property
    def date_label(self) -> str:
        """Human readable window label."""
        return (
            f"{self.window_start.strftime('%d')}-{self.window_end.strftime('%d %b %Y')}"
        )


@dataclass
class RoundTripResult:
    """A matched outbound+return pair from a round-trip search.

    Contains both legs as found in a single Google Flights round-trip search.
    The price is the combined total for both legs.

    Attributes:
        outbound: The outbound flight (e.g., BAQ→MDE on Thursday).
        return_flight: The return flight (e.g., MDE→BAQ on Monday).
        total_price: Combined price for both legs in COP.
        outbound_href: Full Google Flights URL with outbound flight encoded,
            used to navigate to the return screen.
    """

    outbound: FlightFound
    return_flight: FlightFound
    total_price: int
    outbound_href: str = ""

    @property
    def outbound_price_estimate(self) -> int:
        """Estimated outbound leg price (total / 2 — approximate)."""
        return self.total_price // 2

    @property
    def return_price_estimate(self) -> int:
        """Estimated return leg price (total / 2 — approximate)."""
        return self.total_price // 2


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
        price_alerts: List of PriceAlert for cheap flights (for orchestrator).
        errors: List of error messages.
    """

    routes_checked: int
    dates_checked: int
    flights_found: int
    alerts_generated: int
    notifications_sent: int
    prices_found: list[FlightFound]
    price_alerts: list[PriceAlert]
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
        settings: "object | None" = None,
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
            settings: Settings instance for env var overrides (optional).
        """
        self._routes_config_path = routes_config_path
        self._holidays_config_path = holidays_config_path
        self._state_manager = state_manager
        self._notifier = notifier
        self._scraper = scraper
        self._weeks_ahead = weeks_ahead
        self._settings = settings

        self._routes: RoutesConfig | None = None
        self._date_calculator: FlightDateCalculator | None = None

        # Initialize local price store
        self._price_store = FlightPriceStore(path=price_store_path)

    def _load_routes(self) -> RoutesConfig:
        """Load routes configuration, applying env var overrides from settings."""
        if self._routes is None:
            settings = self._settings if hasattr(self, "_settings") else None
            self._routes = RoutesConfig.from_yaml(
                self._routes_config_path, settings=settings
            )
            logger.info(f"Loaded {len(self._routes.routes)} routes")
            policy = self._routes.airline_policy
            logger.info(
                f"Airline policy: priority={policy.priority_airlines}, "
                f"bargain_threshold=${policy.bargain_threshold:,}, "
                f"extra_rules={len(policy.extra_airlines)}"
            )
            for route in self._routes.routes:
                logger.info(f"  {route}: price_threshold=${route.price_threshold:,}")
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

    def _is_valid_time_for_day(
        self, departure_time: str, search_day: SearchDay
    ) -> bool:
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

    def _should_track_flight(self, flight: FlightResult, route: RouteConfig) -> bool:
        """Determine if a flight should be tracked using AirlinePolicy.

        Delegates to the policy loaded from routes.yaml:
        1. Priority airlines (e.g. LATAM) → include if price ≤ route threshold
        2. Any airline if price ≤ bargain_threshold (110K COP default)
        3. Extra airline rules configured in routes.yaml or added at runtime

        Args:
            flight: The flight result.
            route: The route config (provides price_threshold).

        Returns:
            True if flight should be tracked.
        """
        routes = self._load_routes()
        policy = routes.airline_policy
        should, reason = policy.should_track(
            airline=flight.airline,
            price=flight.price,
            route_threshold=route.price_threshold,
        )
        if not should:
            logger.debug(f"    Skipping {flight.airline} ${flight.price:,}: {reason}")
        return should

    def _is_priority_airline(self, airline: str) -> bool:
        """Check if airline is a priority airline per policy."""
        routes = self._load_routes()
        return routes.airline_policy.is_priority(airline)

    def add_airline(self, name: str, max_price: int | None = None) -> None:
        """Add an airline rule at runtime without reloading config.

        Useful for adding airlines dynamically (e.g. from CLI flags or tests)
        without editing routes.yaml.

        Args:
            name: Airline name fragment (case-insensitive match).
            max_price: Max price in COP, or None to always include.
        """
        routes = self._load_routes()
        routes.airline_policy.add_airline(name, max_price)
        logger.info(f"Runtime airline rule added: {name} max_price={max_price}")

    async def track_flights(self) -> FlightTrackerResult:
        """Run the flight tracking process.

        Checks all configured routes for upcoming weekends and generates
        alerts for prices below threshold or significant drops.
        Routes with search_mode=round_trip are paired and searched together.

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
            price_alerts=[],
            errors=[],
        )

        from aventure_tracker.models.flight import SearchMode

        # Separate one-way and round-trip routes
        oneway_routes = [
            r for r in routes.routes if r.search_mode == SearchMode.ONE_WAY
        ]
        rt_routes = [r for r in routes.routes if r.search_mode == SearchMode.ROUND_TRIP]

        # Process one-way routes (existing logic)
        for route in oneway_routes:
            await self._track_oneway_route(route, weekends, scraper, result)

        # Process round-trip route pairs
        # Pair BAQ→MDE with MDE→BAQ by matching origin/destination
        processed_rt: set[str] = set()
        for outbound_route in rt_routes:
            key = f"{outbound_route.origin}-{outbound_route.destination}"
            if key in processed_rt:
                continue
            # Find the matching return route
            return_route = next(
                (
                    r
                    for r in rt_routes
                    if r.origin == outbound_route.destination
                    and r.destination == outbound_route.origin
                ),
                None,
            )
            if return_route is None:
                logger.warning(
                    f"No return route found for {outbound_route} — skipping round-trip"
                )
                continue

            processed_rt.add(key)
            processed_rt.add(f"{return_route.origin}-{return_route.destination}")

            await self._track_round_trip_pair(
                outbound_route, return_route, weekends, scraper, result
            )

        logger.info(
            f"Flight tracking complete: {result.routes_checked} routes, "
            f"{result.dates_checked} dates, {result.flights_found} flights, "
            f"{result.alerts_generated} alerts"
        )
        self._price_store.save()
        logger.info("Flight prices saved to local store")
        return result

    async def _track_oneway_route(
        self,
        route: "RouteConfig",
        weekends: list,
        scraper: "GoogleFlightsScraper",
        result: "FlightTrackerResult",
    ) -> None:
        """Track a single one-way route across all upcoming weekends."""
        logger.info(f"Checking route: {route}")
        result.routes_checked += 1

        for weekend in weekends:
            for search_day in route.search_days:
                travel_date = weekend.get_date_for_day(search_day)
                result.dates_checked += 1

                try:
                    flights = await scraper.scrape(route, travel_date)

                    if not flights:
                        logger.info(
                            f"  {route} {travel_date} ({search_day.value}): No flights found"
                        )
                        continue

                    for flight in flights:
                        departure_time_str = flight.departure_time.strftime("%H:%M")
                        if not self._is_valid_time_for_day(
                            departure_time_str, search_day
                        ):
                            logger.debug(
                                f"    Skipping {flight.airline} {departure_time_str}: "
                                f"outside time window for {search_day.value}"
                            )
                            continue

                        if not self._should_track_flight(flight, route):
                            continue

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

                        priority_marker = "★" if is_priority else ""
                        logger.info(
                            f"  {route} {travel_date} {departure_time_str} "
                            f"{flight.airline}{priority_marker}: ${flight.price:,} COP"
                        )

                        result.flights_found += 1
                        result.prices_found.append(flight_found)

                        self._price_store.set_flight_price(
                            route=route_str,
                            travel_date=travel_date,
                            departure_time=departure_time_str,
                            airline=flight.airline,
                            price=flight.price,
                        )

                        alert = self._create_alert(flight_found, route)
                        if alert.should_notify:
                            result.alerts_generated += 1
                            result.price_alerts.append(alert)

                except Exception as e:
                    error_type = type(e).__name__
                    error_msg = f"[{error_type}] {route} on {travel_date}: {e}"
                    logger.error(error_msg, exc_info=True)
                    result.errors.append(error_msg)

    async def _track_round_trip_pair(
        self,
        outbound_route: "RouteConfig",
        return_route: "RouteConfig",
        weekends: list,
        scraper: "GoogleFlightsScraper",
        result: "FlightTrackerResult",
    ) -> None:
        """Track a paired outbound+return route using round-trip search."""
        logger.info(f"{'=' * 60}")
        logger.info(f"  ROUND-TRIP: {outbound_route} ↔ {return_route.origin}")
        logger.info(f"{'=' * 60}")
        result.routes_checked += 2  # counts both legs

        for weekend in weekends:
            for outbound_day in outbound_route.search_days:
                outbound_date = weekend.get_date_for_day(outbound_day)

                for return_day in outbound_route.return_days:
                    return_date = weekend.get_date_for_day(return_day)
                    result.dates_checked += 1

                    try:
                        pairs = await scraper.scrape_round_trip(
                            outbound_route=outbound_route,
                            outbound_date=outbound_date,
                            return_date=return_date,
                            return_route=return_route,
                        )

                        if not pairs:
                            logger.info(
                                f"  RT {outbound_route} {outbound_date}↔{return_date}: "
                                f"No pairs found"
                            )
                            continue

                        threshold = outbound_route.effective_round_trip_threshold

                        for pair in pairs:
                            total = pair.get("total_price", 0)
                            if total <= 0 or total > threshold:
                                logger.debug(
                                    f"    Skipping RT pair: total ${total:,} > "
                                    f"threshold ${threshold:,}"
                                )
                                continue

                            out = pair["outbound"]
                            returns = pair.get("return_options", [])

                            out_time = out.get("departure_time", "")
                            if not self._is_valid_time_for_day(out_time, outbound_day):
                                logger.debug(
                                    f"    Skipping outbound {out.get('airline')} "
                                    f"{out_time}: outside time window"
                                )
                                continue

                            is_priority = self._is_priority_airline(
                                out.get("airline", "")
                            )

                            outbound_found = FlightFound(
                                flight_id=(
                                    f"RT_{outbound_route.origin}-{outbound_route.destination}"
                                    f"_{outbound_date}_{out_time}_{out.get('airline', '')}"
                                ),
                                route=str(outbound_route),
                                travel_date=outbound_date,
                                departure_time=out_time,
                                airline=out.get("airline", "Unknown"),
                                price=total,  # total round-trip price
                                is_priority=is_priority,
                            )

                            priority_marker = "★" if is_priority else ""
                            logger.info(
                                f"  RT {outbound_route} {outbound_date} {out_time} "
                                f"{out.get('airline')}{priority_marker} ↔ {return_date}: "
                                f"${total:,} COP total ({len(returns)} return options)"
                            )

                            result.flights_found += 1
                            result.prices_found.append(outbound_found)

                            alert = self._create_alert(outbound_found, outbound_route)
                            if alert.should_notify:
                                result.alerts_generated += 1
                                result.price_alerts.append(alert)

                    except Exception as e:
                        error_type = type(e).__name__
                        error_msg = (
                            f"[{error_type}] RT {outbound_route} "
                            f"{outbound_date}↔{return_date}: {e}"
                        )
                        logger.error(error_msg, exc_info=True)
                        result.errors.append(error_msg)

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
            departure_dt = dt.combine(flight.travel_date, time(hour, minute))

            self._notifier.send_flight_alert(
                route=flight.route,
                price=flight.price,
                airline=flight.airline,
                departure=departure_dt,
                link="https://www.google.com/travel/flights",  # Generic link
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
