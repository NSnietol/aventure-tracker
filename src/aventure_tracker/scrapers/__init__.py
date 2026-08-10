"""Web scrapers for Adventure Tracker."""

from aventure_tracker.scrapers.base import BaseScraper, ScraperError
from aventure_tracker.scrapers.google_flights import GoogleFlightsScraper
from aventure_tracker.scrapers.instagram import InstagramScraper

__all__ = [
    "BaseScraper",
    "GoogleFlightsScraper",
    "InstagramScraper",
    "ScraperError",
]
