"""SQLite price history service for tracking event price changes over time.

Stores events and their price history to enable analysis of price trends
and changes across multiple extraction runs.
"""

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from aventure_tracker.models.extracted_event import ExtractedEvent


@dataclass
class PriceRecord:
    """A single price record in the history.

    Attributes:
        price: Price in COP.
        recorded_at: When this price was recorded.
        source_image: Source image filename (optional).
    """

    price: int
    recorded_at: datetime
    source_image: str | None = None

    @property
    def price_formatted(self) -> str:
        """Get price formatted with Colombian separators."""
        return f"${self.price:,}".replace(",", ".")


@dataclass
class PriceChange:
    """Represents a price change between two records.

    Attributes:
        event_id: Event identifier.
        event_name: Event name.
        old_price: Previous price.
        new_price: New price.
        change_amount: Absolute change (new - old).
        change_percent: Percentage change.
        old_recorded_at: When old price was recorded.
        new_recorded_at: When new price was recorded.
    """

    event_id: str
    event_name: str
    old_price: int
    new_price: int
    change_amount: int
    change_percent: float
    old_recorded_at: datetime
    new_recorded_at: datetime

    @property
    def is_increase(self) -> bool:
        """Check if price increased."""
        return self.change_amount > 0

    @property
    def is_decrease(self) -> bool:
        """Check if price decreased."""
        return self.change_amount < 0

    @property
    def direction(self) -> str:
        """Get direction indicator."""
        if self.is_increase:
            return "up"
        elif self.is_decrease:
            return "down"
        return "same"


