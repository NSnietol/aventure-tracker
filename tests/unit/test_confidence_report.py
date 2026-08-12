"""Tests for confidence report generator."""

from datetime import date
from pathlib import Path

import pytest

from aventure_tracker.models.extracted_event import ExtractedEvent, ExtractionResult
from aventure_tracker.services.confidence_report import (
    ConfidenceReport,
    ConfidenceReportGenerator,
    EventIssue,
    FieldIssue,
)


@pytest.fixture
def generator() -> ConfidenceReportGenerator:
    """Create a report generator with 70% threshold."""
    return ConfidenceReportGenerator(confidence_threshold=0.7)


@pytest.fixture
def events_with_issues() -> list[ExtractedEvent]:
    """Create events with varying confidence levels."""
    events = [
        ExtractedEvent(
            name="High Confidence Event",
            date_start=date(2026, 8, 1),
            date_end=date(2026, 8, 1),
            price=195000,
            agency="brutaltravel",
            source_image=Path("calendar_01.jpg"),
        ),
        ExtractedEvent(
            name="Low Confidence Event",
            date_start=date(2026, 8, 5),
            date_end=date(2026, 8, 5),
            price=250000,
            agency="brutaltravel",
            source_image=Path("calendar_02.jpg"),
        ),
        ExtractedEvent(
            name="Very Low Confidence",
            date_start=date(2026, 8, 10),
            date_end=date(2026, 8, 10),
            price=100000,
            agency="brutaltravel",
            source_image=Path("calendar_03.jpg"),
        ),
    ]

    # High confidence event - all fields good
    events[0].set_confidence("name", 0.95)
    events[0].set_confidence("price", 0.9)
    events[0].set_confidence("date_start", 0.85)

    # Low confidence event - one field below threshold
    events[1].set_confidence("name", 0.8)
    events[1].set_confidence("price", 0.6, raw_value="$250.00", notes="Missing zeros?")
    events[1].set_confidence("date_start", 0.75)

    # Very low confidence - multiple fields below threshold
    events[2].set_confidence("name", 0.4, raw_value="V3ry L0w", notes="OCR artifacts")
    events[2].set_confidence("price", 0.3, raw_value="$1OO.OOO")
    events[2].set_confidence("date_start", 0.5)

    return events


@pytest.fixture
def extraction_results(
    events_with_issues: list[ExtractedEvent], tmp_path: Path
) -> list[ExtractionResult]:
    """Create extraction results with events."""
    return [
        ExtractionResult(
            source_image=tmp_path / "calendar_01.jpg",
            agency="brutaltravel",
            month="agosto",
            year=2026,
            events=events_with_issues[:1],
            success=True,
        ),
        ExtractionResult(
            source_image=tmp_path / "calendar_02.jpg",
            agency="brutaltravel",
            month="agosto",
            year=2026,
            events=events_with_issues[1:],
            success=True,
        ),
    ]


class TestFieldIssue:
    """Tests for FieldIssue dataclass."""

    def test_severity_high(self, events_with_issues: list[ExtractedEvent]) -> None:
        """Should return HIGH for confidence < 0.5."""
        event = events_with_issues[2]
        confidence = event.get_confidence("name")
        assert confidence is not None

        issue = FieldIssue(
            event_name=event.name,
            event_id=event.event_id,
            field_name="name",
            confidence=confidence,
        )

        assert issue.severity == "HIGH"

    def test_severity_medium(self, events_with_issues: list[ExtractedEvent]) -> None:
        """Should return MEDIUM for confidence 0.5-0.7."""
        event = events_with_issues[1]
        confidence = event.get_confidence("price")
        assert confidence is not None

        issue = FieldIssue(
            event_name=event.name,
            event_id=event.event_id,
            field_name="price",
            confidence=confidence,
        )

        assert issue.severity == "MEDIUM"

    def test_severity_low(self, events_with_issues: list[ExtractedEvent]) -> None:
        """Should return LOW for confidence just below threshold."""
        # Create an event with confidence between 0.7 and threshold
        event = ExtractedEvent(
            name="Test",
            date_start=date(2026, 8, 1),
            date_end=date(2026, 8, 1),
            price=100000,
            agency="test",
        )
        event.set_confidence("price", 0.75)  # Just above 0.7 but could be flagged with higher threshold

        # With 0.8 threshold, this would be flagged
        confidence = event.get_confidence("price")
        assert confidence is not None

        # Create issue (simulating higher threshold scenario)
        issue = FieldIssue(
            event_name=event.name,
            event_id=event.event_id,
            field_name="price",
            confidence=confidence,
        )

        assert issue.severity == "LOW"


