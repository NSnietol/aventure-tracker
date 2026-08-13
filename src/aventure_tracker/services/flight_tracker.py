"""Flight tracker service for monitoring flight prices."""

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from aventure_tracker.infrastructure.notifier import TelegramNotifier
from aventure_tracker.infrastructure.state_manager import StateManager
from aventure_tracker.models.flight import FlightResult, RouteConfig, RoutesConfig
from aventure_tracker.scrapers.google_flights import GoogleFlightsScraper
from aventure_tracker.services.flight_dates import FlightDateCalculator
from aventure_tracker.services.flight_price_store import FlightPriceStore
from aventure_tracker.services.holidays import HolidayService

logger = logging.getLogger(__name__)


@dataclass
class PriceAlert:
    """Price alert for a flight route.

    Attributes:
        route: The flight route.
        travel_date: Date of travel.
        current_price: Current price found.
        previous_price: Previous price (if tracked).
        price_change: Change from previous price (negative = drop).
        price_change_pct: Percentage change.
        is_below_threshold: Whether price is below threshold.
        is_significant_drop: Whether drop exceeds configured percentage.
    """

    route: RouteConfig
    travel_date: date
    current_price: int
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
class PriceFound:
    """A price found during a tracking run.

    Attributes:
        route: Route string (e.g., "BAQ→MDE").
        travel_date: Date of travel.
        price: Price in COP.
    """

    route: str
    travel_date: date
    price: int


@dataclass
class FlightTrackerResult:
    """Result of a flight tracking run.

    Attributes:
        routes_checked: Number of routes checked.
        dates_checked: Number of dates checked.
        alerts_generated: Number of price alerts.
        notifications_sent: Number of notifications sent.
        prices_found: List of prices found during this run.
        errors: List of error messages.
    """

    routes_checked: int
    dates_checked: int
    alerts_generated: int
    notifications_sent: int
    prices_found: list[PriceFound]
    errors: list[str]


class FlightTrackerService:
    """Service for tracking flight prices and sending alerts.

    Orchestrates the flight scraping, price comparison, and notification
    process for configured routes and upcoming weekends.

    Attributes:
        routes_config_path: Path to routes.yaml configuration.
        holidays_config_path: Path to holidays.yaml configuration.
        weeks_ahead: Number of weeks to check for flights.
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
                dates_to_check = [
                    weekend.get_date_for_day(day) for day in route.search_days
                ]

                for travel_date in dates_to_check:
                    result.dates_checked += 1

                    try:
                        price = await scraper.get_cheapest_price(route, travel_date)

                        if price is None:
                            logger.info(f"  {route} {travel_date}: No price found")
                            continue

                        # Log the price found
                        logger.info(f"  {route} {travel_date}: ${price:,} COP")

                        # Track price in result
                        result.prices_found.append(
                            PriceFound(
                                route=str(route),
                                travel_date=travel_date,
                                price=price,
                            )
                        )

                        alert = self._create_alert(route, travel_date, price)

                        if alert.should_notify:
                            result.alerts_generated += 1
                            await self._send_notification(alert)
                            result.notifications_sent += 1

                        # Update state
                        self._update_price_state(route, travel_date, price)

                    except Exception as e:
                        error_msg = f"Error checking {route} on {travel_date}: {e}"
                        logger.error(error_msg)
                        result.errors.append(error_msg)

        logger.info(
            f"Flight tracking complete: {result.routes_checked} routes, "
            f"{result.dates_checked} dates, {result.alerts_generated} alerts"
        )

        # Save prices to local YAML store
        self._price_store.save()
        logger.info("Flight prices saved to local store")

        return result

    async def check_route(
        self,
        route: RouteConfig,
        travel_date: date,
    ) -> PriceAlert | None:
        """Check a specific route and date for price alerts.

        Args:
            route: Route configuration.
            travel_date: Date to check.

        Returns:
            PriceAlert if price found, None otherwise.
        """
        scraper = self._get_scraper()

        try:
            price = await scraper.get_cheapest_price(route, travel_date)

            if price is None:
                return None

            alert = self._create_alert(route, travel_date, price)
            self._update_price_state(route, travel_date, price)

            return alert

        except Exception as e:
            logger.error(f"Error checking {route}: {e}")
            return None

    def _create_alert(
        self,
        route: RouteConfig,
        travel_date: date,
        current_price: int,
    ) -> PriceAlert:
        """Create a price alert for a route.

        Args:
            route: Route configuration.
            travel_date: Travel date.
            current_price: Current price found.

        Returns:
            PriceAlert with comparison to previous price.
        """
        previous_price = self._get_previous_price(route, travel_date)

        price_change: int | None = None
        price_change_pct: float | None = None

        if previous_price is not None:
            price_change = current_price - previous_price
            if previous_price > 0:
                price_change_pct = round((price_change / previous_price) * 100, 1)

        is_below_threshold = current_price <= route.price_threshold
        is_significant_drop = (
            price_change_pct is not None
            and price_change_pct < 0
            and abs(price_change_pct) >= route.drop_percentage
        )

        return PriceAlert(
            route=route,
            travel_date=travel_date,
            current_price=current_price,
            previous_price=previous_price,
            price_change=price_change,
            price_change_pct=price_change_pct,
            is_below_threshold=is_below_threshold,
            is_significant_drop=is_significant_drop,
        )

    def _get_previous_price(
        self,
        route: RouteConfig,
        travel_date: date,
    ) -> int | None:
        """Get previous price from state.

        Args:
            route: Route configuration.
            travel_date: Travel date.

        Returns:
            Previous price or None if not tracked.
        """
        # First try local price store
        route_str = f"{route.origin}-{route.destination}"
        previous = self._price_store.get_previous_price(route_str, travel_date)
        if previous is not None:
            return previous

        # Fall back to state manager if configured
        if self._state_manager is None:
            return None

        route_key = route.get_route_key(travel_date)
        return self._state_manager.get_last_flight_price(route_key)

    def _update_price_state(
        self,
        route: RouteConfig,
        travel_date: date,
        price: int,
    ) -> None:
        """Update price in state.

        Args:
            route: Route configuration.
            travel_date: Travel date.
            price: Current price.
        """
        # Save to local price store
        route_str = f"{route.origin}-{route.destination}"
        self._price_store.set_price(route_str, travel_date, price)

        # Also update state manager if configured
        if self._state_manager is not None:
            route_key = route.get_route_key(travel_date)
            self._state_manager.set_flight_price(route_key, price)

    async def _send_notification(self, alert: PriceAlert) -> None:
        """Send notification for a price alert.

        Args:
            alert: Price alert to notify about.
        """
        if self._notifier is None:
            logger.info(f"Would notify: {alert.route} at ${alert.current_price:,}")
            return

        try:
            await self._notifier.send_flight_alert(
                route=str(alert.route),
                price=alert.current_price,
                previous_price=alert.previous_price,
                travel_date=alert.travel_date,
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
