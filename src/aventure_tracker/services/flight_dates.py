"""Flight date calculator for generating valid travel weekends."""

import logging
from datetime import date, time, timedelta
from pathlib import Path

from aventure_tracker.models.flight import TimeRange, WeekendTrip
from aventure_tracker.services.holidays import HolidayService

logger = logging.getLogger(__name__)

# Default time ranges based on user's travel pattern:
#
# OUTBOUND (BAQ → MDE):
#   - Thursday evening (18:00–23:59): arrive that night before the plan
#   - Friday morning/afternoon (00:00–16:00): arrive same day as departure
#
# RETURN (MDE → BAQ):
#   - Monday early morning (00:00–10:00): adventure ended Sunday in MDE (~8PM),
#     user flies home Monday morning
#   - Tuesday early morning (00:00–10:00): adventure ended Monday in MDE,
#     user flies home Tuesday morning
#
# NOTE: Sunday is NOT a valid return window by default.
# The only exception is a saturday-only adventure (no Sunday events), where
# a Sunday flight ≥ 11:00 is accepted. That exception is handled exclusively
# in _build_weekend_pairs() in main.py, NOT here.

# Thursday evening (18:00-23:59)
THURSDAY_EVENING = TimeRange(start=time(18, 0), end=time(23, 59))

# Friday morning/afternoon (00:00-16:00)
FRIDAY_DAYTIME = TimeRange(start=time(0, 0), end=time(16, 0))

# Monday early morning (00:00-10:00)
MONDAY_MORNING = TimeRange(start=time(0, 0), end=time(10, 0))

# Tuesday early morning (00:00-10:00) — used when adventure ends Monday in MDE
TUESDAY_MORNING = TimeRange(start=time(0, 0), end=time(10, 0))


