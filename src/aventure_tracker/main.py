"""Adventure Tracker orchestrator — coordinates services and CLI entry point."""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from aventure_tracker.config import Settings
from aventure_tracker.infrastructure.email_notifier import EmailNotifier
from aventure_tracker.infrastructure.state_manager import StateManager
from aventure_tracker.models.orchestrator import OrchestratorResult, RunMode

# Re-exported for backward compatibility
__all__ = [
    "AdventureOrchestrator",
    "OrchestratorResult",
    "RunMode",
    "async_main",
    "create_parser",
    "main",
    "DEFAULT_WEEKS_AHEAD",
]
from aventure_tracker.services.events.activity_service import (
    ActivityTrackerResult,
    ActivityTrackerService,
)
from aventure_tracker.services.extraction.inbox_processor import run_inbox_extraction
from aventure_tracker.services.flights.calendar import FlightCalendarDisplay
from aventure_tracker.services.flights.dates import FlightDateCalculator
from aventure_tracker.services.flights.matcher import EventMatcher
from aventure_tracker.services.flights.tracker import (
    FlightTrackerResult,
    FlightTrackerService,
)
from aventure_tracker.services.flights.weekend_pairs import (
    build_return_only_pairs,
    build_weekend_pairs,
)
from aventure_tracker.services.shared.holidays import HolidayService

DEFAULT_WEEKS_AHEAD = 10


