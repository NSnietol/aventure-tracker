"""Flight calendar display for visualizing prices across routes and dates.

Displays a console-based ASCII table showing flight prices for multiple
routes over the next 10 weeks, with indicators for:
- Price drops (down arrow)
- Price increases (up arrow)
- Target prices (bullseye)
- Bridge weekends (bridge emoji)
"""

import logging
from dataclasses import dataclass
from datetime import date

from aventure_tracker.models.flight import RouteConfig, WeekendTrip
from aventure_tracker.services.flights.dates import FlightDateCalculator

logger = logging.getLogger(__name__)

# Calendar display constants
DEFAULT_WEEKS = 10
PRICE_WIDTH = 9  # Width for price column (e.g., "$123,456")
DATE_WIDTH = 12  # Width for date column (e.g., "Ene 15 (V)")

# Indicators for price status
INDICATOR_DOWN = "↓"  # Price dropped
INDICATOR_UP = "↑"  # Price increased
INDICATOR_TARGET = "●"  # At or below target
INDICATOR_BRIDGE = "☆"  # Bridge weekend


@dataclass
class PriceCell:
    """A cell in the price calendar.

    Attributes:
        price: Flight price in COP, or None if not available.
        previous_price: Previous tracked price, or None.
        is_below_threshold: Whether price is at/below target.
        is_bridge: Whether this is a bridge weekend.
    """

    price: int | None
    previous_price: int | None = None
    is_below_threshold: bool = False
    is_bridge: bool = False

    @property
    def price_change(self) -> int | None:
        """Calculate price change from previous."""
        if self.price is None or self.previous_price is None:
            return None
        return self.price - self.previous_price

    @property
    def indicator(self) -> str:
        """Get the status indicator for this cell."""
        indicators = []

        if self.is_below_threshold and self.price is not None:
            indicators.append(INDICATOR_TARGET)

        change = self.price_change
        if change is not None:
            if change < 0:
                indicators.append(INDICATOR_DOWN)
            elif change > 0:
                indicators.append(INDICATOR_UP)

        if self.is_bridge:
            indicators.append(INDICATOR_BRIDGE)

        return "".join(indicators)

    def format_price(self) -> str:
        """Format the price with indicator."""
        if self.price is None:
            return "-"

        # Format price in thousands (e.g., 150k for 150,000)
        if self.price >= 1000:
            price_str = f"${self.price // 1000}k"
        else:
            price_str = f"${self.price}"

        indicator = self.indicator
        if indicator:
            return f"{price_str}{indicator}"
        return price_str


@dataclass
class CalendarData:
    """Data structure for the flight calendar.

    Attributes:
        routes: List of routes (columns).
        dates: List of travel dates (rows).
        prices: 2D dict mapping (date, route_key) -> PriceCell.
        bridge_dates: Set of dates that are bridge weekends.
    """

    routes: list[RouteConfig]
    dates: list[date]
    prices: dict[tuple[date, str], PriceCell]
    bridge_dates: set[date]

    def get_cell(self, travel_date: date, route: RouteConfig) -> PriceCell:
        """Get the price cell for a date and route."""
        key = (travel_date, str(route))
        return self.prices.get(key, PriceCell(price=None))


