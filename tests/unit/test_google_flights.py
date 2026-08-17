"""Tests for Google Flights Scraper."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aventure_tracker.models.flight import RouteConfig
from aventure_tracker.scrapers.google_flights import GoogleFlightsScraper
from aventure_tracker.scrapers.google_flights.locators import (
    BASE_URL,
    ConsentLocators,
    ResultsLocators,
    SearchFormLocators,
)
from aventure_tracker.scrapers.google_flights.page_objects import (
    ConsentHandler,
    ResultsPage,
)


@pytest.fixture
def scraper() -> GoogleFlightsScraper:
    """Create a Google Flights scraper instance."""
    return GoogleFlightsScraper(headless=True)


@pytest.fixture
def route() -> RouteConfig:
    """Create a test route configuration."""
    return RouteConfig(
        origin="BAQ",
        destination="MDE",
        price_threshold=150000,
        drop_percentage=15,
    )


@pytest.fixture
def mock_page() -> AsyncMock:
    """Create a mock page object."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.keyboard = MagicMock()
    page.keyboard.type = AsyncMock()
    page.keyboard.press = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.click = AsyncMock()
    return page


class TestGoogleFlightsScraperInit:
    """Tests for scraper initialization."""

    def test_default_initialization(self) -> None:
        """Test default initialization."""
        scraper = GoogleFlightsScraper()
        assert scraper._headless is True
        assert scraper._language == "es-419"
        assert scraper._currency == "COP"

    def test_custom_initialization(self) -> None:
        """Test custom initialization."""
        scraper = GoogleFlightsScraper(
            headless=False,
            slow_mo=100,
            language="en",
            currency="USD",
        )
        assert scraper._headless is False
        assert scraper._slow_mo == 100
        assert scraper._language == "en"
        assert scraper._currency == "USD"


class TestBuildSearchUrl:
    """Tests for URL building."""

    def test_build_search_url_one_way(self, scraper: GoogleFlightsScraper) -> None:
        """Test building one-way search URL."""
        url = scraper._build_search_url(
            origin="BAQ",
            destination="MDE",
            departure_date=date(2025, 3, 15),
        )

        assert BASE_URL in url
        assert "BAQ" in url
        assert "MDE" in url
        assert "2025-03-15" in url
        assert "COP" in url
        assert "es-419" in url

    def test_build_search_url_round_trip(self, scraper: GoogleFlightsScraper) -> None:
        """Test building round-trip search URL."""
        url = scraper._build_search_url(
            origin="BAQ",
            destination="MDE",
            departure_date=date(2025, 3, 15),
            return_date=date(2025, 3, 17),
        )

        assert "BAQ" in url
        assert "MDE" in url
        assert "2025-03-15" in url
        assert "2025-03-17" in url


class TestParseDuration:
    """Tests for duration parsing."""

    def test_parse_hours_and_minutes(self, scraper: GoogleFlightsScraper) -> None:
        """Test parsing hours and minutes."""
        duration = scraper._parse_duration("1h 30m")
        assert duration == timedelta(hours=1, minutes=30)

    def test_parse_hours_only(self, scraper: GoogleFlightsScraper) -> None:
        """Test parsing hours only."""
        duration = scraper._parse_duration("2h")
        assert duration == timedelta(hours=2)

    def test_parse_minutes_only(self, scraper: GoogleFlightsScraper) -> None:
        """Test parsing minutes only."""
        duration = scraper._parse_duration("45m")
        assert duration == timedelta(minutes=45)

    def test_parse_with_spaces(self, scraper: GoogleFlightsScraper) -> None:
        """Test parsing with various spacing."""
        duration = scraper._parse_duration("1 h 30 m")
        assert duration == timedelta(hours=1, minutes=30)

    def test_parse_empty_returns_zero(self, scraper: GoogleFlightsScraper) -> None:
        """Test parsing empty string."""
        duration = scraper._parse_duration("")
        assert duration == timedelta()


