"""Tests for extracted event models."""

from datetime import date, datetime
from pathlib import Path

import pytest

from aventure_tracker.models.extracted_event import (
    ConfidenceLevel,
    ExtractedEvent,
    ExtractionResult,
    FieldConfidence,
)


class TestConfidenceLevel:
    """Tests for ConfidenceLevel enum."""

    def test_from_score_high(self) -> None:
        """Should return HIGH for scores >= 0.9."""
        assert ConfidenceLevel.from_score(0.9) == ConfidenceLevel.HIGH
        assert ConfidenceLevel.from_score(0.95) == ConfidenceLevel.HIGH
        assert ConfidenceLevel.from_score(1.0) == ConfidenceLevel.HIGH

    def test_from_score_medium(self) -> None:
        """Should return MEDIUM for scores 0.7-0.89."""
        assert ConfidenceLevel.from_score(0.7) == ConfidenceLevel.MEDIUM
        assert ConfidenceLevel.from_score(0.8) == ConfidenceLevel.MEDIUM
        assert ConfidenceLevel.from_score(0.89) == ConfidenceLevel.MEDIUM

    def test_from_score_low(self) -> None:
        """Should return LOW for scores 0.5-0.69."""
        assert ConfidenceLevel.from_score(0.5) == ConfidenceLevel.LOW
        assert ConfidenceLevel.from_score(0.6) == ConfidenceLevel.LOW
        assert ConfidenceLevel.from_score(0.69) == ConfidenceLevel.LOW

    def test_from_score_uncertain(self) -> None:
        """Should return UNCERTAIN for scores < 0.5."""
        assert ConfidenceLevel.from_score(0.0) == ConfidenceLevel.UNCERTAIN
        assert ConfidenceLevel.from_score(0.3) == ConfidenceLevel.UNCERTAIN
        assert ConfidenceLevel.from_score(0.49) == ConfidenceLevel.UNCERTAIN


class TestFieldConfidence:
    """Tests for FieldConfidence dataclass."""

    def test_create_valid_confidence(self) -> None:
        """Should create confidence with valid score."""
        conf = FieldConfidence(field_name="name", score=0.85)
        assert conf.field_name == "name"
        assert conf.score == 0.85
        assert conf.level == ConfidenceLevel.MEDIUM
        assert conf.percentage == 85
        assert conf.is_reliable is True

    def test_create_with_all_fields(self) -> None:
        """Should create confidence with all optional fields."""
        conf = FieldConfidence(
            field_name="price",
            score=0.6,
            raw_value="$195.000",
            notes="Possible OCR error",
        )
        assert conf.raw_value == "$195.000"
        assert conf.notes == "Possible OCR error"

    def test_invalid_score_raises(self) -> None:
        """Should raise error for invalid scores."""
        with pytest.raises(ValueError):
            FieldConfidence(field_name="test", score=1.5)

        with pytest.raises(ValueError):
            FieldConfidence(field_name="test", score=-0.1)

    def test_is_reliable(self) -> None:
        """Should correctly determine reliability."""
        assert FieldConfidence(field_name="a", score=0.7).is_reliable is True
        assert FieldConfidence(field_name="a", score=0.69).is_reliable is False

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        conf = FieldConfidence(
            field_name="name",
            score=0.9,
            raw_value="Test",
            notes="Note",
        )
        d = conf.to_dict()
        assert d["score"] == 0.9
        assert d["level"] == "high"
        assert d["raw_value"] == "Test"
        assert d["notes"] == "Note"

    def test_to_dict_minimal(self) -> None:
        """Should convert to dictionary without optional fields."""
        conf = FieldConfidence(field_name="name", score=0.9)
        d = conf.to_dict()
        assert "raw_value" not in d
        assert "notes" not in d