class FlightCalendarDisplay:
    """Display flight prices in a calendar format.

    Creates an ASCII table showing prices for each route (column)
    across multiple travel dates (rows) for the next N weeks.

    Example output:
    ```
    ════════════════════════════════════════════════════════
                 FLIGHT CALENDAR (10 weeks)
    ════════════════════════════════════════════════════════
    Date         │ BAQ→MDE   │ BAQ→BOG   │ MDE→SMR
    ─────────────┼───────────┼───────────┼───────────
    Ene 17 (V)   │ $89k●     │ $120k     │ $95k↓
    Ene 24 (V)   │ $105k     │ $118k↓    │ $110k
    Ene 31 (V)☆  │ $150k     │ $140k     │ $125k●
    Feb 07 (V)   │ $98k↓     │ -         │ $115k
    ...
    ═══════════════════════════════════════════════════════

    Legend: ● at/below target │ ↓ price drop │ ↑ price up │ ☆ puente
    ```
    """

    # Spanish month abbreviations
    MONTHS = [
        "Ene",
        "Feb",
        "Mar",
        "Abr",
        "May",
        "Jun",
        "Jul",
        "Ago",
        "Sep",
        "Oct",
        "Nov",
        "Dic",
    ]

    # Spanish day abbreviations
    DAYS = ["L", "M", "X", "J", "V", "S", "D"]

    def __init__(
        self,
        date_calculator: FlightDateCalculator | None = None,
        weeks_ahead: int = DEFAULT_WEEKS,
    ) -> None:
        """Initialize the calendar display.

        Args:
            date_calculator: FlightDateCalculator for getting dates.
            weeks_ahead: Number of weeks to display.
        """
        self._date_calculator = date_calculator
        self._weeks_ahead = weeks_ahead

    def _get_date_calculator(self) -> FlightDateCalculator:
        """Get or create the date calculator."""
        if self._date_calculator is None:
            from aventure_tracker.services.shared.holidays import HolidayService

            holiday_service = HolidayService()
            self._date_calculator = FlightDateCalculator(
                holiday_service=holiday_service
            )
        return self._date_calculator

    def _format_date(self, d: date, is_bridge: bool = False) -> str:
        """Format a date for display.

        Args:
            d: Date to format.
            is_bridge: Whether this is a bridge weekend.

        Returns:
            Formatted string like "Ene 17 (V)" or "Ene 31 (V)☆".
        """
        month = self.MONTHS[d.month - 1]
        day_of_week = self.DAYS[d.weekday()]
        base = f"{month} {d.day:2d} ({day_of_week})"
        if is_bridge:
            return f"{base}{INDICATOR_BRIDGE}"
        return base

    def get_travel_dates(self) -> list[WeekendTrip]:
        """Get the list of travel dates for the calendar.

        Returns:
            List of WeekendTrip objects for upcoming weekends.
        """
        calculator = self._get_date_calculator()
        return calculator.get_upcoming_weekends(weeks_ahead=self._weeks_ahead)

    def build_calendar_data(
        self,
        routes: list[RouteConfig],
        prices: dict[tuple[date, str], int],
        previous_prices: dict[tuple[date, str], int] | None = None,
    ) -> CalendarData:
        """Build the calendar data structure.

        Args:
            routes: List of routes to include.
            prices: Dict mapping (date, route_str) -> price.
            previous_prices: Optional dict of previous prices for comparison.

        Returns:
            CalendarData ready for display.
        """
        weekends = self.get_travel_dates()
        dates = [w.outbound_date for w in weekends]
        bridge_dates = {w.outbound_date for w in weekends if w.is_bridge}

        cells: dict[tuple[date, str], PriceCell] = {}

        for travel_date in dates:
            is_bridge = travel_date in bridge_dates

            for route in routes:
                route_key = str(route)
                key = (travel_date, route_key)

                price = prices.get(key)
                prev_price = previous_prices.get(key) if previous_prices else None

                is_below = price is not None and price <= route.price_threshold

                cells[key] = PriceCell(
                    price=price,
                    previous_price=prev_price,
                    is_below_threshold=is_below,
                    is_bridge=is_bridge,
                )

        return CalendarData(
            routes=routes,
            dates=dates,
            prices=cells,
            bridge_dates=bridge_dates,
        )

    def render(self, data: CalendarData) -> str:
        """Render the calendar as an ASCII table.

        Args:
            data: CalendarData to render.

        Returns:
            Multi-line string with the formatted calendar.
        """
        lines: list[str] = []

        # Calculate column widths
        route_headers = [str(r) for r in data.routes]
        route_widths = [max(len(h), PRICE_WIDTH) for h in route_headers]

        # Total width calculation
        total_width = DATE_WIDTH + sum(w + 3 for w in route_widths) + 1

        # Title
        lines.append("═" * total_width)
        title = f"FLIGHT CALENDAR ({self._weeks_ahead} weeks)"
        lines.append(title.center(total_width))
        lines.append("═" * total_width)

        # Header row
        header_parts = [f"{'Date':<{DATE_WIDTH}}"]
        for i, route_header in enumerate(route_headers):
            header_parts.append(f"{route_header:^{route_widths[i]}}")
        lines.append(" │ ".join(header_parts))

        # Separator
        sep_parts = ["─" * DATE_WIDTH]
        for w in route_widths:
            sep_parts.append("─" * w)
        lines.append("─┼─".join(sep_parts))

        # Data rows
        for travel_date in data.dates:
            is_bridge = travel_date in data.bridge_dates
            date_str = self._format_date(travel_date, is_bridge)

            row_parts = [f"{date_str:<{DATE_WIDTH}}"]
            for i, route in enumerate(data.routes):
                cell = data.get_cell(travel_date, route)
                price_str = cell.format_price()
                row_parts.append(f"{price_str:^{route_widths[i]}}")

            lines.append(" │ ".join(row_parts))

        # Bottom border
        lines.append("═" * total_width)

        # Legend
        legend = (
            f"Legend: {INDICATOR_TARGET} at/below target │ "
            f"{INDICATOR_DOWN} price drop │ "
            f"{INDICATOR_UP} price up │ "
            f"{INDICATOR_BRIDGE} puente"
        )
        lines.append(legend)

        return "\n".join(lines)

    def display(self, data: CalendarData) -> None:
        """Print the calendar to stdout.

        Args:
            data: CalendarData to display.
        """
        print(self.render(data))

    def render_summary(self, data: CalendarData) -> str:
        """Render a summary of notable prices.

        Args:
            data: CalendarData to summarize.

        Returns:
            Multi-line string with notable prices.
        """
        lines: list[str] = []
        lines.append("\n📊 Price Summary:")
        lines.append("─" * 40)

        # Find best prices per route
        for route in data.routes:
            best_price: int | None = None
            best_date: date | None = None

            for travel_date in data.dates:
                cell = data.get_cell(travel_date, route)
                if cell.price is not None:
                    if best_price is None or cell.price < best_price:
                        best_price = cell.price
                        best_date = travel_date

            if best_price is not None and best_date is not None:
                date_str = self._format_date(best_date)
                threshold_note = ""
                if best_price <= route.price_threshold:
                    threshold_note = (
                        f" {INDICATOR_TARGET} (at/below ${route.price_threshold:,})"
                    )
                lines.append(
                    f"  {route}: Best ${best_price:,} on {date_str}{threshold_note}"
                )
            else:
                lines.append(f"  {route}: No prices available")

        # Count alerts
        target_count = sum(
            1
            for cell in data.prices.values()
            if cell.is_below_threshold and cell.price is not None
        )
        drop_count = sum(
            1
            for cell in data.prices.values()
            if cell.price_change is not None and cell.price_change < 0
        )
        bridge_count = len(data.bridge_dates)

        lines.append("─" * 40)
        lines.append(f"  {INDICATOR_TARGET} Prices at/below target: {target_count}")
        lines.append(f"  {INDICATOR_DOWN} Price drops: {drop_count}")
        lines.append(f"  {INDICATOR_BRIDGE} Bridge weekends: {bridge_count}")

        return "\n".join(lines)