class TestCreateFlightResult:
    """Tests for creating FlightResult from scraped data."""

    def test_create_valid_result(
        self, scraper: GoogleFlightsScraper, route: RouteConfig
    ) -> None:
        """Test creating valid FlightResult."""
        data = {
            "price": 120000,
            "airline": "Avianca",
            "duration": "1h 10m",
            "stops": 0,
        }

        result = scraper._create_flight_result(data, route, date(2025, 3, 15))

        assert result is not None
        assert result.price == 120000
        assert result.airline == "Avianca"
        assert result.stops == 0
        assert result.duration == timedelta(hours=1, minutes=10)

    def test_create_result_without_price_returns_none(
        self, scraper: GoogleFlightsScraper, route: RouteConfig
    ) -> None:
        """Test that missing price returns None."""
        data = {
            "airline": "LATAM",
            "duration": "1h",
            "stops": 0,
        }

        result = scraper._create_flight_result(data, route, date(2025, 3, 15))

        assert result is None

    def test_create_result_with_defaults(
        self, scraper: GoogleFlightsScraper, route: RouteConfig
    ) -> None:
        """Test creating result with default values."""
        data = {"price": 150000}

        result = scraper._create_flight_result(data, route, date(2025, 3, 15))

        assert result is not None
        assert result.price == 150000
        assert result.airline == "Unknown"
        assert result.stops == 0


class TestConsentHandler:
    """Tests for ConsentHandler page object."""

    @pytest.mark.asyncio
    async def test_dismiss_consent_when_present(self, mock_page: AsyncMock) -> None:
        """Test dismissing consent when button is present."""
        mock_button = AsyncMock()
        mock_button.click = AsyncMock()
        mock_page.query_selector.return_value = mock_button

        handler = ConsentHandler(mock_page)
        result = await handler.dismiss_consent_if_present()

        assert result is True
        mock_button.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_dismiss_consent_when_not_present(self, mock_page: AsyncMock) -> None:
        """Test handling when consent is not present."""
        mock_page.query_selector.return_value = None

        handler = ConsentHandler(mock_page)
        result = await handler.dismiss_consent_if_present()

        assert result is False


class TestResultsPage:
    """Tests for ResultsPage page object."""

    @pytest.mark.asyncio
    async def test_wait_for_results_success(self, mock_page: AsyncMock) -> None:
        """Test waiting for results successfully."""
        mock_page.wait_for_selector.return_value = MagicMock()

        results_page = ResultsPage(mock_page)
        result = await results_page.wait_for_results()

        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_results_timeout(self, mock_page: AsyncMock) -> None:
        """Test waiting for results with timeout."""
        mock_page.wait_for_selector.side_effect = [
            None,  # Loading indicator
            Exception("Timeout"),  # Results selector
        ]

        results_page = ResultsPage(mock_page)
        result = await results_page.wait_for_results(timeout_ms=1000)

        assert result is False

    def test_parse_price_cop_format(self, mock_page: AsyncMock) -> None:
        """Test parsing COP price format."""
        results_page = ResultsPage(mock_page)

        assert results_page._parse_price("COP 125.000") == 125000
        assert results_page._parse_price("COP 1.250.000") == 1250000

    def test_parse_price_with_commas(self, mock_page: AsyncMock) -> None:
        """Test parsing price with comma separators."""
        results_page = ResultsPage(mock_page)

        assert results_page._parse_price("$125,000") == 125000
        assert results_page._parse_price("$1,250,000") == 1250000

    def test_parse_price_plain_number(self, mock_page: AsyncMock) -> None:
        """Test parsing plain number."""
        results_page = ResultsPage(mock_page)

        assert results_page._parse_price("125000") == 125000

    def test_parse_price_empty_returns_none(self, mock_page: AsyncMock) -> None:
        """Test parsing empty string returns None."""
        results_page = ResultsPage(mock_page)

        assert results_page._parse_price("") is None
        assert results_page._parse_price(None) is None

    def test_parse_stops_nonstop(self, mock_page: AsyncMock) -> None:
        """Test parsing nonstop indicators."""
        results_page = ResultsPage(mock_page)

        assert results_page._parse_stops("Sin escalas") == 0
        assert results_page._parse_stops("Directo") == 0
        assert results_page._parse_stops("Nonstop") == 0

    def test_parse_stops_with_number(self, mock_page: AsyncMock) -> None:
        """Test parsing stops with number."""
        results_page = ResultsPage(mock_page)

        assert results_page._parse_stops("1 escala") == 1
        assert results_page._parse_stops("2 escalas") == 2

    def test_parse_stops_empty(self, mock_page: AsyncMock) -> None:
        """Test parsing empty stops returns 0."""
        results_page = ResultsPage(mock_page)

        assert results_page._parse_stops("") == 0
        assert results_page._parse_stops(None) == 0


