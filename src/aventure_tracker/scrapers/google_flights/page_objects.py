"""Page Object Model components for Google Flights scraper."""

import logging
import re
from datetime import date

from playwright.async_api import Page

from aventure_tracker.scrapers.google_flights.locators import (
    ANIMATION_PAUSE_MS,
    INTERACTION_TIMEOUT_MS,
    RESULTS_TIMEOUT_MS,
    ConsentLocators,
    FiltersLocators,
    ResultsLocators,
    SearchFormLocators,
)

logger = logging.getLogger(__name__)


class ConsentHandler:
    """Handles cookie consent dialogs."""

    def __init__(self, page: Page) -> None:
        self._page = page

    async def dismiss_consent_if_present(self) -> bool:
        """Dismiss consent dialog if present.

        Returns:
            True if consent was dismissed, False otherwise.
        """
        try:
            accept_btn = await self._page.query_selector(
                ConsentLocators.ACCEPT_ALL_BUTTON
            )
            if accept_btn:
                await accept_btn.click()
                logger.debug("Consent dialog dismissed")
                return True
        except Exception as e:
            logger.debug(f"No consent dialog or error: {e}")
        return False


class SearchForm:
    """Page object for the flight search form."""

    def __init__(self, page: Page) -> None:
        self._page = page

    async def _find_visible_input(
        self, selector: str, timeout_ms: int = INTERACTION_TIMEOUT_MS
    ):
        """Find the first visible element matching selector.

        Google Flights duplicates several form inputs (visible + hidden copies).
        wait_for_selector picks the first in DOM order, which is often hidden.
        This method scans all matches and returns the first visible one.

        Args:
            selector: CSS selector to match.
            timeout_ms: Max ms to wait for at least one visible element.

        Returns:
            The first visible element, or None.
        """
        import time as _time

        deadline = _time.monotonic() + timeout_ms / 1000
        while _time.monotonic() < deadline:
            elements = await self._page.query_selector_all(selector)
            for el in elements:
                try:
                    if await el.is_visible():
                        return el
                except Exception:
                    continue
            await self._page.wait_for_timeout(100)
        return None

    async def set_origin(self, airport_code: str) -> None:
        """Set the origin airport.

        Args:
            airport_code: IATA airport code (e.g., "BAQ").
        """
        try:
            # Click on origin input area
            origin_input = await self._find_visible_input(
                SearchFormLocators.ORIGIN_INPUT
            )
            if origin_input:
                await origin_input.click()
                await origin_input.fill("")
                await self._page.keyboard.type(airport_code, delay=100)
                # Wait for autocomplete and select first option
                await self._page.wait_for_timeout(ANIMATION_PAUSE_MS)
                await self._page.keyboard.press("ArrowDown")
                await self._page.keyboard.press("Enter")
                logger.debug(f"Set origin: {airport_code}")
        except Exception as e:
            logger.warning(f"Failed to set origin {airport_code}: {e}")
            raise

    async def set_destination(self, airport_code: str) -> None:
        """Set the destination airport.

        Args:
            airport_code: IATA airport code (e.g., "MDE").
        """
        try:
            # Wait for any open autocomplete from origin to close first
            await self._page.wait_for_timeout(ANIMATION_PAUSE_MS)
            dest_input = await self._find_visible_input(
                SearchFormLocators.DESTINATION_INPUT
            )
            if dest_input:
                await dest_input.click()
                await dest_input.fill("")
                await self._page.keyboard.type(airport_code, delay=100)
                await self._page.wait_for_timeout(ANIMATION_PAUSE_MS)
                await self._page.keyboard.press("ArrowDown")
                await self._page.keyboard.press("Enter")
                logger.debug(f"Set destination: {airport_code}")
        except Exception as e:
            logger.warning(f"Failed to set destination {airport_code}: {e}")
            raise

    async def set_departure_date(self, travel_date: date) -> None:
        """Set the departure date.

        Args:
            travel_date: The travel date.
        """
        try:
            date_input = await self._find_visible_input(
                SearchFormLocators.DEPARTURE_DATE_INPUT
            )
            if date_input:
                await date_input.click()
                # Select date from calendar — use JS click to bypass overlay elements
                date_selector = f"[data-iso='{travel_date.isoformat()}']"
                await self._page.wait_for_selector(
                    date_selector, timeout=INTERACTION_TIMEOUT_MS
                )
                await self._page.evaluate(
                    f"document.querySelector(\"[data-iso='{travel_date.isoformat()}']\").click()"
                )

                # Click done button if present — use JS to avoid overlay
                try:
                    done_btn = await self._page.query_selector(
                        SearchFormLocators.CALENDAR_DONE_BUTTON
                    )
                    if done_btn:
                        await self._page.evaluate(
                            f"document.querySelector('{SearchFormLocators.CALENDAR_DONE_BUTTON}')?.click()"
                        )
                except Exception:
                    pass

                # Press Escape to close any remaining dialog/modal
                await self._page.keyboard.press("Escape")
                await self._page.wait_for_timeout(ANIMATION_PAUSE_MS)

                logger.debug(f"Set departure date: {travel_date}")
        except Exception as e:
            logger.warning(f"Failed to set date {travel_date}: {e}")
            raise

    async def select_one_way(self) -> None:
        """Select one-way trip type."""
        try:
            dropdown = await self._page.query_selector(
                SearchFormLocators.TRIP_TYPE_DROPDOWN
            )
            if dropdown:
                await dropdown.click()
                await self._page.wait_for_timeout(ANIMATION_PAUSE_MS)
                await self._page.click(SearchFormLocators.ONE_WAY_OPTION)
                logger.debug("Selected one-way trip")
        except Exception as e:
            logger.debug(f"Could not select one-way: {e}")

    async def set_return_date(self, return_date: date) -> None:
        """Set the return date for round-trip search.

        Args:
            return_date: The return travel date.
        """
        try:
            return_input = await self._find_visible_input(
                SearchFormLocators.RETURN_DATE_INPUT
            )
            if return_input:
                # Use JS click to bypass any overlay (price chart modal) that
                # may still be open after departure date selection
                await self._page.evaluate(
                    f'document.querySelector("{SearchFormLocators.RETURN_DATE_INPUT}")?.click()'
                )
                date_selector = f"[data-iso='{return_date.isoformat()}']"
                await self._page.wait_for_selector(
                    date_selector, timeout=INTERACTION_TIMEOUT_MS
                )
                await self._page.evaluate(
                    f"document.querySelector(\"[data-iso='{return_date.isoformat()}']\").click()"
                )
                try:
                    done_btn = await self._page.query_selector(
                        SearchFormLocators.CALENDAR_DONE_BUTTON
                    )
                    if done_btn:
                        await done_btn.click()
                except Exception:
                    pass
                logger.debug(f"Set return date: {return_date}")
        except Exception as e:
            logger.warning(f"Failed to set return date {return_date}: {e}")

    async def submit_search(self) -> None:
        """Click the search button."""
        try:
            search_btn = await self._find_visible_input(
                SearchFormLocators.SEARCH_BUTTON
            )
            if search_btn:
                await search_btn.click()
                logger.debug("Search submitted")
        except Exception as e:
            logger.warning(f"Failed to submit search: {e}")
            raise


