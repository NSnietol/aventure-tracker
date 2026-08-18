"""Tests for flight price store."""

from datetime import date, datetime
from pathlib import Path

import yaml

from aventure_tracker.services.flights.price_store import (
    FlightPriceStore,
    PriceRecord,
)


class TestPriceRecord:
    """Tests for PriceRecord."""

    def test_create_record(self) -> None:
        """Should create a price record."""
        now = datetime.now()
        record = PriceRecord(price=150000, checked_at=now)

        assert record.price == 150000
        assert record.checked_at == now

    def test_to_dict(self) -> None:
        """Should convert to dict."""
        now = datetime.now()
        record = PriceRecord(price=150000, checked_at=now)
        data = record.to_dict()

        assert data["price"] == 150000
        assert data["checked_at"] == now.isoformat()

    def test_from_dict(self) -> None:
        """Should create from dict."""
        now = datetime.now()
        data = {"price": 150000, "checked_at": now.isoformat()}
        record = PriceRecord.from_dict(data)

        assert record.price == 150000
        assert record.checked_at.date() == now.date()


class TestFlightPriceStore:
    """Tests for FlightPriceStore."""

    def test_init_creates_empty_store(self, tmp_path: Path) -> None:
        """Should initialize with empty flights store."""
        store = FlightPriceStore(path=tmp_path / "prices.yaml")
        assert len(store.get_all_flights()) == 0

    def test_set_and_get_flight_price(self, tmp_path: Path) -> None:
        """Should set and retrieve flight price."""
        store = FlightPriceStore(path=tmp_path / "prices.yaml")
        store.set_flight_price("BAQ-MDE", date(2026, 8, 15), "18:30", "LATAM", 150000)

        result = store.get_flight("BAQ-MDE", date(2026, 8, 15), "18:30", "LATAM")
        assert result is not None
        assert result.latest_price == 150000

    def test_save_and_load(self, tmp_path: Path) -> None:
        """Should persist and reload flight data."""
        path = tmp_path / "prices.yaml"

        store1 = FlightPriceStore(path=path)
        store1.set_flight_price("BAQ-MDE", date(2026, 8, 15), "18:30", "LATAM", 150000)
        store1.set_flight_price(
            "CTG-MDE", date(2026, 8, 22), "09:00", "Avianca", 180000
        )
        store1.save()

        store2 = FlightPriceStore(path=path)
        r1 = store2.get_flight("BAQ-MDE", date(2026, 8, 15), "18:30", "LATAM")
        r2 = store2.get_flight("CTG-MDE", date(2026, 8, 22), "09:00", "Avianca")
        assert r1 is not None and r1.latest_price == 150000
        assert r2 is not None and r2.latest_price == 180000

    def test_get_lowest_prices(self, tmp_path: Path) -> None:
        """Should get lowest prices per route."""
        store = FlightPriceStore(path=tmp_path / "prices.yaml")
        store.set_flight_price("BAQ-MDE", date(2026, 8, 15), "08:00", "LATAM", 150000)
        store.set_flight_price("BAQ-MDE", date(2026, 8, 22), "10:00", "LATAM", 120000)
        store.set_flight_price("CTG-MDE", date(2026, 8, 15), "09:00", "Avianca", 180000)

        lowest = store.get_lowest_prices()
        assert lowest["BAQ-MDE"] == 120000
        assert lowest["CTG-MDE"] == 180000

    def test_cleanup_old_dates(self, tmp_path: Path) -> None:
        """Should remove flights with past travel dates."""
        store = FlightPriceStore(path=tmp_path / "prices.yaml")
        store.set_flight_price("BAQ-MDE", date(2026, 7, 1), "18:30", "LATAM", 150000)
        store.set_flight_price("BAQ-MDE", date(2026, 8, 15), "18:30", "LATAM", 160000)

        removed = store.cleanup_old_dates(before=date(2026, 8, 1))
        assert removed == 1
        assert len(store.get_all_flights()) == 1

    def test_nonexistent_flight_returns_none(self, tmp_path: Path) -> None:
        """Should return None for unknown flight."""
        store = FlightPriceStore(path=tmp_path / "prices.yaml")
        assert store.get_flight("XXX-YYY", date(2026, 8, 15), "08:00", "LATAM") is None

    def test_yaml_format(self, tmp_path: Path) -> None:
        """Should save flights section in YAML."""
        path = tmp_path / "prices.yaml"
        store = FlightPriceStore(path=path)
        store.set_flight_price("BAQ-MDE", date(2026, 8, 15), "18:30", "LATAM", 150000)
        store.save()

        with open(path) as f:
            data = yaml.safe_load(f)

        assert "updated_at" in data
        assert "flights" in data
