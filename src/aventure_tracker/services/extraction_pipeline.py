"""Extraction pipeline orchestrator.

Coordinates the full extraction flow:
1. Organize raw images from source directory
2. Extract events from each image using local Tesseract OCR
3. Save events to YAML for human review
4. Record events in SQLite for price history tracking
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from aventure_tracker.models.extracted_event import ExtractedEvent, ExtractionResult
from aventure_tracker.services.file_organizer import FileOrganizer
from aventure_tracker.services.image_event_extractor import (
    ExtractionConfig,
    ImageEventExtractor,
)
from aventure_tracker.services.price_history import PriceChange, PriceHistoryDB
from aventure_tracker.services.yaml_event_store import YAMLEventStore


@dataclass
class PipelineConfig:
    """Configuration for the extraction pipeline."""

    source_dir: Path
    target_dir: Path
    db_path: Path
    year: int = 2026
    default_month: str = "agosto"
    api_key: str | None = None
    organize_files: bool = True
    save_yaml: bool = True
    save_db: bool = True


@dataclass
class PipelineStats:
    """Statistics from a pipeline run."""

    images_processed: int = 0
    images_failed: int = 0
    events_extracted: int = 0
    events_needing_review: int = 0
    events_sold_out: int = 0
    price_changes: list[PriceChange] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    processing_time_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "images_processed": self.images_processed,
            "images_failed": self.images_failed,
            "events_extracted": self.events_extracted,
            "events_needing_review": self.events_needing_review,
            "events_sold_out": self.events_sold_out,
            "price_changes_count": len(self.price_changes),
            "errors_count": len(self.errors),
            "processing_time_ms": self.processing_time_ms,
        }


@dataclass
class PipelineResult:
    """Result of a pipeline run."""

    success: bool
    stats: PipelineStats
    extraction_results: list[ExtractionResult]
    started_at: datetime
    completed_at: datetime

    @property
    def duration_seconds(self) -> float:
        """Get total duration in seconds."""
        return (self.completed_at - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": round(self.duration_seconds, 2),
            "stats": self.stats.to_dict(),
        }


class ExtractionPipeline:
    """Orchestrates the full event extraction pipeline."""

    def __init__(self, config: PipelineConfig):
        """Initialize the pipeline.

        Args:
            config: Pipeline configuration.
        """
        self.config = config

        # Initialize components
        self.organizer = FileOrganizer(
            target_base_dir=config.target_dir,
            year=config.year,
        )

        extraction_config = ExtractionConfig(
            year=config.year,
            default_month=config.default_month,
        )
        self.extractor = ImageEventExtractor(config=extraction_config)

        self.yaml_store = YAMLEventStore(config.target_dir)
        self.price_db = PriceHistoryDB(config.db_path)

    def run(self, month: str | None = None) -> PipelineResult:
        """Run the full extraction pipeline.

        Args:
            month: Month to process (default from config).

        Returns:
            PipelineResult with all extraction results and stats.
        """
        started_at = datetime.now()
        month = month or self.config.default_month
        stats = PipelineStats()
        extraction_results: list[ExtractionResult] = []

        try:
            # Step 1: Organize files if enabled
            if self.config.organize_files:
                org_result = self.organizer.organize_directory(
                    self.config.source_dir, month=month
                )
                if org_result.total_failed > 0:
                    for f in org_result.files:
                        if not f.success:
                            stats.errors.append(f"File organize error: {f.error}")

            # Step 2: Process each agency
            agencies = self._discover_agencies()

            for agency in agencies:
                agency_results = self._process_agency(agency, month, stats)
                extraction_results.extend(agency_results)

            # Calculate totals
            stats.images_processed = sum(1 for r in extraction_results if r.success)
            stats.images_failed = sum(1 for r in extraction_results if not r.success)
            stats.processing_time_ms = sum(r.processing_time_ms for r in extraction_results)

        except Exception as e:
            stats.errors.append(f"Pipeline error: {e}")

        completed_at = datetime.now()

        return PipelineResult(
            success=len(stats.errors) == 0,
            stats=stats,
            extraction_results=extraction_results,
            started_at=started_at,
            completed_at=completed_at,
        )

    def run_single_agency(
        self,
        agency: str,
        month: str | None = None,
    ) -> PipelineResult:
        """Run pipeline for a single agency.

        Args:
            agency: Agency name.
            month: Month to process.

        Returns:
            PipelineResult for the agency.
        """
        started_at = datetime.now()
        month = month or self.config.default_month
        stats = PipelineStats()

        # Organize files for this agency only
        if self.config.organize_files:
            self.organizer.organize_directory(self.config.source_dir, month=month)

        extraction_results = self._process_agency(agency, month, stats)

        stats.images_processed = sum(1 for r in extraction_results if r.success)
        stats.images_failed = sum(1 for r in extraction_results if not r.success)
        stats.processing_time_ms = sum(r.processing_time_ms for r in extraction_results)

        completed_at = datetime.now()

        return PipelineResult(
            success=len(stats.errors) == 0,
            stats=stats,
            extraction_results=extraction_results,
            started_at=started_at,
            completed_at=completed_at,
        )

    def _discover_agencies(self) -> list[str]:
        """Discover agencies from target directory.

        Returns:
            List of agency names.
        """
        agencies: list[str] = []

        if not self.config.target_dir.exists():
            return agencies

        for agency_dir in self.config.target_dir.iterdir():
            if agency_dir.is_dir() and not agency_dir.name.startswith("."):
                agencies.append(agency_dir.name)

        return sorted(agencies)

    def _process_agency(
        self,
        agency: str,
        month: str,
        stats: PipelineStats,
    ) -> list[ExtractionResult]:
        """Process all images for an agency.

        Args:
            agency: Agency name.
            month: Month to process.
            stats: Stats to update.

        Returns:
            List of extraction results.
        """
        results: list[ExtractionResult] = []
        agency_dir = self.config.target_dir / agency / str(self.config.year) / month

        if not agency_dir.exists():
            return results

        # Extract from each image
        image_results = self.extractor.extract_from_directory(
            agency_dir, agency=agency, month=month
        )
        results.extend(image_results)

        # Collect all events
        all_events: list[ExtractedEvent] = []
        for result in image_results:
            if result.success:
                all_events.extend(result.events)
                stats.events_needing_review += result.review_count
            else:
                stats.errors.append(f"{result.source_image.name}: {result.error}")

        # Update stats
        stats.events_extracted += len(all_events)
        stats.events_sold_out += sum(1 for e in all_events if e.sold_out)

        # Save to YAML
        if self.config.save_yaml and all_events:
            self.yaml_store.save_events(
                all_events,
                agency=agency,
                year=self.config.year,
                month=month,
                merge=True,
            )

        # Save to database and track price changes
        if self.config.save_db:
            for event in all_events:
                change = self.price_db.upsert_event(event)
                if change is not None:
                    stats.price_changes.append(change)

        return results

    def get_extraction_summary(self, result: PipelineResult) -> str:
        """Generate human-readable summary of extraction.

        Args:
            result: Pipeline result.

        Returns:
            Formatted summary string.
        """
        lines = [
            "=" * 60,
            "EXTRACTION PIPELINE SUMMARY",
            "=" * 60,
            f"Started:  {result.started_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Duration: {result.duration_seconds:.1f} seconds",
            f"Status:   {'SUCCESS' if result.success else 'FAILED'}",
            "",
            "STATISTICS:",
            f"  Images processed:     {result.stats.images_processed}",
            f"  Images failed:        {result.stats.images_failed}",
            f"  Events extracted:     {result.stats.events_extracted}",
            f"  Events sold out:      {result.stats.events_sold_out}",
            f"  Events need review:   {result.stats.events_needing_review}",
            f"  Price changes:        {len(result.stats.price_changes)}",
        ]

        if result.stats.price_changes:
            lines.append("")
            lines.append("PRICE CHANGES:")
            for change in result.stats.price_changes:
                direction = "↑" if change.is_increase else "↓"
                lines.append(
                    f"  {direction} {change.event_name}: "
                    f"${change.old_price:,} → ${change.new_price:,} "
                    f"({change.change_percent:+.1f}%)"
                )

        if result.stats.errors:
            lines.append("")
            lines.append("ERRORS:")
            for error in result.stats.errors[:10]:  # Limit to 10
                lines.append(f"  - {error}")
            if len(result.stats.errors) > 10:
                lines.append(f"  ... and {len(result.stats.errors) - 10} more")

        lines.append("=" * 60)

        return "\n".join(lines)


def run_extraction_cli(
    source_dir: str,
    target_dir: str = "data/agencies",
    db_path: str = "data/events.db",
    month: str = "agosto",
    year: int = 2026,
    agency: str | None = None,
    api_key: str | None = None,
) -> PipelineResult:
    """CLI entry point for running extraction.

    Args:
        source_dir: Source directory with raw images.
        target_dir: Target directory for organized files.
        db_path: Path to SQLite database.
        month: Month to process.
        year: Year for events.
        agency: Optional single agency to process.
        api_key: Anthropic API key (or use env var).

    Returns:
        PipelineResult.
    """
    config = PipelineConfig(
        source_dir=Path(source_dir),
        target_dir=Path(target_dir),
        db_path=Path(db_path),
        year=year,
        default_month=month,
        api_key=api_key,
    )

    pipeline = ExtractionPipeline(config)

    if agency:
        result = pipeline.run_single_agency(agency, month)
    else:
        result = pipeline.run(month)

    # Print summary
    print(pipeline.get_extraction_summary(result))

    return result
