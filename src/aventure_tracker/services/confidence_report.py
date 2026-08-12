"""Low confidence report generator.

Generates reports identifying events and fields that need manual review
due to low extraction confidence.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from aventure_tracker.models.extracted_event import (
    ConfidenceLevel,
    ExtractedEvent,
    ExtractionResult,
    FieldConfidence,
)


@dataclass
class FieldIssue:
    """A field that needs review.

    Attributes:
        event_name: Name of the event.
        event_id: Event identifier.
        field_name: Name of the problematic field.
        confidence: Confidence data for the field.
        source_image: Source image filename.
    """

    event_name: str
    event_id: str
    field_name: str
    confidence: FieldConfidence
    source_image: str | None = None

    @property
    def severity(self) -> str:
        """Get severity based on confidence level."""
        if self.confidence.score < 0.5:
            return "HIGH"
        elif self.confidence.score < 0.7:
            return "MEDIUM"
        return "LOW"


@dataclass
class EventIssue:
    """An event that needs review.

    Attributes:
        event: The event needing review.
        field_issues: List of field issues.
        source_image: Source image filename.
    """

    event: ExtractedEvent
    field_issues: list[FieldIssue]
    source_image: str | None = None

    @property
    def max_severity(self) -> str:
        """Get highest severity among field issues."""
        if any(f.severity == "HIGH" for f in self.field_issues):
            return "HIGH"
        elif any(f.severity == "MEDIUM" for f in self.field_issues):
            return "MEDIUM"
        return "LOW"

    @property
    def issue_count(self) -> int:
        """Get number of field issues."""
        return len(self.field_issues)


@dataclass
class ConfidenceReport:
    """Report of extraction confidence issues.

    Attributes:
        generated_at: When the report was generated.
        agency: Agency name (optional filter).
        threshold: Confidence threshold used.
        event_issues: List of events with issues.
        summary: Summary statistics.
    """

    generated_at: datetime
    agency: str | None
    threshold: float
    event_issues: list[EventIssue] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def total_events(self) -> int:
        """Get total events with issues."""
        return len(self.event_issues)

    @property
    def total_fields(self) -> int:
        """Get total field issues."""
        return sum(e.issue_count for e in self.event_issues)

    @property
    def high_severity_count(self) -> int:
        """Get count of high severity issues."""
        return sum(1 for e in self.event_issues if e.max_severity == "HIGH")


class ConfidenceReportGenerator:
    """Generates confidence reports for extracted events."""

    def __init__(self, confidence_threshold: float = 0.7):
        """Initialize the report generator.

        Args:
            confidence_threshold: Fields below this threshold are flagged.
        """
        self.threshold = confidence_threshold

    def generate_from_results(
        self,
        results: list[ExtractionResult],
        agency: str | None = None,
    ) -> ConfidenceReport:
        """Generate report from extraction results.

        Args:
            results: List of extraction results.
            agency: Optional agency filter.

        Returns:
            ConfidenceReport with all issues.
        """
        event_issues: list[EventIssue] = []

        for result in results:
            if agency and result.agency != agency:
                continue

            for event in result.events:
                issues = self._check_event(event, result.source_image)
                if issues:
                    event_issues.append(issues)

        # Sort by severity (HIGH first)
        severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        event_issues.sort(key=lambda e: severity_order.get(e.max_severity, 3))

        report = ConfidenceReport(
            generated_at=datetime.now(),
            agency=agency,
            threshold=self.threshold,
            event_issues=event_issues,
        )

        report.summary = self._calculate_summary(event_issues)

        return report

    def generate_from_events(
        self,
        events: list[ExtractedEvent],
        agency: str | None = None,
    ) -> ConfidenceReport:
        """Generate report from event list.

        Args:
            events: List of events to analyze.
            agency: Optional agency filter.

        Returns:
            ConfidenceReport with all issues.
        """
        event_issues: list[EventIssue] = []

        for event in events:
            if agency and event.agency != agency:
                continue

            issues = self._check_event(event)
            if issues:
                event_issues.append(issues)

        severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        event_issues.sort(key=lambda e: severity_order.get(e.max_severity, 3))

        report = ConfidenceReport(
            generated_at=datetime.now(),
            agency=agency,
            threshold=self.threshold,
            event_issues=event_issues,
        )

        report.summary = self._calculate_summary(event_issues)

        return report

    def _check_event(
        self,
        event: ExtractedEvent,
        source_image: Path | None = None,
    ) -> EventIssue | None:
        """Check event for confidence issues.

        Args:
            event: Event to check.
            source_image: Source image path.

        Returns:
            EventIssue if issues found, None otherwise.
        """
        field_issues: list[FieldIssue] = []
        image_name = source_image.name if source_image else None

        if event.source_image:
            image_name = event.source_image.name

        for field_name, confidence in event.confidence.items():
            if confidence.score < self.threshold:
                field_issues.append(
                    FieldIssue(
                        event_name=event.name,
                        event_id=event.event_id,
                        field_name=field_name,
                        confidence=confidence,
                        source_image=image_name,
                    )
                )

        if field_issues:
            return EventIssue(
                event=event,
                field_issues=field_issues,
                source_image=image_name,
            )

        return None

    def _calculate_summary(
        self, event_issues: list[EventIssue]
    ) -> dict[str, Any]:
        """Calculate summary statistics.

        Args:
            event_issues: List of event issues.

        Returns:
            Summary dictionary.
        """
        total_fields = sum(e.issue_count for e in event_issues)
        high_count = sum(1 for e in event_issues if e.max_severity == "HIGH")
        medium_count = sum(1 for e in event_issues if e.max_severity == "MEDIUM")
        low_count = sum(1 for e in event_issues if e.max_severity == "LOW")

        # Count by field type
        field_counts: dict[str, int] = {}
        for event_issue in event_issues:
            for field_issue in event_issue.field_issues:
                field_name = field_issue.field_name
                field_counts[field_name] = field_counts.get(field_name, 0) + 1

        return {
            "total_events_with_issues": len(event_issues),
            "total_field_issues": total_fields,
            "high_severity": high_count,
            "medium_severity": medium_count,
            "low_severity": low_count,
            "issues_by_field": field_counts,
        }

    def to_markdown(self, report: ConfidenceReport) -> str:
        """Convert report to Markdown format.

        Args:
            report: Report to convert.

        Returns:
            Markdown string.
        """
        lines = [
            "# Extraction Confidence Report",
            "",
            f"**Generated:** {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Confidence Threshold:** {report.threshold * 100:.0f}%",
        ]

        if report.agency:
            lines.append(f"**Agency:** {report.agency}")

        lines.extend([
            "",
            "## Summary",
            "",
            f"- **Events with issues:** {report.summary.get('total_events_with_issues', 0)}",
            f"- **Total field issues:** {report.summary.get('total_field_issues', 0)}",
            f"- **High severity:** {report.summary.get('high_severity', 0)}",
            f"- **Medium severity:** {report.summary.get('medium_severity', 0)}",
            f"- **Low severity:** {report.summary.get('low_severity', 0)}",
        ])

        # Issues by field
        field_counts = report.summary.get("issues_by_field", {})
        if field_counts:
            lines.extend([
                "",
                "### Issues by Field",
                "",
            ])
            for field_name, count in sorted(
                field_counts.items(), key=lambda x: -x[1]
            ):
                lines.append(f"- **{field_name}:** {count}")

        # Event details
        if report.event_issues:
            lines.extend([
                "",
                "## Events Needing Review",
                "",
            ])

            for event_issue in report.event_issues:
                severity_icon = {
                    "HIGH": "🔴",
                    "MEDIUM": "🟡",
                    "LOW": "🟢",
                }.get(event_issue.max_severity, "⚪")

                lines.extend([
                    f"### {severity_icon} {event_issue.event.name}",
                    "",
                    f"- **Date:** {event_issue.event.date_start.strftime('%d %b %Y')}",
                    f"- **Price:** {event_issue.event.price_formatted}",
                    f"- **Event ID:** `{event_issue.event.event_id}`",
                ])

                if event_issue.source_image:
                    lines.append(f"- **Source:** {event_issue.source_image}")

                lines.extend([
                    "",
                    "**Field Issues:**",
                    "",
                    "| Field | Confidence | Level | Raw Value | Notes |",
                    "|-------|------------|-------|-----------|-------|",
                ])

                for field_issue in event_issue.field_issues:
                    conf = field_issue.confidence
                    raw = conf.raw_value or "-"
                    notes = conf.notes or "-"
                    lines.append(
                        f"| {field_issue.field_name} | {conf.percentage}% | "
                        f"{conf.level.value} | {raw} | {notes} |"
                    )

                lines.append("")

        # No issues
        if not report.event_issues:
            lines.extend([
                "",
                "## ✅ No Issues Found",
                "",
                "All extracted events have confidence scores above the threshold.",
            ])

        return "\n".join(lines)

    def save_report(
        self,
        report: ConfidenceReport,
        output_path: Path,
    ) -> Path:
        """Save report to Markdown file.

        Args:
            report: Report to save.
            output_path: Output file path.

        Returns:
            Path to saved file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        markdown = self.to_markdown(report)
        output_path.write_text(markdown, encoding="utf-8")

        return output_path
