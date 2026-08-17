"""Tests for Flight Tracker Service."""

from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from aventure_tracker.models.flight import FlightResult, RouteConfig
from aventure_tracker.services.flight_tracker import (
    FlightFound,
    FlightTrackerResult,
    FlightTrackerService,
    PriceAlert,
)


@pytest.fixture
def routes_config(tmp_path: Path) -> Path:
    """Create a temporary routes config file."""
    config_path = tmp_path / "routes.yaml"
    config_path.write_text(
        """
routes:
  - origin: BAQ
    destination: MDE
    price_threshold: 150000
    drop_percentage: 15
    search_days: [thursday, friday]
  - origin: CTG
    destination: MDE
    price_threshold: 150000
    drop_percentage: 15
    search_days: [thursday, friday]
"""
    )
    return config_path


@pytest.fixture
def holidays_config(tmp_path: Path) -> Path:
    """Create a temporary holidays config file."""
    config_path = tmp_path / "holidays.yaml"
    config_path.write_text(
        """
holidays:
  2025:
    - date: "2025-08-18"
      name: "Asunción"
"""
    )
    return config_path


@pytest.fixture
def route() -> RouteConfig:
    """Create a test route configuration."""
    return RouteConfig(
        origin="BAQ",
        destination="MDE",
        price_threshold=150000,
        drop_percentage=15,
    )


@pytest.fixture
def mock_state_manager() -> MagicMock:
    """Create a mock state manager."""
    manager = MagicMock()
    manager.get_last_flight_price.return_value = None
    manager.set_flight_price = MagicMock()
    manager.save = AsyncMock()
    return manager


@pytest.fixture
def mock_notifier() -> AsyncMock:
    """Create a mock notifier."""
    notifier = AsyncMock()
    notifier.send_flight_alert = AsyncMock()
    return notifier


@pytest.fixture
def mock_scraper() -> AsyncMock:
    """Create a mock scraper."""
    scraper = AsyncMock()
    # scrape() returns a list of FlightResult objects
    scraper.scrape = AsyncMock(
        return_value=[
            FlightResult(
                price=120000,
                airline="LATAM",
                departure_time=datetime(2025, 3, 15, 18, 30),
                arrival_time=datetime(2025, 3, 15, 19, 45),
                duration=timedelta(hours=1, minutes=15),
                stops=0,
                booking_link="https://example.com/flight",
            )
        ]
    )
    return scraper


@pytest.fixture
def flight_found() -> FlightFound:
    """Create a test FlightFound object."""
    return FlightFound(
        flight_id="BAQ-MDE_2025-03-15_18:30_LATAM",
        route="BAQ→MDE",
        travel_date=date(2025, 3, 15),
        departure_time="18:30",
        airline="LATAM",
        price=120000,
        is_priority=True,
    )


@pytest.fixture
def service(
    routes_config: Path,
    holidays_config: Path,
    mock_state_manager: MagicMock,
    mock_notifier: AsyncMock,
    mock_scraper: AsyncMock,
) -> FlightTrackerService:
    """Create a flight tracker service with mocked dependencies."""
    return FlightTrackerService(
        routes_config_path=routes_config,
        holidays_config_path=holidays_config,
        state_manager=mock_state_manager,
        notifier=mock_notifier,
        scraper=mock_scraper,
        weeks_ahead=2,
    )


class TestFlightTrackerServiceInit:
    """Tests for service initialization."""

    def test_init_with_paths(self, routes_config: Path) -> None:
        """Test initialization with config paths."""
        service = FlightTrackerService(
            routes_config_path=routes_config,
            weeks_ahead=4,
        )
        assert service._routes_config_path == routes_config
        assert service._weeks_ahead == 4

    def test_load_routes(self, service: FlightTrackerService) -> None:
        """Test routes are loaded correctly."""
        routes = service._load_routes()

        assert len(routes.routes) == 2
        assert routes.routes[0].origin == "BAQ"
        assert routes.routes[1].origin == "CTG"