class TestEventIssue:
    """Tests for EventIssue dataclass."""

    def test_max_severity_high(
        self, events_with_issues: list[ExtractedEvent]
    ) -> None:
        """Should return HIGH if any field is HIGH."""
        event = events_with_issues[2]
        field_issues = []

        for field_name in ["name", "price", "date_start"]:
            conf = event.get_confidence(field_name)
            if conf and conf.score < 0.7:
                field_issues.append(
                    FieldIssue(
                        event_name=event.name,
                        event_id=event.event_id,
                        field_name=field_name,
                        confidence=conf,
                    )
                )

        issue = EventIssue(event=event, field_issues=field_issues)
        assert issue.max_severity == "HIGH"

    def test_issue_count(self, events_with_issues: list[ExtractedEvent]) -> None:
        """Should count field issues correctly."""
        event = events_with_issues[2]
        field_issues = []

        for field_name in ["name", "price", "date_start"]:
            conf = event.get_confidence(field_name)
            if conf and conf.score < 0.7:
                field_issues.append(
                    FieldIssue(
                        event_name=event.name,
                        event_id=event.event_id,
                        field_name=field_name,
                        confidence=conf,
                    )
                )

        issue = EventIssue(event=event, field_issues=field_issues)
        assert issue.issue_count == 3  # All three fields below threshold