class TestExtractedEvent:
    """Tests for ExtractedEvent dataclass."""

    @pytest.fixture
    def sample_event(self) -> ExtractedEvent:
        """Create a sample event for testing."""
        event = ExtractedEvent(
            name="Cavernas del Nus",
            date_start=date(2026, 8, 1),
            date_end=date(2026, 8, 1),
            price=195000,
            agency="brutaltravel",
        )
        event.set_confidence("name", 0.95)
        event.set_confidence("date_start", 0.9)
        event.set_confidence("price", 0.85)
        return event

    @pytest.fixture
    def multi_day_event(self) -> ExtractedEvent:
        """Create a multi-day event for testing."""
        return ExtractedEvent(
            name="Tatacoa",
            date_start=date(2026, 8, 21),
            date_end=date(2026, 8, 23),
            price=490000,
            agency="brutaltravel",
        )

    def test_create_event(self, sample_event: ExtractedEvent) -> None:
        """Should create event with all fields."""
        assert sample_event.name == "Cavernas del Nus"
        assert sample_event.date_start == date(2026, 8, 1)
        assert sample_event.price == 195000
        assert sample_event.agency == "brutaltravel"
        assert sample_event.sold_out is False

    def test_event_id(self, sample_event: ExtractedEvent) -> None:
        """Should generate unique event ID."""
        event_id = sample_event.event_id
        assert event_id.startswith("brutaltravel-20260801-")
        assert "cavernas-del-nus" in event_id

    def test_is_multi_day(
        self, sample_event: ExtractedEvent, multi_day_event: ExtractedEvent
    ) -> None:
        """Should correctly identify multi-day events."""
        assert sample_event.is_multi_day is False
        assert multi_day_event.is_multi_day is True

    def test_duration_days(
        self, sample_event: ExtractedEvent, multi_day_event: ExtractedEvent
    ) -> None:
        """Should calculate duration correctly."""
        assert sample_event.duration_days == 1
        assert multi_day_event.duration_days == 3

    def test_price_formatted(self, sample_event: ExtractedEvent) -> None:
        """Should format price with Colombian separators."""
        assert sample_event.price_formatted == "$195.000"

    def test_price_formatted_large(self) -> None:
        """Should format large prices correctly."""
        event = ExtractedEvent(
            name="Test",
            date_start=date(2026, 8, 1),
            date_end=date(2026, 8, 1),
            price=1580000,
            agency="test",
        )
        assert event.price_formatted == "$1.580.000"

    def test_overall_confidence(self, sample_event: ExtractedEvent) -> None:
        """Should calculate average confidence."""
        # sample_event has 0.95, 0.9, 0.85 = avg 0.9
        assert 0.89 <= sample_event.overall_confidence <= 0.91

    def test_overall_confidence_empty(self) -> None:
        """Should return 0 when no confidence data."""
        event = ExtractedEvent(
            name="Test",
            date_start=date(2026, 8, 1),
            date_end=date(2026, 8, 1),
            price=100000,
            agency="test",
        )
        assert event.overall_confidence == 0.0

    def test_low_confidence_fields(self) -> None:
        """Should identify low confidence fields."""
        event = ExtractedEvent(
            name="Test",
            date_start=date(2026, 8, 1),
            date_end=date(2026, 8, 1),
            price=100000,
            agency="test",
        )
        event.set_confidence("name", 0.95)
        event.set_confidence("price", 0.5)  # Low
        event.set_confidence("date_start", 0.6)  # Low

        low_fields = event.low_confidence_fields
        assert "price" in low_fields
        assert "date_start" in low_fields
        assert "name" not in low_fields

    def test_needs_review(self) -> None:
        """Should flag events needing review."""
        event = ExtractedEvent(
            name="Test",
            date_start=date(2026, 8, 1),
            date_end=date(2026, 8, 1),
            price=100000,
            agency="test",
        )
        event.set_confidence("name", 0.95)
        event.set_confidence("price", 0.95)
        assert event.needs_review is False

        event.set_confidence("date_start", 0.5)
        assert event.needs_review is True

    def test_sold_out_event(self) -> None:
        """Should handle sold out events."""
        event = ExtractedEvent(
            name="Popular Trip",
            date_start=date(2026, 8, 15),
            date_end=date(2026, 8, 15),
            price=500000,
            agency="brutaltravel",
            sold_out=True,
        )
        assert event.sold_out is True

    def test_to_dict(self, sample_event: ExtractedEvent) -> None:
        """Should convert to dictionary."""
        d = sample_event.to_dict()
        assert d["name"] == "Cavernas del Nus"
        assert d["date_start"] == "2026-08-01"
        assert d["price"] == 195000
        assert d["agency"] == "brutaltravel"
        assert d["sold_out"] is False
        assert "confidence" in d
        assert "overall_confidence" in d
        assert "needs_review" in d

    def test_to_dict_without_confidence(self, sample_event: ExtractedEvent) -> None:
        """Should convert to dictionary without confidence."""
        d = sample_event.to_dict(include_confidence=False)
        assert "confidence" not in d
        assert "overall_confidence" not in d

    def test_from_dict(self, sample_event: ExtractedEvent) -> None:
        """Should create event from dictionary."""
        d = sample_event.to_dict()
        restored = ExtractedEvent.from_dict(d)

        assert restored.name == sample_event.name
        assert restored.date_start == sample_event.date_start
        assert restored.price == sample_event.price
        assert restored.agency == sample_event.agency
        assert len(restored.confidence) == len(sample_event.confidence)

    def test_from_dict_minimal(self) -> None:
        """Should create event from minimal dictionary."""
        d = {
            "name": "Test Event",
            "date_start": "2026-08-01",
            "price": 100000,
            "agency": "test",
        }
        event = ExtractedEvent.from_dict(d)
        assert event.name == "Test Event"
        assert event.date_start == date(2026, 8, 1)
        assert event.date_end == date(2026, 8, 1)  # Same as start

    def test_set_confidence_with_details(self) -> None:
        """Should set confidence with raw value and notes."""
        event = ExtractedEvent(
            name="Test",
            date_start=date(2026, 8, 1),
            date_end=date(2026, 8, 1),
            price=100000,
            agency="test",
        )
        event.set_confidence(
            "price",
            score=0.6,
            raw_value="$100.00",
            notes="Might be missing zeros",
        )

        conf = event.get_confidence("price")
        assert conf is not None
        assert conf.score == 0.6
        assert conf.raw_value == "$100.00"
        assert conf.notes == "Might be missing zeros"


