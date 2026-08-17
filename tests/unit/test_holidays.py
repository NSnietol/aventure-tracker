"""Tests for Colombian Holiday Service."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aventure_tracker.services.shared.holidays import HolidayService


@pytest.fixture
def holidays_config(tmp_path: Path) -> Path:
    """Create a temporary holidays config file."""
    config_path = tmp_path / "holidays.yaml"
    config_path.write_text(
        """
holidays:
  2025:
    - date: "2025-01-01"
      name: "Año Nuevo"
      type: fixed
    - date: "2025-01-06"
      name: "Reyes Magos"
      type: moved_monday
    - date: "2025-08-07"
      name: "Batalla de Boyacá"
      type: fixed
    - date: "2025-08-18"
      name: "Asunción de la Virgen"
      type: moved_monday
    - date: "2025-12-25"
      name: "Navidad"
      type: fixed
  2026:
    - date: "2026-01-01"
      name: "Año Nuevo"
      type: fixed
"""
    )
    return config_path


@pytest.fixture
def holiday_service(holidays_config: Path) -> HolidayService:
    """Create a HolidayService with test config."""
    return HolidayService(config_path=holidays_config)


class TestHolidayServiceInit:
    """Tests for HolidayService initialization."""

    def test_init_loads_config(self, holidays_config: Path) -> None:
        """Test that config is loaded on initialization."""
        service = HolidayService(config_path=holidays_config)

        # Should have loaded 2025 and 2026 holidays
        holidays_2025 = service.get_holidays(2025)
        assert len(holidays_2025) == 5

    def test_init_with_no_config(self) -> None:
        """Test initialization with no config file."""
        service = HolidayService(config_path=None)
        holidays = service.get_holidays(2025)
        # Should return empty list (would need API fallback)
        assert isinstance(holidays, list)

    def test_init_with_missing_file(self, tmp_path: Path) -> None:
        """Test initialization with missing config file."""
        service = HolidayService(config_path=tmp_path / "nonexistent.yaml")
        holidays = service.get_holidays(2025)
        assert isinstance(holidays, list)


class TestGetHolidays:
    """Tests for get_holidays method."""

    def test_get_holidays_from_config(self, holiday_service: HolidayService) -> None:
        """Test getting holidays from loaded config."""
        holidays = holiday_service.get_holidays(2025)

        assert len(holidays) == 5
        assert date(2025, 1, 1) in holidays
        assert date(2025, 8, 18) in holidays

    def test_get_holidays_caches_results(self, holiday_service: HolidayService) -> None:
        """Test that holidays are cached."""
        holidays1 = holiday_service.get_holidays(2025)
        holidays2 = holiday_service.get_holidays(2025)

        assert holidays1 is holidays2  # Same object

    def test_get_holidays_fallback_to_api(
        self, holiday_service: HolidayService
    ) -> None:
        """Test fallback to API for years not in config."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [
                {"date": "2027-01-01", "name": "New Year"},
                {"date": "2027-07-20", "name": "Independence Day"},
            ]
            mock_get.return_value = mock_response

            holidays = holiday_service.get_holidays(2027)

            assert len(holidays) == 2
            assert date(2027, 1, 1) in holidays
            mock_get.assert_called_once()

    def test_get_holidays_api_timeout_returns_empty(
        self, holiday_service: HolidayService
    ) -> None:
        """Test that API timeout returns empty list."""
        with patch("requests.get") as mock_get:
            import requests

            mock_get.side_effect = requests.exceptions.Timeout()

            holidays = holiday_service.get_holidays(2027)

            assert holidays == []

    def test_get_holidays_api_error_returns_empty(
        self, holiday_service: HolidayService
    ) -> None:
        """Test that API error returns empty list."""
        with patch("requests.get") as mock_get:
            import requests

            mock_get.side_effect = requests.exceptions.ConnectionError()

            holidays = holiday_service.get_holidays(2027)

            assert holidays == []


class TestIsHoliday:
    """Tests for is_holiday method."""

    def test_is_holiday_returns_true_for_holiday(
        self, holiday_service: HolidayService
    ) -> None:
        """Test that is_holiday returns True for holidays."""
        assert holiday_service.is_holiday(date(2025, 1, 1)) is True
        assert holiday_service.is_holiday(date(2025, 8, 18)) is True
        assert holiday_service.is_holiday(date(2025, 12, 25)) is True

    def test_is_holiday_returns_false_for_non_holiday(
        self, holiday_service: HolidayService
    ) -> None:
        """Test that is_holiday returns False for regular days."""
        assert holiday_service.is_holiday(date(2025, 3, 15)) is False
        assert holiday_service.is_holiday(date(2025, 6, 10)) is False