class TestPriceAlert:
    """Tests for PriceAlert dataclass."""

    def test_create_price_alert(
        self, route: RouteConfig, flight_found: FlightFound
    ) -> None:
        """Test creating a price alert."""
        alert = PriceAlert(
            flight=flight_found,
            route_config=route,
            previous_price=150000,
            price_change=-30000,
            price_change_pct=-20.0,
            is_below_threshold=True,
            is_significant_drop=True,
        )

        assert alert.flight.price == 120000
        assert alert.price_change == -30000
        assert alert.price_change_pct == -20.0

    def test_should_notify_below_threshold(
        self, route: RouteConfig, flight_found: FlightFound
    ) -> None:
        """Test should_notify is True when below threshold."""
        alert = PriceAlert(
            flight=flight_found,
            route_config=route,
            previous_price=None,
            price_change=None,
            price_change_pct=None,
            is_below_threshold=True,
            is_significant_drop=False,
        )

        assert alert.should_notify is True

    def test_should_notify_significant_drop(
        self, route: RouteConfig, flight_found: FlightFound
    ) -> None:
        """Test should_notify is True for significant drop."""
        # Create a flight above threshold
        expensive_flight = FlightFound(
            flight_id="BAQ-MDE_2025-03-15_18:30_LATAM",
            route="BAQ→MDE",
            travel_date=date(2025, 3, 15),
            departure_time="18:30",
            airline="LATAM",
            price=170000,  # Above threshold
            is_priority=True,
        )
        alert = PriceAlert(
            flight=expensive_flight,
            route_config=route,
            previous_price=200000,
            price_change=-30000,
            price_change_pct=-15.0,  # 15% drop
            is_below_threshold=False,
            is_significant_drop=True,
        )

        assert alert.should_notify is True

    def test_should_notify_false(
        self, route: RouteConfig, flight_found: FlightFound
    ) -> None:
        """Test should_notify is False when conditions not met."""
        # Create a flight above threshold with small drop
        expensive_flight = FlightFound(
            flight_id="BAQ-MDE_2025-03-15_18:30_LATAM",
            route="BAQ→MDE",
            travel_date=date(2025, 3, 15),
            departure_time="18:30",
            airline="LATAM",
            price=180000,  # Above threshold
            is_priority=True,
        )
        alert = PriceAlert(
            flight=expensive_flight,
            route_config=route,
            previous_price=190000,
            price_change=-10000,
            price_change_pct=-5.3,  # Only 5% drop
            is_below_threshold=False,
            is_significant_drop=False,
        )

        assert alert.should_notify is False


