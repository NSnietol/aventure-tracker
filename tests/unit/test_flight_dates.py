"""Tests for Flight Date Calculator."""

from datetime import date, time, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aventure_tracker.models.flight import WeekendTrip
from aventure_tracker.services.flights.dates import (
    FRIDAY_DAYTIME,
    MONDAY_MORNING,
    THURSDAY_EVENING,
    TUESDAY_MORNING,
    FlightDateCalculator,
)
from aventure_tracker.services.shared.holidays import HolidayService


@pytest.fixture
def mock_holiday_service() -> MagicMock:
    """Create a mock HolidayService."""
    service = MagicMock(spec=HolidayService)
    service.is_bridge_weekend.return_value = False
    return service


@pytest.fixture
def calculator(mock_holiday_service: MagicMock) -> FlightDateCalculator:
    """Create a FlightDateCalculator with mock holiday service."""
    return FlightDateCalculator(holiday_service=mock_holiday_service)


@pytest.fixture
def holidays_config(tmp_path: Path) -> Path:
    """Create a holidays config for testing."""
    config = tmp_path / "holidays.yaml"
    config.write_text(
        """
holidays:
  2025:
    - date: "2025-08-18"
      name: "Asunción de la Virgen"
      type: moved_monday
"""
    )
    return config


class TestTimeRangeConstants:
    """Tests for time range constants."""

    def test_thursday_evening_range(self) -> None:
        """Test Thursday evening time range."""
        assert THURSDAY_EVENING.start == time(18, 0)
        assert THURSDAY_EVENING.end == time(23, 59)

    def test_friday_daytime_range(self) -> None:
        """Test Friday daytime time range."""
        assert FRIDAY_DAYTIME.start == time(0, 0)
        assert FRIDAY_DAYTIME.end == time(16, 0)

    def test_sunday_afternoon_range(self) -> None:
        """Test Tuesday morning time range (replaces old Sunday afternoon)."""
        assert TUESDAY_MORNING.start == time(0, 0)
        assert TUESDAY_MORNING.end == time(10, 0)

    def test_monday_morning_range(self) -> None:
        """Test Monday morning time range."""
        assert MONDAY_MORNING.start == time(0, 0)
        assert MONDAY_MORNING.end == time(10, 0)


class TestFlightDateCalculatorInit:
    """Tests for FlightDateCalculator initialization."""

    def test_init_with_holiday_service(self, mock_holiday_service: MagicMock) -> None:
        """Test initialization with provided holiday service."""
        calc = FlightDateCalculator(holiday_service=mock_holiday_service)
        assert calc._holiday_service is mock_holiday_service

    def test_init_with_config_path(self, holidays_config: Path) -> None:
        """Test initialization with config path creates holiday service."""
        calc = FlightDateCalculator(holidays_config_path=holidays_config)
        assert isinstance(calc._holiday_service, HolidayService)

    def test_init_without_args(self) -> None:
        """Test initialization without arguments creates default service."""
        calc = FlightDateCalculator()
        assert isinstance(calc._holiday_service, HolidayService)


class TestGetUpcomingWeekends:
    """Tests for get_upcoming_weekends method."""

    def test_returns_correct_number_of_weekends(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test that correct number of weekends is returned."""
        weekends = calculator.get_upcoming_weekends(weeks_ahead=4)
        assert len(weekends) == 4

    def test_weekends_are_sequential(self, calculator: FlightDateCalculator) -> None:
        """Test that weekends are one week apart."""
        # Start from a known Monday
        start = date(2025, 3, 3)  # Monday
        weekends = calculator.get_upcoming_weekends(weeks_ahead=3, from_date=start)

        # First Friday should be March 7, 2025
        assert weekends[0].outbound_date == date(2025, 3, 7)
        assert weekends[1].outbound_date == date(2025, 3, 14)
        assert weekends[2].outbound_date == date(2025, 3, 21)

    def test_outbound_date_is_friday(self, calculator: FlightDateCalculator) -> None:
        """Test that outbound dates are Fridays."""
        weekends = calculator.get_upcoming_weekends(weeks_ahead=5)

        for weekend in weekends:
            assert weekend.outbound_date.weekday() == 4  # Friday

    def test_return_date_is_monday(self, calculator: FlightDateCalculator) -> None:
        """Test that return dates are Mondays (adventure ends Sunday in MDE)."""
        weekends = calculator.get_upcoming_weekends(weeks_ahead=5)

        for weekend in weekends:
            assert weekend.return_date.weekday() == 0  # Monday

    def test_return_is_three_days_after_outbound(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test that return is 3 days after outbound (Friday -> Monday)."""
        weekends = calculator.get_upcoming_weekends(weeks_ahead=3)

        for weekend in weekends:
            diff = weekend.return_date - weekend.outbound_date
            assert diff == timedelta(days=3)

    def test_starting_from_friday_includes_that_friday(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test that starting from a Friday includes that weekend."""
        friday = date(2025, 3, 7)  # A Friday
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1, from_date=friday)

        assert weekends[0].outbound_date == friday

    def test_starting_from_saturday_gets_next_friday(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test that starting from Saturday gets next Friday."""
        saturday = date(2025, 3, 8)  # Saturday March 8
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1, from_date=saturday)

        # Should get Friday March 14
        assert weekends[0].outbound_date == date(2025, 3, 14)

    def test_default_from_date_is_today(self, calculator: FlightDateCalculator) -> None:
        """Test that from_date defaults to today."""
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1)

        # Just verify it returns something and doesn't crash
        assert len(weekends) == 1
        assert isinstance(weekends[0], WeekendTrip)