class TestConfidenceReportGenerator:
    """Tests for ConfidenceReportGenerator."""

    def test_generate_from_events(
        self,
        generator: ConfidenceReportGenerator,
        events_with_issues: list[ExtractedEvent],
    ) -> None:
        """Should generate report from events."""
        report = generator.generate_from_events(events_with_issues)

        # Should have 2 events with issues (not the high confidence one)
        assert report.total_events == 2
        assert report.threshold == 0.7

    def test_generate_from_events_filters_high_confidence(
        self,
        generator: ConfidenceReportGenerator,
        events_with_issues: list[ExtractedEvent],
    ) -> None:
        """Should not include events with all high confidence."""
        report = generator.generate_from_events(events_with_issues)

        event_names = [e.event.name for e in report.event_issues]
        assert "High Confidence Event" not in event_names
        assert "Low Confidence Event" in event_names
        assert "Very Low Confidence" in event_names

    def test_generate_from_events_filters_by_agency(
        self,
        generator: ConfidenceReportGenerator,
        events_with_issues: list[ExtractedEvent],
    ) -> None:
        """Should filter by agency."""
        # Add event from different agency
        other_event = ExtractedEvent(
            name="Other Agency Event",
            date_start=date(2026, 8, 1),
            date_end=date(2026, 8, 1),
            price=100000,
            agency="medellinbungee",
        )
        other_event.set_confidence("name", 0.5)

        all_events = events_with_issues + [other_event]

        report = generator.generate_from_events(all_events, agency="brutaltravel")

        assert report.agency == "brutaltravel"
        agencies = {e.event.agency for e in report.event_issues}
        assert agencies == {"brutaltravel"}

    def test_generate_from_results(
        self,
        generator: ConfidenceReportGenerator,
        extraction_results: list[ExtractionResult],
    ) -> None:
        """Should generate report from extraction results."""
        report = generator.generate_from_results(extraction_results)

        assert report.total_events == 2

    def test_summary_statistics(
        self,
        generator: ConfidenceReportGenerator,
        events_with_issues: list[ExtractedEvent],
    ) -> None:
        """Should calculate summary statistics."""
        report = generator.generate_from_events(events_with_issues)

        assert report.summary["total_events_with_issues"] == 2
        assert report.summary["high_severity"] == 1  # Very Low Confidence
        assert report.summary["medium_severity"] == 1  # Low Confidence Event
        assert "issues_by_field" in report.summary

    def test_issues_by_field(
        self,
        generator: ConfidenceReportGenerator,
        events_with_issues: list[ExtractedEvent],
    ) -> None:
        """Should count issues by field type."""
        report = generator.generate_from_events(events_with_issues)

        field_counts = report.summary["issues_by_field"]
        assert "price" in field_counts
        assert "name" in field_counts

    def test_sorted_by_severity(
        self,
        generator: ConfidenceReportGenerator,
        events_with_issues: list[ExtractedEvent],
    ) -> None:
        """Should sort issues by severity (HIGH first)."""
        report = generator.generate_from_events(events_with_issues)

        if len(report.event_issues) >= 2:
            assert report.event_issues[0].max_severity == "HIGH"

    def test_custom_threshold(
        self, events_with_issues: list[ExtractedEvent]
    ) -> None:
        """Should respect custom threshold."""
        strict_generator = ConfidenceReportGenerator(confidence_threshold=0.9)
        report = strict_generator.generate_from_events(events_with_issues)

        # With 0.9 threshold, all events should have issues
        assert report.total_events == 3

    def test_to_markdown(
        self,
        generator: ConfidenceReportGenerator,
        events_with_issues: list[ExtractedEvent],
    ) -> None:
        """Should generate valid Markdown."""
        report = generator.generate_from_events(events_with_issues)
        markdown = generator.to_markdown(report)

        assert "# Extraction Confidence Report" in markdown
        assert "## Summary" in markdown
        assert "## Events Needing Review" in markdown
        assert "Low Confidence Event" in markdown
        assert "Very Low Confidence" in markdown
        assert "| Field | Confidence |" in markdown

    def test_to_markdown_no_issues(self, generator: ConfidenceReportGenerator) -> None:
        """Should show success message when no issues."""
        # All high confidence events
        events = [
            ExtractedEvent(
                name="Good Event",
                date_start=date(2026, 8, 1),
                date_end=date(2026, 8, 1),
                price=100000,
                agency="test",
            )
        ]
        events[0].set_confidence("name", 0.95)
        events[0].set_confidence("price", 0.9)

        report = generator.generate_from_events(events)
        markdown = generator.to_markdown(report)

        assert "No Issues Found" in markdown

    def test_to_markdown_includes_source_image(
        self,
        generator: ConfidenceReportGenerator,
        events_with_issues: list[ExtractedEvent],
    ) -> None:
        """Should include source image in report."""
        report = generator.generate_from_events(events_with_issues)
        markdown = generator.to_markdown(report)

        assert "calendar_02.jpg" in markdown or "Source" in markdown

    def test_to_markdown_includes_raw_values(
        self,
        generator: ConfidenceReportGenerator,
        events_with_issues: list[ExtractedEvent],
    ) -> None:
        """Should include raw values and notes."""
        report = generator.generate_from_events(events_with_issues)
        markdown = generator.to_markdown(report)

        assert "$250.00" in markdown or "Missing zeros" in markdown

    def test_save_report(
        self,
        generator: ConfidenceReportGenerator,
        events_with_issues: list[ExtractedEvent],
        tmp_path: Path,
    ) -> None:
        """Should save report to file."""
        report = generator.generate_from_events(events_with_issues)
        output_path = tmp_path / "reports" / "confidence_report.md"

        saved_path = generator.save_report(report, output_path)

        assert saved_path.exists()
        content = saved_path.read_text()
        assert "# Extraction Confidence Report" in content

    def test_report_properties(
        self,
        generator: ConfidenceReportGenerator,
        events_with_issues: list[ExtractedEvent],
    ) -> None:
        """Should have correct property values."""
        report = generator.generate_from_events(events_with_issues)

        assert report.total_events == 2
        assert report.total_fields == 4  # 1 + 3 field issues
        assert report.high_severity_count == 1


class TestConfidenceReport:
    """Tests for ConfidenceReport dataclass."""

    def test_total_fields(self) -> None:
        """Should calculate total field issues."""
        event1 = ExtractedEvent(
            name="E1",
            date_start=date(2026, 8, 1),
            date_end=date(2026, 8, 1),
            price=100000,
            agency="test",
        )
        event1.set_confidence("name", 0.5)

        event2 = ExtractedEvent(
            name="E2",
            date_start=date(2026, 8, 2),
            date_end=date(2026, 8, 2),
            price=200000,
            agency="test",
        )
        event2.set_confidence("name", 0.4)
        event2.set_confidence("price", 0.3)

        generator = ConfidenceReportGenerator(confidence_threshold=0.7)
        report = generator.generate_from_events([event1, event2])

        assert report.total_fields == 3  # 1 + 2