class TestCreateAlert:
    """Tests for alert creation."""

    def test_create_alert_below_threshold(
        self, service: FlightTrackerService, route: RouteConfig
    ) -> None:
        """Test alert is created for price below threshold."""
        flight = FlightFound(
            flight_id="BAQ-MDE_2025-03-15_18:30_LATAM",
            route="BAQ→MDE",
            travel_date=date(2025, 3, 15),
            departure_time="18:30",
            airline="LATAM",
            price=100000,  # Below 150000 threshold
            is_priority=True,
        )

        alert = service._create_alert(flight, route)

        assert alert.is_below_threshold is True
        assert alert.flight.price == 100000

    def test_create_alert_above_threshold(
        self, service: FlightTrackerService, route: RouteConfig
    ) -> None:
        """Test alert for price above threshold."""
        flight = FlightFound(
            flight_id="BAQ-MDE_2025-03-15_18:30_LATAM",
            route="BAQ→MDE",
            travel_date=date(2025, 3, 15),
            departure_time="18:30",
            airline="LATAM",
            price=200000,  # Above 150000 threshold
            is_priority=True,
        )

        alert = service._create_alert(flight, route)

        assert alert.is_below_threshold is False

    def test_create_alert_with_previous_price(
        self,
        service: FlightTrackerService,
        route: RouteConfig,
        tmp_path: Path,
    ) -> None:
        """Test alert calculates price change correctly."""
        # Set up previous prices in the price store (need 2 entries for previous_price)
        # First record at 180000, then price dropped to 150000
        service._price_store.set_flight_price(
            route="BAQ-MDE",
            travel_date=date(2025, 3, 15),
            departure_time="18:30",
            airline="LATAM",
            price=180000,  # First price (becomes previous_price)
        )
        service._price_store.set_flight_price(
            route="BAQ-MDE",
            travel_date=date(2025, 3, 15),
            departure_time="18:30",
            airline="LATAM",
            price=150000,  # Latest price in history
        )

        # Now flight comes in at 120000 (30000 drop from latest 150000)
        flight = FlightFound(
            flight_id="BAQ-MDE_2025-03-15_18:30_LATAM",
            route="BAQ→MDE",
            travel_date=date(2025, 3, 15),
            departure_time="18:30",
            airline="LATAM",
            price=120000,
            is_priority=True,
        )

        alert = service._create_alert(flight, route)

        # previous_price is second-to-last in history (180000)
        # The comparison is between new price (120000) and previous (180000)
        assert alert.previous_price == 180000
        assert alert.price_change == -60000  # 120000 - 180000
        assert alert.price_change_pct == -33.3  # -60000/180000 * 100
        assert alert.is_significant_drop is True

    def test_create_alert_without_previous_price(
        self, service: FlightTrackerService, route: RouteConfig
    ) -> None:
        """Test alert without previous price."""
        flight = FlightFound(
            flight_id="BAQ-MDE_2025-03-15_19:00_LATAM",  # Different time, no history
            route="BAQ→MDE",
            travel_date=date(2025, 3, 15),
            departure_time="19:00",
            airline="LATAM",
            price=120000,
            is_priority=True,
        )

        alert = service._create_alert(flight, route)

        assert alert.previous_price is None
        assert alert.price_change is None
        assert alert.is_significant_drop is False


class TestTrackFlights:
    """Tests for the main tracking flow."""

    @pytest.mark.asyncio
    async def test_track_flights_returns_result(
        self, service: FlightTrackerService, mock_scraper: AsyncMock
    ) -> None:
        """Test track_flights returns FlightTrackerResult."""
        # scrape() returns list of FlightResult
        mock_scraper.scrape.return_value = [
            FlightResult(
                price=120000,
                airline="LATAM",
                departure_time=datetime(2025, 3, 14, 18, 30),  # Thursday 6:30 PM
                arrival_time=datetime(2025, 3, 14, 19, 45),
                duration=timedelta(hours=1, minutes=15),
                stops=0,
                booking_link="https://example.com",
            )
        ]

        result = await service.track_flights()

        assert isinstance(result, FlightTrackerResult)
        assert result.routes_checked == 2  # 2 routes in test config (BAQ-MDE, CTG-MDE)
        assert result.dates_checked > 0

    @pytest.mark.asyncio
    async def test_track_flights_generates_alerts(
        self,
        service: FlightTrackerService,
        mock_scraper: AsyncMock,
    ) -> None:
        """Test track_flights generates alerts for low prices."""
        # LATAM below threshold triggers alert
        mock_scraper.scrape.return_value = [
            FlightResult(
                price=100000,  # Below 150000 threshold
                airline="LATAM",
                departure_time=datetime(
                    2025, 3, 14, 18, 30
                ),  # Thursday 6:30 PM (valid time)
                arrival_time=datetime(2025, 3, 14, 19, 45),
                duration=timedelta(hours=1, minutes=15),
                stops=0,
                booking_link="https://example.com",
            )
        ]

        result = await service.track_flights()

        assert result.alerts_generated > 0
        assert result.flights_found > 0

    @pytest.mark.asyncio
    async def test_track_flights_sends_notifications(
        self,
        service: FlightTrackerService,
        mock_scraper: AsyncMock,
        mock_notifier: AsyncMock,
    ) -> None:
        """Test track_flights sends notifications for alerts."""
        mock_scraper.scrape.return_value = [
            FlightResult(
                price=100000,  # Below threshold
                airline="LATAM",
                departure_time=datetime(2025, 3, 14, 18, 30),  # Thursday valid time
                arrival_time=datetime(2025, 3, 14, 19, 45),
                duration=timedelta(hours=1, minutes=15),
                stops=0,
                booking_link="https://example.com",
            )
        ]

        result = await service.track_flights()

        # Now tracker collects alerts but doesn't send notifications directly
        # Notifications are sent by the orchestrator after full scan
        assert result.alerts_generated > 0
        assert len(result.price_alerts) > 0
        assert result.notifications_sent == 0  # Orchestrator handles this

    @pytest.mark.asyncio
    async def test_track_flights_handles_no_flights(
        self,
        service: FlightTrackerService,
        mock_scraper: AsyncMock,
    ) -> None:
        """Test track_flights handles no flights found gracefully."""
        mock_scraper.scrape.return_value = []  # No flights

        result = await service.track_flights()

        assert result.alerts_generated == 0
        assert result.flights_found == 0
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_track_flights_collects_errors(
        self,
        service: FlightTrackerService,
        mock_scraper: AsyncMock,
    ) -> None:
        """Test track_flights collects errors."""
        mock_scraper.scrape.side_effect = Exception("Network error")

        result = await service.track_flights()

        assert len(result.errors) > 0
        assert "Network error" in result.errors[0]