class TestIsBridgeWeekend:
    """Tests for is_bridge_weekend method."""

    def test_bridge_weekend_monday_holiday(
        self, holiday_service: HolidayService
    ) -> None:
        """Test bridge weekend when Monday is a holiday."""
        # August 18, 2025 is a Monday holiday (Asunción)
        # So August 15, 2025 (Friday) should be a bridge weekend
        friday = date(2025, 8, 15)
        assert holiday_service.is_bridge_weekend(friday) is True

    def test_bridge_weekend_friday_holiday(self, tmp_path: Path) -> None:
        """Test bridge weekend when Friday is a holiday."""
        config = tmp_path / "holidays.yaml"
        config.write_text(
            """
holidays:
  2025:
    - date: "2025-04-18"
      name: "Viernes Santo"
      type: fixed
"""
        )
        service = HolidayService(config_path=config)

        friday = date(2025, 4, 18)
        assert service.is_bridge_weekend(friday) is True

    def test_not_bridge_weekend_regular(self, holiday_service: HolidayService) -> None:
        """Test regular weekend is not a bridge weekend."""
        # March 14, 2025 is a regular Friday (no nearby holidays)
        friday = date(2025, 3, 14)
        assert holiday_service.is_bridge_weekend(friday) is False

    def test_bridge_weekend_thursday_holiday(self, tmp_path: Path) -> None:
        """Test bridge weekend when Thursday is a holiday."""
        config = tmp_path / "holidays.yaml"
        config.write_text(
            """
holidays:
  2025:
    - date: "2025-04-17"
      name: "Jueves Santo"
      type: fixed
"""
        )
        service = HolidayService(config_path=config)

        # Friday April 18 should be a bridge
        friday = date(2025, 4, 18)
        assert service.is_bridge_weekend(friday) is True

    def test_bridge_weekend_warns_on_non_friday(
        self, holiday_service: HolidayService
    ) -> None:
        """Test that non-Friday dates return False."""
        # A Saturday
        saturday = date(2025, 3, 15)
        assert holiday_service.is_bridge_weekend(saturday) is False


class TestGetNextBridgeWeekends:
    """Tests for get_next_bridge_weekends method."""

    def test_get_next_bridge_weekends(self, holiday_service: HolidayService) -> None:
        """Test finding next bridge weekends."""
        # Starting from January 2025
        bridges = holiday_service.get_next_bridge_weekends(
            from_date=date(2025, 1, 1), count=2
        )

        assert len(bridges) >= 1
        # All results should be Fridays
        for bridge in bridges:
            assert bridge.weekday() == 4

    def test_get_next_bridge_weekends_default_date(
        self, holiday_service: HolidayService
    ) -> None:
        """Test with default date (today)."""
        bridges = holiday_service.get_next_bridge_weekends(count=1)

        # Should return a list (may be empty if no holidays loaded for current year)
        assert isinstance(bridges, list)


class TestGetHolidayName:
    """Tests for get_holiday_name method."""

    def test_get_holiday_name_found(self, tmp_path: Path) -> None:
        """Test getting holiday name for a known holiday."""
        config = tmp_path / "holidays.yaml"
        config.write_text(
            """
holidays:
  2025:
    - date: "2025-01-01"
      name: "Año Nuevo"
      type: fixed
    - date: "2025-08-18"
      name: "Asunción de la Virgen"
      type: moved_monday
"""
        )
        service = HolidayService(config_path=config)

        name = service.get_holiday_name(date(2025, 1, 1))
        assert name == "Año Nuevo"

        name = service.get_holiday_name(date(2025, 8, 18))
        assert name == "Asunción de la Virgen"

    def test_get_holiday_name_not_found(self, holiday_service: HolidayService) -> None:
        """Test getting holiday name for non-holiday."""
        name = holiday_service.get_holiday_name(date(2025, 3, 15))
        assert name is None

    def test_get_holiday_name_no_config(self) -> None:
        """Test getting holiday name with no config."""
        service = HolidayService(config_path=None)
        name = service.get_holiday_name(date(2025, 1, 1))
        assert name is None


class TestEdgeCases:
    """Tests for edge cases."""

    def test_invalid_date_in_config(self, tmp_path: Path) -> None:
        """Test handling of invalid date format in config."""
        config = tmp_path / "holidays.yaml"
        config.write_text(
            """
holidays:
  2025:
    - date: "invalid-date"
      name: "Bad Date"
    - date: "2025-01-01"
      name: "Año Nuevo"
"""
        )
        service = HolidayService(config_path=config)

        # Should still load valid holidays
        holidays = service.get_holidays(2025)
        assert len(holidays) == 1
        assert date(2025, 1, 1) in holidays

    def test_empty_holidays_section(self, tmp_path: Path) -> None:
        """Test handling of empty holidays section."""
        config = tmp_path / "holidays.yaml"
        config.write_text(
            """
holidays:
  2025: []
"""
        )
        service = HolidayService(config_path=config)

        holidays = service.get_holidays(2025)
        assert holidays == []
