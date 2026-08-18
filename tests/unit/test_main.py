"""Tests for Main Orchestrator and CLI."""

import argparse
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aventure_tracker.config import Settings
from aventure_tracker.main import (
    AdventureOrchestrator,
    OrchestratorResult,
    RunMode,
    async_main,
    create_parser,
)
from aventure_tracker.services.flights.tracker import FlightTrackerResult


@pytest.fixture
def mock_settings(tmp_path: Path) -> Settings:
    """Create mock settings with temp config directory."""
    (tmp_path / "routes.yaml").write_text("routes: []")
    (tmp_path / "accounts.yaml").write_text("accounts: []")
    (tmp_path / "holidays.yaml").write_text("holidays: {}")
    (tmp_path / "wishlist.yaml").write_text("destinations: []")
    (tmp_path / "done.yaml").write_text("activities: []")

    settings = Settings(
        config_dir=tmp_path,
        telegram_bot_token="test_token",
        telegram_chat_id="123456",
        log_level="ERROR",
    )
    object.__setattr__(settings, "gist_id", "test_gist_id")
    object.__setattr__(settings, "gist_token", "test_gist_token")
    return settings


@pytest.fixture
def mock_flight_result() -> FlightTrackerResult:
    """Create a mock flight tracker result."""
    return FlightTrackerResult(
        routes_checked=2,
        dates_checked=16,
        flights_found=0,
        alerts_generated=3,
        notifications_sent=3,
        prices_found=[],
        price_alerts=[],
        errors=[],
    )


class TestRunMode:
    """Tests for RunMode enum."""

    def test_all_mode(self) -> None:
        assert RunMode.ALL.value == "all"

    def test_flights_mode(self) -> None:
        assert RunMode.FLIGHTS.value == "flights"

    def test_activities_mode(self) -> None:
        assert RunMode.ACTIVITIES.value == "activities"

    def test_calendar_mode(self) -> None:
        assert RunMode.CALENDAR.value == "calendar"

    def test_parse_from_string(self) -> None:
        assert RunMode("all") == RunMode.ALL
        assert RunMode("flights") == RunMode.FLIGHTS
        assert RunMode("activities") == RunMode.ACTIVITIES
        assert RunMode("calendar") == RunMode.CALENDAR


class TestOrchestratorResult:
    """Tests for OrchestratorResult dataclass."""

    def test_create_result(self, mock_flight_result: FlightTrackerResult) -> None:
        result = OrchestratorResult(
            mode=RunMode.ALL,
            flights_result=mock_flight_result,
            activities_result=None,
            total_alerts=3,
            total_notifications=3,
            errors=[],
            duration_seconds=15.5,
        )
        assert result.mode == RunMode.ALL
        assert result.total_alerts == 3
        assert result.duration_seconds == 15.5

    def test_success_with_no_errors(self) -> None:
        result = OrchestratorResult(
            mode=RunMode.ALL,
            flights_result=None,
            activities_result=None,
            total_alerts=0,
            total_notifications=0,
            errors=[],
            duration_seconds=1.0,
        )
        assert result.success is True

    def test_success_with_errors(self) -> None:
        result = OrchestratorResult(
            mode=RunMode.ALL,
            flights_result=None,
            activities_result=None,
            total_alerts=0,
            total_notifications=0,
            errors=["Something went wrong"],
            duration_seconds=1.0,
        )
        assert result.success is False


class TestAdventureOrchestratorInit:
    """Tests for orchestrator initialization."""

    def test_init_with_defaults(self) -> None:
        orchestrator = AdventureOrchestrator()
        assert orchestrator._mode == RunMode.ALL
        assert orchestrator._weeks_ahead == 10
        assert orchestrator._max_posts == 10
        assert orchestrator._show_calendar is False

    def test_init_with_custom_values(self, mock_settings: Settings) -> None:
        orchestrator = AdventureOrchestrator(
            settings=mock_settings,
            mode=RunMode.FLIGHTS,
            weeks_ahead=4,
            max_posts_per_account=5,
            show_calendar=True,
        )
        assert orchestrator._mode == RunMode.FLIGHTS
        assert orchestrator._weeks_ahead == 4
        assert orchestrator._max_posts == 5
        assert orchestrator._show_calendar is True


