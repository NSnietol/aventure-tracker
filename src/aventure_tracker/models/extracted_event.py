"""Data models for extracted events from calendar images.

These models represent events extracted from travel agency calendars,
with confidence scores for each field to indicate extraction quality.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class ConfidenceLevel(Enum):
    """Confidence level categories for extracted fields."""

    HIGH = "high"  # >= 90%
    MEDIUM = "medium"  # 70-89%
    LOW = "low"  # 50-69%
    UNCERTAIN = "uncertain"  # < 50%

    @classmethod
    def from_score(cls, score: float) -> "ConfidenceLevel":
        """Get confidence level from numeric score.

        Args:
            score: Confidence score between 0.0 and 1.0.

        Returns:
            Corresponding ConfidenceLevel.
        """
        if score >= 0.9:
            return cls.HIGH
        elif score >= 0.7:
            return cls.MEDIUM
        elif score >= 0.5:
            return cls.LOW
        else:
            return cls.UNCERTAIN


@dataclass
class FieldConfidence:
    """Confidence score for a single extracted field.

    Attributes:
        field_name: Name of the field (e.g., "name", "price", "date_start").
        score: Confidence score between 0.0 and 1.0.
        raw_value: Original extracted value before parsing.
        notes: Optional notes about extraction issues.
    """

    field_name: str
    score: float
    raw_value: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        """Validate score is in valid range."""
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"Score must be between 0.0 and 1.0, got {self.score}")

    @property
    def level(self) -> ConfidenceLevel:
        """Get the confidence level category."""
        return ConfidenceLevel.from_score(self.score)

    @property
    def percentage(self) -> int:
        """Get score as percentage (0-100)."""
        return int(self.score * 100)

    @property
    def is_reliable(self) -> bool:
        """Check if confidence is high enough to trust (>= 70%)."""
        return self.score >= 0.7

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "score": self.score,
            "level": self.level.value,
        }
        if self.raw_value:
            result["raw_value"] = self.raw_value
        if self.notes:
            result["notes"] = self.notes
        return result


@dataclass
class ExtractedEvent:
    """An event extracted from a calendar image.

    Attributes:
        name: Event/destination name.
        date_start: Start date of the event.
        date_end: End date (same as start for single-day events).
        price: Price in COP (Colombian Pesos).
        agency: Agency name (normalized).
        sold_out: Whether the event is sold out.
        confidence: Confidence scores for each field.
        source_image: Path to the source image.
        extracted_at: Timestamp of extraction.
    """

    name: str
    date_start: date
    date_end: date
    price: int
    agency: str
    sold_out: bool = False
    confidence: dict[str, FieldConfidence] = field(default_factory=dict)
    source_image: Path | None = None
    extracted_at: datetime = field(default_factory=datetime.now)

    @property
    def event_id(self) -> str:
        """Generate unique event ID from name and date."""
        name_slug = self.name.lower().replace(" ", "-")[:30]
        date_str = self.date_start.strftime("%Y%m%d")
        return f"{self.agency}-{date_str}-{name_slug}"

    @property
    def is_multi_day(self) -> bool:
        """Check if event spans multiple days."""
        return self.date_start != self.date_end

    @property
    def duration_days(self) -> int:
        """Get event duration in days."""
        return (self.date_end - self.date_start).days + 1

    @property
    def price_formatted(self) -> str:
        """Get price formatted with thousand separators."""
        return f"${self.price:,}".replace(",", ".")

    @property
    def overall_confidence(self) -> float:
        """Calculate average confidence across all fields."""
        if not self.confidence:
            return 0.0
        scores = [c.score for c in self.confidence.values()]
        return sum(scores) / len(scores)

    @property
    def low_confidence_fields(self) -> list[str]:
        """Get list of fields with confidence < 70%."""
        return [name for name, conf in self.confidence.items() if not conf.is_reliable]

    @property
    def needs_review(self) -> bool:
        """Check if event needs manual review (any low confidence field)."""
        return len(self.low_confidence_fields) > 0

    def get_confidence(self, field_name: str) -> FieldConfidence | None:
        """Get confidence for a specific field."""
        return self.confidence.get(field_name)

    def set_confidence(
        self,
        field_name: str,
        score: float,
        raw_value: str | None = None,
        notes: str | None = None,
    ) -> None:
        """Set confidence for a field.

        Args:
            field_name: Name of the field.
            score: Confidence score (0.0-1.0).
            raw_value: Original extracted value.
            notes: Optional notes.
        """
        self.confidence[field_name] = FieldConfidence(
            field_name=field_name,
            score=score,
            raw_value=raw_value,
            notes=notes,
        )

    def to_dict(self, include_confidence: bool = True) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization.

        Args:
            include_confidence: Whether to include confidence details.

        Returns:
            Dictionary representation.
        """
        result: dict[str, Any] = {
            "name": self.name,
            "date_start": self.date_start.isoformat(),
            "date_end": self.date_end.isoformat(),
            "price": self.price,
            "agency": self.agency,
            "sold_out": self.sold_out,
        }

        if include_confidence and self.confidence:
            result["confidence"] = {
                name: conf.to_dict() for name, conf in self.confidence.items()
            }
            result["overall_confidence"] = round(self.overall_confidence, 2)
            result["needs_review"] = self.needs_review

        if self.source_image:
            result["source_image"] = str(self.source_image)

        result["extracted_at"] = self.extracted_at.isoformat()

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExtractedEvent":
        """Create ExtractedEvent from dictionary.

        Args:
            data: Dictionary with event data.

        Returns:
            ExtractedEvent instance.
        """
        # Parse dates
        date_start = data["date_start"]
        if isinstance(date_start, str):
            date_start = date.fromisoformat(date_start)

        date_end = data.get("date_end", date_start)
        if isinstance(date_end, str):
            date_end = date.fromisoformat(date_end)

        # Parse confidence
        confidence: dict[str, FieldConfidence] = {}
        if "confidence" in data:
            for field_name, conf_data in data["confidence"].items():
                confidence[field_name] = FieldConfidence(
                    field_name=field_name,
                    score=conf_data["score"],
                    raw_value=conf_data.get("raw_value"),
                    notes=conf_data.get("notes"),
                )

        # Parse extracted_at
        extracted_at = data.get("extracted_at", datetime.now())
        if isinstance(extracted_at, str):
            extracted_at = datetime.fromisoformat(extracted_at)

        # Parse source_image
        source_image = data.get("source_image")
        if source_image:
            source_image = Path(source_image)

        return cls(
            name=data["name"],
            date_start=date_start,
            date_end=date_end,
            price=data["price"],
            agency=data["agency"],
            sold_out=data.get("sold_out", False),
            confidence=confidence,
            source_image=source_image,
            extracted_at=extracted_at,
        )