class FlightDateCalculator:
    """Calculator for generating valid weekend trip dates.

    Uses HolidayService to detect bridge weekends (puentes) and generates
    WeekendTrip objects with appropriate time windows for flights.

    Attributes:
        holiday_service: Service for checking holidays.
    """

    def __init__(
        self,
        holiday_service: HolidayService | None = None,
        holidays_config_path: Path | None = None,
    ) -> None:
        """Initialize the flight date calculator.

        Args:
            holiday_service: Pre-configured holiday service. If None, creates one.
            holidays_config_path: Path to holidays.yaml (used if holiday_service is None).
        """
        if holiday_service is not None:
            self._holiday_service = holiday_service
        else:
            self._holiday_service = HolidayService(config_path=holidays_config_path)

    def get_upcoming_weekends(
        self,
        weeks_ahead: int = 8,
        from_date: date | None = None,
    ) -> list[WeekendTrip]:
        """Get upcoming weekend trips for the specified number of weeks.

        Args:
            weeks_ahead: Number of weeks to look ahead.
            from_date: Start date to search from. Defaults to today.

        Returns:
            List of WeekendTrip objects for each upcoming weekend.
        """
        if from_date is None:
            from_date = date.today()

        weekends: list[WeekendTrip] = []

        # Find the next Friday
        days_until_friday = (4 - from_date.weekday()) % 7
        if days_until_friday == 0 and from_date.weekday() != 4:
            days_until_friday = 7
        # If today is Friday but it's already late, start from next week
        if from_date.weekday() == 4:
            # Keep this Friday
            pass

        next_friday = from_date + timedelta(days=days_until_friday)

        for week in range(weeks_ahead):
            friday = next_friday + timedelta(weeks=week)
            weekend_trip = self._create_weekend_trip(friday)
            weekends.append(weekend_trip)

        logger.info(f"Generated {len(weekends)} upcoming weekends from {from_date}")
        return weekends

    def _create_weekend_trip(self, friday: date) -> WeekendTrip:
        """Create a WeekendTrip for a given Friday.

        Args:
            friday: The Friday of the weekend.

        Returns:
            WeekendTrip with appropriate dates and time ranges.
        """
        thursday = friday - timedelta(days=1)
        sunday = friday + timedelta(days=2)
        monday = friday + timedelta(days=3)

        is_bridge = self._holiday_service.is_bridge_weekend(friday)

        # Determine outbound options
        outbound_times = self._get_outbound_times(thursday, friday)
        outbound_date = self._get_outbound_date(thursday, friday)

        # Determine return options
        return_times = self._get_return_times(sunday, monday)
        return_date = self._get_return_date(sunday, monday)

        return WeekendTrip(
            outbound_date=outbound_date,
            return_date=return_date,
            is_bridge=is_bridge,
            outbound_times=outbound_times,
            return_times=return_times,
        )

    def _get_outbound_times(self, thursday: date, friday: date) -> list[TimeRange]:
        """Get valid outbound time ranges.

        The user prefers:
        - Thursday evening (18:00+) - arrive that night, sleep at destination
        - Friday before 4PM - arrive for afternoon/evening

        Args:
            thursday: Thursday before the weekend.
            friday: Friday of the weekend.

        Returns:
            List of valid time ranges for outbound flights.
        """
        times: list[TimeRange] = []

        # Thursday evening is always valid
        times.append(THURSDAY_EVENING)

        # Friday daytime is always valid
        times.append(FRIDAY_DAYTIME)

        return times

    def _get_return_times(self, sunday: date, monday: date) -> list[TimeRange]:
        """Get valid return time ranges.

        Return flights are Monday early morning (adventure ended Sunday in MDE)
        or Tuesday early morning (adventure ended Monday in MDE).

        Sunday is NOT included here — the only case where Sunday is valid
        (saturday-only adventure, flight ≥ 11:00) is handled in
        _build_weekend_pairs() in main.py.

        Args:
            sunday: Sunday of the weekend.
            monday: Monday after the weekend.

        Returns:
            List of valid time ranges for return flights.
        """
        return [MONDAY_MORNING, TUESDAY_MORNING]

    def _get_outbound_date(self, thursday: date, friday: date) -> date:
        """Get the primary outbound date.

        For regular weekends, Friday is the primary outbound date.
        Thursday evening is also valid but Friday is the anchor date.

        Args:
            thursday: Thursday before the weekend.
            friday: Friday of the weekend.

        Returns:
            Primary outbound date (Friday).
        """
        return friday

    def _get_return_date(self, sunday: date, monday: date) -> date:
        """Get the primary return date.

        Monday is the standard return date (adventure ends Sunday in MDE,
        user flies back Monday morning).

        Args:
            sunday: Sunday of the weekend.
            monday: Monday after the weekend.

        Returns:
            Primary return date (Monday).
        """
        return monday

    def get_bridge_weekends(
        self,
        weeks_ahead: int = 52,
        from_date: date | None = None,
    ) -> list[WeekendTrip]:
        """Get only bridge weekends (puentes) from upcoming weekends.

        Args:
            weeks_ahead: Number of weeks to look ahead.
            from_date: Start date to search from. Defaults to today.

        Returns:
            List of WeekendTrip objects that are bridge weekends.
        """
        all_weekends = self.get_upcoming_weekends(weeks_ahead, from_date)
        return [w for w in all_weekends if w.is_bridge]

    def is_valid_outbound_flight(
        self,
        flight_date: date,
        flight_time: time,
        weekend: WeekendTrip,
    ) -> bool:
        """Check if a flight is valid for outbound travel.

        Args:
            flight_date: Date of the flight.
            flight_time: Departure time of the flight.
            weekend: The weekend trip to check against.

        Returns:
            True if the flight is valid for outbound travel.
        """
        thursday = weekend.outbound_date - timedelta(days=1)
        friday = weekend.outbound_date

        # Check if date is Thursday or Friday of this weekend
        if flight_date == thursday:
            return THURSDAY_EVENING.contains(flight_time)
        elif flight_date == friday:
            return FRIDAY_DAYTIME.contains(flight_time)

        return False

    def is_valid_return_flight(
        self,
        flight_date: date,
        flight_time: time,
        weekend: WeekendTrip,
    ) -> bool:
        """Check if a flight is valid for return travel.

        Note: Sunday validity depends on adventure context and is handled
        by _build_weekend_pairs() in main.py, not here.
        This method checks Monday and Tuesday only.

        Args:
            flight_date: Date of the flight.
            flight_time: Departure time of the flight.
            weekend: The weekend trip to check against.

        Returns:
            True if the flight is valid for return travel.
        """
        monday = weekend.return_date
        tuesday = monday + timedelta(days=1)

        if flight_date == monday:
            return MONDAY_MORNING.contains(flight_time)
        elif flight_date == tuesday:
            return TUESDAY_MORNING.contains(flight_time)

        return False
