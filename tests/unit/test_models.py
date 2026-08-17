"""Tests for data models."""

from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

from aventure_tracker.models import (
    AccountsConfig,
    DoneConfig,
    FlightResult,
    FlightState,
    InstagramAccountConfig,
    InstagramAccountState,
    InstagramPost,
    RouteConfig,
    RoutesConfig,
    StateData,
    TimeRange,
    TrackerResult,
    WeekendTrip,
    WishlistConfig,
)


class TestRouteConfig:
    """Tests for RouteConfig model."""

    def test_route_config_creation(self) -> None:
        """Test creating a valid route config."""
        route = RouteConfig(
            origin="BAQ",
            destination="MDE",
            price_threshold=150000,
            drop_percentage=15,
        )

        assert route.origin == "BAQ"
        assert route.destination == "MDE"
        assert route.price_threshold == 150000
        assert route.drop_percentage == 15

    def test_route_config_uppercase_codes(self) -> None:
        """Test that airport codes are uppercased."""
        route = RouteConfig(
            origin="baq",
            destination="mde",
            price_threshold=150000,
            drop_percentage=15,
        )

        assert route.origin == "BAQ"
        assert route.destination == "MDE"

    def test_route_config_validation_invalid_code(self) -> None:
        """Test validation rejects invalid airport codes."""
        with pytest.raises(ValueError):
            RouteConfig(
                origin="BA",  # Too short
                destination="MDE",
                price_threshold=150000,
                drop_percentage=15,
            )

    def test_route_config_validation_invalid_threshold(self) -> None:
        """Test validation rejects invalid price threshold."""
        with pytest.raises(ValueError):
            RouteConfig(
                origin="BAQ",
                destination="MDE",
                price_threshold=-1,  # Negative
                drop_percentage=15,
            )

    def test_route_config_get_route_key(self) -> None:
        """Test route key generation."""
        route = RouteConfig(
            origin="BAQ",
            destination="MDE",
            price_threshold=150000,
            drop_percentage=15,
        )
        key = route.get_route_key(date(2025, 3, 15))

        assert key == "BAQ-MDE-2025-03-15"

    def test_route_config_str(self) -> None:
        """Test string representation."""
        route = RouteConfig(
            origin="BAQ",
            destination="MDE",
            price_threshold=150000,
            drop_percentage=15,
        )

        assert str(route) == "BAQ→MDE"