class AdventureOrchestrator:
    """Coordinates flight and activity tracking services.

    Initializes infrastructure, delegates work to services, and sends
    notifications. Does not contain domain logic.

    Args:
        settings: Application settings (uses global Settings() if None).
        mode: Execution mode.
        weeks_ahead: Weeks ahead to check for flights (default: 10).
        max_posts_per_account: Max posts per account for activity tracker.
        show_calendar: Whether to display the flight calendar after tracking.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        mode: RunMode = RunMode.ALL,
        weeks_ahead: int = DEFAULT_WEEKS_AHEAD,
        max_posts_per_account: int = 10,
        show_calendar: bool = False,
    ) -> None:
        self._settings = settings or Settings()
        self._mode = mode
        self._weeks_ahead = weeks_ahead
        self._max_posts = max_posts_per_account
        self._show_calendar = show_calendar

        self._state_manager: StateManager | None = None
        self._email_notifier: EmailNotifier | None = None
        self._flight_tracker: FlightTrackerService | None = None
        self._activity_tracker: ActivityTrackerService | None = None
        self._calendar_display: FlightCalendarDisplay | None = None

        self._logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_logging(self) -> None:
        """Configure logging with Colombia-timezone timestamps."""
        log_level = getattr(logging, self._settings.log_level.upper(), logging.INFO)

        class ColombiaFormatter(logging.Formatter):
            def converter(self, timestamp: float):  # type: ignore[override]
                import datetime as _dt

                return _dt.datetime.fromtimestamp(
                    timestamp,
                    tz=_dt.timezone(_dt.timedelta(hours=-5)),
                ).timetuple()

        formatter = ColombiaFormatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S Col",
        )
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root = logging.getLogger()
        root.setLevel(log_level)
        root.handlers.clear()
        root.addHandler(handler)

    async def _init_infrastructure(self) -> None:
        """Initialize Gist state manager and email notifier."""
        if (
            self._settings.is_ci
            and self._settings.gist_id
            and self._settings.gist_token
        ):
            try:
                self._state_manager = StateManager(
                    gist_id=self._settings.gist_id,
                    token=self._settings.gist_token,
                )
                self._state_manager.read()
                self._logger.info("State manager initialized (CI mode)")
            except Exception as e:
                self._logger.warning(
                    f"Gist state manager failed: {e}. Continuing without remote state."
                )
                self._state_manager = None
        else:
            self._logger.info("Local mode - using local YAML storage only")

        if self._settings.resend_api_key and self._settings.email_to:
            if "your_" not in self._settings.resend_api_key.lower():
                self._email_notifier = EmailNotifier(
                    api_key=self._settings.resend_api_key,
                    to_email=self._settings.email_to,
                )
                self._logger.info(
                    f"Email notifier initialized → {self._settings.email_to}"
                )

    def _init_trackers(self) -> None:
        """Instantiate tracker services based on run mode."""
        if self._mode in (RunMode.ALL, RunMode.FLIGHTS, RunMode.CALENDAR):
            self._flight_tracker = FlightTrackerService(
                routes_config_path=self._settings.get_routes_path(),
                holidays_config_path=self._settings.get_holidays_path(),
                state_manager=self._state_manager,
                notifier=None,
                weeks_ahead=self._weeks_ahead,
                settings=self._settings,
            )
            self._logger.info("Flight tracker initialized")

            if self._mode in (RunMode.FLIGHTS, RunMode.CALENDAR) or self._show_calendar:
                holiday_service = HolidayService(
                    config_path=self._settings.get_holidays_path()
                )
                self._calendar_display = FlightCalendarDisplay(
                    date_calculator=FlightDateCalculator(
                        holiday_service=holiday_service
                    ),
                    weeks_ahead=self._weeks_ahead,
                )
                self._logger.info("Flight calendar display initialized")

        if self._mode in (RunMode.ALL, RunMode.ACTIVITIES):
            self._activity_tracker = ActivityTrackerService(
                accounts_config_path=self._settings.get_accounts_path(),
                destinations_config_path=self._settings.get_destinations_path(),
                state_manager=self._state_manager,
                notifier=None,
                use_ocr=True,
                max_posts_per_account=self._max_posts,
            )
            self._logger.info("Activity tracker initialized")

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def run(self) -> OrchestratorResult:
        """Run the adventure tracker and return combined results."""
        self._setup_logging()
        start_time = datetime.now()
        self._logger.info(f"Starting Adventure Tracker in {self._mode.value} mode")

        errors: list[str] = []
        flights_result: FlightTrackerResult | None = None
        activities_result: ActivityTrackerResult | None = None

        try:
            await self._init_infrastructure()
            self._init_trackers()

            if self._mode == RunMode.CALENDAR:
                self._show_flight_calendar()
                return OrchestratorResult(
                    mode=self._mode,
                    flights_result=None,
                    activities_result=None,
                    total_alerts=0,
                    total_notifications=0,
                    errors=[],
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                )

            if self._flight_tracker:
                try:
                    self._logger.info("Step 1/3: Processing inbox images...")
                    run_inbox_extraction(
                        inbox_path=Path("inbox"),
                        cache_path=Path("data/extraction_cache.yaml"),
                    )

                    self._logger.info("Step 2/3: Searching for cheap flights...")
                    flights_result = await self._flight_tracker.track_flights()
                    self._logger.info(
                        f"Flight tracking complete: {flights_result.alerts_generated} alerts"
                    )
                    errors.extend(flights_result.errors)

                    if flights_result.price_alerts:
                        self._logger.info("Step 3/3: Building consolidated report...")
                        await self._send_consolidated_report(flights_result)
                        if self._email_notifier:
                            flights_result.notifications_sent = 1
                    else:
                        self._logger.info("Step 3/3: No cheap flights — no report sent")

                except Exception as e:
                    error = f"[{type(e).__name__}] Flight tracker failed: {e}"
                    self._logger.error(error, exc_info=True)
                    errors.append(error)

            if self._show_calendar and self._calendar_display:
                self._show_flight_calendar()

            if self._activity_tracker:
                try:
                    self._logger.info("Running activity tracker...")
                    since = (
                        datetime.now() - timedelta(hours=24)
                        if self._settings.is_ci
                        else None
                    )
                    activities_result = await self._activity_tracker.track_activities(
                        since=since
                    )
                    self._logger.info(
                        f"Activity tracking complete: {activities_result.alerts_generated} alerts"
                    )
                    errors.extend(activities_result.errors)
                except Exception as e:
                    errors.append(f"Activity tracker failed: {e}")
                    self._logger.error(errors[-1])

            if self._state_manager:
                try:
                    self._state_manager.write()
                    self._logger.info("State saved successfully")
                except Exception as e:
                    errors.append(f"State Manager: Failed to save state: {e}")
                    self._logger.error(errors[-1])

        except Exception as e:
            errors.append(f"Orchestrator failed: {e}")
            self._logger.error(errors[-1])

        total_alerts = (flights_result.alerts_generated if flights_result else 0) + (
            activities_result.alerts_generated if activities_result else 0
        )
        total_notifications = (
            flights_result.notifications_sent if flights_result else 0
        ) + (activities_result.notifications_sent if activities_result else 0)
        duration = (datetime.now() - start_time).total_seconds()

        if errors and self._email_notifier:
            self._send_error_report(errors, flights_result, total_alerts, duration)

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

    # ------------------------------------------------------------------
    # Private helpers — coordination only, no domain logic
    # ------------------------------------------------------------------

    async def _send_consolidated_report(
        self, flights_result: FlightTrackerResult
    ) -> None:
        """Build weekend pairs and send email report."""
        from aventure_tracker.services.flights.tracker import FlightFound

        alerts = flights_result.price_alerts
        self._logger.info(
            f"Building consolidated report for {len(alerts)} cheap flight(s)"
        )

        outbound_all: list[FlightFound] = []
        return_all: list[FlightFound] = []
        for alert in alerts:
            f = alert.flight
            if (
                "BAQ" in f.route
                and "MDE" in f.route
                and f.route.index("BAQ") < f.route.index("MDE")
            ):
                outbound_all.append(f)
            else:
                return_all.append(f)

        outbound_all.sort(key=lambda x: (x.travel_date, x.departure_time))
        return_all.sort(key=lambda x: (x.travel_date, x.departure_time))

        all_dates = [f.travel_date for f in outbound_all + return_all]
        matcher = EventMatcher(destinations_path=self._settings.get_destinations_path())
        matcher.load()
        weekend_matches = matcher.find_events_for_dates(all_dates)

        pairs = build_weekend_pairs(outbound_all, return_all, weekend_matches)

        if not pairs and return_all:
            self._logger.info(
                f"No cheap outbound flights — reporting {len(return_all)} return-only option(s)"
            )
            pairs = build_return_only_pairs(return_all, weekend_matches)

        self._logger.info(f"Built {len(pairs)} weekend pair(s)")
        for p in pairs:
            ret = p.recommended_return
            ret_str = (
                f"{ret.flight.travel_date} {ret.flight.airline} ${ret.flight.price:,}"
                if ret
                else "no return"
            )
            self._logger.info(
                f"  {p.date_label}: {p.outbound.travel_date} {p.outbound.airline} "
                f"${p.outbound.price:,} → {ret_str} "
                f"{'[sunday adventure→monday]' if p.sunday_adventure else ''}"
            )

        pairs_with_events = [p for p in pairs if p.events]
        if not pairs_with_events:
            self._logger.info(
                "No events found for any cheap weekend — skipping notification"
            )
            return

        if not self._email_notifier:
            self._log_report_to_console(pairs_with_events)
            return

        self._email_notifier.send_weekend_report(pairs=pairs_with_events)

    def _log_report_to_console(self, pairs: list) -> None:
        """Fallback: log the weekend report to console when no email notifier."""
        self._logger.info("=== WEEKEND REPORT (no notifier) ===")
        for p in pairs:
            self._logger.info(
                f"Finde {p.date_label}{'  ⚠ sunday→monday' if p.sunday_adventure else ''}:"
            )
            self._logger.info(
                f"  Ida:    {p.outbound.travel_date} {p.outbound.departure_time} "
                f"{p.outbound.airline} ${p.outbound.price:,}"
            )
            for i, ro in enumerate(p.return_options):
                tag = "✅ recomendado" if ro.is_recommended else f"alt {i}"
                self._logger.info(
                    f"  Vuelta: {ro.flight.travel_date} {ro.flight.departure_time} "
                    f"{ro.flight.airline} ${ro.flight.price:,} [{tag}]"
                )
            for ev in p.events[:4]:
                self._logger.info(
                    f"  • {ev.name} ({ev.date_label}) {ev.price_formatted}"
                )
        self._logger.info("===================================")

    def _send_error_report(
        self,
        errors: list[str],
        flights_result: FlightTrackerResult | None,
        total_alerts: int,
        duration: float,
    ) -> None:
        """Send error report email, building the GitHub Actions URL if available."""
        try:
            routes_checked = flights_result.routes_checked if flights_result else 0
            run_url_base = os.environ.get("GITHUB_SERVER_URL", "")
            repo = os.environ.get("GITHUB_REPOSITORY", "")
            run_id = os.environ.get("GITHUB_RUN_ID", "")
            run_url = (
                f"{run_url_base}/{repo}/actions/runs/{run_id}"
                if run_url_base and repo and run_id
                else ""
            )
            self._email_notifier.send_error_report(  # type: ignore[union-attr]
                errors=errors,
                mode=self._mode.value,
                duration_seconds=duration,
                routes_checked=routes_checked,
                routes_total=2,
                alerts_generated=total_alerts,
                run_url=run_url,
            )
            self._logger.info(f"Error report sent via email ({len(errors)} errors)")
        except Exception as e:
            self._logger.error(f"Failed to send error report email: {e}")

    def _show_flight_calendar(
        self,
        prices: dict | None = None,
        previous_prices: dict | None = None,
    ) -> None:
        """Display the flight price calendar in the console."""
        if not self._calendar_display or not self._flight_tracker:
            self._logger.warning("Calendar display or flight tracker not initialized")
            return
        try:
            routes = self._flight_tracker._load_routes()
            data = self._calendar_display.build_calendar_data(
                routes=routes.routes,
                prices=prices or {},
                previous_prices=previous_prices,
            )
            print("\n")
            self._calendar_display.display(data)
            print(self._calendar_display.render_summary(data))
            print()
        except Exception as e:
            self._logger.error(f"Failed to display calendar: {e}")


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def create_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="aventure-tracker",
        description="Track cheap flights and adventure activity events",
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
        "--calendar", action="store_true", help="Show flight calendar after tracking"
    )
    parser.add_argument(
        "--max-posts",
        "-p",
        type=int,
        default=10,
        help="Maximum posts per account (default: 10)",
    )
    parser.add_argument(
        "--config-dir",
        "-c",
        type=str,
        default="config",
        help="Path to configuration directory (default: config)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose (debug) logging"
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true", help="Run without sending notifications"
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    return parser


async def async_main(args: argparse.Namespace) -> int:
    """Async entry point — builds settings, runs orchestrator, prints summary."""
    log_level = "DEBUG" if args.verbose else "INFO"
    settings = Settings(config_dir=args.config_dir, log_level=log_level)

    if args.dry_run:
        settings = Settings(
            config_dir=args.config_dir,
            log_level=log_level,
            telegram_bot_token="",
            telegram_chat_id="",
        )

    orchestrator = AdventureOrchestrator(
        settings=settings,
        mode=RunMode(args.mode),
        weeks_ahead=args.weeks,
        max_posts_per_account=args.max_posts,
        show_calendar=args.calendar,
    )
    result = await orchestrator.run()

    print("\n" + "=" * 50)
    print("Adventure Tracker Summary")
    print("=" * 50)
    print(f"Mode: {result.mode.value}")
    print(f"Duration: {result.duration_seconds:.1f}s")
    print(f"Total Alerts: {result.total_alerts}")
    print(f"Notifications Sent: {result.total_notifications}")

    if result.flights_result:
        fr = result.flights_result
        print("\nFlights:")
        print(f"  Routes checked: {fr.routes_checked}")
        print(f"  Dates checked: {fr.dates_checked}")
        print(f"  Flights found: {fr.flights_found}")
        print(f"  Alerts: {fr.alerts_generated}")
        if fr.prices_found:
            print(f"\n  Flights tracked ({len(fr.prices_found)}):")
            current_route = None
            for flight in sorted(
                fr.prices_found,
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
        ar = result.activities_result
        print("\nActivities:")
        print(f"  Accounts checked: {ar.accounts_checked}")
        print(f"  Posts found: {ar.posts_found}")
        print(f"  Posts processed: {ar.posts_processed}")
        print(f"  Alerts: {ar.alerts_generated}")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors[:5]:
            print(f"  - {error}")
        if len(result.errors) > 5:
            print(f"  ... and {len(result.errors) - 5} more")

    print("=" * 50)
    return 0 if result.success else 1


def main() -> int:
    """CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
