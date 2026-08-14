"""Tests for weekend pairing logic in AdventureOrchestrator."""

import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock

from aventure_tracker.services.flight_tracker import FlightFound, WeekendPair, ReturnOption
from aventure_tracker.main import AdventureOrchestrator


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


def make_event(name: str, date_start: date, date_end: date | None = None, price: int = 150_000):
    ev = MagicMock()
    ev.name = name
    ev.date_start = date_start
    ev.date_end = date_end or date_start
    ev.price = price
    ev.price_formatted = f"${price:,}".replace(",", ".")
    ev.date_label = date_start.strftime("%d %b")
    ev.agency = "brutal"
    return ev


def make_orchestrator() -> AdventureOrchestrator:
    """Create a minimal orchestrator for testing static/helper methods."""
    from aventure_tracker.config import Settings
    orch = AdventureOrchestrator.__new__(AdventureOrchestrator)
    orch._settings = Settings()
    orch._logger = MagicMock()
    orch._notifier = None
    orch._email_notifier = None
    return orch


# ---------------------------------------------------------------------------
# _has_sunday_events tests
# ---------------------------------------------------------------------------

class TestHasSundayEvents:
    """Tests for the Sunday-adventure detection helper."""

    def _sunday(self, week_offset: int = 0) -> date:
        """Return a known Sunday date."""
        return date(2026, 8, 23) + timedelta(weeks=week_offset)  # Aug 23 = Sunday

    def test_event_on_sunday_returns_true(self) -> None:
        sunday = self._sunday()
        events = [make_event("Canyoning", sunday)]
        result = AdventureOrchestrator._has_sunday_events(
            events, sunday - timedelta(days=3), sunday + timedelta(days=1)
        )
        assert result is True

    def test_event_spanning_sunday_returns_true(self) -> None:
        sunday = self._sunday()
        events = [make_event("Tatacoa", sunday - timedelta(days=1), sunday + timedelta(days=1))]
        result = AdventureOrchestrator._has_sunday_events(
            events, sunday - timedelta(days=3), sunday + timedelta(days=1)
        )
        assert result is True

    def test_event_only_saturday_returns_false(self) -> None:
        sunday = self._sunday()
        saturday = sunday - timedelta(days=1)
        events = [make_event("Hike", saturday)]
        result = AdventureOrchestrator._has_sunday_events(
            events, sunday - timedelta(days=3), sunday + timedelta(days=1)
        )
        assert result is False

    def test_no_events_returns_false(self) -> None:
        sunday = self._sunday()
        result = AdventureOrchestrator._has_sunday_events(
            [], sunday - timedelta(days=3), sunday + timedelta(days=1)
        )
        assert result is False

    def test_window_with_no_sunday_returns_false(self) -> None:
        # Window that doesn't include a Sunday (e.g., Mon-Wed)
        monday = date(2026, 8, 24)  # Monday
        events = [make_event("Hike", monday)]
        result = AdventureOrchestrator._has_sunday_events(
            events, monday, monday + timedelta(days=2)
        )
        assert result is False


# ---------------------------------------------------------------------------
# _build_weekend_pairs tests
# ---------------------------------------------------------------------------