class TestOrchestratorRun:
    """Tests for orchestrator run method."""

    @pytest.mark.asyncio
    async def test_run_flights_only(
        self,
        mock_settings: Settings,
        mock_flight_result: FlightTrackerResult,
    ) -> None:
        orchestrator = AdventureOrchestrator(
            settings=mock_settings,
            mode=RunMode.FLIGHTS,
        )
        with patch.object(orchestrator, "_init_infrastructure", new_callable=AsyncMock):
            with patch("aventure_tracker.main.FlightTrackerService") as mock_flight_cls:
                mock_flight = AsyncMock()
                mock_flight.track_flights = AsyncMock(return_value=mock_flight_result)
                mock_flight_cls.return_value = mock_flight

                result = await orchestrator.run()

        assert result.mode == RunMode.FLIGHTS
        assert result.flights_result is not None
        assert result.activities_result is None
        assert result.total_alerts == 3

    @pytest.mark.asyncio
    async def test_run_handles_flight_tracker_error(
        self,
        mock_settings: Settings,
    ) -> None:
        orchestrator = AdventureOrchestrator(
            settings=mock_settings,
            mode=RunMode.FLIGHTS,
        )
        with patch.object(orchestrator, "_init_infrastructure", new_callable=AsyncMock):
            with patch("aventure_tracker.main.FlightTrackerService") as mock_flight_cls:
                mock_flight = AsyncMock()
                mock_flight.track_flights = AsyncMock(
                    side_effect=Exception("Scraper error")
                )
                mock_flight_cls.return_value = mock_flight

                result = await orchestrator.run()

        assert len(result.errors) > 0
        assert "Scraper error" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_calculates_duration(self, mock_settings: Settings) -> None:
        orchestrator = AdventureOrchestrator(
            settings=mock_settings,
            mode=RunMode.FLIGHTS,
        )
        with patch.object(orchestrator, "_init_infrastructure", new_callable=AsyncMock):
            with patch("aventure_tracker.main.FlightTrackerService") as mock_flight_cls:
                mock_flight = AsyncMock()
                mock_flight.track_flights = AsyncMock(
                    return_value=FlightTrackerResult(
                        routes_checked=0,
                        dates_checked=0,
                        flights_found=0,
                        alerts_generated=0,
                        notifications_sent=0,
                        prices_found=[],
                        price_alerts=[],
                        errors=[],
                    )
                )
                mock_flight_cls.return_value = mock_flight
                result = await orchestrator.run()

        assert result.duration_seconds >= 0


class TestCLIParser:
    """Tests for CLI argument parser."""

    def test_create_parser(self) -> None:
        parser = create_parser()
        assert parser.prog == "aventure-tracker"

    def test_default_arguments(self) -> None:
        parser = create_parser()
        args = parser.parse_args([])
        assert args.mode == "all"
        assert args.weeks == 10
        assert args.max_posts == 10
        assert args.config_dir == "config"
        assert args.verbose is False
        assert args.dry_run is False
        assert args.calendar is False

    def test_mode_argument(self) -> None:
        parser = create_parser()
        assert parser.parse_args(["--mode", "flights"]).mode == "flights"
        assert parser.parse_args(["-m", "activities"]).mode == "activities"
        assert parser.parse_args(["-m", "calendar"]).mode == "calendar"

    def test_calendar_argument(self) -> None:
        assert create_parser().parse_args(["--calendar"]).calendar is True

    def test_weeks_argument(self) -> None:
        parser = create_parser()
        assert parser.parse_args(["--weeks", "4"]).weeks == 4
        assert parser.parse_args(["-w", "12"]).weeks == 12

    def test_max_posts_argument(self) -> None:
        parser = create_parser()
        assert parser.parse_args(["--max-posts", "5"]).max_posts == 5
        assert parser.parse_args(["-p", "20"]).max_posts == 20

    def test_config_dir_argument(self) -> None:
        parser = create_parser()
        assert parser.parse_args(["--config-dir", "/custom"]).config_dir == "/custom"
        assert parser.parse_args(["-c", "my-config"]).config_dir == "my-config"

    def test_verbose_flag(self) -> None:
        parser = create_parser()
        assert parser.parse_args(["--verbose"]).verbose is True
        assert parser.parse_args(["-v"]).verbose is True

    def test_dry_run_flag(self) -> None:
        parser = create_parser()
        assert parser.parse_args(["--dry-run"]).dry_run is True
        assert parser.parse_args(["-n"]).dry_run is True

    def test_combined_arguments(self) -> None:
        args = create_parser().parse_args(
            ["--mode", "flights", "--weeks", "4", "--verbose", "--dry-run"]
        )
        assert args.mode == "flights"
        assert args.weeks == 4
        assert args.verbose is True
        assert args.dry_run is True

    def test_invalid_mode_rejected(self) -> None:
        with pytest.raises(SystemExit):
            create_parser().parse_args(["--mode", "invalid"])