class TestBridgeWeekendDetection:
    """Tests for bridge weekend (puente) detection."""

    def test_bridge_weekend_flag_from_holiday_service(
        self, mock_holiday_service: MagicMock
    ) -> None:
        """Test that is_bridge comes from holiday service."""
        mock_holiday_service.is_bridge_weekend.return_value = True
        calc = FlightDateCalculator(holiday_service=mock_holiday_service)

        weekends = calc.get_upcoming_weekends(
            weeks_ahead=1, from_date=date(2025, 8, 11)
        )

        assert weekends[0].is_bridge is True
        mock_holiday_service.is_bridge_weekend.assert_called()

    def test_regular_weekend_not_bridge(self, mock_holiday_service: MagicMock) -> None:
        """Test that regular weekends are not marked as bridge."""
        mock_holiday_service.is_bridge_weekend.return_value = False
        calc = FlightDateCalculator(holiday_service=mock_holiday_service)

        weekends = calc.get_upcoming_weekends(weeks_ahead=1, from_date=date(2025, 3, 3))

        assert weekends[0].is_bridge is False


class TestGetBridgeWeekends:
    """Tests for get_bridge_weekends method."""

    def test_filters_only_bridge_weekends(
        self, mock_holiday_service: MagicMock
    ) -> None:
        """Test that only bridge weekends are returned."""
        # Make every other call return True for bridge
        mock_holiday_service.is_bridge_weekend.side_effect = [
            False,
            True,
            False,
            True,
            False,
        ]
        calc = FlightDateCalculator(holiday_service=mock_holiday_service)

        bridges = calc.get_bridge_weekends(weeks_ahead=5, from_date=date(2025, 3, 3))

        assert len(bridges) == 2
        for weekend in bridges:
            assert weekend.is_bridge is True

    def test_returns_empty_when_no_bridges(
        self, mock_holiday_service: MagicMock
    ) -> None:
        """Test empty list when no bridge weekends found."""
        mock_holiday_service.is_bridge_weekend.return_value = False
        calc = FlightDateCalculator(holiday_service=mock_holiday_service)

        bridges = calc.get_bridge_weekends(weeks_ahead=5, from_date=date(2025, 3, 3))

        assert bridges == []


