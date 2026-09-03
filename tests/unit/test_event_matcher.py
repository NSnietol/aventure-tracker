"""Tests for EventMatcher service."""

from datetime import date
from pathlib import Path

import pytest

from aventure_tracker.services.flights.matcher import (
    EventMatcher,
    MatchedEvent,
    WeekendMatch,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CACHE_YAML = """
version: 1
entries:
  hash_cover:
    image_hash: hash_cover
    agency: brutal
    month: agosto
    year: 2026
    events_count: 0
    is_cover: true
    processed_at: '2026-08-01T00:00:00'
    source_path: inbox/brutal/cover.png
    events_data: []

  hash_a:
    image_hash: hash_a
    agency: brutal
    month: agosto
    year: 2026
    events_count: 3
    is_cover: false
    processed_at: '2026-08-01T00:00:00'
    source_path: inbox/brutal/a.png
    events_data:
      - name: Canyoning San Carlos
        date_start: '2026-08-23'
        date_end: '2026-08-23'
        price: 180000
        agency: brutal
        sold_out: false
      - name: Tatacoa
        date_start: '2026-08-21'
        date_end: '2026-08-23'
        price: 490000
        agency: brutal
        sold_out: false
      - name: Salto del Indio
        date_start: '2026-08-23'
        date_end: '2026-08-23'
        price: 140000
        agency: brutal
        sold_out: false

  hash_b:
    image_hash: hash_b
    agency: brutal
    month: septiembre
    year: 2026
    events_count: 2
    is_cover: false
    processed_at: '2026-08-01T00:00:00'
    source_path: inbox/brutal/b.png
    events_data:
      - name: Río Claro
        date_start: '2026-09-20'
        date_end: '2026-09-20'
        price: 200000
        agency: brutal
        sold_out: false
      - name: Sold Out Event
        date_start: '2026-08-23'
        date_end: '2026-08-23'
        price: 100000
        agency: brutal
        sold_out: true
"""

DESTINATIONS_YAML = """
blacklist:
  ya_fue:
    - Tatacoa
  playa:
    - Rincón del Mar
"""


@pytest.fixture
def cache_file(tmp_path: Path) -> Path:
    """Write sample cache YAML to a temp file."""
    p = tmp_path / "extraction_cache.yaml"
    p.write_text(CACHE_YAML, encoding="utf-8")
    return p


@pytest.fixture
def destinations_file(tmp_path: Path) -> Path:
    """Write sample destinations YAML to a temp file."""
    p = tmp_path / "destinations.yaml"
    p.write_text(DESTINATIONS_YAML, encoding="utf-8")
    return p


@pytest.fixture
def matcher(cache_file: Path, destinations_file: Path, tmp_path: Path) -> EventMatcher:
    """EventMatcher loaded with test data (no manual events)."""
    m = EventMatcher(
        cache_path=cache_file,
        destinations_path=destinations_file,
        manual_events_path=tmp_path / "no_manual.yaml",
    )
    m.load()
    return m


# ---------------------------------------------------------------------------
# MatchedEvent tests
# ---------------------------------------------------------------------------


class TestMatchedEvent:
    """Tests for MatchedEvent dataclass."""

    def test_price_formatted_single_day(self) -> None:
        ev = MatchedEvent(
            name="Test",
            agency="brutal",
            date_start=date(2026, 8, 23),
            date_end=date(2026, 8, 23),
            price=140000,
        )
        assert ev.price_formatted == "$140.000"

    def test_date_label_single_day(self) -> None:
        ev = MatchedEvent(
            name="Test",
            agency="brutal",
            date_start=date(2026, 8, 23),
            date_end=date(2026, 8, 23),
            price=140000,
        )
        assert "23" in ev.date_label

    def test_date_label_multi_day(self) -> None:
        ev = MatchedEvent(
            name="Test",
            agency="brutal",
            date_start=date(2026, 8, 21),
            date_end=date(2026, 8, 23),
            price=490000,
        )
        assert "21" in ev.date_label
        assert "23" in ev.date_label


# ---------------------------------------------------------------------------
# WeekendMatch tests
# ---------------------------------------------------------------------------


class TestWeekendMatch:
    """Tests for WeekendMatch dataclass."""

    def test_has_events_true(self) -> None:
        ev = MatchedEvent("X", "brutal", date(2026, 8, 23), date(2026, 8, 23), 100000)
        wm = WeekendMatch(date(2026, 8, 21), date(2026, 8, 25), events=[ev])
        assert wm.has_events is True

    def test_has_events_false(self) -> None:
        wm = WeekendMatch(date(2026, 8, 21), date(2026, 8, 25))
        assert wm.has_events is False

    def test_date_label(self) -> None:
        wm = WeekendMatch(date(2026, 8, 21), date(2026, 8, 25))
        assert "21" in wm.date_label
        assert "25" in wm.date_label


# ---------------------------------------------------------------------------
# EventMatcher.load() tests
# ---------------------------------------------------------------------------


class TestEventMatcherLoad:
    """Tests for loading events from cache."""

    def test_loads_events_skips_covers(self, matcher: EventMatcher) -> None:
        # cover entry has is_cover=true → should be skipped
        # hash_a has 3 events, hash_b has 2 events (1 sold_out still loaded)
        assert len(matcher._all_events) == 5

    def test_missing_cache_loads_empty(self, tmp_path: Path) -> None:
        m = EventMatcher(
            cache_path=tmp_path / "nonexistent.yaml",
            manual_events_path=tmp_path / "no_manual.yaml",
        )
        m.load()
        assert m._all_events is not None  # no crash
        assert len(m._all_events) == 0

    def test_missing_destinations_loads_empty_blacklist(
        self, cache_file: Path, tmp_path: Path
    ) -> None:
        m = EventMatcher(
            cache_path=cache_file,
            destinations_path=tmp_path / "nonexistent.yaml",
            manual_events_path=tmp_path / "no_manual.yaml",
        )
        m.load()
        # No crash, no blacklist
        assert m._destinations is not None
        assert len(m._destinations.get_all_blacklisted()) == 0


# ---------------------------------------------------------------------------
# Manual events tests
# ---------------------------------------------------------------------------


class TestManualEvents:
    """Tests for manual_events.yaml loading."""

    def test_loads_manual_events(self, tmp_path: Path) -> None:
        manual = tmp_path / "manual_events.yaml"
        manual.write_text(
            "events:\n"
            "  - name: Reencuentro Grupo Peru\n"
            "    agency: personal\n"
            "    date_start: '2026-10-23'\n"
            "    date_end: '2026-10-26'\n"
            "    price: 0\n"
        )
        m = EventMatcher(
            cache_path=tmp_path / "no_cache.yaml",
            manual_events_path=manual,
        )
        m.load()
        assert len(m._all_events) == 1
        ev = m._all_events[0]
        assert ev.name == "Reencuentro Grupo Peru"
        assert ev.is_manual is True
        assert ev.agency == "personal"
        assert ev.price == 0

    def test_manual_event_matched_to_window(self, tmp_path: Path) -> None:
        manual = tmp_path / "manual_events.yaml"
        manual.write_text(
            "events:\n"
            "  - name: Reencuentro Grupo Peru\n"
            "    agency: personal\n"
            "    date_start: '2026-10-23'\n"
            "    date_end: '2026-10-26'\n"
            "    price: 0\n"
        )
        m = EventMatcher(
            cache_path=tmp_path / "no_cache.yaml",
            manual_events_path=manual,
        )
        m.load()
        # Outbound Thu Oct 22 → window Oct 22–26 → overlaps manual event Oct 23-26
        results = m.find_events_for_dates([date(2026, 10, 22)])
        assert len(results) == 1
        assert len(results[0].events) == 1
        assert results[0].events[0].name == "Reencuentro Grupo Peru"
        assert results[0].events[0].is_manual is True

    def test_missing_manual_file_no_crash(self, tmp_path: Path) -> None:
        m = EventMatcher(
            cache_path=tmp_path / "no_cache.yaml",
            manual_events_path=tmp_path / "nonexistent.yaml",
        )
        m.load()  # must not raise
        assert m._all_events == []

    def test_price_zero_shows_dash_label(self) -> None:
        ev = MatchedEvent(
            name="Test",
            agency="personal",
            date_start=date(2026, 10, 23),
            date_end=date(2026, 10, 26),
            price=0,
            is_manual=True,
        )
        assert ev.price_formatted == "$0"
        assert ev.is_manual is True


# ---------------------------------------------------------------------------
# EventMatcher.find_events_for_dates() tests
# ---------------------------------------------------------------------------


class TestFindEventsForDates:
    """Tests for matching cheap dates to events."""

    def test_no_dates_returns_empty(self, matcher: EventMatcher) -> None:
        result = matcher.find_events_for_dates([])
        assert result == []

    def test_finds_events_in_window(self, matcher: EventMatcher) -> None:
        # Aug 23 is in our test data (Canyoning, Salto del Indio)
        result = matcher.find_events_for_dates([date(2026, 8, 23)])
        assert len(result) == 1
        match = result[0]
        assert match.has_events

    def test_blacklisted_events_excluded(self, matcher: EventMatcher) -> None:
        # Tatacoa is blacklisted (ya_fue)
        result = matcher.find_events_for_dates([date(2026, 8, 21)])
        assert len(result) == 1
        names = [e.name for e in result[0].events]
        assert "Tatacoa" not in names

    def test_sold_out_events_excluded(self, matcher: EventMatcher) -> None:
        # "Sold Out Event" on Aug 23 has sold_out=true
        result = matcher.find_events_for_dates([date(2026, 8, 23)])
        names = [e.name for e in result[0].events]
        assert "Sold Out Event" not in names

    def test_events_sorted_by_price(self, matcher: EventMatcher) -> None:
        result = matcher.find_events_for_dates([date(2026, 8, 23)])
        events = result[0].events
        prices = [e.price for e in events]
        assert prices == sorted(prices)

    def test_window_spans_four_days(self, matcher: EventMatcher) -> None:
        result = matcher.find_events_for_dates([date(2026, 8, 21)])
        match = result[0]
        assert (match.window_end - match.window_start).days == 4

    def test_two_separate_weekends_give_two_windows(
        self, matcher: EventMatcher
    ) -> None:
        # Aug 21 and Sep 20 are far apart → two separate windows
        result = matcher.find_events_for_dates([date(2026, 8, 21), date(2026, 9, 20)])
        assert len(result) == 2

    def test_adjacent_dates_merged_into_one_window(self, matcher: EventMatcher) -> None:
        # Aug 21, 22, 23 — each creates its own window (no merging)
        # Each cheap flight date gets its own window so all pairs are represented
        result = matcher.find_events_for_dates(
            [date(2026, 8, 21), date(2026, 8, 22), date(2026, 8, 23)]
        )
        assert len(result) == 3

    def test_no_events_in_window_returns_empty_match(
        self, matcher: EventMatcher
    ) -> None:
        # Jan 1 has no events in test data
        result = matcher.find_events_for_dates([date(2026, 1, 1)])
        assert len(result) == 1
        assert result[0].has_events is False

    def test_no_events_loaded_returns_empty(
        self, tmp_path: Path, destinations_file: Path
    ) -> None:
        # Cache with only covers → no events
        empty_cache = tmp_path / "empty.yaml"
        empty_cache.write_text(
            "version: 1\nentries:\n  h: {image_hash: h, agency: x, month: ago, "
            "year: 2026, events_count: 0, is_cover: true, "
            "processed_at: '2026-01-01T00:00:00', source_path: x, events_data: []}\n"
        )
        m = EventMatcher(
            cache_path=empty_cache,
            destinations_path=destinations_file,
            manual_events_path=tmp_path / "no_manual.yaml",
        )
        m.load()
        result = m.find_events_for_dates([date(2026, 8, 23)])
        assert result == []


# ---------------------------------------------------------------------------
# EventMatcher._group_into_windows() tests
# ---------------------------------------------------------------------------


class TestGroupIntoWindows:
    """Tests for internal window grouping logic."""

    def test_empty_input(self, matcher: EventMatcher) -> None:
        assert matcher._group_into_windows([]) == []

    def test_single_date(self, matcher: EventMatcher) -> None:
        windows = matcher._group_into_windows([date(2026, 8, 21)])
        assert len(windows) == 1
        start, end = windows[0]
        assert end == start + __import__("datetime").timedelta(days=4)

    def test_duplicate_dates_deduplicated(self, matcher: EventMatcher) -> None:
        windows = matcher._group_into_windows(
            [date(2026, 8, 21), date(2026, 8, 21), date(2026, 8, 21)]
        )
        assert len(windows) == 1

    def test_dates_within_same_window_merged(self, matcher: EventMatcher) -> None:
        # Aug 21, 23, 25 — each creates its own window (no merging of overlapping windows)
        # New behavior: each unique date is its own window_start
        windows = matcher._group_into_windows(
            [date(2026, 8, 21), date(2026, 8, 23), date(2026, 8, 25)]
        )
        assert len(windows) == 3

    def test_dates_far_apart_create_separate_windows(
        self, matcher: EventMatcher
    ) -> None:
        windows = matcher._group_into_windows([date(2026, 8, 21), date(2026, 9, 5)])
        assert len(windows) == 2
