"""Tests for flight price store."""

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from aventure_tracker.services.flight_price_store import (
    FlightPriceStore,
    PriceRecord,
    RouteHistory,
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


class TestRouteHistory:
    """Tests for RouteHistory."""

    def test_create_history(self) -> None:
        """Should create route history."""
        history = RouteHistory(
            route="BAQ-MDE",
            travel_date=date(2026, 8, 15),
            records=[],
        )

        assert history.route == "BAQ-MDE"
        assert history.travel_date == date(2026, 8, 15)

    def test_latest_price(self) -> None:
        """Should return latest price."""
        history = RouteHistory(
            route="BAQ-MDE",
            travel_date=date(2026, 8, 15),
            records=[
                PriceRecord(price=200000, checked_at=datetime.now() - timedelta(days=1)),
                PriceRecord(price=150000, checked_at=datetime.now()),
            ],
        )

        assert history.latest_price == 150000

    def test_previous_price(self) -> None:
        """Should return previous price."""
        history = RouteHistory(
            route="BAQ-MDE",
            travel_date=date(2026, 8, 15),
            records=[
                PriceRecord(price=200000, checked_at=datetime.now() - timedelta(days=1)),
                PriceRecord(price=150000, checked_at=datetime.now()),
            ],
        )

        assert history.previous_price == 200000

    def test_lowest_price(self) -> None:
        """Should return lowest price."""
        history = RouteHistory(
            route="BAQ-MDE",
            travel_date=date(2026, 8, 15),
            records=[
                PriceRecord(price=200000, checked_at=datetime.now() - timedelta(days=2)),
                PriceRecord(price=120000, checked_at=datetime.now() - timedelta(days=1)),
                PriceRecord(price=150000, checked_at=datetime.now()),
            ],
        )

        assert history.lowest_price == 120000

    def test_price_change(self) -> None:
        """Should calculate price change."""
        history = RouteHistory(
            route="BAQ-MDE",
            travel_date=date(2026, 8, 15),
            records=[
                PriceRecord(price=200000, checked_at=datetime.now() - timedelta(days=1)),
                PriceRecord(price=150000, checked_at=datetime.now()),
            ],
        )

        assert history.price_change == -50000

    def test_add_price(self) -> None:
        """Should add new price record."""
        history = RouteHistory(
            route="BAQ-MDE",
            travel_date=date(2026, 8, 15),
            records=[],
        )

        history.add_price(150000)

        assert len(history.records) == 1
        assert history.latest_price == 150000


class TestFlightPriceStore:
    """Tests for FlightPriceStore."""

    def test_init_creates_empty_store(self, tmp_path: Path) -> None:
        """Should initialize with empty store."""
        store = FlightPriceStore(path=tmp_path / "prices.yaml")

        assert len(store.get_all_routes()) == 0

    def test_set_and_get_price(self, tmp_path: Path) -> None:
        """Should set and get prices."""
        store = FlightPriceStore(path=tmp_path / "prices.yaml")

        store.set_price("BAQ-MDE", date(2026, 8, 15), 150000)

        assert store.get_price("BAQ-MDE", date(2026, 8, 15)) == 150000

    def test_get_previous_price(self, tmp_path: Path) -> None:
        """Should get previous price."""
        store = FlightPriceStore(path=tmp_path / "prices.yaml")

        store.set_price("BAQ-MDE", date(2026, 8, 15), 200000)
        store.set_price("BAQ-MDE", date(2026, 8, 15), 150000)

        assert store.get_previous_price("BAQ-MDE", date(2026, 8, 15)) == 200000

    def test_save_and_load(self, tmp_path: Path) -> None:
        """Should persist and load data."""
        path = tmp_path / "prices.yaml"

        # Save
        store1 = FlightPriceStore(path=path)
        store1.set_price("BAQ-MDE", date(2026, 8, 15), 150000)
        store1.set_price("CTG-MDE", date(2026, 8, 22), 180000)
        store1.save()

        # Load
        store2 = FlightPriceStore(path=path)

        assert store2.get_price("BAQ-MDE", date(2026, 8, 15)) == 150000
        assert store2.get_price("CTG-MDE", date(2026, 8, 22)) == 180000

    def test_get_history(self, tmp_path: Path) -> None:
        """Should get full history."""
        store = FlightPriceStore(path=tmp_path / "prices.yaml")

        store.set_price("BAQ-MDE", date(2026, 8, 15), 200000)
        store.set_price("BAQ-MDE", date(2026, 8, 15), 180000)
        store.set_price("BAQ-MDE", date(2026, 8, 15), 150000)

        history = store.get_history("BAQ-MDE", date(2026, 8, 15))

        assert history is not None
        assert len(history.records) == 3
        assert history.lowest_price == 150000

    def test_get_all_routes(self, tmp_path: Path) -> None:
        """Should get all tracked routes."""
        store = FlightPriceStore(path=tmp_path / "prices.yaml")

        store.set_price("BAQ-MDE", date(2026, 8, 15), 150000)
        store.set_price("CTG-MDE", date(2026, 8, 15), 180000)
        store.set_price("BAQ-MDE", date(2026, 8, 22), 160000)

        routes = store.get_all_routes()

        assert len(routes) == 3

    def test_get_routes_for_date(self, tmp_path: Path) -> None:
        """Should get routes for specific date."""
        store = FlightPriceStore(path=tmp_path / "prices.yaml")

        store.set_price("BAQ-MDE", date(2026, 8, 15), 150000)
        store.set_price("CTG-MDE", date(2026, 8, 15), 180000)
        store.set_price("BAQ-MDE", date(2026, 8, 22), 160000)

        routes = store.get_routes_for_date(date(2026, 8, 15))

        assert len(routes) == 2

    def test_get_lowest_prices(self, tmp_path: Path) -> None:
        """Should get lowest prices per route."""
        store = FlightPriceStore(path=tmp_path / "prices.yaml")

        store.set_price("BAQ-MDE", date(2026, 8, 15), 150000)
        store.set_price("BAQ-MDE", date(2026, 8, 22), 120000)
        store.set_price("CTG-MDE", date(2026, 8, 15), 180000)

        lowest = store.get_lowest_prices()

        assert lowest["BAQ-MDE"] == 120000
        assert lowest["CTG-MDE"] == 180000

    def test_cleanup_old_dates(self, tmp_path: Path) -> None:
        """Should remove old entries."""
        store = FlightPriceStore(path=tmp_path / "prices.yaml")

        store.set_price("BAQ-MDE", date(2026, 7, 1), 150000)  # Old
        store.set_price("BAQ-MDE", date(2026, 8, 15), 160000)  # Current

        removed = store.cleanup_old_dates(before=date(2026, 8, 1))

        assert removed == 1
        assert len(store.get_all_routes()) == 1

    def test_nonexistent_route(self, tmp_path: Path) -> None:
        """Should return None for nonexistent route."""
        store = FlightPriceStore(path=tmp_path / "prices.yaml")

        assert store.get_price("XXX-YYY", date(2026, 8, 15)) is None
        assert store.get_previous_price("XXX-YYY", date(2026, 8, 15)) is None
        assert store.get_history("XXX-YYY", date(2026, 8, 15)) is None

    def test_yaml_format(self, tmp_path: Path) -> None:
        """Should save in readable YAML format."""
        path = tmp_path / "prices.yaml"
        store = FlightPriceStore(path=path)

        store.set_price("BAQ-MDE", date(2026, 8, 15), 150000)
        store.save()

        # Verify YAML structure
        with open(path) as f:
            data = yaml.safe_load(f)

        assert "updated_at" in data
        assert "routes" in data
        assert "BAQ-MDE_2026-08-15" in data["routes"]
