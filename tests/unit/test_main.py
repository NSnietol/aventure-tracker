"""Tests for Main Orchestrator and CLI."""

import argparse
from datetime import datetime
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
from aventure_tracker.services.activity_tracker import ActivityTrackerResult
from aventure_tracker.services.flight_tracker import FlightTrackerResult


@pytest.fixture
def mock_settings(tmp_path: Path) -> Settings:
    """Create mock settings with temp config directory."""
    # Create config files
    (tmp_path / "routes.yaml").write_text("routes: []")
    (tmp_path / "accounts.yaml").write_text("accounts: []")
    (tmp_path / "holidays.yaml").write_text("holidays: {}")
    (tmp_path / "wishlist.yaml").write_text("destinations: []")
    (tmp_path / "done.yaml").write_text("activities: []")

    # Note: Using aliases properly - Settings expects env vars GITHUB_GIST_ID
    # For direct construction, we use the model field names
    settings = Settings(
        config_dir=tmp_path,
        telegram_bot_token="test_token",
        telegram_chat_id="123456",
        log_level="ERROR",
    )
    # Override gist settings directly (avoiding alias issues)
    object.__setattr__(settings, "gist_id", "test_gist_id")
    object.__setattr__(settings, "gist_token", "test_gist_token")

    return settings


@pytest.fixture
def mock_flight_result() -> FlightTrackerResult:
    """Create a mock flight tracker result."""
    return FlightTrackerResult(
        routes_checked=2,
        dates_checked=16,
        alerts_generated=3,
        notifications_sent=3,
        errors=[],
    )


@pytest.fixture
def mock_activity_result() -> ActivityTrackerResult:
    """Create a mock activity tracker result."""
    return ActivityTrackerResult(
        accounts_checked=5,
        posts_found=50,
        posts_processed=45,
        alerts_generated=2,
        notifications_sent=2,
        errors=[],
    )


class TestRunMode:
    """Tests for RunMode enum."""

    def test_all_mode(self) -> None:
        """Test ALL mode value."""
        assert RunMode.ALL.value == "all"

    def test_flights_mode(self) -> None:
        """Test FLIGHTS mode value."""
        assert RunMode.FLIGHTS.value == "flights"

    def test_activities_mode(self) -> None:
        """Test ACTIVITIES mode value."""
        assert RunMode.ACTIVITIES.value == "activities"

    def test_parse_from_string(self) -> None:
        """Test parsing mode from string."""
        assert RunMode("all") == RunMode.ALL
        assert RunMode("flights") == RunMode.FLIGHTS
        assert RunMode("activities") == RunMode.ACTIVITIES


class TestOrchestratorResult:
    """Tests for OrchestratorResult dataclass."""

    def test_create_result(
        self,
        mock_flight_result: FlightTrackerResult,
        mock_activity_result: ActivityTrackerResult,
    ) -> None:
        """Test creating an orchestrator result."""
        result = OrchestratorResult(
            mode=RunMode.ALL,
            flights_result=mock_flight_result,
            activities_result=mock_activity_result,
            total_alerts=5,
            total_notifications=5,
            errors=[],
            duration_seconds=15.5,
        )

        assert result.mode == RunMode.ALL
        assert result.total_alerts == 5
        assert result.duration_seconds == 15.5

    def test_success_with_no_errors(self) -> None:
        """Test success property with no errors."""
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
        """Test success property with errors."""
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
        """Test initialization with default values."""
        orchestrator = AdventureOrchestrator()

        assert orchestrator._mode == RunMode.ALL
        assert orchestrator._weeks_ahead == 8
        assert orchestrator._max_posts == 10

    def test_init_with_custom_values(self, mock_settings: Settings) -> None:
        """Test initialization with custom values."""
        orchestrator = AdventureOrchestrator(
            settings=mock_settings,
            mode=RunMode.FLIGHTS,
            weeks_ahead=4,
            max_posts_per_account=5,
        )

        assert orchestrator._mode == RunMode.FLIGHTS
        assert orchestrator._weeks_ahead == 4
        assert orchestrator._max_posts == 5


