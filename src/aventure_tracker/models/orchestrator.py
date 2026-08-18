"""Orchestrator data models: RunMode and OrchestratorResult."""

from dataclasses import dataclass
from enum import Enum


class RunMode(Enum):
    """Execution mode for the adventure tracker."""

    ALL = "all"
    FLIGHTS = "flights"
    ACTIVITIES = "activities"
    CALENDAR = "calendar"


@dataclass
class OrchestratorResult:
    """Result of a full orchestrator run.

    Attributes:
        mode: The execution mode that was run.
        flights_result: Flight tracking result (if run).
        activities_result: Activity tracking result (if run).
        total_alerts: Total alerts generated.
        total_notifications: Total notifications sent.
        errors: Combined errors from both trackers.
        duration_seconds: Total execution time in seconds.
    """

    mode: RunMode
    flights_result: object  # FlightTrackerResult | None
    activities_result: object  # ActivityTrackerResult | None
    total_alerts: int
    total_notifications: int
    errors: list[str]
    duration_seconds: float

    @property
    def success(self) -> bool:
        """True when the run completed without any errors."""
        return len(self.errors) == 0
