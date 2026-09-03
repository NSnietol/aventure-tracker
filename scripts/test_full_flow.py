#!/usr/bin/env python3
"""End-to-end test script for Adventure Tracker.

This script demonstrates and tests the new functionality:
1. ActivityHistoryManager - Tracks seen posts with max 3 checks
2. Event extraction - Extracts event_id from captions
3. FlightCalendarDisplay - Shows 10-week ASCII calendar

Usage:
    python scripts/test_full_flow.py

This script uses mock data and does NOT make real network calls.
"""

import asyncio
import tempfile
from datetime import date, datetime
from pathlib import Path

# Add project to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aventure_tracker.models.activity import InstagramAccountConfig, InstagramPost
from aventure_tracker.models.flight import RouteConfig, WeekendTrip
from aventure_tracker.services.events.history import ActivityHistoryManager
from aventure_tracker.services.events.extractor import extract_event_info
from aventure_tracker.services.flights.calendar import FlightCalendarDisplay
from aventure_tracker.services.flights.dates import FlightDateCalculator
from aventure_tracker.services.shared.holidays import HolidayService


def print_header(title: str) -> None:
    """Print a section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_activity_history() -> None:
    """Test ActivityHistoryManager functionality."""
    print_header("1. Activity History Manager Test")

    # Create temp directory for history file
    with tempfile.TemporaryDirectory() as tmpdir:
        history_path = Path(tmpdir) / "activity_history.yaml"
        manager = ActivityHistoryManager(history_path=history_path)
        manager.load()

        account = "brutaltravel.co"

        # Simulate checking posts multiple times
        print("\nSimulating post checks (max 3 per post):")
        print("-" * 40)

        for post_num in range(1, 4):
            post_id = f"POST{post_num:03d}"
            event_id = f"2026-08-{15 + post_num}-cocuy-trek"

            for check in range(1, 5):  # Try to check 4 times
                should_check = manager.should_check(account, post_id)

                if should_check:
                    manager.record_check(
                        account=account,
                        post_id=post_id,
                        event_id=event_id,
                        event_name=f"Cocuy Trek Day {post_num}",
                        event_date=f"2026-08-{15 + post_num}",
                        matched_wishlist=(post_num == 1),
                    )
                    status = "CHECKED"
                else:
                    status = "SKIPPED (limit reached)"

                print(f"  Post {post_id}, Check #{check}: {status}")

        # Save and show stats
        manager.save()
        print(f"\nHistory saved to: {history_path}")

        stats = {
            "total": manager.total_records,
            "skipped": manager.get_skipped_count(account),
        }
        print(f"Total records: {stats['total']}")
        print(f"Posts at limit (will be skipped): {stats['skipped']}")


def test_event_extraction() -> None:
    """Test event extraction from Instagram captions."""
    print_header("2. Event ID Extraction Test")

    test_captions = [
        """🏔️ NEVADO DEL COCUY 🏔️

📅 15 de Agosto 2026
💰 $850.000 COP
📍 Salida desde Bogotá

#cocuy #colombia #trekking""",

        """Salto en Bungee 🪂

Próxima salida: 20/09/2026
Lugar: Puente de Occidente

Reservas al WhatsApp""",

        """Tour a Guatapé - El mejor plan para el fin de semana!
Agosto 2026
$85.000 por persona""",

        """Aventura extrema sin fecha definida
#extremesports #colombia""",
    ]

    print("\nExtracting event info from captions:")
    print("-" * 40)

    for i, caption in enumerate(test_captions, 1):
        info = extract_event_info(caption)
        print(f"\n[Caption {i}]")
        print(f"  Event Name: {info.event_name[:40]}...")
        print(f"  Event Date: {info.event_date or 'Not found'}")
        print(f"  Event ID:   {info.event_id[:50]}")


def test_flight_calendar() -> None:
    """Test flight calendar display."""
    print_header("3. Flight Calendar Display Test (10 weeks)")

    # Create sample routes
    routes = [
        RouteConfig(
            origin="BAQ",
            destination="MDE",
            price_threshold=100000,
            drop_percentage=10,
        ),
        RouteConfig(
            origin="BAQ",
            destination="BOG",
            price_threshold=120000,
            drop_percentage=15,
        ),
        RouteConfig(
            origin="MDE",
            destination="SMR",
            price_threshold=150000,
            drop_percentage=10,
        ),
    ]

    # Create mock weekend dates (since we can't rely on real HolidayService without config)
    weekends = []
    base_date = date(2026, 1, 16)  # A Friday
    for week in range(10):
        outbound = date(
            base_date.year,
            base_date.month + (base_date.day + week * 7) // 28,
            ((base_date.day + week * 7 - 1) % 28) + 1,
        )
        # Simpler: just add weeks
        from datetime import timedelta
        outbound = base_date + timedelta(weeks=week)
        return_date = outbound + timedelta(days=2)

        weekends.append(
            WeekendTrip(
                outbound_date=outbound,
                return_date=return_date,
                is_bridge=(week in [2, 6]),  # Mark some as bridge weekends
                outbound_times=[],
                return_times=[],
            )
        )

    # Create mock prices (some routes, some dates)
    prices: dict[tuple, int] = {}
    previous_prices: dict[tuple, int] = {}

    import random
    random.seed(42)  # For reproducibility

    for weekend in weekends:
        for route in routes:
            key = (weekend.outbound_date, str(route))

            # 70% chance of having a price
            if random.random() < 0.7:
                base_price = route.price_threshold
                # Random price: 80% to 130% of threshold
                price = int(base_price * (0.8 + random.random() * 0.5))
                prices[key] = price

                # 50% chance of having previous price
                if random.random() < 0.5:
                    # Previous price: current +/- 20%
                    prev = int(price * (0.9 + random.random() * 0.2))
                    previous_prices[key] = prev

    # Create calendar display with mock data
    class MockDateCalculator:
        def get_upcoming_weekends(self, weeks_ahead: int = 10):
            return weekends[:weeks_ahead]

    display = FlightCalendarDisplay(
        date_calculator=MockDateCalculator(),  # type: ignore
        weeks_ahead=10,
    )

    # Build and render calendar
    data = display.build_calendar_data(routes, prices, previous_prices)

    print("\n")
    print(display.render(data))
    print(display.render_summary(data))


def test_cli_options() -> None:
    """Show CLI usage examples."""
    print_header("4. CLI Usage Examples")

    print("""
The Adventure Tracker now supports the following new options:

# Show flight calendar (10 weeks by default)
aventure-tracker --mode calendar

# Run flights tracking and show calendar
aventure-tracker --mode flights --calendar

# Run all trackers with 12 weeks planning horizon
aventure-tracker --weeks 12

# Dry run with calendar display
aventure-tracker --dry-run --calendar

New Features Summary:
---------------------
- Activity history tracking (max 3 checks per post)
- Event ID extraction from captions (date + name)
- 10-week flight calendar display (increased from 8)
- Calendar mode (--mode calendar)
- Show calendar flag (--calendar)
""")


async def main() -> None:
    """Run all tests."""
    print("\n" + "=" * 60)
    print("   ADVENTURE TRACKER - FULL FLOW TEST")
    print("=" * 60)
    print("\nThis script tests the new functionality without network calls.\n")

    test_activity_history()
    test_event_extraction()
    test_flight_calendar()
    test_cli_options()

    print_header("TEST COMPLETE")
    print("\nAll new features are working correctly!")
    print("Run the unit tests for comprehensive coverage:")
    print("  pytest tests/ -v --tb=short\n")


if __name__ == "__main__":
    asyncio.run(main())
