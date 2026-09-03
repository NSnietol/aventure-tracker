"""Tests for weekend pairing logic."""

from datetime import date, timedelta
from unittest.mock import MagicMock

from aventure_tracker.services.flights.tracker import FlightFound
from aventure_tracker.services.flights.weekend_pairs import (
    build_weekend_pairs,
    has_sunday_events,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_flight(
    route: str,
    travel_date: date,
    departure_time: str = "18:30",
    airline: str = "LATAM",
    price: int = 250_000,
    is_priority: bool = True,
) -> FlightFound:
    return FlightFound(
        flight_id=f"{route}_{travel_date}_{departure_time}_{airline}",
        route=route,
        travel_date=travel_date,
        departure_time=departure_time,
        airline=airline,
        price=price,
        is_priority=is_priority,
    )


def make_event(
    name: str, date_start: date, date_end: date | None = None, price: int = 150_000
):
    ev = MagicMock()
    ev.name = name
    ev.date_start = date_start
    ev.date_end = date_end or date_start
    ev.price = price
    ev.price_formatted = f"${price:,}".replace(",", ".")
    ev.date_label = date_start.strftime("%d %b")
    ev.agency = "brutal"
    return ev


def make_match(window_start: date, events: list):
    m = MagicMock()
    m.window_start = window_start
    m.events = events
    return m


# ---------------------------------------------------------------------------
# has_sunday_events tests
# ---------------------------------------------------------------------------


class TestHasSundayEvents:
    """Tests for the Sunday-adventure detection helper."""

    def _sunday(self, week_offset: int = 0) -> date:
        return date(2026, 8, 23) + timedelta(weeks=week_offset)  # Aug 23 = Sunday

    def test_event_on_sunday_returns_true(self) -> None:
        sunday = self._sunday()
        events = [make_event("Canyoning", sunday)]
        result = has_sunday_events(
            events, sunday - timedelta(days=3), sunday + timedelta(days=1)
        )
        assert result is True

    def test_event_spanning_sunday_returns_true(self) -> None:
        sunday = self._sunday()
        events = [
            make_event(
                "Tatacoa", sunday - timedelta(days=1), sunday + timedelta(days=1)
            )
        ]
        result = has_sunday_events(
            events, sunday - timedelta(days=3), sunday + timedelta(days=1)
        )
        assert result is True

    def test_event_only_saturday_returns_false(self) -> None:
        sunday = self._sunday()
        saturday = sunday - timedelta(days=1)
        events = [make_event("Hike", saturday)]
        result = has_sunday_events(
            events, sunday - timedelta(days=3), sunday + timedelta(days=1)
        )
        assert result is False

    def test_no_events_returns_false(self) -> None:
        sunday = self._sunday()
        result = has_sunday_events(
            [], sunday - timedelta(days=3), sunday + timedelta(days=1)
        )
        assert result is False

    def test_window_with_no_sunday_returns_false(self) -> None:
        monday = date(2026, 8, 24)  # Monday — no Sunday in Mon-Wed window
        events = [make_event("Hike", monday)]
        result = has_sunday_events(events, monday, monday + timedelta(days=2))
        assert result is False


# ---------------------------------------------------------------------------
# build_weekend_pairs tests
# ---------------------------------------------------------------------------


class TestBuildWeekendPairs:
    """Tests for the pairing logic."""

    THU = date(2026, 8, 20)
    FRI = date(2026, 8, 21)
    SUN = date(2026, 8, 23)
    MON = date(2026, 8, 24)

    def test_basic_pair_with_return(self) -> None:
        outbound = [make_flight("BAQ→MDE", self.THU, "18:30", "LATAM", 250_000, True)]
        returns = [make_flight("MDE→BAQ", self.SUN, "16:45", "LATAM", 280_000, True)]
        pairs = build_weekend_pairs(outbound, returns, [make_match(self.THU, [])])
        assert len(pairs) == 1
        assert pairs[0].outbound == outbound[0]
        assert pairs[0].has_return is True
        assert len(pairs[0].return_options) == 1

    def test_no_return_gives_empty_return_options(self) -> None:
        outbound = [make_flight("BAQ→MDE", self.THU, "18:30", "LATAM", 250_000, True)]
        pairs = build_weekend_pairs(outbound, [], [make_match(self.THU, [])])
        assert len(pairs) == 1
        assert pairs[0].has_return is False

    def test_sunday_adventure_filters_sunday_returns(self) -> None:
        outbound = [make_flight("BAQ→MDE", self.THU, "18:30", "LATAM", 250_000, True)]
        sunday_return = make_flight(
            "MDE→BAQ", self.SUN, "16:45", "LATAM", 280_000, True
        )
        monday_return = make_flight(
            "MDE→BAQ", self.MON, "07:00", "LATAM", 290_000, True
        )
        sunday_event = make_event("Canyoning", self.SUN)
        pairs = build_weekend_pairs(
            outbound,
            [sunday_return, monday_return],
            [make_match(self.THU, [sunday_event])],
        )
        assert pairs[0].sunday_adventure is True
        return_dates = [ro.flight.travel_date for ro in pairs[0].return_options]
        assert self.SUN not in return_dates
        assert self.MON in return_dates

    def test_no_sunday_adventure_allows_sunday_returns(self) -> None:
        outbound = [make_flight("BAQ→MDE", self.THU)]
        sunday_return = make_flight(
            "MDE→BAQ", self.SUN, "14:00", "LATAM", 280_000, True
        )
        saturday_event = make_event("Trek", self.FRI)
        pairs = build_weekend_pairs(
            outbound, [sunday_return], [make_match(self.THU, [saturday_event])]
        )
        assert pairs[0].sunday_adventure is False
        return_dates = [ro.flight.travel_date for ro in pairs[0].return_options]
        assert self.SUN in return_dates

    def test_sunday_return_too_early_filtered(self) -> None:
        outbound = [make_flight("BAQ→MDE", self.THU)]
        early_return = make_flight("MDE→BAQ", self.SUN, "09:00", "LATAM", 200_000, True)
        late_return = make_flight("MDE→BAQ", self.SUN, "15:00", "LATAM", 250_000, True)
        pairs = build_weekend_pairs(
            outbound, [early_return, late_return], [make_match(self.THU, [])]
        )
        times = [ro.flight.departure_time for ro in pairs[0].return_options]
        assert "09:00" not in times
        assert "15:00" in times

    def test_priority_return_preferred_over_slightly_cheaper(self) -> None:
        outbound = [make_flight("BAQ→MDE", self.THU, is_priority=True)]
        latam_return = make_flight("MDE→BAQ", self.SUN, "16:45", "LATAM", 280_000, True)
        wingo_return = make_flight(
            "MDE→BAQ", self.SUN, "17:00", "Wingo", 220_000, False
        )
        # Savings 60K < 100K → LATAM preferred
        pairs = build_weekend_pairs(
            outbound, [latam_return, wingo_return], [make_match(self.THU, [])]
        )
        assert pairs[0].recommended_return.flight.airline == "LATAM"

    def test_non_priority_wins_when_100k_cheaper(self) -> None:
        outbound = [make_flight("BAQ→MDE", self.THU, is_priority=True)]
        latam_return = make_flight("MDE→BAQ", self.SUN, "16:45", "LATAM", 280_000, True)
        wingo_return = make_flight(
            "MDE→BAQ", self.SUN, "17:00", "Wingo", 170_000, False
        )
        # Savings 110K ≥ 100K → Wingo recommended
        pairs = build_weekend_pairs(
            outbound, [latam_return, wingo_return], [make_match(self.THU, [])]
        )
        assert pairs[0].recommended_return.flight.airline == "Wingo"

    def test_top_3_return_options(self) -> None:
        outbound = [make_flight("BAQ→MDE", self.THU)]
        returns = [
            make_flight("MDE→BAQ", self.SUN, "14:00", "Wingo", 200_000, False),
            make_flight("MDE→BAQ", self.SUN, "15:00", "JetSMART", 210_000, False),
            make_flight("MDE→BAQ", self.SUN, "16:45", "LATAM", 280_000, True),
            make_flight("MDE→BAQ", self.MON, "07:00", "Avianca", 220_000, False),
        ]
        pairs = build_weekend_pairs(outbound, returns, [make_match(self.THU, [])])
        assert len(pairs[0].return_options) <= 3

    def test_first_return_option_is_recommended(self) -> None:
        outbound = [make_flight("BAQ→MDE", self.THU)]
        returns = [make_flight("MDE→BAQ", self.SUN, "16:45", "LATAM", 280_000, True)]
        pairs = build_weekend_pairs(outbound, returns, [make_match(self.THU, [])])
        assert pairs[0].return_options[0].is_recommended is True

    def test_total_price_is_outbound_plus_recommended_return(self) -> None:
        outbound = [make_flight("BAQ→MDE", self.THU, price=250_000)]
        returns = [make_flight("MDE→BAQ", self.SUN, price=280_000)]
        pairs = build_weekend_pairs(outbound, returns, [make_match(self.THU, [])])
        assert pairs[0].total_price == 530_000