class TestBuildWeekendPairs:
    """Tests for the pairing logic."""

    # Base dates for a Thu-Mon window
    THU = date(2026, 8, 20)   # Thursday
    FRI = date(2026, 8, 21)   # Friday
    SUN = date(2026, 8, 23)   # Sunday
    MON = date(2026, 8, 24)   # Monday

    def test_basic_pair_with_return(self) -> None:
        orch = make_orchestrator()
        outbound = [make_flight("BAQ→MDE", self.THU, "18:30", "LATAM", 250_000, True)]
        returns = [make_flight("MDE→BAQ", self.SUN, "16:45", "LATAM", 280_000, True)]

        match = MagicMock()
        match.window_start = self.THU
        match.events = []

        pairs = orch._build_weekend_pairs(outbound, returns, [match])
        assert len(pairs) == 1
        assert pairs[0].outbound == outbound[0]
        assert pairs[0].has_return is True
        assert len(pairs[0].return_options) == 1

    def test_no_return_gives_empty_return_options(self) -> None:
        orch = make_orchestrator()
        outbound = [make_flight("BAQ→MDE", self.THU, "18:30", "LATAM", 250_000, True)]

        match = MagicMock()
        match.window_start = self.THU
        match.events = []

        pairs = orch._build_weekend_pairs(outbound, [], [match])
        assert len(pairs) == 1
        assert pairs[0].has_return is False

    def test_sunday_adventure_filters_sunday_returns(self) -> None:
        orch = make_orchestrator()
        outbound = [make_flight("BAQ→MDE", self.THU, "18:30", "LATAM", 250_000, True)]
        sunday_return = make_flight("MDE→BAQ", self.SUN, "16:45", "LATAM", 280_000, True)
        monday_return = make_flight("MDE→BAQ", self.MON, "07:00", "LATAM", 290_000, True)

        sunday_event = make_event("Canyoning", self.SUN)

        match = MagicMock()
        match.window_start = self.THU
        match.events = [sunday_event]

        pairs = orch._build_weekend_pairs(outbound, [sunday_return, monday_return], [match])
        assert pairs[0].sunday_adventure is True
        # Sunday return must be filtered out
        return_dates = [ro.flight.travel_date for ro in pairs[0].return_options]
        assert self.SUN not in return_dates
        assert self.MON in return_dates

    def test_no_sunday_adventure_allows_sunday_returns(self) -> None:
        orch = make_orchestrator()
        outbound = [make_flight("BAQ→MDE", self.THU)]
        sunday_return = make_flight("MDE→BAQ", self.SUN, "14:00", "LATAM", 280_000, True)
        saturday_event = make_event("Trek", self.FRI)  # Saturday, not Sunday

        match = MagicMock()
        match.window_start = self.THU
        match.events = [saturday_event]

        pairs = orch._build_weekend_pairs(outbound, [sunday_return], [match])
        assert pairs[0].sunday_adventure is False
        return_dates = [ro.flight.travel_date for ro in pairs[0].return_options]
        assert self.SUN in return_dates

    def test_sunday_return_too_early_filtered(self) -> None:
        """Sunday returns before 11AM are filtered when no sunday adventure."""
        orch = make_orchestrator()
        outbound = [make_flight("BAQ→MDE", self.THU)]
        early_return = make_flight("MDE→BAQ", self.SUN, "09:00", "LATAM", 200_000, True)
        late_return = make_flight("MDE→BAQ", self.SUN, "15:00", "LATAM", 250_000, True)

        match = MagicMock()
        match.window_start = self.THU
        match.events = []

        pairs = orch._build_weekend_pairs(outbound, [early_return, late_return], [match])
        times = [ro.flight.departure_time for ro in pairs[0].return_options]
        assert "09:00" not in times
        assert "15:00" in times

    def test_priority_return_preferred_over_slightly_cheaper(self) -> None:
        """Non-priority return only wins if it's ≥100K cheaper than LATAM."""
        orch = make_orchestrator()
        outbound = [make_flight("BAQ→MDE", self.THU, is_priority=True)]
        latam_return = make_flight("MDE→BAQ", self.SUN, "16:45", "LATAM", 280_000, True)
        wingo_return = make_flight("MDE→BAQ", self.SUN, "17:00", "Wingo", 220_000, False)
        # Savings = 280K - 220K = 60K → NOT enough (< 100K) → LATAM preferred

        match = MagicMock()
        match.window_start = self.THU
        match.events = []

        pairs = orch._build_weekend_pairs(outbound, [latam_return, wingo_return], [match])
        assert pairs[0].recommended_return.flight.airline == "LATAM"

    def test_non_priority_wins_when_100k_cheaper(self) -> None:
        """Non-priority return wins if it's ≥100K cheaper than LATAM."""
        orch = make_orchestrator()
        outbound = [make_flight("BAQ→MDE", self.THU, is_priority=True)]
        latam_return = make_flight("MDE→BAQ", self.SUN, "16:45", "LATAM", 280_000, True)
        wingo_return = make_flight("MDE→BAQ", self.SUN, "17:00", "Wingo", 170_000, False)
        # Savings = 280K - 170K = 110K → enough → Wingo recommended

        match = MagicMock()
        match.window_start = self.THU
        match.events = []

        pairs = orch._build_weekend_pairs(outbound, [latam_return, wingo_return], [match])
        assert pairs[0].recommended_return.flight.airline == "Wingo"

    def test_top_3_return_options(self) -> None:
        """At most 3 return options are shown."""
        orch = make_orchestrator()
        outbound = [make_flight("BAQ→MDE", self.THU)]
        returns = [
            make_flight("MDE→BAQ", self.SUN, "14:00", "Wingo", 200_000, False),
            make_flight("MDE→BAQ", self.SUN, "15:00", "JetSMART", 210_000, False),
            make_flight("MDE→BAQ", self.SUN, "16:45", "LATAM", 280_000, True),
            make_flight("MDE→BAQ", self.MON, "07:00", "Avianca", 220_000, False),
        ]

        match = MagicMock()
        match.window_start = self.THU
        match.events = []

        pairs = orch._build_weekend_pairs(outbound, returns, [match])
        assert len(pairs[0].return_options) <= 3

    def test_first_return_option_is_recommended(self) -> None:
        orch = make_orchestrator()
        outbound = [make_flight("BAQ→MDE", self.THU)]
        returns = [make_flight("MDE→BAQ", self.SUN, "16:45", "LATAM", 280_000, True)]

        match = MagicMock()
        match.window_start = self.THU
        match.events = []

        pairs = orch._build_weekend_pairs(outbound, returns, [match])
        assert pairs[0].return_options[0].is_recommended is True

    def test_total_price_is_outbound_plus_recommended_return(self) -> None:
        orch = make_orchestrator()
        outbound = [make_flight("BAQ→MDE", self.THU, price=250_000)]
        returns = [make_flight("MDE→BAQ", self.SUN, price=280_000)]

        match = MagicMock()
        match.window_start = self.THU
        match.events = []

        pairs = orch._build_weekend_pairs(outbound, returns, [match])
        assert pairs[0].total_price == 530_000
