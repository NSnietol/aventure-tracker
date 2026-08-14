"""Main orchestrator and CLI for Adventure Tracker."""

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from aventure_tracker.config import Settings
from aventure_tracker.infrastructure.email_notifier import EmailNotifier
from aventure_tracker.infrastructure.notifier import TelegramNotifier
from aventure_tracker.infrastructure.state_manager import StateManager
from aventure_tracker.services.activity_tracker import (
    ActivityTrackerResult,
    ActivityTrackerService,
)
from aventure_tracker.services.event_matcher import EventMatcher
from aventure_tracker.services.flight_calendar import (
    FlightCalendarDisplay,
)
from aventure_tracker.services.flight_tracker import (
    FlightTrackerResult,
    FlightTrackerService,
)
from aventure_tracker.services.holidays import HolidayService
from aventure_tracker.services.flight_dates import FlightDateCalculator

# Default weeks ahead for flight calendar (user requested 2.5 months planning horizon)
DEFAULT_WEEKS_AHEAD = 10


class RunMode(Enum):
    """Execution mode for the tracker."""

    ALL = "all"
    FLIGHTS = "flights"
    ACTIVITIES = "activities"
    CALENDAR = "calendar"  # Show flight calendar only


@dataclass
class OrchestratorResult:
    """Result of a full orchestrator run.

    Attributes:
        mode: The execution mode that was run.
        flights_result: Flight tracking result (if run).
        activities_result: Activity tracking result (if run).
        total_alerts: Total alerts generated.
        total_notifications: Total notifications sent.
        errors: Combined errors from both trackers.
        duration_seconds: Total execution time.
    """

    mode: RunMode
    flights_result: FlightTrackerResult | None
    activities_result: ActivityTrackerResult | None
    total_alerts: int
    total_notifications: int
    errors: list[str]
    duration_seconds: float

    @property
    def success(self) -> bool:
        """Check if run completed without critical errors."""
        return len(self.errors) == 0


