"""Web scrapers for Adventure Tracker."""

from aventure_tracker.scrapers.base import BaseScraper, ScraperError
from aventure_tracker.scrapers.google_flights import GoogleFlightsScraper

__all__ = [
    "BaseScraper",
    "GoogleFlightsScraper",
    "ScraperError",
]
