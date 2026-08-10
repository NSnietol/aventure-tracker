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
class FlightTrackerResult:
    """Result of a flight tracking run.

    Attributes:
        routes_checked: Number of routes checked.
        dates_checked: Number of dates checked.
        alerts_generated: Number of price alerts.
        notifications_sent: Number of notifications sent.
        errors: List of error messages.
    """

    routes_checked: int
    dates_checked: int
    alerts_generated: int
    notifications_sent: int
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
    ) -> None:
        """Initialize the flight tracker service.

        Args:
            routes_config_path: Path to routes.yaml.
            holidays_config_path: Path to holidays.yaml.
            state_manager: StateManager for persistence (optional).
            notifier: TelegramNotifier for alerts (optional).
            scraper: GoogleFlightsScraper instance (optional).
            weeks_ahead: Number of weeks to check ahead.
        """
        self._routes_config_path = routes_config_path
        self._holidays_config_path = holidays_config_path
        self._state_manager = state_manager
        self._notifier = notifier
        self._scraper = scraper
        self._weeks_ahead = weeks_ahead

        self._routes: RoutesConfig | None = None
        self._date_calculator: FlightDateCalculator | None = None

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
            errors=[],
        )

        for route in routes.routes:
            logger.info(f"Checking route: {route}")
            result.routes_checked += 1

            for weekend in weekends:
                travel_date = weekend.outbound_date
                result.dates_checked += 1

                try:
                    price = await scraper.get_cheapest_price(route, travel_date)

                    if price is None:
                        logger.warning(f"No price found for {route} on {travel_date}")
                        continue

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
        if self._state_manager is None:
            return

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
