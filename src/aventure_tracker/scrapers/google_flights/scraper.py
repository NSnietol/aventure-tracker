"""Google Flights scraper implementation."""

import logging
from datetime import date, datetime, timedelta
from urllib.parse import quote

from aventure_tracker.models.flight import FlightResult, RouteConfig
from aventure_tracker.scrapers.base import BaseScraper, NavigationError, ScraperError
from aventure_tracker.scrapers.google_flights.locators import BASE_URL
from aventure_tracker.scrapers.google_flights.page_objects import (
    ConsentHandler,
    ResultsPage,
)

logger = logging.getLogger(__name__)


class GoogleFlightsScraper(BaseScraper):
    """Scraper for Google Flights using Page Object Model.

    Extracts flight prices for specified routes and dates.
    Uses URL-based search to navigate directly to results.
    """

    def __init__(
        self,
        headless: bool = True,
        slow_mo: int = 0,
        language: str = "es-419",
        currency: str = "COP",
    ) -> None:
        """Initialize Google Flights scraper.

        Args:
            headless: Run browser in headless mode.
            slow_mo: Slow down operations by specified ms.
            language: Language code for Google Flights.
            currency: Currency code for prices.
        """
        super().__init__(headless=headless, slow_mo=slow_mo)
        self._language = language
        self._currency = currency

    def _build_search_url(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: date | None = None,
    ) -> str:
        """Build Google Flights search URL.

        Args:
            origin: Origin airport code.
            destination: Destination airport code.
            departure_date: Departure date.
            return_date: Return date for round-trip (None for one-way).

        Returns:
            Google Flights search URL.
        """
        # Format: /travel/flights/search?tfs=...
        # Using the explore/query format which is more reliable
        date_str = departure_date.strftime("%Y-%m-%d")

        # Build query string
        query_parts = [
            f"Vuelos de {origin} a {destination}",
            f"el {date_str}",
        ]

        if return_date:
            query_parts.append(f"vuelta {return_date.strftime('%Y-%m-%d')}")

        query = " ".join(query_parts)

        url = f"{BASE_URL}?q={quote(query)}&curr={self._currency}&hl={self._language}"

        return url

    def _build_direct_url(
        self,
        origin: str,
        destination: str,
        departure_date: date,
    ) -> str:
        """Build direct Google Flights URL with encoded parameters.

        Uses the direct booking path format.

        Args:
            origin: Origin airport code.
            destination: Destination airport code.
            departure_date: Departure date.

        Returns:
            Direct search URL.
        """
        # Format used by Google when sharing flight searches
        date_str = departure_date.strftime("%Y-%m-%d")

        url = (
            f"https://www.google.com/travel/flights/search"
            f"?tfs=CBwQAhoiEgoyMDI1LTAzLTE1agwIAhIIL20ve29yaWdpbn1yDAgCEggvbS97ZGVzdH0"
            f"&curr={self._currency}"
            f"&hl={self._language}"
        )

        # Simpler approach: use booking/flights format
        url = (
            f"https://www.google.com/travel/flights/booking"
            f"?f={origin}"
            f"&t={destination}"
            f"&d={date_str}"
            f"&curr={self._currency}"
            f"&hl={self._language}"
        )

        return url

    async def scrape(
        self,
        route: RouteConfig,
        travel_date: date,
        return_date: date | None = None,
    ) -> list[FlightResult]:
        """Scrape flight prices for a route and date.

        Args:
            route: Route configuration with origin/destination.
            travel_date: Date of travel.
            return_date: Return date for round-trip (None for one-way).

        Returns:
            List of FlightResult objects.

        Raises:
            ScraperError: If scraping fails.
        """
        results: list[FlightResult] = []

        async with self.browser_session() as page:
            try:
                # Handle consent dialog
                consent = ConsentHandler(page)

                # Build and navigate to search URL
                url = self._build_search_url(
                    route.origin,
                    route.destination,
                    travel_date,
                    return_date,
                )

                logger.info(f"Scraping flights: {route} on {travel_date}")
                await self.navigate(url, wait_until="networkidle")

                # Dismiss consent if needed
                await consent.dismiss_consent_if_present()

                # Wait a bit for dynamic content
                await self._add_human_delay(1000, 2000)

                # Extract results
                results_page = ResultsPage(page)
                if await results_page.wait_for_results():
                    flights_data = await results_page.get_flight_details()

                    for data in flights_data:
                        result = self._create_flight_result(
                            data,
                            route,
                            travel_date,
                        )
                        if result:
                            results.append(result)

                logger.info(f"Found {len(results)} flights for {route}")

            except NavigationError:
                logger.error(f"Navigation failed for {route}")
                raise
            except Exception as e:
                logger.error(f"Scraping error for {route}: {e}")
                raise ScraperError(f"Failed to scrape {route}: {e}") from e

        return results

    async def get_cheapest_price(
        self,
        route: RouteConfig,
        travel_date: date,
    ) -> int | None:
        """Get the cheapest flight price for a route.

        This is a convenience method that only extracts the minimum price.

        Args:
            route: Route configuration.
            travel_date: Date of travel.

        Returns:
            Cheapest price in COP or None if not found.
        """
        async with self.browser_session() as page:
            try:
                consent = ConsentHandler(page)

                url = self._build_search_url(
                    route.origin,
                    route.destination,
                    travel_date,
                )

                await self.navigate(url, wait_until="networkidle")
                await consent.dismiss_consent_if_present()
                await self._add_human_delay(1000, 2000)

                results_page = ResultsPage(page)
                if await results_page.wait_for_results():
                    return await results_page.get_cheapest_price()

            except Exception as e:
                logger.error(f"Error getting cheapest price: {e}")

        return None

    async def scrape_multiple_dates(
        self,
        route: RouteConfig,
        dates: list[date],
    ) -> dict[date, int | None]:
        """Scrape prices for multiple dates.

        Args:
            route: Route configuration.
            dates: List of dates to check.

        Returns:
            Dictionary mapping dates to prices.
        """
        results: dict[date, int | None] = {}

        async with self.browser_session() as page:
            consent = ConsentHandler(page)

            for travel_date in dates:
                try:
                    url = self._build_search_url(
                        route.origin,
                        route.destination,
                        travel_date,
                    )

                    await self.navigate(url, wait_until="networkidle")

                    # Only dismiss consent on first page
                    if travel_date == dates[0]:
                        await consent.dismiss_consent_if_present()

                    await self._add_human_delay(500, 1500)

                    results_page = ResultsPage(page)
                    if await results_page.wait_for_results(timeout_ms=15000):
                        price = await results_page.get_cheapest_price()
                        results[travel_date] = price
                    else:
                        results[travel_date] = None

                except Exception as e:
                    logger.warning(f"Error for {travel_date}: {e}")
                    results[travel_date] = None

                # Add delay between requests to avoid rate limiting
                await self._add_human_delay(2000, 4000)

        return results

    def _create_flight_result(
        self,
        data: dict,
        route: RouteConfig,
        travel_date: date,
    ) -> FlightResult | None:
        """Create FlightResult from scraped data.

        Args:
            data: Scraped flight data dictionary.
            route: Route configuration.
            travel_date: Travel date.

        Returns:
            FlightResult or None if invalid data.
        """
        try:
            price = data.get("price")
            if not price:
                return None

            # Parse departure time if available
            departure_time_str = data.get("departure_time")
            if departure_time_str:
                try:
                    hour, minute = map(int, departure_time_str.split(":"))
                    departure_dt = datetime.combine(
                        travel_date,
                        datetime.min.time().replace(hour=hour, minute=minute),
                    )
                except (ValueError, AttributeError):
                    departure_dt = datetime.combine(travel_date, datetime.min.time())
            else:
                departure_dt = datetime.combine(travel_date, datetime.min.time())

            # Parse duration if available
            duration_str = data.get("duration", "1h")
            duration = self._parse_duration(duration_str)

            arrival_dt = departure_dt + duration

            return FlightResult(
                price=price,
                airline=data.get("airline", "Unknown"),
                departure_time=departure_dt,
                arrival_time=arrival_dt,
                duration=duration,
                stops=data.get("stops", 0),
                booking_link=self._build_search_url(
                    route.origin,
                    route.destination,
                    travel_date,
                ),
            )

        except Exception as e:
            logger.debug(f"Could not create FlightResult: {e}")
            return None

    def _parse_duration(self, duration_str: str) -> timedelta:
        """Parse duration string to timedelta.

        Args:
            duration_str: Duration like "1h 30m" or "2h".

        Returns:
            timedelta object.
        """
        import re

        hours = 0
        minutes = 0

        # Match hours
        h_match = re.search(r"(\d+)\s*h", duration_str)
        if h_match:
            hours = int(h_match.group(1))

        # Match minutes
        m_match = re.search(r"(\d+)\s*m", duration_str)
        if m_match:
            minutes = int(m_match.group(1))

        return timedelta(hours=hours, minutes=minutes)