class PriceHistoryDB:
    """SQLite database for storing event price history."""

    def __init__(self, db_path: Path):
        """Initialize the price history database.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    agency TEXT NOT NULL,
                    date_start TEXT NOT NULL,
                    date_end TEXT NOT NULL,
                    current_price INTEGER NOT NULL,
                    sold_out INTEGER DEFAULT 0,
                    first_seen_at TEXT NOT NULL,
                    last_updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    recorded_at TEXT NOT NULL,
                    source_image TEXT,
                    FOREIGN KEY (event_id) REFERENCES events(event_id)
                );

                CREATE INDEX IF NOT EXISTS idx_price_history_event
                    ON price_history(event_id);
                CREATE INDEX IF NOT EXISTS idx_price_history_date
                    ON price_history(recorded_at);
                CREATE INDEX IF NOT EXISTS idx_events_agency
                    ON events(agency);
                CREATE INDEX IF NOT EXISTS idx_events_date
                    ON events(date_start);
            """)

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def upsert_event(self, event: ExtractedEvent) -> PriceChange | None:
        """Insert or update an event, recording price if changed.

        Args:
            event: Event to upsert.

        Returns:
            PriceChange if price changed, None otherwise.
        """
        now = datetime.now().isoformat()
        source_image = str(event.source_image.name) if event.source_image else None

        with self._get_connection() as conn:
            # Check if event exists
            existing = conn.execute(
                "SELECT event_id, name, current_price, last_updated_at FROM events WHERE event_id = ?",
                (event.event_id,),
            ).fetchone()

            if existing is None:
                # Insert new event
                conn.execute(
                    """
                    INSERT INTO events
                    (event_id, name, agency, date_start, date_end, current_price,
                     sold_out, first_seen_at, last_updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.name,
                        event.agency,
                        event.date_start.isoformat(),
                        event.date_end.isoformat(),
                        event.price,
                        1 if event.sold_out else 0,
                        now,
                        now,
                    ),
                )

                # Record initial price
                conn.execute(
                    """
                    INSERT INTO price_history (event_id, price, recorded_at, source_image)
                    VALUES (?, ?, ?, ?)
                    """,
                    (event.event_id, event.price, now, source_image),
                )

                return None  # No price change for new events

            # Event exists - check for price change
            old_price = existing["current_price"]
            price_changed = old_price != event.price

            # Update event
            conn.execute(
                """
                UPDATE events
                SET name = ?, current_price = ?, sold_out = ?, last_updated_at = ?
                WHERE event_id = ?
                """,
                (
                    event.name,
                    event.price,
                    1 if event.sold_out else 0,
                    now,
                    event.event_id,
                ),
            )

            if price_changed:
                # Record new price in history
                conn.execute(
                    """
                    INSERT INTO price_history (event_id, price, recorded_at, source_image)
                    VALUES (?, ?, ?, ?)
                    """,
                    (event.event_id, event.price, now, source_image),
                )

                # Calculate change
                change_amount = event.price - old_price
                change_percent = (
                    (change_amount / old_price) * 100 if old_price > 0 else 0
                )

                return PriceChange(
                    event_id=event.event_id,
                    event_name=event.name,
                    old_price=old_price,
                    new_price=event.price,
                    change_amount=change_amount,
                    change_percent=change_percent,
                    old_recorded_at=datetime.fromisoformat(existing["last_updated_at"]),
                    new_recorded_at=datetime.fromisoformat(now),
                )

            return None

    def get_price_history(self, event_id: str) -> list[PriceRecord]:
        """Get price history for an event.

        Args:
            event_id: Event identifier.

        Returns:
            List of PriceRecord sorted by date (oldest first).
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT price, recorded_at, source_image
                FROM price_history
                WHERE event_id = ?
                ORDER BY recorded_at ASC
                """,
                (event_id,),
            ).fetchall()

        return [
            PriceRecord(
                price=row["price"],
                recorded_at=datetime.fromisoformat(row["recorded_at"]),
                source_image=row["source_image"],
            )
            for row in rows
        ]

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        """Get event details by ID.

        Args:
            event_id: Event identifier.

        Returns:
            Event data dict or None if not found.
        """
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM events WHERE event_id = ?",
                (event_id,),
            ).fetchone()

        if row is None:
            return None

        return dict(row)

    def get_events_by_agency(
        self,
        agency: str,
        include_sold_out: bool = True,
        future_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Get all events for an agency.

        Args:
            agency: Agency name.
            include_sold_out: Whether to include sold out events.
            future_only: Only include events with date_start >= today.

        Returns:
            List of event data dicts.
        """
        query = "SELECT * FROM events WHERE agency = ?"
        params: list[Any] = [agency]

        if not include_sold_out:
            query += " AND sold_out = 0"

        if future_only:
            today = date.today().isoformat()
            query += " AND date_start >= ?"
            params.append(today)

        query += " ORDER BY date_start ASC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [dict(row) for row in rows]

    def get_recent_price_changes(
        self,
        days: int = 7,
        agency: str | None = None,
    ) -> list[PriceChange]:
        """Get price changes from the last N days.

        Args:
            days: Number of days to look back.
            agency: Optional agency filter.

        Returns:
            List of PriceChange records.
        """
        cutoff = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = cutoff - timedelta(days=days)

        query = """
            SELECT
                ph1.event_id,
                e.name as event_name,
                ph1.price as new_price,
                ph1.recorded_at as new_recorded_at,
                (
                    SELECT price FROM price_history ph2
                    WHERE ph2.event_id = ph1.event_id
                    AND ph2.recorded_at < ph1.recorded_at
                    ORDER BY ph2.recorded_at DESC
                    LIMIT 1
                ) as old_price,
                (
                    SELECT recorded_at FROM price_history ph2
                    WHERE ph2.event_id = ph1.event_id
                    AND ph2.recorded_at < ph1.recorded_at
                    ORDER BY ph2.recorded_at DESC
                    LIMIT 1
                ) as old_recorded_at
            FROM price_history ph1
            JOIN events e ON e.event_id = ph1.event_id
            WHERE ph1.recorded_at >= ?
        """
        params: list[Any] = [cutoff.isoformat()]

        if agency:
            query += " AND e.agency = ?"
            params.append(agency)

        query += " ORDER BY ph1.recorded_at DESC"

        changes: list[PriceChange] = []

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        for row in rows:
            if row["old_price"] is None:
                continue  # Skip first records (no previous price)

            old_price = row["old_price"]
            new_price = row["new_price"]
            change_amount = new_price - old_price

            if change_amount == 0:
                continue  # Skip if no actual change

            change_percent = (change_amount / old_price) * 100 if old_price > 0 else 0

            changes.append(
                PriceChange(
                    event_id=row["event_id"],
                    event_name=row["event_name"],
                    old_price=old_price,
                    new_price=new_price,
                    change_amount=change_amount,
                    change_percent=change_percent,
                    old_recorded_at=datetime.fromisoformat(row["old_recorded_at"]),
                    new_recorded_at=datetime.fromisoformat(row["new_recorded_at"]),
                )
            )

        return changes

    def get_statistics(self, agency: str | None = None) -> dict[str, Any]:
        """Get database statistics.

        Args:
            agency: Optional agency filter.

        Returns:
            Dict with counts and statistics.
        """
        with self._get_connection() as conn:
            if agency:
                events_count = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE agency = ?", (agency,)
                ).fetchone()[0]
                sold_out_count = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE agency = ? AND sold_out = 1",
                    (agency,),
                ).fetchone()[0]
                price_records = conn.execute(
                    """
                    SELECT COUNT(*) FROM price_history ph
                    JOIN events e ON e.event_id = ph.event_id
                    WHERE e.agency = ?
                    """,
                    (agency,),
                ).fetchone()[0]
            else:
                events_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
                sold_out_count = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE sold_out = 1"
                ).fetchone()[0]
                price_records = conn.execute(
                    "SELECT COUNT(*) FROM price_history"
                ).fetchone()[0]

            agencies = conn.execute("SELECT DISTINCT agency FROM events").fetchall()

        return {
            "total_events": events_count,
            "sold_out_events": sold_out_count,
            "available_events": events_count - sold_out_count,
            "price_records": price_records,
            "agencies": [row["agency"] for row in agencies],
        }

    def close(self) -> None:
        """Close database connections (no-op for sqlite3 with context manager)."""
        pass