@dataclass
class ExtractionResult:
    """Result of extracting events from an image.

    Attributes:
        source_image: Path to the processed image.
        agency: Agency name.
        month: Month name (e.g., "agosto").
        year: Year (e.g., 2026).
        events: List of extracted events.
        raw_text: Raw text extracted from image (for debugging).
        processing_time_ms: Time taken to process in milliseconds.
        success: Whether extraction was successful.
        error: Error message if extraction failed.
    """

    source_image: Path
    agency: str
    month: str
    year: int
    events: list[ExtractedEvent] = field(default_factory=list)
    raw_text: str | None = None
    processing_time_ms: int = 0
    success: bool = True
    error: str | None = None

    @property
    def event_count(self) -> int:
        """Get number of extracted events."""
        return len(self.events)

    @property
    def events_needing_review(self) -> list[ExtractedEvent]:
        """Get events that need manual review."""
        return [e for e in self.events if e.needs_review]

    @property
    def review_count(self) -> int:
        """Get number of events needing review."""
        return len(self.events_needing_review)

    @property
    def average_confidence(self) -> float:
        """Get average confidence across all events."""
        if not self.events:
            return 0.0
        return sum(e.overall_confidence for e in self.events) / len(self.events)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_image": str(self.source_image),
            "agency": self.agency,
            "month": self.month,
            "year": self.year,
            "event_count": self.event_count,
            "review_count": self.review_count,
            "average_confidence": round(self.average_confidence, 2),
            "processing_time_ms": self.processing_time_ms,
            "success": self.success,
            "error": self.error,
            "events": [e.to_dict() for e in self.events],
        }

    def to_yaml(self) -> str:
        """Convert to YAML string."""
        return yaml.dump(
            self.to_dict(),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
