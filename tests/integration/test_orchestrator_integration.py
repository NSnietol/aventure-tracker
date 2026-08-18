"""Integration tests for the Adventure Orchestrator.

These tests verify the end-to-end flow with mocked external services.
Run with: pytest tests/integration -v -m integration
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from aventure_tracker.config import Settings
from aventure_tracker.main import AdventureOrchestrator, RunMode
from aventure_tracker.services.events.activity_service import ActivityTrackerResult
from aventure_tracker.services.flights.tracker import FlightTrackerResult


@pytest.fixture
def integration_config(tmp_path: Path) -> Path:
    """Create a complete configuration directory for integration tests."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Routes configuration
    (config_dir / "routes.yaml").write_text(
        """
routes:
  - origin: BAQ
    destination: MDE
    price_threshold: 150000
    drop_percentage: 15
  - origin: CTG
    destination: MDE
    price_threshold: 150000
    drop_percentage: 15
"""
    )

    # Accounts configuration
    (config_dir / "accounts.yaml").write_text(
        """
accounts:
  - username: test_adventure
    name: Test Adventure Account
    enabled: true
  - username: test_travel
    name: Test Travel Account
    enabled: true
"""
    )

    # Holidays configuration
    (config_dir / "holidays.yaml").write_text(
        """
holidays:
  2025:
    - date: "2025-08-18"
      name: "Asunción de la Virgen"
    - date: "2025-10-13"
      name: "Día de la Raza"
    - date: "2025-11-03"
      name: "Todos los Santos"
"""
    )

    # Wishlist configuration
    (config_dir / "wishlist.yaml").write_text(
        """
destinations:
  - Guatapé
  - Santa Marta
  - San Gil
  - Salento
"""
    )

    # Done configuration
    (config_dir / "done.yaml").write_text(
        """
activities:
  - Guatapé - Piedra del Peñol 2024
"""
    )

    return config_dir


@pytest.fixture
def integration_settings(integration_config: Path) -> Settings:
    """Create settings for integration tests."""
    settings = Settings(
        config_dir=integration_config,
        log_level="ERROR",
    )
    # Set gist credentials for state manager
    object.__setattr__(settings, "gist_id", "")
    object.__setattr__(settings, "gist_token", "")
    return settings


@pytest.mark.integration
class TestOrchestratorIntegration:
    """Integration tests for the full orchestrator flow."""

    @pytest.mark.asyncio
    async def test_full_run_with_mocked_scrapers(
        self,
        integration_settings: Settings,
    ) -> None:
        """Test complete orchestrator run with mocked scrapers."""
        orchestrator = AdventureOrchestrator(
            settings=integration_settings,
            mode=RunMode.ALL,
            weeks_ahead=2,
        )

        # Mock both trackers
        with patch("aventure_tracker.main.FlightTrackerService") as mock_flight_cls:
            with patch(
                "aventure_tracker.main.ActivityTrackerService"
            ) as mock_activity_cls:
                # Setup flight tracker mock
                mock_flight = AsyncMock()
                mock_flight.track_flights = AsyncMock(
                    return_value=FlightTrackerResult(
                        routes_checked=2,
                        dates_checked=4,
                        flights_found=0,
                        alerts_generated=1,
                        notifications_sent=0,  # No notifier configured
                        prices_found=[],
                        price_alerts=[],
                        errors=[],
                    )
                )
                mock_flight_cls.return_value = mock_flight

                # Setup activity tracker mock
                mock_activity = AsyncMock()
                mock_activity.track_activities = AsyncMock(
                    return_value=ActivityTrackerResult(
                        accounts_checked=2,
                        posts_found=10,
                        posts_processed=8,
                        posts_skipped=0,
                        alerts_generated=2,
                        notifications_sent=0,
                        errors=[],
                    )
                )
                mock_activity_cls.return_value = mock_activity

                result = await orchestrator.run()

        # Verify results
        assert result.success is True
        assert result.mode == RunMode.ALL
        assert result.total_alerts == 3  # 1 flight + 2 activity
        assert result.flights_result is not None
        assert result.activities_result is not None
        assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_flights_only_mode(
        self,
        integration_settings: Settings,
    ) -> None:
        """Test orchestrator in flights-only mode."""
        orchestrator = AdventureOrchestrator(
            settings=integration_settings,
            mode=RunMode.FLIGHTS,
            weeks_ahead=4,
        )

        with patch("aventure_tracker.main.FlightTrackerService") as mock_flight_cls:
            mock_flight = AsyncMock()
            mock_flight.track_flights = AsyncMock(
                return_value=FlightTrackerResult(
                    routes_checked=2,
                    dates_checked=8,
                    flights_found=0,
                    alerts_generated=2,
                    notifications_sent=0,
                    prices_found=[],
                    price_alerts=[],
                    errors=[],
                )
            )
            mock_flight_cls.return_value = mock_flight

            result = await orchestrator.run()

        assert result.success is True
        assert result.mode == RunMode.FLIGHTS
        assert result.flights_result is not None
        assert result.activities_result is None

    @pytest.mark.asyncio
    async def test_activities_only_mode(
        self,
        integration_settings: Settings,
    ) -> None:
        """Test orchestrator in activities-only mode."""
        orchestrator = AdventureOrchestrator(
            settings=integration_settings,
            mode=RunMode.ACTIVITIES,
        )

        with patch("aventure_tracker.main.ActivityTrackerService") as mock_activity_cls:
            mock_activity = AsyncMock()
            mock_activity.track_activities = AsyncMock(
                return_value=ActivityTrackerResult(
                    accounts_checked=2,
                    posts_found=15,
                    posts_processed=12,
                    posts_skipped=0,
                    alerts_generated=3,
                    notifications_sent=0,
                    errors=[],
                )
            )
            mock_activity_cls.return_value = mock_activity

            result = await orchestrator.run()

        assert result.success is True
        assert result.mode == RunMode.ACTIVITIES
        assert result.flights_result is None
        assert result.activities_result is not None

    @pytest.mark.asyncio
    async def test_graceful_error_handling(
        self,
        integration_settings: Settings,
    ) -> None:
        """Test orchestrator handles partial failures gracefully."""
        orchestrator = AdventureOrchestrator(
            settings=integration_settings,
            mode=RunMode.ALL,
        )

        with patch("aventure_tracker.main.FlightTrackerService") as mock_flight_cls:
            with patch(
                "aventure_tracker.main.ActivityTrackerService"
            ) as mock_activity_cls:
                # Flight tracker fails
                mock_flight = AsyncMock()
                mock_flight.track_flights = AsyncMock(
                    side_effect=Exception("Network timeout")
                )
                mock_flight_cls.return_value = mock_flight

                # Activity tracker succeeds
                mock_activity = AsyncMock()
                mock_activity.track_activities = AsyncMock(
                    return_value=ActivityTrackerResult(
                        accounts_checked=2,
                        posts_found=5,
                        posts_processed=5,
                        posts_skipped=0,
                        alerts_generated=1,
                        notifications_sent=0,
                        errors=[],
                    )
                )
                mock_activity_cls.return_value = mock_activity

                result = await orchestrator.run()

        # Should complete with errors recorded
        assert result.success is False
        assert len(result.errors) > 0
        assert "Network timeout" in result.errors[0]
        # Activity tracker should still have run
        assert result.activities_result is not None