class AdventureOrchestrator:
    """Main orchestrator that coordinates flight and activity tracking.

    Provides the primary entry point for running the adventure tracker,
    managing state persistence, and coordinating notifications.

    Attributes:
        settings: Application settings.
        mode: Execution mode (all, flights, activities, calendar).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        mode: RunMode = RunMode.ALL,
        weeks_ahead: int = DEFAULT_WEEKS_AHEAD,
        max_posts_per_account: int = 10,
        show_calendar: bool = False,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            settings: Application settings (uses global if not provided).
            mode: Execution mode.
            weeks_ahead: Weeks ahead to check for flights (default: 10).
            max_posts_per_account: Max Instagram posts per account.
            show_calendar: Whether to display the flight calendar.
        """
        self._settings = settings or Settings()
        self._mode = mode
        self._weeks_ahead = weeks_ahead
        self._max_posts = max_posts_per_account
        self._show_calendar = show_calendar

        self._state_manager: StateManager | None = None
        self._notifier: TelegramNotifier | None = None
        self._email_notifier: EmailNotifier | None = None
        self._flight_tracker: FlightTrackerService | None = None
        self._activity_tracker: ActivityTrackerService | None = None
        self._calendar_display: FlightCalendarDisplay | None = None

        self._logger = logging.getLogger(__name__)

    def _setup_logging(self) -> None:
        """Configure logging based on settings."""
        log_level = getattr(logging, self._settings.log_level.upper(), logging.INFO)

        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    async def _init_infrastructure(self) -> None:
        """Initialize infrastructure components.
        
        - In CI (GitHub Actions): Use Gist for state persistence
        - In local: Skip Gist, use local YAML files only
        """
        # State manager ONLY in CI environment
        if self._settings.is_ci and self._settings.gist_id and self._settings.gist_token:
            try:
                self._state_manager = StateManager(
                    gist_id=self._settings.gist_id,
                    token=self._settings.gist_token,
                )
                self._state_manager.read()  # Load initial state
                self._logger.info("State manager initialized (CI mode)")
            except Exception as e:
                self._logger.warning(f"Gist state manager failed: {e}. Continuing without remote state.")
                self._state_manager = None
        else:
            self._logger.info("Local mode - using local YAML storage only")

        # Telegram notifier (if configured)
        if self._settings.telegram_bot_token and self._settings.telegram_chat_id:
            # Skip if placeholder values
            if "your_" not in self._settings.telegram_bot_token.lower():
                self._notifier = TelegramNotifier(
                    bot_token=self._settings.telegram_bot_token,
                    chat_id=self._settings.telegram_chat_id,
                )
                self._logger.info("Telegram notifier initialized")

        # Email notifier via Resend (if configured)
        if self._settings.resend_api_key and self._settings.email_to:
            if "your_" not in self._settings.resend_api_key.lower():
                self._email_notifier = EmailNotifier(
                    api_key=self._settings.resend_api_key,
                    to_email=self._settings.email_to,
                )
                self._logger.info(f"Email notifier initialized → {self._settings.email_to}")

    def _init_trackers(self) -> None:
        """Initialize tracker services."""
        if self._mode in (RunMode.ALL, RunMode.FLIGHTS, RunMode.CALENDAR):
            self._flight_tracker = FlightTrackerService(
                routes_config_path=self._settings.get_routes_path(),
                holidays_config_path=self._settings.get_holidays_path(),
                state_manager=self._state_manager,
                notifier=self._notifier,
                weeks_ahead=self._weeks_ahead,
            )
            self._logger.info("Flight tracker initialized")

            # Initialize calendar display for flights/calendar mode
            if self._mode in (RunMode.FLIGHTS, RunMode.CALENDAR) or self._show_calendar:
                holiday_service = HolidayService(
                    config_path=self._settings.get_holidays_path()
                )
                date_calculator = FlightDateCalculator(holiday_service=holiday_service)
                self._calendar_display = FlightCalendarDisplay(
                    date_calculator=date_calculator,
                    weeks_ahead=self._weeks_ahead,
                )
                self._logger.info("Flight calendar display initialized")

        if self._mode in (RunMode.ALL, RunMode.ACTIVITIES):
            self._activity_tracker = ActivityTrackerService(
                accounts_config_path=self._settings.get_accounts_path(),
                wishlist_config_path=self._settings.get_wishlist_path(),
                done_config_path=self._settings.get_done_path(),
                state_manager=self._state_manager,
                notifier=self._notifier,
                use_ocr=True,
                max_posts_per_account=self._max_posts,
            )
            self._logger.info("Activity tracker initialized")

    async def run(self) -> OrchestratorResult:
        """Run the adventure tracker.

        Executes flight and/or activity tracking based on mode,
        persists state, and returns combined results.

        Returns:
            OrchestratorResult with tracking statistics.
        """
        self._setup_logging()
        start_time = datetime.now()

        self._logger.info(f"Starting Adventure Tracker in {self._mode.value} mode")

        errors: list[str] = []
        flights_result: FlightTrackerResult | None = None
        activities_result: ActivityTrackerResult | None = None
        calendar_prices: dict = {}

        try:
            # Initialize infrastructure
            await self._init_infrastructure()
            self._init_trackers()

            # Calendar-only mode: just show the calendar template
            if self._mode == RunMode.CALENDAR:
                self._show_flight_calendar(calendar_prices)
                return OrchestratorResult(
                    mode=self._mode,
                    flights_result=None,
                    activities_result=None,
                    total_alerts=0,
                    total_notifications=0,
                    errors=[],
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                )

            # Run flight tracker
            if self._flight_tracker and self._mode != RunMode.CALENDAR:
                try:
                    self._logger.info("Running flight tracker...")
                    flights_result = await self._flight_tracker.track_flights()
                    self._logger.info(
                        f"Flight tracking complete: {flights_result.alerts_generated} alerts"
                    )
                    errors.extend(flights_result.errors)

                    # If cheap flights found, run event extraction + send consolidated report
                    if flights_result.price_alerts:
                        await self._send_consolidated_report(flights_result)
                        if self._notifier:
                            flights_result.notifications_sent = 1

                except Exception as e:
                    error = f"Flight tracker failed: {e}"
                    self._logger.error(error)
                    errors.append(error)

            # Show calendar after flight tracking if requested
            if self._show_calendar and self._calendar_display:
                self._show_flight_calendar(calendar_prices)

            # Run activity tracker
            if self._activity_tracker:
                try:
                    self._logger.info("Running activity tracker...")
                    # Only check posts from last 24 hours in CI
                    since = None
                    if self._settings.is_ci:
                        since = datetime.now() - timedelta(hours=24)

                    activities_result = await self._activity_tracker.track_activities(
                        since=since
                    )
                    self._logger.info(
                        f"Activity tracking complete: {activities_result.alerts_generated} alerts"
                    )
                    errors.extend(activities_result.errors)
                except Exception as e:
                    error = f"Activity tracker failed: {e}"
                    self._logger.error(error)
                    errors.append(error)

            # Save state
            if self._state_manager:
                try:
                    self._state_manager.write()
                    self._logger.info("State saved successfully")
                except Exception as e:
                    error = f"Failed to save state: {e}"
                    self._logger.error(error)
                    errors.append(error)

        except Exception as e:
            error = f"Orchestrator failed: {e}"
            self._logger.error(error)
            errors.append(error)

        # Calculate totals
        total_alerts = 0
        total_notifications = 0

        if flights_result:
            total_alerts += flights_result.alerts_generated
            total_notifications += flights_result.notifications_sent

        if activities_result:
            total_alerts += activities_result.alerts_generated
            total_notifications += activities_result.notifications_sent

        duration = (datetime.now() - start_time).total_seconds()

        result = OrchestratorResult(
            mode=self._mode,
            flights_result=flights_result,
            activities_result=activities_result,
            total_alerts=total_alerts,
            total_notifications=total_notifications,
            errors=errors,
            duration_seconds=duration,
        )

        self._logger.info(
            f"Adventure Tracker complete: {total_alerts} alerts, "
            f"{total_notifications} notifications, {duration:.1f}s"
        )

        return result

    async def _send_consolidated_report(
        self, flights_result: FlightTrackerResult
    ) -> None:
        """Build and send a consolidated weekend report.

        Runs event extraction from the cache, matches events to cheap flight
        dates, and sends a single Telegram message with flights + events.

        Args:
            flights_result: Result from flight tracker with price_alerts.
        """
        from aventure_tracker.services.flight_tracker import FlightFound

        alerts = flights_result.price_alerts
        self._logger.info(
            f"Building consolidated report for {len(alerts)} cheap flight(s)"
        )

        # Collect cheap flights by direction
        outbound: list[FlightFound] = []
        return_flights: list[FlightFound] = []
        cheap_dates = []

        for alert in alerts:
            f = alert.flight
            cheap_dates.append(f.travel_date)
            if "BAQ" in f.route and f.route.endswith("MDE"):
                outbound.append(f)
            else:
                return_flights.append(f)

        # Sort by date
        outbound.sort(key=lambda x: (x.travel_date, x.departure_time))
        return_flights.sort(key=lambda x: (x.travel_date, x.departure_time))

        # Match events from extraction cache
        matcher = EventMatcher(
            destinations_path=self._settings.get_destinations_path(),
        )
        matcher.load()
        weekend_matches = matcher.find_events_for_dates(cheap_dates)

        total_events = sum(len(m.events) for m in weekend_matches)
        self._logger.info(
            f"Found {total_events} matching events across "
            f"{len(weekend_matches)} weekend windows"
        )

        # Send single consolidated notification
        if self._notifier:
            self._notifier.send_weekend_report(
                outbound_flights=outbound,
                return_flights=return_flights,
                weekend_matches=weekend_matches,
            )
        if self._email_notifier:
            self._email_notifier.send_weekend_report(
                outbound_flights=outbound,
                return_flights=return_flights,
                weekend_matches=weekend_matches,
            )
        if not self._notifier and not self._email_notifier:
            # Log to console when no notifier configured
            self._logger.info("=== WEEKEND REPORT (no notifier) ===")
            if outbound:
                self._logger.info("Ida (BAQ→MDE):")
                for f in outbound:
                    self._logger.info(f"  {f.travel_date} {f.departure_time} {f.airline} ${f.price:,}")
            if return_flights:
                self._logger.info("Vuelta (MDE→BAQ):")
                for f in return_flights:
                    self._logger.info(f"  {f.travel_date} {f.departure_time} {f.airline} ${f.price:,}")
            for match in weekend_matches:
                if match.has_events:
                    self._logger.info(f"Planes {match.date_label}:")
                    for ev in match.events[:5]:
                        self._logger.info(f"  • {ev.name} ({ev.date_label}) {ev.price_formatted}")
            self._logger.info("===================================")

    def _show_flight_calendar(
        self,
        prices: dict[tuple, int] | None = None,
        previous_prices: dict[tuple, int] | None = None,
    ) -> None:
        """Display the flight calendar in the console.

        Args:
            prices: Dict of (date, route_str) -> price.
            previous_prices: Optional dict of previous prices for comparison.
        """
        if not self._calendar_display:
            self._logger.warning("Calendar display not initialized")
            return

        if not self._flight_tracker:
            self._logger.warning("Flight tracker not initialized")
            return

        try:
            # Get routes from config
            routes = self._flight_tracker._load_routes()

            # Build calendar data
            data = self._calendar_display.build_calendar_data(
                routes=routes.routes,
                prices=prices or {},
                previous_prices=previous_prices,
            )

            # Display calendar
            print("\n")
            self._calendar_display.display(data)

            # Show summary
            print(self._calendar_display.render_summary(data))
            print()

        except Exception as e:
            self._logger.error(f"Failed to display calendar: {e}")


