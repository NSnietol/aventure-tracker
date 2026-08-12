"""Tests for extraction pipeline orchestrator."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aventure_tracker.models.extracted_event import ExtractedEvent, ExtractionResult
from aventure_tracker.services.extraction_pipeline import (
    ExtractionPipeline,
    PipelineConfig,
    PipelineResult,
    PipelineStats,
    run_extraction_cli,
)
from aventure_tracker.services.price_history import PriceChange


@pytest.fixture
def tmp_dirs(tmp_path: Path) -> dict[str, Path]:
    """Create temporary directory structure."""
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    db_path = tmp_path / "events.db"

    source_dir.mkdir()
    target_dir.mkdir()

    return {
        "source": source_dir,
        "target": target_dir,
        "db": db_path,
    }


@pytest.fixture
def config(tmp_dirs: dict[str, Path]) -> PipelineConfig:
    """Create pipeline config."""
    return PipelineConfig(
        source_dir=tmp_dirs["source"],
        target_dir=tmp_dirs["target"],
        db_path=tmp_dirs["db"],
        year=2026,
        default_month="agosto",
        api_key="test-key",
    )


@pytest.fixture
def sample_extraction_result(tmp_path: Path) -> ExtractionResult:
    """Create a sample extraction result."""
    events = [
        ExtractedEvent(
            name="Cavernas del Nus",
            date_start=date(2026, 8, 1),
            date_end=date(2026, 8, 1),
            price=195000,
            agency="brutaltravel",
        ),
        ExtractedEvent(
            name="Tatacoa",
            date_start=date(2026, 8, 21),
            date_end=date(2026, 8, 23),
            price=490000,
            agency="brutaltravel",
        ),
    ]
    events[0].set_confidence("name", 0.95)
    events[0].set_confidence("price", 0.9)
    events[1].set_confidence("name", 0.5)  # Low confidence

    return ExtractionResult(
        source_image=tmp_path / "calendar.jpg",
        agency="brutaltravel",
        month="agosto",
        year=2026,
        events=events,
        processing_time_ms=100,
        success=True,
    )


class TestPipelineStats:
    """Tests for PipelineStats."""

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        stats = PipelineStats(
            images_processed=5,
            events_extracted=15,
            events_needing_review=2,
        )
        d = stats.to_dict()

        assert d["images_processed"] == 5
        assert d["events_extracted"] == 15
        assert d["events_needing_review"] == 2

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        stats = PipelineStats()
        assert stats.images_processed == 0
        assert stats.errors == []
        assert stats.price_changes == []


class TestPipelineResult:
    """Tests for PipelineResult."""

    def test_duration_seconds(self, tmp_path: Path) -> None:
        """Should calculate duration."""
        from datetime import datetime, timedelta

        start = datetime.now()
        end = start + timedelta(seconds=5)

        result = PipelineResult(
            success=True,
            stats=PipelineStats(),
            extraction_results=[],
            started_at=start,
            completed_at=end,
        )

        assert result.duration_seconds == 5.0

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        from datetime import datetime

        result = PipelineResult(
            success=True,
            stats=PipelineStats(images_processed=3),
            extraction_results=[],
            started_at=datetime(2026, 8, 1, 10, 0, 0),
            completed_at=datetime(2026, 8, 1, 10, 1, 0),
        )
        d = result.to_dict()

        assert d["success"] is True
        assert d["duration_seconds"] == 60.0
        assert "stats" in d


class TestExtractionPipeline:
    """Tests for ExtractionPipeline."""

    def test_init_creates_components(self, config: PipelineConfig) -> None:
        """Should initialize all components."""
        with patch("aventure_tracker.services.extraction_pipeline.ImageEventExtractor"):
            pipeline = ExtractionPipeline(config)

            assert pipeline.organizer is not None
            assert pipeline.extractor is not None
            assert pipeline.yaml_store is not None
            assert pipeline.price_db is not None

    def test_discover_agencies(
        self, config: PipelineConfig, tmp_dirs: dict[str, Path]
    ) -> None:
        """Should discover agency directories."""
        # Create agency directories
        (tmp_dirs["target"] / "brutaltravel").mkdir()
        (tmp_dirs["target"] / "medellinbungee").mkdir()
        (tmp_dirs["target"] / ".hidden").mkdir()

        with patch("aventure_tracker.services.extraction_pipeline.ImageEventExtractor"):
            pipeline = ExtractionPipeline(config)
            agencies = pipeline._discover_agencies()

        assert "brutaltravel" in agencies
        assert "medellinbungee" in agencies
        assert ".hidden" not in agencies

    def test_discover_agencies_empty(self, config: PipelineConfig) -> None:
        """Should return empty list for empty directory."""
        with patch("aventure_tracker.services.extraction_pipeline.ImageEventExtractor"):
            pipeline = ExtractionPipeline(config)
            agencies = pipeline._discover_agencies()

        assert agencies == []

    @patch("aventure_tracker.services.extraction_pipeline.ImageEventExtractor")
    def test_run_processes_all_agencies(
        self,
        mock_extractor_cls: MagicMock,
        config: PipelineConfig,
        tmp_dirs: dict[str, Path],
        sample_extraction_result: ExtractionResult,
    ) -> None:
        """Should process all discovered agencies."""
        # Setup directories
        brutal_dir = tmp_dirs["target"] / "brutaltravel" / "2026" / "agosto"
        brutal_dir.mkdir(parents=True)
        (brutal_dir / "cal1.jpg").write_bytes(b"\xff\xd8\xff")

        # Setup mock
        mock_extractor = MagicMock()
        mock_extractor.extract_from_directory.return_value = [sample_extraction_result]
        mock_extractor_cls.return_value = mock_extractor

        pipeline = ExtractionPipeline(config)
        result = pipeline.run(month="agosto")

        assert result.success is True
        assert result.stats.images_processed == 1
        assert result.stats.events_extracted == 2

    @patch("aventure_tracker.services.extraction_pipeline.ImageEventExtractor")
    def test_run_saves_to_yaml(
        self,
        mock_extractor_cls: MagicMock,
        config: PipelineConfig,
        tmp_dirs: dict[str, Path],
        sample_extraction_result: ExtractionResult,
    ) -> None:
        """Should save events to YAML."""
        # Setup
        brutal_dir = tmp_dirs["target"] / "brutaltravel" / "2026" / "agosto"
        brutal_dir.mkdir(parents=True)
        (brutal_dir / "cal1.jpg").write_bytes(b"\xff\xd8\xff")

        mock_extractor = MagicMock()
        mock_extractor.extract_from_directory.return_value = [sample_extraction_result]
        mock_extractor_cls.return_value = mock_extractor

        pipeline = ExtractionPipeline(config)
        pipeline.run(month="agosto")

        # Check YAML was created
        yaml_file = brutal_dir / "events.yaml"
        assert yaml_file.exists()

    @patch("aventure_tracker.services.extraction_pipeline.ImageEventExtractor")
    def test_run_saves_to_database(
        self,
        mock_extractor_cls: MagicMock,
        config: PipelineConfig,
        tmp_dirs: dict[str, Path],
        sample_extraction_result: ExtractionResult,
    ) -> None:
        """Should save events to SQLite database."""
        # Setup
        brutal_dir = tmp_dirs["target"] / "brutaltravel" / "2026" / "agosto"
        brutal_dir.mkdir(parents=True)
        (brutal_dir / "cal1.jpg").write_bytes(b"\xff\xd8\xff")

        mock_extractor = MagicMock()
        mock_extractor.extract_from_directory.return_value = [sample_extraction_result]
        mock_extractor_cls.return_value = mock_extractor

        pipeline = ExtractionPipeline(config)
        pipeline.run(month="agosto")

        # Check database was created and has events
        assert tmp_dirs["db"].exists()
        stats = pipeline.price_db.get_statistics()
        assert stats["total_events"] == 2

    @patch("aventure_tracker.services.extraction_pipeline.ImageEventExtractor")
    def test_run_tracks_price_changes(
        self,
        mock_extractor_cls: MagicMock,
        config: PipelineConfig,
        tmp_dirs: dict[str, Path],
    ) -> None:
        """Should track price changes between runs."""
        # Setup
        brutal_dir = tmp_dirs["target"] / "brutaltravel" / "2026" / "agosto"
        brutal_dir.mkdir(parents=True)
        (brutal_dir / "cal1.jpg").write_bytes(b"\xff\xd8\xff")

        mock_extractor = MagicMock()
        mock_extractor_cls.return_value = mock_extractor

        # First run
        events1 = [
            ExtractedEvent(
                name="Test Event",
                date_start=date(2026, 8, 1),
                date_end=date(2026, 8, 1),
                price=100000,
                agency="brutaltravel",
            )
        ]
        result1 = ExtractionResult(
            source_image=brutal_dir / "cal1.jpg",
            agency="brutaltravel",
            month="agosto",
            year=2026,
            events=events1,
            success=True,
        )
        mock_extractor.extract_from_directory.return_value = [result1]

        pipeline = ExtractionPipeline(config)
        pipeline.run(month="agosto")

        # Second run with price change
        events2 = [
            ExtractedEvent(
                name="Test Event",
                date_start=date(2026, 8, 1),
                date_end=date(2026, 8, 1),
                price=120000,  # Price increased
                agency="brutaltravel",
            )
        ]
        result2 = ExtractionResult(
            source_image=brutal_dir / "cal1.jpg",
            agency="brutaltravel",
            month="agosto",
            year=2026,
            events=events2,
            success=True,
        )
        mock_extractor.extract_from_directory.return_value = [result2]

        result = pipeline.run(month="agosto")

        assert len(result.stats.price_changes) == 1
        assert result.stats.price_changes[0].old_price == 100000
        assert result.stats.price_changes[0].new_price == 120000

    @patch("aventure_tracker.services.extraction_pipeline.ImageEventExtractor")
    def test_run_counts_sold_out(
        self,
        mock_extractor_cls: MagicMock,
        config: PipelineConfig,
        tmp_dirs: dict[str, Path],
    ) -> None:
        """Should count sold out events."""
        # Setup
        brutal_dir = tmp_dirs["target"] / "brutaltravel" / "2026" / "agosto"
        brutal_dir.mkdir(parents=True)
        (brutal_dir / "cal1.jpg").write_bytes(b"\xff\xd8\xff")

        events = [
            ExtractedEvent(
                name="Available",
                date_start=date(2026, 8, 1),
                date_end=date(2026, 8, 1),
                price=100000,
                agency="brutaltravel",
            ),
            ExtractedEvent(
                name="Sold Out",
                date_start=date(2026, 8, 2),
                date_end=date(2026, 8, 2),
                price=200000,
                agency="brutaltravel",
                sold_out=True,
            ),
        ]
        result = ExtractionResult(
            source_image=brutal_dir / "cal1.jpg",
            agency="brutaltravel",
            month="agosto",
            year=2026,
            events=events,
            success=True,
        )

        mock_extractor = MagicMock()
        mock_extractor.extract_from_directory.return_value = [result]
        mock_extractor_cls.return_value = mock_extractor

        pipeline = ExtractionPipeline(config)
        result = pipeline.run(month="agosto")

        assert result.stats.events_sold_out == 1

    @patch("aventure_tracker.services.extraction_pipeline.ImageEventExtractor")
    def test_run_counts_needs_review(
        self,
        mock_extractor_cls: MagicMock,
        config: PipelineConfig,
        tmp_dirs: dict[str, Path],
        sample_extraction_result: ExtractionResult,
    ) -> None:
        """Should count events needing review."""
        # Setup
        brutal_dir = tmp_dirs["target"] / "brutaltravel" / "2026" / "agosto"
        brutal_dir.mkdir(parents=True)
        (brutal_dir / "cal1.jpg").write_bytes(b"\xff\xd8\xff")

        mock_extractor = MagicMock()
        mock_extractor.extract_from_directory.return_value = [sample_extraction_result]
        mock_extractor_cls.return_value = mock_extractor

        pipeline = ExtractionPipeline(config)
        result = pipeline.run(month="agosto")

        # sample_extraction_result has 1 event with low confidence
        assert result.stats.events_needing_review == 1

    @patch("aventure_tracker.services.extraction_pipeline.ImageEventExtractor")
    def test_run_handles_extraction_errors(
        self,
        mock_extractor_cls: MagicMock,
        config: PipelineConfig,
        tmp_dirs: dict[str, Path],
    ) -> None:
        """Should handle and record extraction errors."""
        # Setup
        brutal_dir = tmp_dirs["target"] / "brutaltravel" / "2026" / "agosto"
        brutal_dir.mkdir(parents=True)
        (brutal_dir / "cal1.jpg").write_bytes(b"\xff\xd8\xff")

        failed_result = ExtractionResult(
            source_image=brutal_dir / "cal1.jpg",
            agency="brutaltravel",
            month="agosto",
            year=2026,
            events=[],
            success=False,
            error="API rate limited",
        )

        mock_extractor = MagicMock()
        mock_extractor.extract_from_directory.return_value = [failed_result]
        mock_extractor_cls.return_value = mock_extractor

        pipeline = ExtractionPipeline(config)
        result = pipeline.run(month="agosto")

        assert result.stats.images_failed == 1
        assert any("API rate limited" in e for e in result.stats.errors)

    @patch("aventure_tracker.services.extraction_pipeline.ImageEventExtractor")
    def test_run_single_agency(
        self,
        mock_extractor_cls: MagicMock,
        config: PipelineConfig,
        tmp_dirs: dict[str, Path],
        sample_extraction_result: ExtractionResult,
    ) -> None:
        """Should process only specified agency."""
        # Setup multiple agencies
        brutal_dir = tmp_dirs["target"] / "brutaltravel" / "2026" / "agosto"
        brutal_dir.mkdir(parents=True)
        (brutal_dir / "cal1.jpg").write_bytes(b"\xff\xd8\xff")

        medellin_dir = tmp_dirs["target"] / "medellinbungee" / "2026" / "agosto"
        medellin_dir.mkdir(parents=True)
        (medellin_dir / "cal1.jpg").write_bytes(b"\xff\xd8\xff")

        mock_extractor = MagicMock()
        mock_extractor.extract_from_directory.return_value = [sample_extraction_result]
        mock_extractor_cls.return_value = mock_extractor

        pipeline = ExtractionPipeline(config)
        result = pipeline.run_single_agency("brutaltravel", month="agosto")

        # Should only call extract for brutaltravel
        mock_extractor.extract_from_directory.assert_called_once()
        call_args = mock_extractor.extract_from_directory.call_args
        assert "brutaltravel" in str(call_args)

    @patch("aventure_tracker.services.extraction_pipeline.ImageEventExtractor")
    def test_get_extraction_summary(
        self,
        mock_extractor_cls: MagicMock,
        config: PipelineConfig,
        tmp_dirs: dict[str, Path],
        sample_extraction_result: ExtractionResult,
    ) -> None:
        """Should generate readable summary."""
        brutal_dir = tmp_dirs["target"] / "brutaltravel" / "2026" / "agosto"
        brutal_dir.mkdir(parents=True)
        (brutal_dir / "cal1.jpg").write_bytes(b"\xff\xd8\xff")

        mock_extractor = MagicMock()
        mock_extractor.extract_from_directory.return_value = [sample_extraction_result]
        mock_extractor_cls.return_value = mock_extractor

        pipeline = ExtractionPipeline(config)
        result = pipeline.run(month="agosto")
        summary = pipeline.get_extraction_summary(result)

        assert "EXTRACTION PIPELINE SUMMARY" in summary
        assert "SUCCESS" in summary
        assert "Images processed" in summary
        assert "Events extracted" in summary

    @patch("aventure_tracker.services.extraction_pipeline.ImageEventExtractor")
    def test_skip_yaml_when_disabled(
        self,
        mock_extractor_cls: MagicMock,
        config: PipelineConfig,
        tmp_dirs: dict[str, Path],
        sample_extraction_result: ExtractionResult,
    ) -> None:
        """Should skip YAML save when disabled."""
        config.save_yaml = False

        brutal_dir = tmp_dirs["target"] / "brutaltravel" / "2026" / "agosto"
        brutal_dir.mkdir(parents=True)
        (brutal_dir / "cal1.jpg").write_bytes(b"\xff\xd8\xff")

        mock_extractor = MagicMock()
        mock_extractor.extract_from_directory.return_value = [sample_extraction_result]
        mock_extractor_cls.return_value = mock_extractor

        pipeline = ExtractionPipeline(config)
        pipeline.run(month="agosto")

        yaml_file = brutal_dir / "events.yaml"
        assert not yaml_file.exists()

    @patch("aventure_tracker.services.extraction_pipeline.ImageEventExtractor")
    def test_skip_db_when_disabled(
        self,
        mock_extractor_cls: MagicMock,
        config: PipelineConfig,
        tmp_dirs: dict[str, Path],
        sample_extraction_result: ExtractionResult,
    ) -> None:
        """Should skip DB save when disabled."""
        config.save_db = False

        brutal_dir = tmp_dirs["target"] / "brutaltravel" / "2026" / "agosto"
        brutal_dir.mkdir(parents=True)
        (brutal_dir / "cal1.jpg").write_bytes(b"\xff\xd8\xff")

        mock_extractor = MagicMock()
        mock_extractor.extract_from_directory.return_value = [sample_extraction_result]
        mock_extractor_cls.return_value = mock_extractor

        pipeline = ExtractionPipeline(config)
        pipeline.run(month="agosto")

        # DB should exist (created on init) but have no events
        stats = pipeline.price_db.get_statistics()
        assert stats["total_events"] == 0


class TestRunExtractionCLI:
    """Tests for CLI entry point."""

    @patch("aventure_tracker.services.extraction_pipeline.ExtractionPipeline")
    @patch("builtins.print")
    def test_run_extraction_cli(
        self,
        mock_print: MagicMock,
        mock_pipeline_cls: MagicMock,
        tmp_dirs: dict[str, Path],
    ) -> None:
        """Should run pipeline and print summary."""
        from datetime import datetime

        mock_pipeline = MagicMock()
        mock_result = PipelineResult(
            success=True,
            stats=PipelineStats(),
            extraction_results=[],
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        mock_pipeline.run.return_value = mock_result
        mock_pipeline.get_extraction_summary.return_value = "Summary"
        mock_pipeline_cls.return_value = mock_pipeline

        result = run_extraction_cli(
            source_dir=str(tmp_dirs["source"]),
            target_dir=str(tmp_dirs["target"]),
            db_path=str(tmp_dirs["db"]),
        )

        assert result == mock_result
        mock_print.assert_called_with("Summary")

    @patch("aventure_tracker.services.extraction_pipeline.ExtractionPipeline")
    @patch("builtins.print")
    def test_run_extraction_cli_single_agency(
        self,
        mock_print: MagicMock,
        mock_pipeline_cls: MagicMock,
        tmp_dirs: dict[str, Path],
    ) -> None:
        """Should run for single agency when specified."""
        from datetime import datetime

        mock_pipeline = MagicMock()
        mock_result = PipelineResult(
            success=True,
            stats=PipelineStats(),
            extraction_results=[],
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        mock_pipeline.run_single_agency.return_value = mock_result
        mock_pipeline.get_extraction_summary.return_value = "Summary"
        mock_pipeline_cls.return_value = mock_pipeline

        run_extraction_cli(
            source_dir=str(tmp_dirs["source"]),
            agency="brutaltravel",
        )

        mock_pipeline.run_single_agency.assert_called_once_with("brutaltravel", "agosto")
