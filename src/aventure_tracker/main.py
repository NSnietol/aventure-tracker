"""Main orchestrator and CLI for Adventure Tracker."""

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from aventure_tracker.config import Settings
from aventure_tracker.infrastructure.notifier import TelegramNotifier
from aventure_tracker.infrastructure.state_manager import StateManager
from aventure_tracker.services.activity_tracker import (
    ActivityTrackerResult,
    ActivityTrackerService,
)
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
        print(f"  Alerts: {result.flights_result.alerts_generated}")

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