@pytest.mark.integration
class TestConfigurationIntegration:
    """Integration tests for configuration loading."""

    def test_load_all_config_files(self, integration_config: Path) -> None:
        """Test all configuration files can be loaded."""
        from aventure_tracker.models.activity import AccountsConfig, WishlistConfig
        from aventure_tracker.models.flight import RoutesConfig

        # Load routes
        routes = RoutesConfig.from_yaml(integration_config / "routes.yaml")
        assert len(routes.routes) == 2
        assert routes.routes[0].origin == "BAQ"

        # Load accounts
        accounts = AccountsConfig.from_yaml(integration_config / "accounts.yaml")
        assert len(accounts.accounts) == 2
        assert len(accounts.enabled_accounts) == 2

        # Load wishlist
        wishlist = WishlistConfig.from_yaml(integration_config / "wishlist.yaml")
        assert len(wishlist.destinations) == 4
        assert "Guatapé" in wishlist.destinations

    def test_settings_path_helpers(self, integration_settings: Settings) -> None:
        """Test settings path helper methods."""
        assert integration_settings.get_routes_path().exists()
        assert integration_settings.get_accounts_path().exists()
        assert integration_settings.get_holidays_path().exists()
        assert integration_settings.get_wishlist_path().exists()
        assert integration_settings.get_done_path().exists()


@pytest.mark.integration
class TestServiceIntegration:
    """Integration tests for service interactions."""

    def test_flight_date_calculator_with_holidays(
        self, integration_config: Path
    ) -> None:
        """Test flight date calculator uses holiday configuration."""
        from aventure_tracker.services.flights.dates import FlightDateCalculator
        from aventure_tracker.services.shared.holidays import HolidayService

        holiday_service = HolidayService(
            config_path=integration_config / "holidays.yaml"
        )
        calculator = FlightDateCalculator(holiday_service=holiday_service)

        # Get upcoming weekends
        weekends = calculator.get_upcoming_weekends(weeks_ahead=4)
        assert len(weekends) == 4

        # All should have outbound on Friday
        for weekend in weekends:
            assert weekend.outbound_date.weekday() == 4  # Friday

    def test_inventory_manager_with_config(self, integration_config: Path) -> None:
        """Test inventory manager loads configuration files."""
        from aventure_tracker.services.events.inventory import InventoryManager

        # Create a destinations.yaml file for the test
        destinations_file = integration_config / "destinations.yaml"
        destinations_file.write_text(
            """
blacklist:
  ya_fue:
    - Cerro Tusa
    - San Luis
  playa:
    - Rincón del Mar
  no_interesa:
    - avistamiento de ballenas
"""
        )

        inventory = InventoryManager(destinations_path=destinations_file)
        inventory.load()

        # Check blacklist loaded (normalized to lowercase)
        all_blacklisted = inventory.destinations.get_all_blacklisted()
        assert len(all_blacklisted) == 4
        assert "cerro tusa" in all_blacklisted
        assert "san luis" in all_blacklisted

        # Check ya_fue count
        ya_fue = inventory.destinations.get_by_reason("ya_fue")
        assert len(ya_fue) == 2
