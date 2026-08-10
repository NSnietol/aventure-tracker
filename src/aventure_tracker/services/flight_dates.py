"""Flight date calculator for generating valid travel weekends."""

import logging
from datetime import date, time, timedelta
from pathlib import Path

from aventure_tracker.models.flight import TimeRange, WeekendTrip
from aventure_tracker.services.holidays import HolidayService

logger = logging.getLogger(__name__)

# Default time ranges based on user's travel pattern:
# - Outbound: Thursday 6PM+ or Friday before 4PM
# - Return: Sunday 2PM+ or Monday before 10AM

# Thursday evening (18:00-23:59)
THURSDAY_EVENING = TimeRange(start=time(18, 0), end=time(23, 59))

# Friday morning/afternoon (00:00-16:00)
FRIDAY_DAYTIME = TimeRange(start=time(0, 0), end=time(16, 0))

# Sunday afternoon/evening (14:00-23:59)
SUNDAY_AFTERNOON = TimeRange(start=time(14, 0), end=time(23, 59))

# Monday early morning (00:00-10:00)
MONDAY_MORNING = TimeRange(start=time(0, 0), end=time(10, 0))


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

        The user prefers:
        - Sunday afternoon (2PM+) - if no late return routes available
        - Monday early morning (<10AM) - arrive back for work

        Some routes don't have late Sunday returns, so Monday early is preferred.

        Args:
            sunday: Sunday of the weekend.
            monday: Monday after the weekend.

        Returns:
            List of valid time ranges for return flights.
        """
        times: list[TimeRange] = []

        # Sunday afternoon is valid
        times.append(SUNDAY_AFTERNOON)

        # Monday morning is valid
        times.append(MONDAY_MORNING)

        return times

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

        Sunday is the anchor date, but Monday morning is also valid.

        Args:
            sunday: Sunday of the weekend.
            monday: Monday after the weekend.

        Returns:
            Primary return date (Sunday).
        """
        return sunday

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

        Args:
            flight_date: Date of the flight.
            flight_time: Departure time of the flight.
            weekend: The weekend trip to check against.

        Returns:
            True if the flight is valid for return travel.
        """
        sunday = weekend.return_date
        monday = weekend.return_date + timedelta(days=1)

        # Check if date is Sunday or Monday of this weekend
        if flight_date == sunday:
            return SUNDAY_AFTERNOON.contains(flight_time)
        elif flight_date == monday:
            return MONDAY_MORNING.contains(flight_time)

        return False
