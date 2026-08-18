"""Weekend pair building logic — groups cheap flights with events per weekend window."""

import logging
from datetime import date, timedelta
from datetime import time as dtime

from aventure_tracker.services.flights.tracker import ReturnOption, WeekendPair

logger = logging.getLogger(__name__)

# How many COP cheaper a non-priority airline must be to override LATAM preference
_LATAM_SAVING_THRESHOLD = 100_000


def has_sunday_events(
    events: list,
    window_start: date,
    window_end: date,
) -> bool:
    """Check whether any events fall on a Sunday within the weekend window.

    When True, return flights must be Monday (the adventurer is busy all day
    Sunday and can't fly back that evening).

    Args:
        events: List of MatchedEvent for this window.
        window_start: First day of the window.
        window_end: Last day of the window.

    Returns:
        True if any event starts or spans a Sunday in this window.
    """
    sundays: set[date] = set()
    current = window_start
    while current <= window_end:
        if current.weekday() == 6:  # Sunday
            sundays.add(current)
        current += timedelta(days=1)

    if not sundays:
        return False

    for ev in events:
        for sunday in sundays:
            if ev.date_start <= sunday <= ev.date_end:
                return True
    return False


def build_weekend_pairs(
    outbound_all: list,
    return_all: list,
    weekend_matches: list,
) -> list[WeekendPair]:
    """Build one WeekendPair per cheap outbound flight.

    Return-day selection rules (in priority order):
    1. If events fall on Sunday (sunday_adventure=True):
           → return must be Monday. Sunday returns are blocked.
           → if adventure ends Monday in MDE, Tuesday return is also valid.
    2. If adventure is Saturday-only (no Sunday events):
           → Sunday return ≥ 11:00 is allowed.
           → Monday return is also valid.
    3. Priority airline (LATAM) outbound → prefer same for return unless
       another airline is ≥100K cheaper.
    4. Show top 3 return options sorted by price.
    5. If no return found → still include pair (has_return=False).

    Window covers outbound_date through outbound_date + 5 days (Tue)
    to capture both Monday and Tuesday return flights.

    Args:
        outbound_all: All cheap outbound flights sorted by date.
        return_all: All tracked return flights sorted by date.
        weekend_matches: WeekendMatch objects with events per window.

    Returns:
        List of WeekendPair.
    """
    match_by_window: dict = {m.window_start: m for m in weekend_matches}
    returns_by_date: dict = {}
    for f in return_all:
        returns_by_date.setdefault(f.travel_date, []).append(f)

    pairs: list[WeekendPair] = []

    for outbound in outbound_all:
        window_start = outbound.travel_date
        window_end = window_start + timedelta(days=5)

        match = match_by_window.get(window_start)
        events = match.events if match else []

        sunday_adv = has_sunday_events(events, window_start, window_end)

        # Collect candidate return flights
        candidates = []
        current = window_start
        while current <= window_end:
            for f in returns_by_date.get(current, []):
                weekday = f.travel_date.weekday()
                if weekday == 6:  # Sunday
                    if sunday_adv:
                        logger.debug(
                            f"  Skipping Sunday return {f.travel_date} "
                            f"{f.airline} ${f.price:,} (sunday adventure active)"
                        )
                        continue
                    else:
                        try:
                            h, m = map(int, f.departure_time.split(":"))
                            if dtime(h, m) < dtime(11, 0):
                                logger.debug(
                                    f"  Skipping Sunday return {f.travel_date} "
                                    f"{f.airline} {f.departure_time} (< 11:00)"
                                )
                                continue
                        except Exception:
                            pass
                candidates.append(f)
            current += timedelta(days=1)

        candidates.sort(key=lambda f: f.price)

        # LATAM preference: keep priority return unless another is ≥100K cheaper
        priority_returns = [f for f in candidates if f.is_priority]
        non_priority_returns = [f for f in candidates if not f.is_priority]

        if outbound.is_priority and priority_returns:
            best_priority = priority_returns[0]
            better_non_priority = [
                f
                for f in non_priority_returns
                if best_priority.price - f.price >= _LATAM_SAVING_THRESHOLD
            ]
            if better_non_priority:
                ordered = (
                    better_non_priority
                    + [best_priority]
                    + [f for f in non_priority_returns if f not in better_non_priority]
                )
            else:
                ordered = [best_priority] + non_priority_returns
        else:
            ordered = candidates

        # Deduplicate and take top 3
        seen_ids: set[str] = set()
        top3: list = []
        for f in ordered:
            if f.flight_id not in seen_ids and len(top3) < 3:
                top3.append(f)
                seen_ids.add(f.flight_id)

        priority_price = next((f.price for f in top3 if f.is_priority), None)
        return_options: list[ReturnOption] = [
            ReturnOption(
                flight=f,
                is_recommended=(i == 0),
                savings_vs_priority=(
                    (priority_price - f.price)
                    if priority_price and not f.is_priority
                    else None
                ),
            )
            for i, f in enumerate(top3)
        ]

        pairs.append(
            WeekendPair(
                window_start=window_start,
                window_end=window_end,
                outbound=outbound,
                return_options=return_options,
                events=events,
                sunday_adventure=sunday_adv,
            )
        )

    return pairs


def build_return_only_pairs(
    return_all: list,
    weekend_matches: list,
) -> list[WeekendPair]:
    """Build WeekendPair list when only return flights are cheap (no cheap outbound).

    Creates one pair per return-flight weekend showing the cheap return option
    and any matching events for that window.

    Args:
        return_all: Cheap return flights sorted by date.
        weekend_matches: WeekendMatch objects with events per window.

    Returns:
        List of WeekendPair with return_only=True.
    """
    match_by_window: dict = {m.window_start: m for m in weekend_matches}
    pairs: list[WeekendPair] = []
    seen_windows: set[date] = set()

    for ret_flight in return_all:
        window_start = ret_flight.travel_date - timedelta(days=4)
        if window_start in seen_windows:
            continue
        seen_windows.add(window_start)

        window_end = ret_flight.travel_date + timedelta(days=1)
        match = match_by_window.get(window_start)
        events = match.events if match else []

        pairs.append(
            WeekendPair(
                window_start=window_start,
                window_end=window_end,
                outbound=ret_flight,
                return_options=[
                    ReturnOption(
                        flight=ret_flight,
                        is_recommended=True,
                        savings_vs_priority=None,
                    )
                ],
                events=events,
                sunday_adventure=has_sunday_events(events, window_start, window_end),
                return_only=True,
            )
        )

    return pairs