class TestTimeRanges:
    """Tests for time range validation in WeekendTrip."""

    def test_outbound_times_include_thursday_evening(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test that outbound times include Thursday evening."""
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1)
        weekend = weekends[0]

        assert any(
            tr.start == time(18, 0) and tr.end == time(23, 59)
            for tr in weekend.outbound_times
        )

    def test_outbound_times_include_friday_daytime(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test that outbound times include Friday daytime."""
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1)
        weekend = weekends[0]

        assert any(
            tr.start == time(0, 0) and tr.end == time(16, 0)
            for tr in weekend.outbound_times
        )

    def test_return_times_include_monday_morning(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test that return times include Monday morning."""
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1)
        weekend = weekends[0]

        assert any(
            tr.start == time(0, 0) and tr.end == time(10, 0)
            for tr in weekend.return_times
        )

    def test_return_times_include_tuesday_morning(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test that return times include Tuesday morning (adventure ends Monday in MDE)."""
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1)
        weekend = weekends[0]

        # Both Monday and Tuesday morning should be in return_times
        assert len(weekend.return_times) == 2

    def test_return_times_do_not_include_sunday(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test that Sunday is NOT in return_times (handled by _build_weekend_pairs)."""
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1)
        weekend = weekends[0]

        # No range that ends at 23:59 (that would be Sunday afternoon)
        assert not any(tr.end == time(23, 59) for tr in weekend.return_times)


class TestIsValidOutboundFlight:
    """Tests for is_valid_outbound_flight method."""

    def test_thursday_evening_flight_valid(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test Thursday 7PM flight is valid."""
        friday = date(2025, 3, 7)
        thursday = friday - timedelta(days=1)
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1, from_date=friday)
        weekend = weekends[0]

        assert (
            calculator.is_valid_outbound_flight(thursday, time(19, 0), weekend) is True
        )

    def test_thursday_afternoon_flight_invalid(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test Thursday 3PM flight is invalid (too early)."""
        friday = date(2025, 3, 7)
        thursday = friday - timedelta(days=1)
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1, from_date=friday)
        weekend = weekends[0]

        assert (
            calculator.is_valid_outbound_flight(thursday, time(15, 0), weekend) is False
        )

    def test_friday_morning_flight_valid(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test Friday 10AM flight is valid."""
        friday = date(2025, 3, 7)
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1, from_date=friday)
        weekend = weekends[0]

        assert calculator.is_valid_outbound_flight(friday, time(10, 0), weekend) is True

    def test_friday_evening_flight_invalid(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test Friday 6PM flight is invalid (too late)."""
        friday = date(2025, 3, 7)
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1, from_date=friday)
        weekend = weekends[0]

        assert (
            calculator.is_valid_outbound_flight(friday, time(18, 0), weekend) is False
        )

    def test_wrong_day_invalid(self, calculator: FlightDateCalculator) -> None:
        """Test Wednesday flight is invalid regardless of time."""
        friday = date(2025, 3, 7)
        wednesday = friday - timedelta(days=2)
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1, from_date=friday)
        weekend = weekends[0]

        assert (
            calculator.is_valid_outbound_flight(wednesday, time(19, 0), weekend)
            is False
        )


class TestIsValidReturnFlight:
    """Tests for is_valid_return_flight method."""

    def test_sunday_flight_invalid(self, calculator: FlightDateCalculator) -> None:
        """Test Sunday flight is invalid in is_valid_return_flight.

        Sunday validity is handled exclusively by _build_weekend_pairs(),
        not by this method.
        """
        friday = date(2025, 3, 7)
        sunday = friday + timedelta(days=2)
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1, from_date=friday)
        weekend = weekends[0]

        assert calculator.is_valid_return_flight(sunday, time(16, 0), weekend) is False

    def test_monday_early_morning_flight_valid(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test Monday 6AM flight is valid."""
        friday = date(2025, 3, 7)
        monday = friday + timedelta(days=3)
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1, from_date=friday)
        weekend = weekends[0]

        assert calculator.is_valid_return_flight(monday, time(6, 0), weekend) is True

    def test_monday_afternoon_flight_invalid(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test Monday 2PM flight is invalid (too late)."""
        friday = date(2025, 3, 7)
        monday = friday + timedelta(days=3)
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1, from_date=friday)
        weekend = weekends[0]

        assert calculator.is_valid_return_flight(monday, time(14, 0), weekend) is False

    def test_tuesday_early_morning_flight_valid(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test Tuesday 6AM flight is valid (adventure ended Monday in MDE)."""
        friday = date(2025, 3, 7)
        tuesday = friday + timedelta(days=4)
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1, from_date=friday)
        weekend = weekends[0]

        assert calculator.is_valid_return_flight(tuesday, time(6, 0), weekend) is True

    def test_tuesday_afternoon_flight_invalid(
        self, calculator: FlightDateCalculator
    ) -> None:
        """Test Tuesday 2PM flight is invalid (too late)."""
        friday = date(2025, 3, 7)
        tuesday = friday + timedelta(days=4)
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1, from_date=friday)
        weekend = weekends[0]

        assert calculator.is_valid_return_flight(tuesday, time(14, 0), weekend) is False

    def test_wednesday_flight_invalid(self, calculator: FlightDateCalculator) -> None:
        """Test Wednesday flight is invalid regardless of time."""
        friday = date(2025, 3, 7)
        wednesday = friday + timedelta(days=5)
        weekends = calculator.get_upcoming_weekends(weeks_ahead=1, from_date=friday)
        weekend = weekends[0]

        assert (
            calculator.is_valid_return_flight(wednesday, time(6, 0), weekend) is False
        )


class TestIntegrationWithHolidayService:
    """Integration tests with real HolidayService."""

    def test_real_bridge_weekend_detection(self, holidays_config: Path) -> None:
        """Test bridge weekend detection with real holiday service."""
        calc = FlightDateCalculator(holidays_config_path=holidays_config)

        # August 15, 2025 is Friday before Monday holiday (August 18)
        weekends = calc.get_upcoming_weekends(
            weeks_ahead=1, from_date=date(2025, 8, 15)
        )

        assert weekends[0].is_bridge is True

    def test_real_regular_weekend(self, holidays_config: Path) -> None:
        """Test regular weekend with real holiday service."""
        calc = FlightDateCalculator(holidays_config_path=holidays_config)

        # March 7, 2025 is a regular Friday (no nearby holidays)
        weekends = calc.get_upcoming_weekends(weeks_ahead=1, from_date=date(2025, 3, 7))

        assert weekends[0].is_bridge is False

    def test_return_date_is_monday_not_sunday(self, holidays_config: Path) -> None:
        """Test that return_date is Monday, not Sunday."""
        calc = FlightDateCalculator(holidays_config_path=holidays_config)
        weekends = calc.get_upcoming_weekends(weeks_ahead=1, from_date=date(2025, 3, 7))
        weekend = weekends[0]

        # return_date should be Monday (weekday 0), not Sunday (weekday 6)
        assert weekend.return_date.weekday() == 0  # Monday
        assert weekend.return_date == date(2025, 3, 10)  # Friday Mar 7 + 3 days