class TestSendNotification:
    """Tests for notification sending."""

    @pytest.mark.asyncio
    async def test_send_notification_calls_notifier(
        self,
        service: FlightTrackerService,
        route: RouteConfig,
        flight_found: FlightFound,
        mock_notifier: AsyncMock,
    ) -> None:
        """Test notification is sent via notifier."""
        alert = PriceAlert(
            flight=flight_found,
            route_config=route,
            previous_price=None,
            price_change=None,
            price_change_pct=None,
            is_below_threshold=True,
            is_significant_drop=False,
        )

        await service._send_notification(alert)

        mock_notifier.send_flight_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_notification_handles_error(
        self,
        service: FlightTrackerService,
        route: RouteConfig,
        flight_found: FlightFound,
        mock_notifier: AsyncMock,
    ) -> None:
        """Test notification error is handled."""
        mock_notifier.send_flight_alert.side_effect = Exception("Send failed")

        alert = PriceAlert(
            flight=flight_found,
            route_config=route,
            previous_price=None,
            price_change=None,
            price_change_pct=None,
            is_below_threshold=True,
            is_significant_drop=False,
        )

        # Should not raise
        await service._send_notification(alert)


class TestGetUpcomingDates:
    """Tests for date retrieval."""

    def test_get_upcoming_dates(self, service: FlightTrackerService) -> None:
        """Test get_upcoming_dates returns dates."""
        dates = service.get_upcoming_dates()

        assert len(dates) == 2  # weeks_ahead=2
        for d in dates:
            assert d.weekday() == 4  # All Fridays

    def test_get_bridge_weekends(self, service: FlightTrackerService) -> None:
        """Test get_bridge_weekends returns dates."""
        bridges = service.get_bridge_weekends()

        assert isinstance(bridges, list)
        # May be empty depending on holidays config


class TestSaveState:
    """Tests for state persistence."""

    @pytest.mark.asyncio
    async def test_save_state_calls_manager(
        self, service: FlightTrackerService, mock_state_manager: MagicMock
    ) -> None:
        """Test save_state calls state manager."""
        await service.save_state()

        mock_state_manager.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_state_without_manager(self, routes_config: Path) -> None:
        """Test save_state handles no state manager."""
        service = FlightTrackerService(routes_config_path=routes_config)

        # Should not raise
        await service.save_state()


class TestFlightTrackerResultDataclass:
    """Tests for FlightTrackerResult dataclass."""

    def test_create_result(self) -> None:
        """Test creating FlightTrackerResult."""
        result = FlightTrackerResult(
            routes_checked=2,
            dates_checked=16,
            flights_found=10,
            alerts_generated=5,
            notifications_sent=5,
            prices_found=[],
            price_alerts=[],
            errors=[],
        )

        assert result.routes_checked == 2
        assert result.dates_checked == 16
        assert result.flights_found == 10
        assert result.alerts_generated == 5
        assert result.errors == []
