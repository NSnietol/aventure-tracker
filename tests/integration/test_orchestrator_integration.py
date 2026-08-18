"""Integration tests for the Adventure Tracker orchestrator.

These tests verify the end-to-end flow with mocked external services.
Run with: pytest tests/integration -v -m integration
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from aventure_tracker.config import Settings
from aventure_tracker.main import AdventureOrchestrator, RunMode
from aventure_tracker.services.flights.tracker import FlightTrackerResult


@pytest.fixture
def integration_config(tmp_path: Path) -> Path:
    """Create a complete configuration directory for integration tests."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

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
    (config_dir / "accounts.yaml").write_text(
        """
accounts:
  - username: test_adventure
    name: Test Adventure Account
    enabled: true
"""
    )
    (config_dir / "holidays.yaml").write_text(
        """
holidays:
  2025:
    - date: "2025-08-18"
      name: "Asunción de la Virgen"
"""
    )
    (config_dir / "wishlist.yaml").write_text(
        """
destinations:
  - Guatapé
  - Santa Marta
  - San Gil
  - Salento
"""
    )
    (config_dir / "done.yaml").write_text(
        """
activities:
  - Guatapé - Piedra del Peñol 2024
"""
    )
    return config_dir


@pytest.fixture
def integration_settings(integration_config: Path) -> Settings:
    settings = Settings(config_dir=integration_config, log_level="ERROR")
    object.__setattr__(settings, "gist_id", "")
    object.__setattr__(settings, "gist_token", "")
    return settings


@pytest.mark.integration
class TestOrchestratorIntegration:
    """Integration tests for the full orchestrator flow."""

    @pytest.mark.asyncio
    async def test_flights_only_mode(self, integration_settings: Settings) -> None:
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
    async def test_graceful_error_handling(
        self, integration_settings: Settings
    ) -> None:
        """Test orchestrator handles flight tracker failures gracefully."""
        orchestrator = AdventureOrchestrator(
            settings=integration_settings,
            mode=RunMode.FLIGHTS,
        )
        with patch("aventure_tracker.main.FlightTrackerService") as mock_flight_cls:
            mock_flight = AsyncMock()
            mock_flight.track_flights = AsyncMock(
                side_effect=Exception("Network timeout")
            )
            mock_flight_cls.return_value = mock_flight
            result = await orchestrator.run()

        assert result.success is False
        assert len(result.errors) > 0
        assert "Network timeout" in result.errors[0]

    def test_inventory_manager_with_config(self, integration_config: Path) -> None:
        """Test inventory manager loads configuration files."""
        from aventure_tracker.services.events.inventory import InventoryManager

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
        all_blacklisted = inventory.destinations.get_all_blacklisted()
        assert len(all_blacklisted) == 4
        assert "cerro tusa" in all_blacklisted

        ya_fue = inventory.destinations.get_by_reason("ya_fue")
        assert len(ya_fue) == 2


@pytest.mark.integration
class TestConfigurationIntegration:
    """Integration tests for configuration loading."""

    def test_load_all_config_files(self, integration_config: Path) -> None:
        from aventure_tracker.models.activity import AccountsConfig, WishlistConfig
        from aventure_tracker.models.flight import RoutesConfig

        routes = RoutesConfig.from_yaml(integration_config / "routes.yaml")
        assert len(routes.routes) == 2
        assert routes.routes[0].origin == "BAQ"

        accounts = AccountsConfig.from_yaml(integration_config / "accounts.yaml")
        assert len(accounts.accounts) == 1

        wishlist = WishlistConfig.from_yaml(integration_config / "wishlist.yaml")
        assert len(wishlist.destinations) == 4
        assert "Guatapé" in wishlist.destinations

    def test_settings_path_helpers(self, integration_settings: Settings) -> None:
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
        from aventure_tracker.services.flights.dates import FlightDateCalculator
        from aventure_tracker.services.shared.holidays import HolidayService

        holiday_service = HolidayService(
            config_path=integration_config / "holidays.yaml"
        )
        calculator = FlightDateCalculator(holiday_service=holiday_service)
        weekends = calculator.get_upcoming_weekends(weeks_ahead=4)
        assert len(weekends) == 4
        for weekend in weekends:
            assert weekend.outbound_date.weekday() == 4  # Friday