class TestRoutesConfig:
    """Tests for RoutesConfig model."""

    def test_routes_config_from_yaml(self, temp_config_dir: Path) -> None:
        """Test loading routes from YAML."""
        config = RoutesConfig.from_yaml(temp_config_dir / "routes.yaml")

        assert len(config.routes) == 1
        assert config.routes[0].origin == "BAQ"
        assert config.routes[0].destination == "MDE"

    def test_routes_config_file_not_found(self, tmp_path: Path) -> None:
        """Test error when file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            RoutesConfig.from_yaml(tmp_path / "nonexistent.yaml")


class TestFlightResult:
    """Tests for FlightResult model."""

    def test_flight_result_creation(self) -> None:
        """Test creating a flight result."""
        flight = FlightResult(
            price=145000,
            airline="Avianca",
            departure_time=datetime(2025, 3, 15, 18, 30),
            arrival_time=datetime(2025, 3, 15, 19, 45),
            duration=timedelta(hours=1, minutes=15),
            stops=0,
            booking_link="https://example.com/book",
        )

        assert flight.price == 145000
        assert flight.airline == "Avianca"
        assert flight.is_direct is True
        assert flight.departure_date == date(2025, 3, 15)
        assert flight.departure_time_only == time(18, 30)

    def test_flight_result_format_duration(self) -> None:
        """Test duration formatting."""
        flight = FlightResult(
            price=145000,
            airline="Avianca",
            departure_time=datetime(2025, 3, 15, 18, 30),
            arrival_time=datetime(2025, 3, 15, 19, 45),
            duration=timedelta(hours=1, minutes=15),
            stops=0,
            booking_link="https://example.com/book",
        )

        assert flight.format_duration() == "1h 15m"

    def test_flight_result_format_duration_minutes_only(self) -> None:
        """Test duration formatting for short flights."""
        flight = FlightResult(
            price=145000,
            airline="Avianca",
            departure_time=datetime(2025, 3, 15, 18, 30),
            arrival_time=datetime(2025, 3, 15, 19, 15),
            duration=timedelta(minutes=45),
            stops=0,
            booking_link="https://example.com/book",
        )

        assert flight.format_duration() == "45m"


class TestTimeRange:
    """Tests for TimeRange model."""

    def test_time_range_contains(self) -> None:
        """Test time range containment check."""
        range_ = TimeRange(start=time(18, 0), end=time(23, 59))

        assert range_.contains(time(18, 0)) is True
        assert range_.contains(time(20, 30)) is True
        assert range_.contains(time(23, 59)) is True
        assert range_.contains(time(17, 59)) is False
        assert range_.contains(time(0, 0)) is False


class TestWeekendTrip:
    """Tests for WeekendTrip model."""

    def test_weekend_trip_valid_times(self) -> None:
        """Test checking valid flight times."""
        trip = WeekendTrip(
            outbound_date=date(2025, 3, 14),
            return_date=date(2025, 3, 16),
            is_bridge=False,
            outbound_times=[TimeRange(start=time(18, 0), end=time(23, 59))],
            return_times=[TimeRange(start=time(14, 0), end=time(23, 59))],
        )

        assert trip.is_valid_outbound_time(time(19, 0)) is True
        assert trip.is_valid_outbound_time(time(10, 0)) is False
        assert trip.is_valid_return_time(time(15, 0)) is True
        assert trip.is_valid_return_time(time(10, 0)) is False


class TestInstagramPost:
    """Tests for InstagramPost model."""

    def test_instagram_post_creation(self) -> None:
        """Test creating an Instagram post."""
        post = InstagramPost(
            id="ABC123",
            url="https://instagram.com/p/ABC123",
            image_urls=["https://example.com/img1.jpg", "https://example.com/img2.jpg"],
            caption="Viaje a Guatapé #adventure",
            timestamp=datetime(2025, 3, 15, 10, 30),
        )

        assert post.id == "ABC123"
        assert post.has_images is True
        assert post.first_image_url == "https://example.com/img1.jpg"

    def test_instagram_post_no_images(self) -> None:
        """Test post without images."""
        post = InstagramPost(
            id="ABC123",
            url="https://instagram.com/p/ABC123",
            image_urls=[],
            caption="Text only post",
            timestamp=datetime(2025, 3, 15, 10, 30),
        )

        assert post.has_images is False
        assert post.first_image_url is None


class TestAccountsConfig:
    """Tests for AccountsConfig model."""

    def test_accounts_config_from_yaml(self, temp_config_dir: Path) -> None:
        """Test loading accounts from YAML."""
        config = AccountsConfig.from_yaml(temp_config_dir / "accounts.yaml")

        assert len(config.accounts) == 1
        assert config.accounts[0].username == "testaccount"
        assert config.accounts[0].enabled is True

    def test_accounts_config_enabled_only(self) -> None:
        """Test filtering enabled accounts."""
        config = AccountsConfig(
            accounts=[
                InstagramAccountConfig(username="active", name="Active", enabled=True),
                InstagramAccountConfig(
                    username="inactive", name="Inactive", enabled=False
                ),
            ]
        )

        enabled = config.enabled_accounts
        assert len(enabled) == 1
        assert enabled[0].username == "active"


class TestWishlistConfig:
    """Tests for WishlistConfig model."""

    def test_wishlist_config_from_yaml(self, temp_config_dir: Path) -> None:
        """Test loading wishlist from YAML."""
        config = WishlistConfig.from_yaml(temp_config_dir / "wishlist.yaml")

        assert len(config.destinations) == 2
        assert "Guatapé" in config.destinations

    def test_wishlist_config_normalized(self) -> None:
        """Test normalized destinations."""
        config = WishlistConfig(destinations=["Guatapé", "San Gil", "JARDÍN"])
        normalized = config.get_normalized_destinations()

        assert "guatapé" in normalized
        assert "san gil" in normalized
        assert "jardín" in normalized

    def test_wishlist_config_missing_file(self, tmp_path: Path) -> None:
        """Test returns empty config for missing file."""
        config = WishlistConfig.from_yaml(tmp_path / "nonexistent.yaml")
        assert len(config.destinations) == 0


class TestDoneConfig:
    """Tests for DoneConfig model."""

    def test_done_config_from_yaml(self, temp_config_dir: Path) -> None:
        """Test loading done activities from YAML."""
        config = DoneConfig.from_yaml(temp_config_dir / "done.yaml")

        assert len(config.activities) == 1
        assert "Bungee Medellín" in config.activities

    def test_done_config_normalized(self) -> None:
        """Test normalized activities."""
        config = DoneConfig(activities=["Bungee Medellín", "Guatapé - Agosto 2024"])
        normalized = config.get_normalized_activities()

        assert "bungee medellín" in normalized
        assert "guatapé - agosto 2024" in normalized


class TestFlightState:
    """Tests for FlightState model."""

    def test_flight_state_creation(self) -> None:
        """Test creating a flight state."""
        state = FlightState(last_price=150000)

        assert state.last_price == 150000
        assert state.last_notified is None
        assert state.price_history == []

    def test_flight_state_add_price(self) -> None:
        """Test adding prices to history."""
        state = FlightState(last_price=150000)
        state.add_price(150000)
        state.add_price(145000)
        state.add_price(140000)

        assert len(state.price_history) == 3
        assert state.price_history == [150000, 145000, 140000]

    def test_flight_state_price_history_limit(self) -> None:
        """Test price history is limited to 10."""
        state = FlightState(last_price=100000)
        for i in range(15):
            state.add_price(100000 + i * 1000)

        assert len(state.price_history) == 10

    def test_flight_state_average_price(self) -> None:
        """Test average price calculation."""
        state = FlightState(last_price=150000, price_history=[100000, 110000, 120000])

        assert state.average_price == 110000.0

    def test_flight_state_average_price_empty(self) -> None:
        """Test average price with no history."""
        state = FlightState(last_price=150000)

        assert state.average_price is None

    def test_flight_state_drop_percentage(self) -> None:
        """Test drop percentage calculation."""
        state = FlightState(last_price=150000)
        drop = state.calculate_drop_percentage(127500)  # 15% drop

        assert drop == 15.0


class TestInstagramAccountState:
    """Tests for InstagramAccountState model."""

    def test_instagram_state_add_seen_post(self) -> None:
        """Test adding seen posts."""
        state = InstagramAccountState()
        state.add_seen_post("ABC123")
        state.add_seen_post("DEF456")

        assert state.is_seen("ABC123") is True
        assert state.is_seen("DEF456") is True
        assert state.is_seen("XYZ789") is False

    def test_instagram_state_no_duplicates(self) -> None:
        """Test no duplicate post IDs."""
        state = InstagramAccountState()
        state.add_seen_post("ABC123")
        state.add_seen_post("ABC123")

        assert len(state.seen_post_ids) == 1

    def test_instagram_state_limit_100(self) -> None:
        """Test seen posts limited to 100."""
        state = InstagramAccountState()
        for i in range(150):
            state.add_seen_post(f"post_{i}")

        assert len(state.seen_post_ids) == 100


class TestStateData:
    """Tests for StateData model."""

    def test_state_data_empty(self) -> None:
        """Test creating empty state."""
        state = StateData.empty()

        assert state.version == 1
        assert state.flights == {}
        assert state.instagram == {}

    def test_state_data_set_flight(self) -> None:
        """Test setting flight state."""
        state = StateData.empty()
        flight_state = state.set_flight_state(
            "BAQ-MDE-2025-03-15", 150000, notified=True
        )

        assert flight_state.last_price == 150000
        assert flight_state.last_notified is not None
        assert 150000 in flight_state.price_history

    def test_state_data_get_flight(self) -> None:
        """Test getting flight state."""
        state = StateData.empty()
        state.set_flight_state("BAQ-MDE-2025-03-15", 150000)

        retrieved = state.get_flight_state("BAQ-MDE-2025-03-15")
        assert retrieved is not None
        assert retrieved.last_price == 150000

        not_found = state.get_flight_state("CTG-MDE-2025-03-15")
        assert not_found is None

    def test_state_data_mark_post_seen(self) -> None:
        """Test marking Instagram post as seen."""
        state = StateData.empty()
        state.mark_post_seen("testaccount", "ABC123")

        assert state.is_post_seen("testaccount", "ABC123") is True
        assert state.is_post_seen("testaccount", "DEF456") is False
        assert state.is_post_seen("otheraccount", "ABC123") is False

    def test_state_data_serialization(self) -> None:
        """Test state serialization/deserialization."""
        state = StateData.empty()
        state.set_flight_state("BAQ-MDE-2025-03-15", 150000)
        state.mark_post_seen("testaccount", "ABC123")

        # Serialize
        data = state.to_dict()
        assert "flights" in data
        assert "instagram" in data

        # Deserialize
        restored = StateData.from_dict(data)
        assert restored.get_flight_state("BAQ-MDE-2025-03-15") is not None
        assert restored.is_post_seen("testaccount", "ABC123") is True


class TestTrackerResult:
    """Tests for TrackerResult model."""

    def test_tracker_result_success(self) -> None:
        """Test successful tracker result."""
        result = TrackerResult(success=True, notifications_sent=3, items_checked=10)

        assert result.success is True
        assert result.notifications_sent == 3
        assert result.has_errors is False

    def test_tracker_result_with_errors(self) -> None:
        """Test tracker result with errors."""
        result = TrackerResult(success=False)
        result.add_error("Failed to connect")
        result.add_error("Timeout")

        assert result.has_errors is True
        assert len(result.errors) == 2