class TestOrchestratorRun:
    """Tests for orchestrator run method."""

    @pytest.mark.asyncio
    async def test_run_all_mode(
        self,
        mock_settings: Settings,
        mock_flight_result: FlightTrackerResult,
        mock_activity_result: ActivityTrackerResult,
    ) -> None:
        """Test running in ALL mode."""
        orchestrator = AdventureOrchestrator(
            settings=mock_settings,
            mode=RunMode.ALL,
        )

        with patch.object(
            orchestrator, "_init_infrastructure", new_callable=AsyncMock
        ) as mock_init:
            with patch(
                "aventure_tracker.main.FlightTrackerService"
            ) as mock_flight_cls:
                with patch(
                    "aventure_tracker.main.ActivityTrackerService"
                ) as mock_activity_cls:
                    mock_flight = AsyncMock()
                    mock_flight.track_flights = AsyncMock(
                        return_value=mock_flight_result
                    )
                    mock_flight_cls.return_value = mock_flight

                    mock_activity = AsyncMock()
                    mock_activity.track_activities = AsyncMock(
                        return_value=mock_activity_result
                    )
                    mock_activity_cls.return_value = mock_activity

                    result = await orchestrator.run()

        assert result.mode == RunMode.ALL
        assert result.flights_result is not None
        assert result.activities_result is not None
        assert result.total_alerts == 5  # 3 + 2

    @pytest.mark.asyncio
    async def test_run_flights_only(
        self,
        mock_settings: Settings,
        mock_flight_result: FlightTrackerResult,
    ) -> None:
        """Test running in FLIGHTS mode only."""
        orchestrator = AdventureOrchestrator(
            settings=mock_settings,
            mode=RunMode.FLIGHTS,
        )

        with patch.object(
            orchestrator, "_init_infrastructure", new_callable=AsyncMock
        ):
            with patch(
                "aventure_tracker.main.FlightTrackerService"
            ) as mock_flight_cls:
                mock_flight = AsyncMock()
                mock_flight.track_flights = AsyncMock(return_value=mock_flight_result)
                mock_flight_cls.return_value = mock_flight

                result = await orchestrator.run()

        assert result.mode == RunMode.FLIGHTS
        assert result.flights_result is not None
        assert result.activities_result is None
        assert result.total_alerts == 3

    @pytest.mark.asyncio
    async def test_run_activities_only(
        self,
        mock_settings: Settings,
        mock_activity_result: ActivityTrackerResult,
    ) -> None:
        """Test running in ACTIVITIES mode only."""
        orchestrator = AdventureOrchestrator(
            settings=mock_settings,
            mode=RunMode.ACTIVITIES,
        )

        with patch.object(
            orchestrator, "_init_infrastructure", new_callable=AsyncMock
        ):
            with patch(
                "aventure_tracker.main.ActivityTrackerService"
            ) as mock_activity_cls:
                mock_activity = AsyncMock()
                mock_activity.track_activities = AsyncMock(
                    return_value=mock_activity_result
                )
                mock_activity_cls.return_value = mock_activity

                result = await orchestrator.run()

        assert result.mode == RunMode.ACTIVITIES
        assert result.flights_result is None
        assert result.activities_result is not None
        assert result.total_alerts == 2

    @pytest.mark.asyncio
    async def test_run_handles_flight_tracker_error(
        self,
        mock_settings: Settings,
    ) -> None:
        """Test run handles flight tracker errors gracefully."""
        orchestrator = AdventureOrchestrator(
            settings=mock_settings,
            mode=RunMode.FLIGHTS,
        )

        with patch.object(
            orchestrator, "_init_infrastructure", new_callable=AsyncMock
        ):
            with patch(
                "aventure_tracker.main.FlightTrackerService"
            ) as mock_flight_cls:
                mock_flight = AsyncMock()
                mock_flight.track_flights = AsyncMock(
                    side_effect=Exception("Scraper error")
                )
                mock_flight_cls.return_value = mock_flight

                result = await orchestrator.run()

        assert len(result.errors) > 0
        assert "Scraper error" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_calculates_duration(
        self,
        mock_settings: Settings,
    ) -> None:
        """Test run calculates duration."""
        orchestrator = AdventureOrchestrator(
            settings=mock_settings,
            mode=RunMode.FLIGHTS,
        )

        with patch.object(
            orchestrator, "_init_infrastructure", new_callable=AsyncMock
        ):
            with patch(
                "aventure_tracker.main.FlightTrackerService"
            ) as mock_flight_cls:
                mock_flight = AsyncMock()
                mock_flight.track_flights = AsyncMock(
                    return_value=FlightTrackerResult(
                        routes_checked=0,
                        dates_checked=0,
                        alerts_generated=0,
                        notifications_sent=0,
                        errors=[],
                    )
                )
                mock_flight_cls.return_value = mock_flight

                result = await orchestrator.run()

        assert result.duration_seconds >= 0


