"""Tests for price history SQLite service."""

from datetime import date, datetime
from pathlib import Path

import pytest

from aventure_tracker.models.extracted_event import ExtractedEvent
from aventure_tracker.services.price_history import (
    PriceChange,
    PriceHistoryDB,
    PriceRecord,
)


@pytest.fixture
def db(tmp_path: Path) -> PriceHistoryDB:
    """Create a PriceHistoryDB instance with temp database."""
    return PriceHistoryDB(tmp_path / "test_events.db")


@pytest.fixture
def sample_event() -> ExtractedEvent:
    """Create a sample event for testing."""
    return ExtractedEvent(
        name="Cavernas del Nus",
        date_start=date(2026, 8, 1),
        date_end=date(2026, 8, 1),
        price=195000,
        agency="brutaltravel",
        source_image=Path("calendar_01.jpg"),
    )


@pytest.fixture
def multi_day_event() -> ExtractedEvent:
    """Create a multi-day event for testing."""
    return ExtractedEvent(
        name="Tatacoa",
        date_start=date(2026, 8, 21),
        date_end=date(2026, 8, 23),
        price=490000,
        agency="brutaltravel",
    )


class TestPriceRecord:
    """Tests for PriceRecord dataclass."""

    def test_price_formatted(self) -> None:
        """Should format price with Colombian separators."""
        record = PriceRecord(price=195000, recorded_at=datetime.now())
        assert record.price_formatted == "$195.000"

    def test_price_formatted_large(self) -> None:
        """Should format large prices correctly."""
        record = PriceRecord(price=1580000, recorded_at=datetime.now())
        assert record.price_formatted == "$1.580.000"


class TestPriceChange:
    """Tests for PriceChange dataclass."""

    def test_price_increase(self) -> None:
        """Should detect price increase."""
        change = PriceChange(
            event_id="test",
            event_name="Test",
            old_price=100000,
            new_price=120000,
            change_amount=20000,
            change_percent=20.0,
            old_recorded_at=datetime.now(),
            new_recorded_at=datetime.now(),
        )
        assert change.is_increase is True
        assert change.is_decrease is False
        assert change.direction == "up"

    def test_price_decrease(self) -> None:
        """Should detect price decrease."""
        change = PriceChange(
            event_id="test",
            event_name="Test",
            old_price=120000,
            new_price=100000,
            change_amount=-20000,
            change_percent=-16.67,
            old_recorded_at=datetime.now(),
            new_recorded_at=datetime.now(),
        )
        assert change.is_increase is False
        assert change.is_decrease is True
        assert change.direction == "down"

    def test_price_same(self) -> None:
        """Should handle no change."""
        change = PriceChange(
            event_id="test",
            event_name="Test",
            old_price=100000,
            new_price=100000,
            change_amount=0,
            change_percent=0.0,
            old_recorded_at=datetime.now(),
            new_recorded_at=datetime.now(),
        )
        assert change.is_increase is False
        assert change.is_decrease is False
        assert change.direction == "same"


