"""Colombian holiday service for detecting puentes (bridge weekends)."""

import logging
from datetime import date, timedelta
from pathlib import Path

import requests
import yaml

logger = logging.getLogger(__name__)

# Nager.Date API for holiday lookup fallback
NAGER_API_BASE = "https://date.nager.at/api/v3"
NAGER_TIMEOUT_SECONDS = 10


class HolidayServiceError(Exception):
    """Base exception for holiday service errors."""

    pass


class HolidayService:
    """Service for Colombian holiday detection and bridge weekend identification.

    Loads holidays from a YAML configuration file with hardcoded dates for
    2025-2026. Falls back to the Nager.Date API for other years.

    Attributes:
        config_path: Path to the holidays.yaml configuration file.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        """Initialize the holiday service.

        Args:
            config_path: Path to holidays.yaml. If None, uses default.
        """
        self._config_path = config_path
        self._holidays_cache: dict[int, list[date]] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load holidays from YAML configuration file."""
        if self._config_path is None or not self._config_path.exists():
            logger.warning("Holidays config not found, using empty config")
            return

        try:
            with open(self._config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or "holidays" not in data:
                logger.warning("Invalid holidays config format")
                return

            for year_key, holidays_list in data.get("holidays", {}).items():
                year = int(year_key)  # Handle both string and int keys
                self._holidays_cache[year] = []

                for holiday in holidays_list:
                    date_str = holiday.get("date")
                    if date_str:
                        try:
                            holiday_date = date.fromisoformat(date_str)
                            self._holidays_cache[year].append(holiday_date)
                        except ValueError as e:
                            logger.warning(f"Invalid date format in config: {date_str} - {e}")

            logger.info(
                f"Loaded holidays for years: {list(self._holidays_cache.keys())}"
            )

        except Exception as e:
            logger.error(f"Failed to load holidays config: {e}")

    def _fetch_from_api(self, year: int) -> list[date]:
        """Fetch holidays from Nager.Date API.

        Args:
            year: Year to fetch holidays for.

        Returns:
            List of holiday dates.
        """
        url = f"{NAGER_API_BASE}/PublicHolidays/{year}/CO"

        try:
            response = requests.get(url, timeout=NAGER_TIMEOUT_SECONDS)
            response.raise_for_status()

            holidays: list[date] = []
            for holiday_data in response.json():
                date_str = holiday_data.get("date")
                if date_str:
                    holidays.append(date.fromisoformat(date_str))

            logger.info(f"Fetched {len(holidays)} holidays from API for {year}")
            return holidays

        except requests.exceptions.Timeout:
            logger.warning(f"API timeout fetching holidays for {year}")
            return []
        except requests.exceptions.RequestException as e:
            logger.warning(f"API error fetching holidays for {year}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching holidays: {e}")
            return []

    def get_holidays(self, year: int) -> list[date]:
        """Get all holidays for a given year.

        First checks the local configuration, then falls back to the API.

        Args:
            year: Year to get holidays for.

        Returns:
            List of holiday dates, may be empty if no data available.
        """
        # Check cache first (includes loaded config)
        if year in self._holidays_cache:
            return self._holidays_cache[year]

        # Try API fallback
        holidays = self._fetch_from_api(year)
        self._holidays_cache[year] = holidays
        return holidays

    def is_holiday(self, day: date) -> bool:
        """Check if a date is a Colombian holiday.

        Args:
            day: Date to check.

        Returns:
            True if the date is a holiday.
        """
        holidays = self.get_holidays(day.year)
        return day in holidays

    def is_bridge_weekend(self, friday: date) -> bool:
        """Check if a weekend is a bridge weekend (puente).

        A bridge weekend occurs when:
        - The Friday itself is a holiday
        - The Monday following the weekend is a holiday
        - The Thursday before is a holiday (making Friday a bridge day)

        Args:
            friday: The Friday of the weekend to check.

        Returns:
            True if this is a bridge weekend.
        """
        if friday.weekday() != 4:  # 4 = Friday
            logger.warning(f"{friday} is not a Friday")
            return False

        # Check if Monday after the weekend is a holiday
        monday = friday + timedelta(days=3)
        if self.is_holiday(monday):
            return True

        # Check if Friday is a holiday
        if self.is_holiday(friday):
            return True

        # Check if Thursday before is a holiday (making Friday a bridge)
        thursday = friday - timedelta(days=1)
        if self.is_holiday(thursday):
            return True

        return False

    def get_next_bridge_weekends(
        self,
        from_date: date | None = None,
        count: int = 5,
    ) -> list[date]:
        """Get the next N bridge weekends from a given date.

        Args:
            from_date: Start date to search from. Defaults to today.
            count: Number of bridge weekends to find.

        Returns:
            List of Friday dates that are bridge weekends.
        """
        if from_date is None:
            from_date = date.today()

        # Find the next Friday
        days_until_friday = (4 - from_date.weekday()) % 7
        if days_until_friday == 0 and from_date.weekday() != 4:
            days_until_friday = 7
        current_friday = from_date + timedelta(days=days_until_friday)

        bridge_weekends: list[date] = []
        max_weeks = 52 * 2  # Search up to 2 years

        for _ in range(max_weeks):
            if self.is_bridge_weekend(current_friday):
                bridge_weekends.append(current_friday)
                if len(bridge_weekends) >= count:
                    break
            current_friday += timedelta(days=7)

        return bridge_weekends

    def get_holiday_name(self, day: date) -> str | None:
        """Get the name of a holiday if the date is a holiday.

        Note: Only works for holidays loaded from config (not API).

        Args:
            day: Date to check.

        Returns:
            Holiday name or None if not a holiday or name unknown.
        """
        if self._config_path is None or not self._config_path.exists():
            return None

        try:
            with open(self._config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            holidays_dict = data.get("holidays", {})
            # Try both string and int keys (YAML may parse years as int)
            year_data = holidays_dict.get(str(day.year), holidays_dict.get(day.year, []))

            for holiday in year_data:
                date_str = holiday.get("date")
                if date_str and date.fromisoformat(date_str) == day:
                    return holiday.get("name")

        except Exception:
            pass

        return None