class ResultsPage:
    """Page object for flight search results."""

    def __init__(self, page: Page) -> None:
        self._page = page

    async def wait_for_results(self, timeout_ms: int = RESULTS_TIMEOUT_MS) -> bool:
        """Wait for results to load.

        Args:
            timeout_ms: Maximum time to wait.

        Returns:
            True if results loaded, False if no results found.
        """
        try:
            # Wait for loading to finish
            await self._page.wait_for_selector(
                ResultsLocators.LOADING_INDICATOR,
                state="hidden",
                timeout=timeout_ms,
            )
        except Exception:
            pass  # Loading indicator may not always appear

        # Check for results
        try:
            await self._page.wait_for_selector(
                f"{ResultsLocators.PRICE_ELEMENT}, {ResultsLocators.NO_RESULTS}",
                timeout=timeout_ms,
            )
            logger.debug("Results page loaded")
            return True
        except Exception as e:
            logger.warning(f"Results not loaded: {e}")
            return False

    async def get_cheapest_price(self) -> int | None:
        """Extract the cheapest flight price from results.

        Returns:
            Price in COP as integer, or None if not found.
        """
        try:
            # Try multiple price selectors
            price_selectors = [
                ResultsLocators.CHEAPEST_PRICE,
                ResultsLocators.PRICE_ELEMENT,
                ".YMlIz .FpEdX",
                "[data-gs]",
            ]

            for selector in price_selectors:
                elements = await self._page.query_selector_all(selector)
                for element in elements:
                    text = await element.text_content()
                    if text:
                        price = self._parse_price(text)
                        if price:
                            logger.debug(f"Found price: {price} COP")
                            return price

            logger.warning("No price found in results")
            return None

        except Exception as e:
            logger.error(f"Error extracting price: {e}")
            return None

    async def get_all_prices(self) -> list[int]:
        """Get all prices from the results page.

        Returns:
            List of prices in COP.
        """
        prices: list[int] = []

        try:
            elements = await self._page.query_selector_all(
                ResultsLocators.PRICE_ELEMENT
            )

            for element in elements:
                text = await element.text_content()
                if text:
                    price = self._parse_price(text)
                    if price and price not in prices:
                        prices.append(price)

            logger.debug(f"Found {len(prices)} unique prices")

        except Exception as e:
            logger.error(f"Error getting prices: {e}")

        return sorted(prices)

    async def get_flight_details(self, accept_round_trip: bool = False) -> list[dict]:
        """Extract detailed flight information.

        Args:
            accept_round_trip: When True, accept cards showing combined round-trip
                prices (used on the return screen of a round-trip search).

        Returns:
            List of flight detail dictionaries.
        """
        flights: list[dict] = []

        try:
            cards = await self._page.query_selector_all(
                ResultsLocators.FLIGHT_LIST_ITEM
            )

            for card in cards[:10]:  # Limit to first 10 results
                try:
                    flight = await self._extract_flight_from_card(
                        card, accept_round_trip=accept_round_trip
                    )
                    if flight:
                        flights.append(flight)
                except Exception as e:
                    logger.debug(f"Could not extract flight: {e}")
                    continue

            logger.debug(f"Extracted {len(flights)} flight details")

        except Exception as e:
            logger.error(f"Error extracting flight details: {e}")

        return flights

    async def get_flight_details_with_hrefs(self) -> list[dict]:
        """Extract flight details for round-trip outbound selection.

        Flight cards are <div role="link" jsaction="click:..."> elements
        with NO href attribute — the URL is generated dynamically on click.
        We extract flight data from aria-labels and store the card index
        so scrape_round_trip can click them by position.

        Returns:
            List of flight detail dicts. Each dict has an 'href' key
            (empty string — click-based navigation is used instead).
        """
        flights: list[dict] = []

        try:
            # Flight cards are <div role="link"> with aria-label containing price info
            cards = await self._page.query_selector_all(
                "[role='link'][aria-label*='pesos colombianos']"
            )
            logger.debug(f"Found {len(cards)} flight card elements")

            for i, card in enumerate(cards[:8]):
                try:
                    aria = await card.get_attribute("aria-label") or ""
                    # In round-trip mode, "ida y vuelta" cards are correct — don't filter
                    flight = self._parse_aria_label(aria, accept_round_trip=True)
                    if not flight:
                        continue
                    # No href available — caller must click by card index
                    flight["href"] = ""
                    flight["_card_index"] = i
                    flights.append(flight)
                except Exception as e:
                    logger.debug(f"Could not extract flight card {i}: {e}")
                    continue

            logger.debug(f"Extracted {len(flights)} flight details with hrefs")

        except Exception as e:
            logger.error(f"Error extracting flight details with hrefs: {e}")

        return flights

    async def _extract_flight_from_card(
        self, card, accept_round_trip: bool = False
    ) -> dict | None:
        """Extract flight info from a result card.

        Args:
            card: The card element.
            accept_round_trip: When True, accept cards with round-trip prices.

        Returns:
            Flight info dictionary or None.
        """
        try:
            # Try to extract from aria-label first (most reliable)
            link_elem = await card.query_selector("[role='link'][aria-label]")
            if link_elem:
                aria_label = await link_elem.get_attribute("aria-label")
                if aria_label:
                    result = self._parse_aria_label(
                        aria_label, accept_round_trip=accept_round_trip
                    )
                    if result and result.get("price"):
                        return result

            # Fallback to individual selectors
            # Extract price
            price_elem = await card.query_selector(ResultsLocators.PRICE_ELEMENT)
            price_text = await price_elem.text_content() if price_elem else None
            price = self._parse_price(price_text) if price_text else None

            if not price:
                return None

            # Extract departure time from aria-label
            time_elem = await card.query_selector("span[aria-label*='Hora de salida']")
            departure_time = None
            if time_elem:
                time_label = await time_elem.get_attribute("aria-label")
                if time_label:
                    departure_time = self._parse_time(time_label)

            # Fallback time extraction
            if not departure_time:
                time_elem = await card.query_selector(ResultsLocators.DEPARTURE_TIME)
                if time_elem:
                    time_text = await time_elem.text_content()
                    departure_time = self._parse_time(time_text)

            # Extract duration
            duration_elem = await card.query_selector(ResultsLocators.DURATION)
            duration = await duration_elem.text_content() if duration_elem else "N/A"

            # Extract stops
            stops_elem = await card.query_selector(ResultsLocators.STOPS_INFO)
            stops_text = await stops_elem.text_content() if stops_elem else "Direct"
            stops = self._parse_stops(stops_text)

            return {
                "price": price,
                "airline": "Unknown",  # Can't reliably extract from selectors
                "departure_time": departure_time,
                "duration": duration.strip() if duration else "N/A",
                "stops": stops,
            }

        except Exception as e:
            logger.debug(f"Card extraction failed: {e}")
            return None

    def _parse_aria_label(
        self, aria_label: str, accept_round_trip: bool = False
    ) -> dict | None:
        """Parse flight info from aria-label attribute.

        The aria-label contains structured info like:
        "Precio total ida y vuelta desde 696318 pesos colombianos.
         El precio no incluye acceso a los compartimentos superiores.
         Vuelo sin escalas de Wingo.
         Sale de ... a las 12:25 p.m. y llega a ... a las 1:43 p.m..
         Duración total: 1 h 18 min."

        Args:
            aria_label: The aria-label text.

        Returns:
            Flight info dictionary or None.
        """
        try:
            result = {
                "price": None,
                "airline": "Unknown",
                "departure_time": None,
                "duration": "N/A",
                "stops": 0,
            }

            # Skip round-trip cards in one-way searches.
            # Google sometimes returns combined round-trip prices even for
            # one-way queries. Those prices are ~2x the real one-way price
            # and must not be compared against the per-leg threshold.
            # In round-trip mode (accept_round_trip=True), these cards are correct.
            if not accept_round_trip and "ida y vuelta" in aria_label.lower():
                logger.debug("Skipping round-trip card in one-way search")
                return None

            # Extract price: "Desde NNNNNN pesos" (one-way) or
            # "desde NNNNNN pesos" (round-trip — already filtered above)
            price_match = re.search(r"desde\s+(\d+)\s+pesos", aria_label, re.IGNORECASE)
            if price_match:
                result["price"] = int(price_match.group(1))

            # Extract airline: "Vuelo sin escalas de AIRLINE" or "Vuelo con N escala(s) de AIRLINE"
            airline_match = re.search(
                r"Vuelo (?:sin escalas|con \d+ escalas?) de ([^.]+)\.", aria_label
            )
            if airline_match:
                result["airline"] = airline_match.group(1).strip()

            # Extract stops
            if "sin escalas" in aria_label.lower():
                result["stops"] = 0
            else:
                stops_match = re.search(r"con (\d+) escalas?", aria_label)
                if stops_match:
                    result["stops"] = int(stops_match.group(1))

            # Extract departure time: "a las HH:MM a.m./p.m."
            time_match = re.search(
                r"a las\s*(\d{1,2}:\d{2})\s*(a\.m\.|p\.m\.)", aria_label
            )
            if time_match:
                result["departure_time"] = self._parse_time(
                    f"{time_match.group(1)} {time_match.group(2)}"
                )

            # Extract duration: "Duración total: X h Y min"
            duration_match = re.search(
                r"Duración total:\s*(\d+\s*h(?:\s*\d+\s*min)?)", aria_label
            )
            if duration_match:
                result["duration"] = duration_match.group(1).strip()

            return result if result["price"] else None

        except Exception as e:
            logger.debug(f"Failed to parse aria-label: {e}")
            return None

    def _parse_time(self, text: str | None) -> str | None:
        """Parse time from text.

        Args:
            text: Time text like "6:30 p.m." or "18:30".

        Returns:
            Time in HH:MM format or None.
        """
        if not text:
            return None

        text = text.strip()

        # Try to match HH:MM format
        match = re.search(r"(\d{1,2}):(\d{2})", text)
        if match:
            hour = int(match.group(1))
            minute = match.group(2)

            # Handle AM/PM
            text_lower = text.lower()
            if "p" in text_lower and hour < 12:
                hour += 12
            elif "a" in text_lower and hour == 12:
                hour = 0

            return f"{hour:02d}:{minute}"

        return None

    def _parse_price(self, text: str | None) -> int | None:
        """Parse price from text.

        Args:
            text: Price text like "COP 125.000" or "$125,000".

        Returns:
            Price as integer or None.
        """
        if not text:
            return None

        # Remove currency symbols and whitespace
        cleaned = text.replace("COP", "").replace("$", "").strip()

        # Handle different thousand separators
        # Colombian format: 125.000 or 125,000
        cleaned = cleaned.replace(".", "").replace(",", "")

        # Extract digits
        digits = re.sub(r"[^\d]", "", cleaned)

        if digits:
            try:
                return int(digits)
            except ValueError:
                pass

        return None

    def _parse_stops(self, text: str | None) -> int:
        """Parse number of stops from text.

        Args:
            text: Stops text like "Sin escalas", "1 escala", "2 escalas".

        Returns:
            Number of stops as integer.
        """
        if not text:
            return 0

        text_lower = text.lower()

        if "sin" in text_lower or "directo" in text_lower or "nonstop" in text_lower:
            return 0

        # Find number in text
        match = re.search(r"(\d+)", text)
        if match:
            return int(match.group(1))

        return 0


class FiltersPanel:
    """Page object for flight filters."""

    def __init__(self, page: Page) -> None:
        self._page = page

    async def filter_nonstop_only(self) -> None:
        """Apply filter to show only nonstop flights."""
        try:
            dropdown = await self._page.query_selector(FiltersLocators.STOPS_DROPDOWN)
            if dropdown:
                await dropdown.click()
                await self._page.wait_for_timeout(ANIMATION_PAUSE_MS)
                await self._page.click(FiltersLocators.NONSTOP_OPTION)
                await self._page.wait_for_timeout(ANIMATION_PAUSE_MS)
                logger.debug("Applied nonstop filter")
        except Exception as e:
            logger.debug(f"Could not apply nonstop filter: {e}")

    async def apply_filters(self) -> None:
        """Click apply filters button if present."""
        try:
            apply_btn = await self._page.query_selector(FiltersLocators.APPLY_FILTERS)
            if apply_btn:
                await apply_btn.click()
        except Exception:
            pass
