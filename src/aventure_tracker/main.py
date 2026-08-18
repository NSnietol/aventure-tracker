"""Main orchestrator and CLI for Adventure Tracker."""

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path

from aventure_tracker.config import Settings
from aventure_tracker.infrastructure.email_notifier import EmailNotifier
from aventure_tracker.infrastructure.state_manager import StateManager
from aventure_tracker.services.events.activity_service import (
    ActivityTrackerResult,
    ActivityTrackerService,
)
from aventure_tracker.services.flights.calendar import (
    FlightCalendarDisplay,
)
from aventure_tracker.services.flights.dates import FlightDateCalculator
from aventure_tracker.services.flights.matcher import EventMatcher
from aventure_tracker.services.flights.tracker import (
    FlightTrackerResult,
    FlightTrackerService,
)
from aventure_tracker.services.shared.holidays import HolidayService

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
        self._email_notifier: EmailNotifier | None = None
        self._flight_tracker: FlightTrackerService | None = None
        self._activity_tracker: ActivityTrackerService | None = None
        self._calendar_display: FlightCalendarDisplay | None = None

        self._logger = logging.getLogger(__name__)

    def _setup_logging(self) -> None:
        """Configure logging based on settings."""

        log_level = getattr(logging, self._settings.log_level.upper(), logging.INFO)

        # Use Colombia time (UTC-5) for log timestamps
        _colombia_offset = -5 * 3600  # seconds

        class ColombiaFormatter(logging.Formatter):
            def converter(self, timestamp: float):  # type: ignore[override]
                import datetime

                return datetime.datetime.fromtimestamp(
                    timestamp,
                    tz=datetime.timezone(datetime.timedelta(hours=-5)),
                ).timetuple()

        formatter = ColombiaFormatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S Col",
        )

        handler = logging.StreamHandler()
        handler.setFormatter(formatter)

        root = logging.getLogger()
        root.setLevel(log_level)
        # Remove existing handlers to avoid duplicate output
        root.handlers.clear()
        root.addHandler(handler)

    async def _init_infrastructure(self) -> None:
        """Initialize infrastructure components.

        - In CI (GitHub Actions): Use Gist for state persistence
        - In local: Skip Gist, use local YAML files only
        """
        # State manager ONLY in CI environment
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
                self._state_manager.read()  # Load initial state
                self._logger.info("State manager initialized (CI mode)")
            except Exception as e:
                self._logger.warning(
                    f"Gist state manager failed: {e}. Continuing without remote state."
                )
                self._state_manager = None
        else:
            self._logger.info("Local mode - using local YAML storage only")

        # Email notifier via Resend (if configured)
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
        """Initialize tracker services."""
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
                destinations_config_path=self._settings.get_destinations_path(),
                state_manager=self._state_manager,
                notifier=None,
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
                    # Step 1: Process new inbox images → update extraction cache
                    self._logger.info("Step 1/3: Processing inbox images...")
                    self._run_inbox_extraction()

                    # Step 2: Search for cheap flights
                    self._logger.info("Step 2/3: Searching for cheap flights...")
                    flights_result = await self._flight_tracker.track_flights()
                    self._logger.info(
                        f"Flight tracking complete: {flights_result.alerts_generated} alerts"
                    )
                    errors.extend(flights_result.errors)

                    # Step 3: If cheap flights found, cross with events + send report
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
                    error = f"State Manager: Failed to save state: {e}"
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

        # Send error report if there were errors and email notifier is available
        if errors and self._email_notifier:
            try:
                routes_checked = flights_result.routes_checked if flights_result else 0
                run_url = os.environ.get("GITHUB_SERVER_URL", "")
                repo = os.environ.get("GITHUB_REPOSITORY", "")
                run_id = os.environ.get("GITHUB_RUN_ID", "")
                if run_url and repo and run_id:
                    run_url = f"{run_url}/{repo}/actions/runs/{run_id}"
                else:
                    run_url = ""

                self._email_notifier.send_error_report(
                    errors=errors,
                    mode=self._mode.value,
                    duration_seconds=duration,
                    routes_checked=routes_checked,
                    routes_total=2,  # BAQ→MDE + MDE→BAQ
                    alerts_generated=total_alerts,
                    run_url=run_url,
                )
                self._logger.info(f"Error report sent via email ({len(errors)} errors)")
            except Exception as e:
                self._logger.error(f"Failed to send error report email: {e}")

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

    def _run_inbox_extraction(self) -> None:
        """Process new images from inbox/ and update extraction cache.

        Runs the same logic as scripts/extract_events.py but inline,
        skipping images already in cache (content-based deduplication).
        """
        import os

        from aventure_tracker.services.extraction.cache import ExtractionCache
        from aventure_tracker.services.extraction.extractor import (
            ExtractionConfig,
            ImageEventExtractor,
            ModelProvider,
        )
        from aventure_tracker.services.extraction.organizer import detect_file_type

        inbox_path = Path("inbox")
        cache_path = Path("data/extraction_cache.yaml")

        if not inbox_path.exists():
            self._logger.info("No inbox/ directory found, skipping image extraction")
            return

        # Auto-detect provider
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        provider = ModelProvider.GEMINI if gemini_key else ModelProvider.OLLAMA

        cache = ExtractionCache(cache_path)
        config = ExtractionConfig(provider=provider)
        extractor = ImageEventExtractor(config=config)

        total_new = 0
        total_events = 0

        for agency_dir in sorted(inbox_path.iterdir()):
            if not agency_dir.is_dir() or agency_dir.name.startswith("."):
                continue
            agency = agency_dir.name

            for image_path in sorted(agency_dir.iterdir()):
                if image_path.name.startswith("."):
                    continue
                if not detect_file_type(image_path):
                    continue
                if cache.is_processed(image_path):
                    continue  # Already in cache, skip

                self._logger.info(f"  Extracting: {agency}/{image_path.name}")
                result = extractor.extract_from_image(image_path, agency)

                if result.success:
                    cache.add(result)
                    total_new += 1
                    total_events += len(result.events)
                    self._logger.info(
                        f"  → {len(result.events)} events extracted ({result.processing_time_ms}ms)"
                    )
                else:
                    self._logger.warning(f"  → Failed: {result.error}")

        if total_new > 0:
            self._logger.info(
                f"Inbox extraction complete: {total_new} new images, {total_events} events"
            )
        else:
            self._logger.info("Inbox extraction: all images already cached")

    async def _send_consolidated_report(
        self, flights_result: FlightTrackerResult
    ) -> None:
        """Build and send a consolidated weekend report, segmented by weekend.

        For each cheap outbound flight found:
        - Groups matching return flights for that same weekend window
        - Applies Sunday-adventure → Monday-return rule
        - Applies LATAM-preference rule (keep LATAM unless another is ≥100K cheaper)
        - Shows top 3 return options
        - Matches agency events for that window

        Args:
            flights_result: Result from flight tracker with price_alerts.
        """
        from aventure_tracker.services.flights.tracker import (
            FlightFound,
        )

        alerts = flights_result.price_alerts
        self._logger.info(
            f"Building consolidated report for {len(alerts)} cheap flight(s)"
        )

        # Separate by direction
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

        # Match events from extraction cache
        all_dates = [f.travel_date for f in outbound_all + return_all]
        matcher = EventMatcher(destinations_path=self._settings.get_destinations_path())
        matcher.load()
        weekend_matches = matcher.find_events_for_dates(all_dates)

        # Build WeekendPair list
        pairs = self._build_weekend_pairs(outbound_all, return_all, weekend_matches)

        # If no outbound found but return flights are cheap → report return-only pairs
        if not pairs and return_all:
            self._logger.info(
                f"No cheap outbound flights — reporting {len(return_all)} return-only option(s)"
            )
            pairs = self._build_return_only_pairs(return_all, weekend_matches)

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

        # Only notify if at least one weekend has events — no point alerting without plans
        pairs_with_events = [p for p in pairs if p.events]
        if not pairs_with_events:
            self._logger.info(
                "No events found for any cheap weekend — skipping notification"
            )
            return

        # Console fallback when no email notifier
        if not self._email_notifier:
            self._logger.info("=== WEEKEND REPORT (no notifier) ===")
            for p in pairs_with_events:
                self._logger.info(
                    f"Finde {p.date_label}{'  ⚠ sunday→monday' if p.sunday_adventure else ''}:"
                )
                self._logger.info(
                    f"  Ida:    {p.outbound.travel_date} {p.outbound.departure_time} {p.outbound.airline} ${p.outbound.price:,}"
                )
                for i, ro in enumerate(p.return_options):
                    tag = "✅ recomendado" if ro.is_recommended else f"alt {i}"
                    self._logger.info(
                        f"  Vuelta: {ro.flight.travel_date} {ro.flight.departure_time} {ro.flight.airline} ${ro.flight.price:,} [{tag}]"
                    )
                for ev in p.events[:4]:
                    self._logger.info(
                        f"  • {ev.name} ({ev.date_label}) {ev.price_formatted}"
                    )
            self._logger.info("===================================")
            return

        if self._email_notifier:
            self._email_notifier.send_weekend_report(pairs=pairs_with_events)

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    @staticmethod
    def _has_sunday_events(events: list, window_start: date, window_end: date) -> bool:
        """Check if any events fall on Sunday within the weekend window.

        If yes, return flights must be Monday (adventure runs all day Sunday).

        Args:
            events: List of MatchedEvent for this window.
            window_start: First day of the window.
            window_end: Last day of the window.

        Returns:
            True if any event starts or spans a Sunday in this window.
        """
        from datetime import timedelta

        # Find all Sundays in the window
        sundays = set()
        current = window_start
        while current <= window_end:
            if current.weekday() == 6:  # Sunday
                sundays.add(current)
            current += timedelta(days=1)

        if not sundays:
            return False

        for ev in events:
            for sunday in sundays:
                if ev.date_start <= sunday <= ev.date_end:
                    return True
        return False

    def _build_weekend_pairs(
        self,
        outbound_all: list,
        return_all: list,
        weekend_matches: list,
    ) -> list:
        """Build WeekendPair list: one pair per cheap outbound flight.

        Return-day selection rules (in priority order):
        1. If events fall on Sunday (sunday_adventure=True):
               → return must be Monday. Sunday returns are blocked entirely.
               → if adventure ends Monday in MDE, return is Tuesday.
        2. If adventure is saturday-only (no Sunday events):
               → Sunday return ≥ 11:00 is allowed (group arrives MDE ~8PM
                 on Saturday, next morning is Sunday).
               → Monday return is also valid.
        3. Priority airline (LATAM) outbound → prefer same for return unless
           another airline is ≥100K cheaper.
        4. Show top 3 return options sorted by price.
        5. If no return found → still include pair (has_return=False).

        Window covers outbound_date through outbound_date + 5 days (Tue)
        to capture both Monday and Tuesday return flights.

        Args:
            outbound_all: All cheap outbound flights sorted by date.
            return_all: All tracked return flights sorted by date.
            weekend_matches: WeekendMatch objects with events per window.

        Returns:
            List of WeekendPair.
        """
        from datetime import time as dtime
        from datetime import timedelta

        from aventure_tracker.services.flights.tracker import ReturnOption, WeekendPair

        # Build a quick lookup: window_start → WeekendMatch
        match_by_window: dict = {}
        for m in weekend_matches:
            match_by_window[m.window_start] = m

        # Return flights indexed by date for fast lookup
        returns_by_date: dict = {}
        for f in return_all:
            returns_by_date.setdefault(f.travel_date, []).append(f)

        pairs = []

        for outbound in outbound_all:
            window_start = outbound.travel_date
            # Extend to Tuesday (+5) to capture tuesday-morning returns
            # when the adventure ends on Monday in MDE.
            window_end = window_start + timedelta(days=5)

            # Get events for this window
            match = match_by_window.get(window_start)
            events = match.events if match else []

            # Detect whether any event spans a Sunday in the window
            sunday_adv = self._has_sunday_events(events, window_start, window_end)

            # Collect candidate return flights within the window
            candidates = []
            current = window_start
            while current <= window_end:
                day_flights = returns_by_date.get(current, [])
                for f in day_flights:
                    weekday = f.travel_date.weekday()  # 0=Mon … 6=Sun

                    if weekday == 6:  # Sunday
                        if sunday_adv:
                            # Events on Sunday → Sunday return is blocked
                            self._logger.debug(
                                f"  Skipping Sunday return {f.travel_date} "
                                f"{f.airline} ${f.price:,} (sunday adventure active)"
                            )
                            continue
                        else:
                            # Saturday-only adventure → Sunday ≥ 11:00 allowed
                            try:
                                h, m = map(int, f.departure_time.split(":"))
                                if dtime(h, m) < dtime(11, 0):
                                    self._logger.debug(
                                        f"  Skipping Sunday return {f.travel_date} "
                                        f"{f.airline} {f.departure_time} (< 11:00)"
                                    )
                                    continue
                            except Exception:
                                pass  # Accept if time can't be parsed

                    candidates.append(f)
                current += timedelta(days=1)

            # Sort candidates by price
            candidates.sort(key=lambda f: f.price)

            # Apply LATAM preference rule:
            # If outbound is priority → keep priority return unless another is ≥100K cheaper
            priority_returns = [f for f in candidates if f.is_priority]
            non_priority_returns = [f for f in candidates if not f.is_priority]

            ordered: list = []
            if outbound.is_priority and priority_returns:
                best_priority = priority_returns[0]
                significant_saving = 100_000
                better_non_priority = [
                    f
                    for f in non_priority_returns
                    if best_priority.price - f.price >= significant_saving
                ]
                if better_non_priority:
                    ordered = (
                        better_non_priority
                        + [best_priority]
                        + [
                            f
                            for f in non_priority_returns
                            if f not in better_non_priority
                        ]
                    )
                else:
                    ordered = [best_priority] + non_priority_returns
            else:
                ordered = candidates

            # Deduplicate by flight_id, keep top 3
            seen_ids: set[str] = set()
            top3: list = []
            for f in ordered:
                if f.flight_id not in seen_ids and len(top3) < 3:
                    top3.append(f)
                    seen_ids.add(f.flight_id)

            # Build ReturnOption list
            return_options: list[ReturnOption] = []
            priority_price = next((f.price for f in top3 if f.is_priority), None)
            for i, f in enumerate(top3):
                savings = (
                    (priority_price - f.price)
                    if priority_price and not f.is_priority
                    else None
                )
                return_options.append(
                    ReturnOption(
                        flight=f,
                        is_recommended=(i == 0),
                        savings_vs_priority=savings,
                    )
                )

            pairs.append(
                WeekendPair(
                    window_start=window_start,
                    window_end=window_end,
                    outbound=outbound,
                    return_options=return_options,
                    events=events,
                    sunday_adventure=sunday_adv,
                )
            )

        return pairs

    def _build_return_only_pairs(
        self,
        return_all: list,
        weekend_matches: list,
    ) -> list:
        """Build WeekendPair list when only return flights are cheap (no cheap outbound).

        Creates one pair per return flight showing the cheap return option
        and matching events for that weekend window.

        Args:
            return_all: Cheap return flights sorted by date.
            weekend_matches: WeekendMatch objects with events per window.

        Returns:
            List of WeekendPair (outbound will be None-like, return is the alert).
        """
        from datetime import timedelta

        from aventure_tracker.services.flights.tracker import ReturnOption, WeekendPair

        match_by_window: dict = {}
        for m in weekend_matches:
            match_by_window[m.window_start] = m

        pairs = []
        seen_windows: set = set()

        for ret_flight in return_all:
            # Window: return date - 4 days (approx Thu of that weekend)
            window_start = ret_flight.travel_date - timedelta(days=4)
            if window_start in seen_windows:
                continue
            seen_windows.add(window_start)

            window_end = ret_flight.travel_date + timedelta(days=1)
            match = match_by_window.get(window_start)
            events = match.events if match else []

            # Wrap the return flight as a ReturnOption
            return_option = ReturnOption(
                flight=ret_flight,
                is_recommended=True,
                savings_vs_priority=None,
            )

            # Create a synthetic "outbound" placeholder pointing to same weekend
            # We reuse the return flight as the "anchor" for display
            pairs.append(
                WeekendPair(
                    window_start=window_start,
                    window_end=window_end,
                    outbound=ret_flight,  # anchor for date/window only
                    return_options=[return_option],
                    events=events,
                    sunday_adventure=self._has_sunday_events(
                        events, window_start, window_end
                    ),
                    return_only=True,
                )
            )

        return pairs

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
        print("\nFlights:")
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
        print("\nActivities:")
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
