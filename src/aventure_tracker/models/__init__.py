"""Data models for Adventure Tracker."""

from aventure_tracker.models.activity import (
    AccountsConfig,
    DoneConfig,
    InstagramAccountConfig,
    InstagramPost,
    WishlistConfig,
)
from aventure_tracker.models.flight import (
    FlightResult,
    RouteConfig,
    RoutesConfig,
    TimeRange,
    WeekendTrip,
)
from aventure_tracker.models.state import (
    FlightState,
    InstagramAccountState,
    StateData,
    TrackerResult,
)

__all__ = [
    # Flight models
    "RouteConfig",
    "RoutesConfig",
    "FlightResult",
    "TimeRange",
    "WeekendTrip",
    # Activity models
    "InstagramPost",
    "InstagramAccountConfig",
    "AccountsConfig",
    "WishlistConfig",
    "DoneConfig",
    # State models
    "FlightState",
    "InstagramAccountState",
    "StateData",
    "TrackerResult",
]
