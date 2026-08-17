"""Tests for YAML event store service."""

from datetime import date
from pathlib import Path

import pytest
import yaml

from aventure_tracker.models.extracted_event import ExtractedEvent
from aventure_tracker.services.yaml_event_store import YAMLEventStore


@pytest.fixture
def store(tmp_path: Path) -> YAMLEventStore:
    """Create a YAMLEventStore instance with temp directory."""
    return YAMLEventStore(tmp_path / "agencies")


@pytest.fixture
def sample_events() -> list[ExtractedEvent]:
    """Create sample events for testing."""
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
        ExtractedEvent(
            name="Sold Out Trip",
            date_start=date(2026, 8, 15),
            date_end=date(2026, 8, 15),
            price=300000,
            agency="brutaltravel",
            sold_out=True,
        ),
    ]
    # Add confidence to first event
    events[0].set_confidence("name", 0.95)
    events[0].set_confidence("price", 0.85, raw_value="$195.000")
    events[0].set_confidence("date_start", 0.9)

    # Add low confidence to second event
    events[1].set_confidence("name", 0.7)
    events[1].set_confidence("price", 0.5, notes="Possible OCR error")

    return events


class TestYAMLEventStore:
    """Tests for YAMLEventStore class."""

    def test_save_events(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should save events to YAML file."""
        file_path = store.save_events(
            sample_events, agency="brutaltravel", year=2026, month="agosto"
        )

        assert file_path.exists()
        assert file_path.name == "events.yaml"
        assert "brutaltravel/2026/agosto" in str(file_path)

    def test_save_creates_directories(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should create necessary directories."""
        store.save_events(
            sample_events, agency="newagency", year=2026, month="septiembre"
        )

        expected_dir = store.base_dir / "newagency" / "2026" / "septiembre"
        assert expected_dir.exists()

    def test_saved_file_is_readable_yaml(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should save valid YAML that can be parsed."""
        file_path = store.save_events(
            sample_events, agency="brutaltravel", year=2026, month="agosto"
        )

        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        # Skip comment header and parse YAML
        yaml_start = content.find("metadata:")
        data = yaml.safe_load(content[yaml_start:])

        assert "metadata" in data
        assert "events" in data
        assert len(data["events"]) == 3

    def test_saved_file_has_header(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should include human-readable header."""
        file_path = store.save_events(
            sample_events, agency="brutaltravel", year=2026, month="agosto"
        )

        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        assert "Eventos Extraídos" in content
        assert "Brutaltravel" in content
        assert "Agosto" in content
        assert "needs_review" in content

    def test_load_events(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should load events from YAML file."""
        store.save_events(
            sample_events, agency="brutaltravel", year=2026, month="agosto"
        )

        loaded = store.load_events(agency="brutaltravel", year=2026, month="agosto")

        assert len(loaded) == 3
        # Events should be sorted by date
        assert loaded[0].name == "Cavernas del Nus"
        assert loaded[1].name == "Sold Out Trip"
        assert loaded[2].name == "Tatacoa"

    def test_load_preserves_event_data(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should preserve all event data through save/load cycle."""
        store.save_events(
            sample_events, agency="brutaltravel", year=2026, month="agosto"
        )
        loaded = store.load_events(agency="brutaltravel", year=2026, month="agosto")

        cavernas = next(e for e in loaded if e.name == "Cavernas del Nus")
        assert cavernas.date_start == date(2026, 8, 1)
        assert cavernas.price == 195000
        assert cavernas.agency == "brutaltravel"
        assert cavernas.sold_out is False

    def test_load_preserves_multi_day_dates(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should preserve multi-day event dates."""
        store.save_events(
            sample_events, agency="brutaltravel", year=2026, month="agosto"
        )
        loaded = store.load_events(agency="brutaltravel", year=2026, month="agosto")

        tatacoa = next(e for e in loaded if e.name == "Tatacoa")
        assert tatacoa.date_start == date(2026, 8, 21)
        assert tatacoa.date_end == date(2026, 8, 23)
        assert tatacoa.is_multi_day is True

    def test_load_preserves_sold_out(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should preserve sold_out status."""
        store.save_events(
            sample_events, agency="brutaltravel", year=2026, month="agosto"
        )
        loaded = store.load_events(agency="brutaltravel", year=2026, month="agosto")

        sold_out_event = next(e for e in loaded if e.name == "Sold Out Trip")
        assert sold_out_event.sold_out is True

    def test_load_preserves_confidence(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should preserve confidence scores."""
        store.save_events(
            sample_events, agency="brutaltravel", year=2026, month="agosto"
        )
        loaded = store.load_events(agency="brutaltravel", year=2026, month="agosto")

        cavernas = next(e for e in loaded if e.name == "Cavernas del Nus")
        assert len(cavernas.confidence) == 3

        name_conf = cavernas.get_confidence("name")
        assert name_conf is not None
        assert name_conf.score == 0.95

        price_conf = cavernas.get_confidence("price")
        assert price_conf is not None
        assert price_conf.raw_value == "$195.000"

    def test_load_nonexistent_returns_empty(self, store: YAMLEventStore) -> None:
        """Should return empty list for nonexistent file."""
        loaded = store.load_events(agency="fake", year=2026, month="agosto")
        assert loaded == []

    def test_merge_events(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should merge new events with existing."""
        # Save initial events
        store.save_events(
            sample_events[:1], agency="brutaltravel", year=2026, month="agosto"
        )

        # Save more events with merge
        store.save_events(
            sample_events[1:],
            agency="brutaltravel",
            year=2026,
            month="agosto",
            merge=True,
        )

        loaded = store.load_events(agency="brutaltravel", year=2026, month="agosto")
        assert len(loaded) == 3

    def test_merge_updates_existing(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should update existing events when merging by event_id."""
        # Save initial
        store.save_events(
            sample_events[:1], agency="brutaltravel", year=2026, month="agosto"
        )

        # Create updated version with different price
        updated_event = ExtractedEvent(
            name="Cavernas del Nus",
            date_start=date(2026, 8, 1),
            date_end=date(2026, 8, 1),
            price=250000,  # Updated price
            agency="brutaltravel",
        )

        store.save_events(
            [updated_event],
            agency="brutaltravel",
            year=2026,
            month="agosto",
            merge=True,
        )

        loaded = store.load_events(agency="brutaltravel", year=2026, month="agosto")
        assert len(loaded) == 1
        assert loaded[0].price == 250000

    def test_overwrite_without_merge(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should overwrite when merge=False."""
        store.save_events(
            sample_events, agency="brutaltravel", year=2026, month="agosto"
        )

        new_event = ExtractedEvent(
            name="New Event",
            date_start=date(2026, 8, 5),
            date_end=date(2026, 8, 5),
            price=100000,
            agency="brutaltravel",
        )

        store.save_events(
            [new_event], agency="brutaltravel", year=2026, month="agosto", merge=False
        )

        loaded = store.load_events(agency="brutaltravel", year=2026, month="agosto")
        assert len(loaded) == 1
        assert loaded[0].name == "New Event"

    def test_get_event_by_id(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should retrieve event by ID."""
        store.save_events(
            sample_events, agency="brutaltravel", year=2026, month="agosto"
        )

        event_id = sample_events[0].event_id
        event = store.get_event_by_id(
            event_id, agency="brutaltravel", year=2026, month="agosto"
        )

        assert event is not None
        assert event.name == "Cavernas del Nus"

    def test_get_event_by_id_not_found(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should return None for unknown event ID."""
        store.save_events(
            sample_events, agency="brutaltravel", year=2026, month="agosto"
        )

        event = store.get_event_by_id(
            "fake-id", agency="brutaltravel", year=2026, month="agosto"
        )

        assert event is None

    def test_delete_event(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should delete event by ID."""
        store.save_events(
            sample_events, agency="brutaltravel", year=2026, month="agosto"
        )

        event_id = sample_events[0].event_id
        result = store.delete_event(
            event_id, agency="brutaltravel", year=2026, month="agosto"
        )

        assert result is True

        loaded = store.load_events(agency="brutaltravel", year=2026, month="agosto")
        assert len(loaded) == 2
        assert all(e.event_id != event_id for e in loaded)

    def test_delete_event_not_found(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should return False when deleting unknown event."""
        store.save_events(
            sample_events, agency="brutaltravel", year=2026, month="agosto"
        )

        result = store.delete_event(
            "fake-id", agency="brutaltravel", year=2026, month="agosto"
        )

        assert result is False

    def test_list_available_months(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should list available months with event counts."""
        store.save_events(
            sample_events, agency="brutaltravel", year=2026, month="agosto"
        )
        store.save_events(
            sample_events[:1], agency="brutaltravel", year=2026, month="septiembre"
        )

        months = store.list_available_months(agency="brutaltravel")

        assert len(months) == 2
        assert months[0]["month"] == "agosto"
        assert months[0]["event_count"] == 3
        assert months[1]["month"] == "septiembre"
        assert months[1]["event_count"] == 1

    def test_list_available_months_filter_year(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should filter by year."""
        store.save_events(
            sample_events, agency="brutaltravel", year=2026, month="agosto"
        )

        # Create event for different year (manually create the dir structure)
        event_2025 = ExtractedEvent(
            name="Test",
            date_start=date(2025, 8, 1),
            date_end=date(2025, 8, 1),
            price=100000,
            agency="brutaltravel",
        )
        store.save_events(
            [event_2025], agency="brutaltravel", year=2025, month="agosto"
        )

        months = store.list_available_months(agency="brutaltravel", year=2026)

        assert len(months) == 1
        assert months[0]["year"] == 2026

    def test_list_available_months_empty(self, store: YAMLEventStore) -> None:
        """Should return empty list for unknown agency."""
        months = store.list_available_months(agency="unknown")
        assert months == []

    def test_metadata_includes_statistics(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should include statistics in metadata."""
        file_path = store.save_events(
            sample_events, agency="brutaltravel", year=2026, month="agosto"
        )

        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        yaml_start = content.find("metadata:")
        data = yaml.safe_load(content[yaml_start:])

        meta = data["metadata"]
        assert meta["total_events"] == 3
        assert meta["sold_out_count"] == 1
        assert meta["needs_review_count"] == 1  # Tatacoa has low confidence
        assert "average_confidence" in meta

    def test_events_sorted_by_date(
        self, store: YAMLEventStore, sample_events: list[ExtractedEvent]
    ) -> None:
        """Should save events sorted by date."""
        # Shuffle the events
        shuffled = [sample_events[2], sample_events[0], sample_events[1]]
        store.save_events(shuffled, agency="brutaltravel", year=2026, month="agosto")

        loaded = store.load_events(agency="brutaltravel", year=2026, month="agosto")

        dates = [e.date_start for e in loaded]
        assert dates == sorted(dates)