class TestAsyncMain:
    """Tests for async_main function."""

    @pytest.mark.asyncio
    async def test_async_main_success(self, tmp_path: Path) -> None:
        args = argparse.Namespace(
            mode="flights",
            weeks=2,
            max_posts=5,
            config_dir=str(tmp_path),
            verbose=False,
            dry_run=True,
            calendar=False,
        )
        with patch("aventure_tracker.main.AdventureOrchestrator") as mock_cls:
            mock_orch = AsyncMock()
            mock_orch.run = AsyncMock(
                return_value=OrchestratorResult(
                    mode=RunMode.FLIGHTS,
                    flights_result=None,
                    activities_result=None,
                    total_alerts=0,
                    total_notifications=0,
                    errors=[],
                    duration_seconds=1.0,
                )
            )
            mock_cls.return_value = mock_orch
            exit_code = await async_main(args)
        assert exit_code == 0

    @pytest.mark.asyncio
    async def test_async_main_with_errors(self, tmp_path: Path) -> None:
        args = argparse.Namespace(
            mode="flights",
            weeks=2,
            max_posts=5,
            config_dir=str(tmp_path),
            verbose=False,
            calendar=False,
            dry_run=True,
        )
        with patch("aventure_tracker.main.AdventureOrchestrator") as mock_cls:
            mock_orch = AsyncMock()
            mock_orch.run = AsyncMock(
                return_value=OrchestratorResult(
                    mode=RunMode.FLIGHTS,
                    flights_result=None,
                    activities_result=None,
                    total_alerts=0,
                    total_notifications=0,
                    errors=["Something failed"],
                    duration_seconds=1.0,
                )
            )
            mock_cls.return_value = mock_orch
            exit_code = await async_main(args)
        assert exit_code == 1


class TestInitInfrastructure:
    """Tests for infrastructure initialization."""

    @pytest.mark.asyncio
    async def test_init_with_credentials_in_ci(self, mock_settings: Settings) -> None:
        """Test that StateManager is created when is_ci=True and gist credentials present."""
        with patch("aventure_tracker.main.StateManager") as mock_state_cls:
            mock_state = MagicMock()
            mock_state.read = MagicMock(return_value=None)
            mock_state_cls.return_value = mock_state

            with patch.dict(
                os.environ,
                {
                    "GITHUB_ACTIONS": "true",
                    "GITHUB_GIST_ID": "valid_gist",
                    "GITHUB_GIST_TOKEN": "valid_token",
                },
                clear=False,
            ):
                mock_settings_ci = Settings(config_dir=mock_settings.config_dir)
                orchestrator = AdventureOrchestrator(settings=mock_settings_ci)
                await orchestrator._init_infrastructure()

        assert orchestrator._state_manager is not None
        mock_state.read.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_without_credentials(self, tmp_path: Path) -> None:
        settings = Settings(
            config_dir=tmp_path,
            gist_id="",
            gist_token="",
            resend_api_key="",
            email_to="",
        )
        orchestrator = AdventureOrchestrator(settings=settings)
        await orchestrator._init_infrastructure()
        assert orchestrator._state_manager is None
        assert orchestrator._email_notifier is None