class TestLocators:
    """Tests for locator constants."""

    def test_base_url_is_google_flights(self) -> None:
        """Test BASE_URL is correct."""
        assert "google.com/travel/flights" in BASE_URL

    def test_search_form_locators_exist(self) -> None:
        """Test SearchFormLocators has expected attributes."""
        assert SearchFormLocators.ORIGIN_INPUT
        assert SearchFormLocators.DESTINATION_INPUT
        assert SearchFormLocators.SEARCH_BUTTON

    def test_results_locators_exist(self) -> None:
        """Test ResultsLocators has expected attributes."""
        assert ResultsLocators.PRICE_ELEMENT
        assert ResultsLocators.FLIGHT_LIST_ITEM
        assert ResultsLocators.LOADING_INDICATOR

    def test_consent_locators_exist(self) -> None:
        """Test ConsentLocators has expected attributes."""
        assert ConsentLocators.ACCEPT_ALL_BUTTON
        assert ConsentLocators.CONSENT_DIALOG


class TestScrapeIntegration:
    """Integration-style tests with mocked browser session."""

    @pytest.mark.asyncio
    async def test_scrape_returns_results(
        self,
        scraper: GoogleFlightsScraper,
        route: RouteConfig,
    ) -> None:
        """Test scrape method returns results with mocked session."""
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_selector = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=None)
        mock_page.query_selector_all = AsyncMock(return_value=[])

        with patch.object(scraper, "browser_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_page
            mock_session.return_value.__aexit__.return_value = None

            with patch.object(scraper, "navigate", new_callable=AsyncMock):
                with patch.object(scraper, "_add_human_delay", new_callable=AsyncMock):
                    # Mock ResultsPage methods
                    with patch(
                        "aventure_tracker.scrapers.google_flights.scraper.ResultsPage"
                    ) as MockResultsPage:
                        mock_results = AsyncMock()
                        mock_results.wait_for_results = AsyncMock(return_value=True)
                        mock_results.get_flight_details = AsyncMock(
                            return_value=[
                                {
                                    "price": 120000,
                                    "airline": "Avianca",
                                    "duration": "1h",
                                    "stops": 0,
                                }
                            ]
                        )
                        MockResultsPage.return_value = mock_results

                        with patch(
                            "aventure_tracker.scrapers.google_flights.scraper.ConsentHandler"
                        ) as MockConsent:
                            MockConsent.return_value.dismiss_consent_if_present = (
                                AsyncMock(return_value=False)
                            )

                            results = await scraper.scrape(route, date(2025, 3, 15))

                            assert len(results) == 1
                            assert results[0].price == 120000
                            assert results[0].airline == "Avianca"

    @pytest.mark.asyncio
    async def test_get_cheapest_price(
        self,
        scraper: GoogleFlightsScraper,
        route: RouteConfig,
    ) -> None:
        """Test get_cheapest_price method."""
        mock_page = AsyncMock()

        with patch.object(scraper, "browser_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_page
            mock_session.return_value.__aexit__.return_value = None

            with patch.object(scraper, "navigate", new_callable=AsyncMock):
                with patch.object(scraper, "_add_human_delay", new_callable=AsyncMock):
                    with patch(
                        "aventure_tracker.scrapers.google_flights.scraper.ResultsPage"
                    ) as MockResultsPage:
                        mock_results = AsyncMock()
                        mock_results.wait_for_results = AsyncMock(return_value=True)
                        mock_results.get_cheapest_price = AsyncMock(return_value=99000)
                        MockResultsPage.return_value = mock_results

                        with patch(
                            "aventure_tracker.scrapers.google_flights.scraper.ConsentHandler"
                        ) as MockConsent:
                            MockConsent.return_value.dismiss_consent_if_present = (
                                AsyncMock(return_value=False)
                            )

                            price = await scraper.get_cheapest_price(
                                route, date(2025, 3, 15)
                            )

                            assert price == 99000