class TestExtractionResult:
    """Tests for ExtractionResult dataclass."""

    @pytest.fixture
    def sample_result(self, tmp_path: Path) -> ExtractionResult:
        """Create a sample extraction result."""
        events = [
            ExtractedEvent(
                name="Event 1",
                date_start=date(2026, 8, 1),
                date_end=date(2026, 8, 1),
                price=100000,
                agency="brutaltravel",
            ),
            ExtractedEvent(
                name="Event 2",
                date_start=date(2026, 8, 2),
                date_end=date(2026, 8, 2),
                price=200000,
                agency="brutaltravel",
            ),
        ]
        events[0].set_confidence("name", 0.95)
        events[0].set_confidence("price", 0.9)
        events[1].set_confidence("name", 0.5)  # Low confidence
        events[1].set_confidence("price", 0.85)

        return ExtractionResult(
            source_image=tmp_path / "calendar.jpg",
            agency="brutaltravel",
            month="agosto",
            year=2026,
            events=events,
            processing_time_ms=150,
        )

    def test_event_count(self, sample_result: ExtractionResult) -> None:
        """Should count events correctly."""
        assert sample_result.event_count == 2

    def test_events_needing_review(self, sample_result: ExtractionResult) -> None:
        """Should identify events needing review."""
        review_events = sample_result.events_needing_review
        assert len(review_events) == 1
        assert review_events[0].name == "Event 2"

    def test_review_count(self, sample_result: ExtractionResult) -> None:
        """Should count events needing review."""
        assert sample_result.review_count == 1

    def test_average_confidence(self, sample_result: ExtractionResult) -> None:
        """Should calculate average confidence."""
        # Event 1: (0.95 + 0.9) / 2 = 0.925
        # Event 2: (0.5 + 0.85) / 2 = 0.675
        # Average: (0.925 + 0.675) / 2 = 0.8
        assert 0.75 <= sample_result.average_confidence <= 0.85

    def test_average_confidence_empty(self, tmp_path: Path) -> None:
        """Should return 0 for empty results."""
        result = ExtractionResult(
            source_image=tmp_path / "empty.jpg",
            agency="test",
            month="agosto",
            year=2026,
        )
        assert result.average_confidence == 0.0

    def test_failed_result(self, tmp_path: Path) -> None:
        """Should handle failed extraction."""
        result = ExtractionResult(
            source_image=tmp_path / "bad.jpg",
            agency="test",
            month="agosto",
            year=2026,
            success=False,
            error="Could not parse image",
        )
        assert result.success is False
        assert result.error == "Could not parse image"
        assert result.event_count == 0

    def test_to_dict(self, sample_result: ExtractionResult) -> None:
        """Should convert to dictionary."""
        d = sample_result.to_dict()
        assert d["agency"] == "brutaltravel"
        assert d["month"] == "agosto"
        assert d["year"] == 2026
        assert d["event_count"] == 2
        assert d["review_count"] == 1
        assert d["processing_time_ms"] == 150
        assert d["success"] is True
        assert len(d["events"]) == 2

    def test_to_yaml(self, sample_result: ExtractionResult) -> None:
        """Should convert to YAML string."""
        yaml_str = sample_result.to_yaml()
        assert "brutaltravel" in yaml_str
        assert "agosto" in yaml_str
        assert "Event 1" in yaml_str
        assert "Event 2" in yaml_str