class TestPriceHistoryDB:
    """Tests for PriceHistoryDB class."""

    def test_creates_database(self, tmp_path: Path) -> None:
        """Should create database file."""
        db_path = tmp_path / "subdir" / "events.db"
        PriceHistoryDB(db_path)
        assert db_path.exists()

    def test_upsert_new_event(
        self, db: PriceHistoryDB, sample_event: ExtractedEvent
    ) -> None:
        """Should insert new event and return None (no price change)."""
        change = db.upsert_event(sample_event)

        assert change is None

        # Verify event was stored
        event = db.get_event(sample_event.event_id)
        assert event is not None
        assert event["name"] == "Cavernas del Nus"
        assert event["current_price"] == 195000
        assert event["agency"] == "brutaltravel"

    def test_upsert_records_initial_price(
        self, db: PriceHistoryDB, sample_event: ExtractedEvent
    ) -> None:
        """Should record initial price in history."""
        db.upsert_event(sample_event)

        history = db.get_price_history(sample_event.event_id)
        assert len(history) == 1
        assert history[0].price == 195000

    def test_upsert_detects_price_change(
        self, db: PriceHistoryDB, sample_event: ExtractedEvent
    ) -> None:
        """Should detect and return price change."""
        db.upsert_event(sample_event)

        # Update with new price
        updated_event = ExtractedEvent(
            name=sample_event.name,
            date_start=sample_event.date_start,
            date_end=sample_event.date_end,
            price=220000,  # Price increased
            agency=sample_event.agency,
        )

        change = db.upsert_event(updated_event)

        assert change is not None
        assert change.old_price == 195000
        assert change.new_price == 220000
        assert change.change_amount == 25000
        assert change.is_increase is True

    def test_upsert_no_change_returns_none(
        self, db: PriceHistoryDB, sample_event: ExtractedEvent
    ) -> None:
        """Should return None when price unchanged."""
        db.upsert_event(sample_event)

        # Same price
        change = db.upsert_event(sample_event)

        assert change is None

    def test_upsert_records_price_history(
        self, db: PriceHistoryDB, sample_event: ExtractedEvent
    ) -> None:
        """Should record all price changes in history."""
        db.upsert_event(sample_event)

        # First change
        sample_event.price = 210000
        db.upsert_event(sample_event)

        # Second change
        sample_event.price = 180000
        db.upsert_event(sample_event)

        history = db.get_price_history(sample_event.event_id)
        assert len(history) == 3
        assert history[0].price == 195000  # Initial
        assert history[1].price == 210000  # First change
        assert history[2].price == 180000  # Second change

    def test_upsert_preserves_source_image(
        self, db: PriceHistoryDB, sample_event: ExtractedEvent
    ) -> None:
        """Should store source image in price history."""
        db.upsert_event(sample_event)

        history = db.get_price_history(sample_event.event_id)
        assert history[0].source_image == "calendar_01.jpg"

    def test_upsert_updates_sold_out(
        self, db: PriceHistoryDB, sample_event: ExtractedEvent
    ) -> None:
        """Should update sold_out status."""
        db.upsert_event(sample_event)

        sample_event.sold_out = True
        db.upsert_event(sample_event)

        event = db.get_event(sample_event.event_id)
        assert event["sold_out"] == 1

    def test_get_event_not_found(self, db: PriceHistoryDB) -> None:
        """Should return None for unknown event."""
        event = db.get_event("fake-id")
        assert event is None

    def test_get_price_history_empty(self, db: PriceHistoryDB) -> None:
        """Should return empty list for unknown event."""
        history = db.get_price_history("fake-id")
        assert history == []

    def test_get_events_by_agency(
        self,
        db: PriceHistoryDB,
        sample_event: ExtractedEvent,
        multi_day_event: ExtractedEvent,
    ) -> None:
        """Should get all events for an agency."""
        db.upsert_event(sample_event)
        db.upsert_event(multi_day_event)

        # Add event from different agency
        other_event = ExtractedEvent(
            name="Other Trip",
            date_start=date(2026, 8, 5),
            date_end=date(2026, 8, 5),
            price=100000,
            agency="medellinbungee",
        )
        db.upsert_event(other_event)

        events = db.get_events_by_agency("brutaltravel")
        assert len(events) == 2

        events = db.get_events_by_agency("medellinbungee")
        assert len(events) == 1

    def test_get_events_by_agency_exclude_sold_out(
        self, db: PriceHistoryDB, sample_event: ExtractedEvent
    ) -> None:
        """Should optionally exclude sold out events."""
        db.upsert_event(sample_event)

        sold_out_event = ExtractedEvent(
            name="Sold Out Trip",
            date_start=date(2026, 8, 10),
            date_end=date(2026, 8, 10),
            price=200000,
            agency="brutaltravel",
            sold_out=True,
        )
        db.upsert_event(sold_out_event)

        # Include sold out
        events = db.get_events_by_agency("brutaltravel", include_sold_out=True)
        assert len(events) == 2

        # Exclude sold out
        events = db.get_events_by_agency("brutaltravel", include_sold_out=False)
        assert len(events) == 1
        assert events[0]["name"] == "Cavernas del Nus"

    def test_get_events_by_agency_future_only(self, db: PriceHistoryDB) -> None:
        """Should optionally filter to future events only."""
        # Past event
        past_event = ExtractedEvent(
            name="Past Trip",
            date_start=date(2020, 1, 1),
            date_end=date(2020, 1, 1),
            price=100000,
            agency="brutaltravel",
        )
        db.upsert_event(past_event)

        # Future event
        future_event = ExtractedEvent(
            name="Future Trip",
            date_start=date(2030, 1, 1),
            date_end=date(2030, 1, 1),
            price=200000,
            agency="brutaltravel",
        )
        db.upsert_event(future_event)

        # All events
        events = db.get_events_by_agency("brutaltravel", future_only=False)
        assert len(events) == 2

        # Future only
        events = db.get_events_by_agency("brutaltravel", future_only=True)
        assert len(events) == 1
        assert events[0]["name"] == "Future Trip"

    def test_get_events_sorted_by_date(
        self,
        db: PriceHistoryDB,
        sample_event: ExtractedEvent,
        multi_day_event: ExtractedEvent,
    ) -> None:
        """Should return events sorted by date_start."""
        # Insert in reverse order
        db.upsert_event(multi_day_event)  # Aug 21
        db.upsert_event(sample_event)  # Aug 1

        events = db.get_events_by_agency("brutaltravel")
        dates = [e["date_start"] for e in events]
        assert dates == sorted(dates)

    def test_get_statistics(
        self,
        db: PriceHistoryDB,
        sample_event: ExtractedEvent,
        multi_day_event: ExtractedEvent,
    ) -> None:
        """Should return database statistics."""
        db.upsert_event(sample_event)
        db.upsert_event(multi_day_event)

        # Add sold out event
        sold_out = ExtractedEvent(
            name="Sold Out",
            date_start=date(2026, 8, 5),
            date_end=date(2026, 8, 5),
            price=100000,
            agency="brutaltravel",
            sold_out=True,
        )
        db.upsert_event(sold_out)

        # Add price change to get more history
        sample_event.price = 200000
        db.upsert_event(sample_event)

        stats = db.get_statistics()
        assert stats["total_events"] == 3
        assert stats["sold_out_events"] == 1
        assert stats["available_events"] == 2
        assert stats["price_records"] == 4  # 3 initial + 1 change
        assert "brutaltravel" in stats["agencies"]

    def test_get_statistics_by_agency(
        self, db: PriceHistoryDB, sample_event: ExtractedEvent
    ) -> None:
        """Should filter statistics by agency."""
        db.upsert_event(sample_event)

        other_event = ExtractedEvent(
            name="Other",
            date_start=date(2026, 8, 5),
            date_end=date(2026, 8, 5),
            price=100000,
            agency="medellinbungee",
        )
        db.upsert_event(other_event)

        stats = db.get_statistics(agency="brutaltravel")
        assert stats["total_events"] == 1

    def test_get_recent_price_changes(
        self, db: PriceHistoryDB, sample_event: ExtractedEvent
    ) -> None:
        """Should get recent price changes."""
        db.upsert_event(sample_event)

        # Change price
        sample_event.price = 220000
        db.upsert_event(sample_event)

        changes = db.get_recent_price_changes(days=7)
        assert len(changes) == 1
        assert changes[0].old_price == 195000
        assert changes[0].new_price == 220000

    def test_get_recent_price_changes_by_agency(
        self, db: PriceHistoryDB, sample_event: ExtractedEvent
    ) -> None:
        """Should filter price changes by agency."""
        db.upsert_event(sample_event)
        sample_event.price = 220000
        db.upsert_event(sample_event)

        other_event = ExtractedEvent(
            name="Other",
            date_start=date(2026, 8, 5),
            date_end=date(2026, 8, 5),
            price=100000,
            agency="medellinbungee",
        )
        db.upsert_event(other_event)
        other_event.price = 120000
        db.upsert_event(other_event)

        # All changes
        changes = db.get_recent_price_changes(days=7)
        assert len(changes) == 2

        # Filtered by agency
        changes = db.get_recent_price_changes(days=7, agency="brutaltravel")
        assert len(changes) == 1
        assert changes[0].event_name == "Cavernas del Nus"

    def test_get_recent_price_changes_excludes_initial(
        self, db: PriceHistoryDB, sample_event: ExtractedEvent
    ) -> None:
        """Should not include initial price as a 'change'."""
        db.upsert_event(sample_event)

        changes = db.get_recent_price_changes(days=7)
        assert len(changes) == 0  # No actual changes, just initial insert

    def test_price_change_percent_calculation(
        self, db: PriceHistoryDB, sample_event: ExtractedEvent
    ) -> None:
        """Should calculate correct percentage change."""
        db.upsert_event(sample_event)

        # 20% increase
        sample_event.price = 234000  # 195000 * 1.2 = 234000
        change = db.upsert_event(sample_event)

        assert change is not None
        assert 19.9 <= change.change_percent <= 20.1
