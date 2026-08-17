"""Event matcher: correlates cheap flight dates with agency events from cache.

Reads the extraction_cache.yaml (events already extracted from agency calendar
images via Gemini/Ollama) and matches them against weekend windows where
cheap flights were found. Filters out blacklisted destinations.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from aventure_tracker.models.activity import DestinationsConfig

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = Path("data/extraction_cache.yaml")
DEFAULT_DESTINATIONS_PATH = Path("config/destinations.yaml")


@dataclass
class MatchedEvent:
    """An event matched to a cheap flight weekend.

    Attributes:
        name: Event name.
        agency: Agency name.
        date_start: Start date.
        date_end: End date.
        price: Price in COP.
        sold_out: Whether event is sold out.
    """

    name: str
    agency: str
    date_start: date
    date_end: date
    price: int
    sold_out: bool = False

    @property
    def price_formatted(self) -> str:
        """Price formatted as $XXX.XXX."""
        return f"${self.price:,}".replace(",", ".")

    @property
    def date_label(self) -> str:
        """Human readable date range."""
        if self.date_start == self.date_end:
            return self.date_start.strftime("%d %b")
        return f"{self.date_start.strftime('%d')}-{self.date_end.strftime('%d %b')}"


@dataclass
class WeekendMatch:
    """All events found for a specific weekend window.

    Attributes:
        window_start: First day of the window (e.g., Thursday).
        window_end: Last day of the window (e.g., Monday).
        events: Events available during this window, sorted by price.
    """

    window_start: date
    window_end: date
    events: list[MatchedEvent] = field(default_factory=list)

    @property
    def has_events(self) -> bool:
        """Whether any events were found."""
        return len(self.events) > 0

    @property
    def date_label(self) -> str:
        """Human readable window label."""
        return (
            f"{self.window_start.strftime('%d')}-{self.window_end.strftime('%d %b %Y')}"
        )


class EventMatcher:
    """Matches cheap flight dates to available agency events.

    Reads events from the extraction cache (events already extracted from
    agency calendar images via Gemini/Ollama) and correlates them with
    weekend windows where cheap flights were found.
    Filters out blacklisted destinations.
    """

    def __init__(
        self,
        cache_path: Path | None = None,
        destinations_path: Path | None = None,
    ) -> None:
        """Initialize the matcher.

        Args:
            cache_path: Path to extraction_cache.yaml.
            destinations_path: Path to destinations.yaml (blacklist).
        """
        self._cache_path = cache_path or DEFAULT_CACHE_PATH
        self._destinations_path = destinations_path or DEFAULT_DESTINATIONS_PATH
        self._all_events: list[MatchedEvent] = []
        self._destinations: DestinationsConfig | None = None

    def load(self) -> None:
        """Load events from cache and blacklist from destinations."""
        self._load_events()
        self._load_blacklist()

    def _load_events(self) -> None:
        """Load all events from the extraction cache."""
        if not self._cache_path.exists():
            logger.warning(f"Extraction cache not found: {self._cache_path}")
            self._all_events = []
            return

        with open(self._cache_path, encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}

        self._all_events = []
        for entry in data.get("entries", {}).values():
            if entry.get("is_cover", False):
                continue
            for ev in entry.get("events_data", []):
                try:
                    self._all_events.append(
                        MatchedEvent(
                            name=ev["name"],
                            agency=ev.get("agency", "unknown"),
                            date_start=date.fromisoformat(ev["date_start"]),
                            date_end=date.fromisoformat(ev["date_end"]),
                            price=int(ev["price"]),
                            sold_out=bool(ev.get("sold_out", False)),
                        )
                    )
                except (KeyError, ValueError) as e:
                    logger.debug(f"Skipping malformed event entry: {e}")

        logger.info(f"Loaded {len(self._all_events)} events from extraction cache")

    def _load_blacklist(self) -> None:
        """Load blacklist from destinations config."""
        if self._destinations_path.exists():
            self._destinations = DestinationsConfig.from_yaml(self._destinations_path)
            count = len(self._destinations.get_all_blacklisted())
            logger.info(f"Loaded {count} blacklisted destinations")
        else:
            self._destinations = DestinationsConfig(blacklist={})

    def _is_blacklisted(self, event_name: str) -> bool:
        """Check if an event name matches the blacklist."""
        if self._destinations is None:
            return False
        is_blocked, _, _ = self._destinations.is_blacklisted(event_name)
        return is_blocked

    def find_events_for_dates(
        self,
        cheap_dates: list[date],
    ) -> list[WeekendMatch]:
        """Find events available during cheap flight weekends.

        Groups cheap flight dates into weekend windows (Thu→Mon) and finds
        all non-blacklisted, non-sold-out events that fall within each window.

        Args:
            cheap_dates: List of dates where cheap flights were found.

        Returns:
            List of WeekendMatch, one per unique weekend window.
        """
        if not cheap_dates:
            return []

        if not self._all_events:
            logger.warning("No events in cache — run extract_events.py first")
            return []

        windows = self._group_into_windows(cheap_dates)
        results: list[WeekendMatch] = []

        for window_start, window_end in windows:
            matched_events: list[MatchedEvent] = []

            for event in self._all_events:
                if event.sold_out:
                    continue
                if self._is_blacklisted(event.name):
                    logger.debug(f"Skipping blacklisted: {event.name}")
                    continue
                # Event overlaps with this window
                if event.date_start <= window_end and event.date_end >= window_start:
                    matched_events.append(event)

            # Sort by price ascending
            matched_events.sort(key=lambda e: e.price)

            results.append(
                WeekendMatch(
                    window_start=window_start,
                    window_end=window_end,
                    events=matched_events,
                )
            )

        return results

    def _group_into_windows(
        self,
        dates: list[date],
    ) -> list[tuple[date, date]]:
        """Group individual travel dates into weekend windows (Thu→Mon).

        Args:
            dates: List of travel dates (may be any day of the week).

        Returns:
            Deduplicated list of (window_start, window_end) tuples.
        """
        if not dates:
            return []

        sorted_dates = sorted(set(dates))
        windows: list[tuple[date, date]] = []
        seen: set[date] = set()

        for d in sorted_dates:
            if d in seen:
                continue
            window_start = d
            window_end = d + timedelta(days=4)
            windows.append((window_start, window_end))
            current = window_start
            while current <= window_end:
                seen.add(current)
                current += timedelta(days=1)

        return windows
