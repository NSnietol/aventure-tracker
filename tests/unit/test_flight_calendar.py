"""Tests for FlightCalendarDisplay."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from aventure_tracker.models.flight import RouteConfig, WeekendTrip
from aventure_tracker.services.flight_calendar import (
    DEFAULT_WEEKS,
    INDICATOR_BRIDGE,
    INDICATOR_DOWN,
    INDICATOR_TARGET,
    INDICATOR_UP,
    CalendarData,
    FlightCalendarDisplay,
    PriceCell,
)


@pytest.fixture
def sample_routes() -> list[RouteConfig]:
    """Create sample routes for testing."""
    return [
        RouteConfig(
            origin="BAQ",
            destination="MDE",
            price_threshold=100000,
            drop_percentage=10,
        ),
        RouteConfig(
            origin="BAQ",
            destination="BOG",
            price_threshold=120000,
            drop_percentage=15,
        ),
    ]


@pytest.fixture
def sample_weekends() -> list[WeekendTrip]:
    """Create sample weekends for testing."""
    return [
        WeekendTrip(
            outbound_date=date(2026, 1, 16),
            return_date=date(2026, 1, 18),
            is_bridge=False,
            outbound_times=[],
            return_times=[],
        ),
        WeekendTrip(
            outbound_date=date(2026, 1, 23),
            return_date=date(2026, 1, 25),
            is_bridge=True,  # Bridge weekend
            outbound_times=[],
            return_times=[],
        ),
        WeekendTrip(
            outbound_date=date(2026, 1, 30),
            return_date=date(2026, 2, 1),
            is_bridge=False,
            outbound_times=[],
            return_times=[],
        ),
    ]


@pytest.fixture
def mock_date_calculator(sample_weekends: list[WeekendTrip]) -> MagicMock:
    """Create a mock date calculator."""
    calculator = MagicMock()
    calculator.get_upcoming_weekends.return_value = sample_weekends
    return calculator


@pytest.fixture
def display(mock_date_calculator: MagicMock) -> FlightCalendarDisplay:
    """Create a calendar display with mocked calculator."""
    return FlightCalendarDisplay(
        date_calculator=mock_date_calculator,
        weeks_ahead=10,
    )


class TestPriceCell:
    """Tests for PriceCell dataclass."""

    def test_price_cell_with_price(self) -> None:
        """Test creating a price cell with a price."""
        cell = PriceCell(price=95000)

        assert cell.price == 95000
        assert cell.previous_price is None
        assert cell.price_change is None

    def test_price_cell_with_price_change(self) -> None:
        """Test price change calculation."""
        cell = PriceCell(price=90000, previous_price=100000)

        assert cell.price_change == -10000

    def test_price_cell_indicator_target(self) -> None:
        """Test target indicator when below threshold."""
        cell = PriceCell(price=95000, is_below_threshold=True)

        assert INDICATOR_TARGET in cell.indicator

    def test_price_cell_indicator_down(self) -> None:
        """Test down indicator for price drop."""
        cell = PriceCell(price=90000, previous_price=100000)

        assert INDICATOR_DOWN in cell.indicator

    def test_price_cell_indicator_up(self) -> None:
        """Test up indicator for price increase."""
        cell = PriceCell(price=110000, previous_price=100000)

        assert INDICATOR_UP in cell.indicator

    def test_price_cell_indicator_bridge(self) -> None:
        """Test bridge indicator."""
        cell = PriceCell(price=100000, is_bridge=True)

        assert INDICATOR_BRIDGE in cell.indicator

    def test_price_cell_multiple_indicators(self) -> None:
        """Test cell with multiple indicators."""
        cell = PriceCell(
            price=90000,
            previous_price=100000,
            is_below_threshold=True,
            is_bridge=True,
        )

        indicator = cell.indicator
        assert INDICATOR_TARGET in indicator
        assert INDICATOR_DOWN in indicator
        assert INDICATOR_BRIDGE in indicator

    def test_format_price_thousands(self) -> None:
        """Test formatting price in thousands."""
        cell = PriceCell(price=150000)

        formatted = cell.format_price()

        assert "$150k" in formatted

    def test_format_price_with_indicator(self) -> None:
        """Test formatting price with indicator."""
        cell = PriceCell(price=95000, is_below_threshold=True)

        formatted = cell.format_price()

        assert "$95k" in formatted
        assert INDICATOR_TARGET in formatted

    def test_format_price_none(self) -> None:
        """Test formatting when no price."""
        cell = PriceCell(price=None)

        assert cell.format_price() == "-"


class TestCalendarData:
    """Tests for CalendarData dataclass."""

    def test_get_cell_existing(self, sample_routes: list[RouteConfig]) -> None:
        """Test getting an existing cell."""
        d = date(2026, 1, 16)
        route = sample_routes[0]
        cell = PriceCell(price=100000)

        data = CalendarData(
            routes=sample_routes,
            dates=[d],
            prices={(d, str(route)): cell},
            bridge_dates=set(),
        )

        result = data.get_cell(d, route)
        assert result.price == 100000

    def test_get_cell_missing(self, sample_routes: list[RouteConfig]) -> None:
        """Test getting a missing cell returns empty cell."""
        d = date(2026, 1, 16)
        route = sample_routes[0]

        data = CalendarData(
            routes=sample_routes,
            dates=[d],
            prices={},
            bridge_dates=set(),
        )

        result = data.get_cell(d, route)
        assert result.price is None


class TestFlightCalendarDisplayInit:
    """Tests for calendar display initialization."""

    def test_default_weeks(self) -> None:
        """Test default weeks ahead."""
        display = FlightCalendarDisplay()

        assert display._weeks_ahead == DEFAULT_WEEKS

    def test_custom_weeks(self) -> None:
        """Test custom weeks ahead."""
        display = FlightCalendarDisplay(weeks_ahead=12)

        assert display._weeks_ahead == 12


class TestFormatDate:
    """Tests for date formatting."""

    def test_format_date_friday(self, display: FlightCalendarDisplay) -> None:
        """Test formatting a Friday date."""
        d = date(2026, 1, 16)  # Friday

        formatted = display._format_date(d)

        assert "Ene" in formatted
        assert "16" in formatted
        assert "(V)" in formatted

    def test_format_date_bridge(self, display: FlightCalendarDisplay) -> None:
        """Test formatting a bridge weekend date."""
        d = date(2026, 1, 23)

        formatted = display._format_date(d, is_bridge=True)

        assert INDICATOR_BRIDGE in formatted


class TestBuildCalendarData:
    """Tests for building calendar data."""

    def test_build_with_prices(
        self,
        display: FlightCalendarDisplay,
        sample_routes: list[RouteConfig],
    ) -> None:
        """Test building calendar data with prices."""
        prices = {
            (date(2026, 1, 16), "BAQ→MDE"): 95000,
            (date(2026, 1, 16), "BAQ→BOG"): 125000,
            (date(2026, 1, 23), "BAQ→MDE"): 150000,
        }

        data = display.build_calendar_data(sample_routes, prices)

        assert len(data.routes) == 2
        assert len(data.dates) == 3

        # Check price was set
        cell = data.get_cell(date(2026, 1, 16), sample_routes[0])
        assert cell.price == 95000

    def test_build_marks_below_threshold(
        self,
        display: FlightCalendarDisplay,
        sample_routes: list[RouteConfig],
    ) -> None:
        """Test that below-threshold prices are marked."""
        # BAQ→MDE threshold is 100000
        prices = {
            (date(2026, 1, 16), "BAQ→MDE"): 95000,  # Below threshold
        }

        data = display.build_calendar_data(sample_routes, prices)

        cell = data.get_cell(date(2026, 1, 16), sample_routes[0])
        assert cell.is_below_threshold is True

    def test_build_marks_bridge_weekends(
        self,
        display: FlightCalendarDisplay,
        sample_routes: list[RouteConfig],
    ) -> None:
        """Test that bridge weekends are marked."""
        prices = {
            (date(2026, 1, 23), "BAQ→MDE"): 120000,
        }

        data = display.build_calendar_data(sample_routes, prices)

        # Jan 23 is marked as bridge in mock
        assert date(2026, 1, 23) in data.bridge_dates
        cell = data.get_cell(date(2026, 1, 23), sample_routes[0])
        assert cell.is_bridge is True

    def test_build_with_previous_prices(
        self,
        display: FlightCalendarDisplay,
        sample_routes: list[RouteConfig],
    ) -> None:
        """Test building with price comparison."""
        prices = {
            (date(2026, 1, 16), "BAQ→MDE"): 90000,
        }
        previous = {
            (date(2026, 1, 16), "BAQ→MDE"): 100000,
        }

        data = display.build_calendar_data(sample_routes, prices, previous)

        cell = data.get_cell(date(2026, 1, 16), sample_routes[0])
        assert cell.price_change == -10000


class TestRender:
    """Tests for calendar rendering."""

    def test_render_produces_output(
        self,
        display: FlightCalendarDisplay,
        sample_routes: list[RouteConfig],
    ) -> None:
        """Test render produces non-empty output."""
        prices = {
            (date(2026, 1, 16), "BAQ→MDE"): 95000,
            (date(2026, 1, 16), "BAQ→BOG"): 120000,
        }
        data = display.build_calendar_data(sample_routes, prices)

        output = display.render(data)

        assert len(output) > 0
        assert "FLIGHT CALENDAR" in output

    def test_render_includes_routes(
        self,
        display: FlightCalendarDisplay,
        sample_routes: list[RouteConfig],
    ) -> None:
        """Test render includes route headers."""
        prices = {}
        data = display.build_calendar_data(sample_routes, prices)

        output = display.render(data)

        assert "BAQ→MDE" in output
        assert "BAQ→BOG" in output

    def test_render_includes_dates(
        self,
        display: FlightCalendarDisplay,
        sample_routes: list[RouteConfig],
    ) -> None:
        """Test render includes dates."""
        prices = {}
        data = display.build_calendar_data(sample_routes, prices)

        output = display.render(data)

        assert "Ene" in output

    def test_render_includes_prices(
        self,
        display: FlightCalendarDisplay,
        sample_routes: list[RouteConfig],
    ) -> None:
        """Test render includes price values."""
        prices = {
            (date(2026, 1, 16), "BAQ→MDE"): 95000,
        }
        data = display.build_calendar_data(sample_routes, prices)

        output = display.render(data)

        assert "$95k" in output

    def test_render_includes_legend(
        self,
        display: FlightCalendarDisplay,
        sample_routes: list[RouteConfig],
    ) -> None:
        """Test render includes legend."""
        prices = {}
        data = display.build_calendar_data(sample_routes, prices)

        output = display.render(data)

        assert "Legend" in output
        assert "target" in output.lower()
        assert "puente" in output.lower()


class TestRenderSummary:
    """Tests for summary rendering."""

    def test_summary_shows_best_prices(
        self,
        display: FlightCalendarDisplay,
        sample_routes: list[RouteConfig],
    ) -> None:
        """Test summary shows best price per route."""
        prices = {
            (date(2026, 1, 16), "BAQ→MDE"): 95000,
            (date(2026, 1, 23), "BAQ→MDE"): 110000,
            (date(2026, 1, 30), "BAQ→MDE"): 100000,
        }
        data = display.build_calendar_data(sample_routes, prices)

        summary = display.render_summary(data)

        # Should show $95,000 as best price
        assert "95" in summary
        assert "BAQ→MDE" in summary

    def test_summary_counts_targets(
        self,
        display: FlightCalendarDisplay,
        sample_routes: list[RouteConfig],
    ) -> None:
        """Test summary counts prices at/below target."""
        prices = {
            (date(2026, 1, 16), "BAQ→MDE"): 95000,  # Below 100k threshold
            (date(2026, 1, 23), "BAQ→MDE"): 150000,  # Above threshold
        }
        data = display.build_calendar_data(sample_routes, prices)

        summary = display.render_summary(data)

        assert "at/below target" in summary.lower()

    def test_summary_counts_drops(
        self,
        display: FlightCalendarDisplay,
        sample_routes: list[RouteConfig],
    ) -> None:
        """Test summary counts price drops."""
        prices = {
            (date(2026, 1, 16), "BAQ→MDE"): 90000,
        }
        previous = {
            (date(2026, 1, 16), "BAQ→MDE"): 100000,
        }
        data = display.build_calendar_data(sample_routes, prices, previous)

        summary = display.render_summary(data)

        assert "drop" in summary.lower()

    def test_summary_counts_bridges(
        self,
        display: FlightCalendarDisplay,
        sample_routes: list[RouteConfig],
    ) -> None:
        """Test summary counts bridge weekends."""
        prices = {}
        data = display.build_calendar_data(sample_routes, prices)

        summary = display.render_summary(data)

        # Our mock has 1 bridge weekend
        assert "bridge" in summary.lower() or "puente" in summary.lower()


class TestGetTravelDates:
    """Tests for getting travel dates."""

    def test_get_travel_dates_calls_calculator(
        self,
        display: FlightCalendarDisplay,
        mock_date_calculator: MagicMock,
    ) -> None:
        """Test get_travel_dates uses the calculator."""
        weekends = display.get_travel_dates()

        mock_date_calculator.get_upcoming_weekends.assert_called_once()
        assert len(weekends) == 3