class TestCLIParser:
    """Tests for CLI argument parser."""

    def test_create_parser(self) -> None:
        """Test parser creation."""
        parser = create_parser()

        assert parser.prog == "aventure-tracker"

    def test_default_arguments(self) -> None:
        """Test default argument values."""
        parser = create_parser()
        args = parser.parse_args([])

        assert args.mode == "all"
        assert args.weeks == 8
        assert args.max_posts == 10
        assert args.config_dir == "config"
        assert args.verbose is False
        assert args.dry_run is False

    def test_mode_argument(self) -> None:
        """Test mode argument parsing."""
        parser = create_parser()

        args = parser.parse_args(["--mode", "flights"])
        assert args.mode == "flights"

        args = parser.parse_args(["-m", "activities"])
        assert args.mode == "activities"

    def test_weeks_argument(self) -> None:
        """Test weeks argument parsing."""
        parser = create_parser()

        args = parser.parse_args(["--weeks", "4"])
        assert args.weeks == 4

        args = parser.parse_args(["-w", "12"])
        assert args.weeks == 12

    def test_max_posts_argument(self) -> None:
        """Test max-posts argument parsing."""
        parser = create_parser()

        args = parser.parse_args(["--max-posts", "5"])
        assert args.max_posts == 5

        args = parser.parse_args(["-p", "20"])
        assert args.max_posts == 20

    def test_config_dir_argument(self) -> None:
        """Test config-dir argument parsing."""
        parser = create_parser()

        args = parser.parse_args(["--config-dir", "/custom/config"])
        assert args.config_dir == "/custom/config"

        args = parser.parse_args(["-c", "my-config"])
        assert args.config_dir == "my-config"

    def test_verbose_flag(self) -> None:
        """Test verbose flag parsing."""
        parser = create_parser()

        args = parser.parse_args(["--verbose"])
        assert args.verbose is True

        args = parser.parse_args(["-v"])
        assert args.verbose is True

    def test_dry_run_flag(self) -> None:
        """Test dry-run flag parsing."""
        parser = create_parser()

        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

        args = parser.parse_args(["-n"])
        assert args.dry_run is True

    def test_combined_arguments(self) -> None:
        """Test combining multiple arguments."""
        parser = create_parser()

        args = parser.parse_args(
            ["--mode", "flights", "--weeks", "4", "--verbose", "--dry-run"]
        )

        assert args.mode == "flights"
        assert args.weeks == 4
        assert args.verbose is True
        assert args.dry_run is True

    def test_invalid_mode_rejected(self) -> None:
        """Test invalid mode is rejected."""
        parser = create_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["--mode", "invalid"])


class TestAsyncMain:
    """Tests for async_main function."""

    @pytest.mark.asyncio
    async def test_async_main_success(self, tmp_path: Path) -> None:
        """Test async_main returns 0 on success."""
        # Create config files
        (tmp_path / "routes.yaml").write_text("routes: []")
        (tmp_path / "accounts.yaml").write_text("accounts: []")
        (tmp_path / "holidays.yaml").write_text("holidays: {}")
        (tmp_path / "wishlist.yaml").write_text("destinations: []")
        (tmp_path / "done.yaml").write_text("activities: []")

        args = argparse.Namespace(
            mode="flights",
            weeks=2,
            max_posts=5,
            config_dir=str(tmp_path),
            verbose=False,
            dry_run=True,  # Don't send notifications
        )

        with patch(
            "aventure_tracker.main.AdventureOrchestrator"
        ) as mock_orchestrator_cls:
            mock_orchestrator = AsyncMock()
            mock_orchestrator.run = AsyncMock(
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
            mock_orchestrator_cls.return_value = mock_orchestrator

            exit_code = await async_main(args)

        assert exit_code == 0

    @pytest.mark.asyncio
    async def test_async_main_with_errors(self, tmp_path: Path) -> None:
        """Test async_main returns 1 with errors."""
        args = argparse.Namespace(
            mode="flights",
            weeks=2,
            max_posts=5,
            config_dir=str(tmp_path),
            verbose=False,
            dry_run=True,
        )

        with patch(
            "aventure_tracker.main.AdventureOrchestrator"
        ) as mock_orchestrator_cls:
            mock_orchestrator = AsyncMock()
            mock_orchestrator.run = AsyncMock(
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
            mock_orchestrator_cls.return_value = mock_orchestrator

            exit_code = await async_main(args)

        assert exit_code == 1


class TestInitInfrastructure:
    """Tests for infrastructure initialization."""

    @pytest.mark.asyncio
    async def test_init_with_credentials(self, mock_settings: Settings) -> None:
        """Test initialization with valid credentials."""
        orchestrator = AdventureOrchestrator(settings=mock_settings)

        with patch(
            "aventure_tracker.main.StateManager"
        ) as mock_state_cls:
            with patch(
                "aventure_tracker.main.TelegramNotifier"
            ) as mock_notifier_cls:
                mock_state = MagicMock()
                mock_state.read = MagicMock()
                mock_state_cls.return_value = mock_state

                mock_notifier_cls.return_value = MagicMock()

                await orchestrator._init_infrastructure()

        # Check infrastructure was created
        assert orchestrator._state_manager is not None
        assert orchestrator._notifier is not None
        mock_state.read.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_without_credentials(self, tmp_path: Path) -> None:
        """Test initialization without credentials."""
        settings = Settings(
            config_dir=tmp_path,
            telegram_bot_token="",
            telegram_chat_id="",
            gist_id="",
            gist_token="",
        )

        orchestrator = AdventureOrchestrator(settings=settings)
        await orchestrator._init_infrastructure()

        assert orchestrator._state_manager is None
        assert orchestrator._notifier is None