def create_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        prog="aventure-tracker",
        description="Track cheap flights and Instagram adventure activities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  aventure-tracker                  # Run all trackers
  aventure-tracker --mode flights   # Only track flights
  aventure-tracker --mode activities # Only track activities
  aventure-tracker --mode calendar  # Show flight calendar only
  aventure-tracker --calendar       # Show calendar after tracking
  aventure-tracker --weeks 12       # Check 12 weeks ahead for flights
  aventure-tracker --verbose        # Enable debug logging
        """,
    )

    parser.add_argument(
        "--mode",
        "-m",
        type=str,
        choices=["all", "flights", "activities", "calendar"],
        default="all",
        help="Execution mode (default: all)",
    )

    parser.add_argument(
        "--weeks",
        "-w",
        type=int,
        default=DEFAULT_WEEKS_AHEAD,
        help=f"Weeks ahead to check for flights (default: {DEFAULT_WEEKS_AHEAD})",
    )

    parser.add_argument(
        "--calendar",
        action="store_true",
        help="Show flight calendar after tracking",
    )

    parser.add_argument(
        "--max-posts",
        "-p",
        type=int,
        default=10,
        help="Maximum posts per Instagram account (default: 10)",
    )

    parser.add_argument(
        "--config-dir",
        "-c",
        type=str,
        default="config",
        help="Path to configuration directory (default: config)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose (debug) logging",
    )

    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Run without sending notifications",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    return parser


async def async_main(args: argparse.Namespace) -> int:
    """Async main entry point.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    # Build settings from args
    settings = Settings(
        config_dir=args.config_dir,
        log_level="DEBUG" if args.verbose else "INFO",
    )

    # Parse mode
    mode = RunMode(args.mode)

    # Disable notifications for dry run
    if args.dry_run:
        settings = Settings(
            config_dir=args.config_dir,
            log_level="DEBUG" if args.verbose else "INFO",
            telegram_bot_token="",  # Disable notifications
            telegram_chat_id="",
        )

    # Create and run orchestrator
    orchestrator = AdventureOrchestrator(
        settings=settings,
        mode=mode,
        weeks_ahead=args.weeks,
        max_posts_per_account=args.max_posts,
        show_calendar=args.calendar,
    )

    result = await orchestrator.run()

    # Print summary
    print("\n" + "=" * 50)
    print("Adventure Tracker Summary")
    print("=" * 50)
    print(f"Mode: {result.mode.value}")
    print(f"Duration: {result.duration_seconds:.1f}s")
    print(f"Total Alerts: {result.total_alerts}")
    print(f"Notifications Sent: {result.total_notifications}")

    if result.flights_result:
        print(f"\nFlights:")
        print(f"  Routes checked: {result.flights_result.routes_checked}")
        print(f"  Dates checked: {result.flights_result.dates_checked}")
        print(f"  Flights found: {result.flights_result.flights_found}")
        print(f"  Alerts: {result.flights_result.alerts_generated}")

        if result.flights_result.prices_found:
            print(f"\n  Flights tracked ({len(result.flights_result.prices_found)}):")
            # Group by route for cleaner output
            current_route = None
            for flight in sorted(
                result.flights_result.prices_found,
                key=lambda x: (x.route, x.travel_date, x.departure_time),
            ):
                if flight.route != current_route:
                    current_route = flight.route
                    print(f"    {flight.route}:")
                priority = "★" if flight.is_priority else ""
                print(
                    f"      {flight.travel_date} {flight.departure_time} "
                    f"{flight.airline}{priority}: ${flight.price:,} COP"
                )

    if result.activities_result:
        print(f"\nActivities:")
        print(f"  Accounts checked: {result.activities_result.accounts_checked}")
        print(f"  Posts found: {result.activities_result.posts_found}")
        print(f"  Posts processed: {result.activities_result.posts_processed}")
        print(f"  Alerts: {result.activities_result.alerts_generated}")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors[:5]:  # Show first 5 errors
            print(f"  - {error}")
        if len(result.errors) > 5:
            print(f"  ... and {len(result.errors) - 5} more")

    print("=" * 50)

    return 0 if result.success else 1


def main() -> int:
    """CLI entry point.

    Returns:
        Exit code.
    """
    parser = create_parser()
    args = parser.parse_args()

    try:
        return asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
