"""Tests for Base Scraper with Playwright stealth."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aventure_tracker.scrapers.base import (
    DEFAULT_NAVIGATION_TIMEOUT_MS,
    DEFAULT_TIMEOUT_MS,
    DEFAULT_USER_AGENTS,
    DEFAULT_VIEWPORTS,
    BaseScraper,
    ElementNotFoundError,
    NavigationError,
    ScraperError,
)


class ConcreteScraper(BaseScraper):
    """Concrete implementation for testing."""

    async def scrape(self, url: str) -> dict:
        """Simple scrape implementation."""
        await self.navigate(url)
        return {"url": url, "status": "scraped"}


@pytest.fixture
def scraper() -> ConcreteScraper:
    """Create a concrete scraper instance."""
    return ConcreteScraper()


class TestBaseScraper:
    """Tests for BaseScraper initialization."""

    def test_default_initialization(self, scraper: ConcreteScraper) -> None:
        """Test scraper initializes with defaults."""
        assert scraper._headless is True
        assert scraper._slow_mo == 0
        assert scraper._user_agents == DEFAULT_USER_AGENTS
        assert scraper._viewports == DEFAULT_VIEWPORTS
        assert scraper._timeout_ms == DEFAULT_TIMEOUT_MS
        assert scraper._navigation_timeout_ms == DEFAULT_NAVIGATION_TIMEOUT_MS

    def test_custom_initialization(self) -> None:
        """Test scraper with custom configuration."""
        custom_agents = ["CustomAgent/1.0"]
        custom_viewports = [{"width": 800, "height": 600}]

        scraper = ConcreteScraper(
            headless=False,
            slow_mo=100,
            user_agents=custom_agents,
            viewports=custom_viewports,
            timeout_ms=5000,
            navigation_timeout_ms=10000,
        )

        assert scraper._headless is False
        assert scraper._slow_mo == 100
        assert scraper._user_agents == custom_agents
        assert scraper._viewports == custom_viewports
        assert scraper._timeout_ms == 5000
        assert scraper._navigation_timeout_ms == 10000

    def test_page_property_initially_none(self, scraper: ConcreteScraper) -> None:
        """Test page property is None before setup."""
        assert scraper.page is None

    def test_is_connected_initially_false(self, scraper: ConcreteScraper) -> None:
        """Test is_connected is False before setup."""
        assert scraper.is_connected is False


class TestRandomSelection:
    """Tests for random user agent and viewport selection."""

    def test_get_random_user_agent(self, scraper: ConcreteScraper) -> None:
        """Test random user agent selection."""
        agent = scraper._get_random_user_agent()
        assert agent in DEFAULT_USER_AGENTS

    def test_get_random_viewport(self, scraper: ConcreteScraper) -> None:
        """Test random viewport selection."""
        viewport = scraper._get_random_viewport()
        assert viewport in DEFAULT_VIEWPORTS
        assert "width" in viewport
        assert "height" in viewport


class TestHumanDelay:
    """Tests for human-like delay simulation."""

    @pytest.mark.asyncio
    async def test_add_human_delay(self, scraper: ConcreteScraper) -> None:
        """Test human delay is applied."""
        import time

        start = time.time()
        await scraper._add_human_delay(min_ms=100, max_ms=200)
        elapsed = time.time() - start

        # Should be at least 100ms
        assert elapsed >= 0.1
        # Should be less than 500ms (with some buffer)
        assert elapsed < 0.5


class TestNavigationWithoutPage:
    """Tests for methods that require page to be initialized."""

    @pytest.mark.asyncio
    async def test_navigate_without_page_raises(self, scraper: ConcreteScraper) -> None:
        """Test navigate raises when page not initialized."""
        with pytest.raises(ScraperError, match="Page not initialized"):
            await scraper.navigate("https://example.com")

    @pytest.mark.asyncio
    async def test_wait_for_selector_without_page_raises(
        self, scraper: ConcreteScraper
    ) -> None:
        """Test wait_for_selector raises when page not initialized."""
        with pytest.raises(ScraperError, match="Page not initialized"):
            await scraper.wait_for_selector("div")

    @pytest.mark.asyncio
    async def test_click_without_page_raises(self, scraper: ConcreteScraper) -> None:
        """Test click raises when page not initialized."""
        with pytest.raises(ScraperError, match="Page not initialized"):
            await scraper.click("button")

    @pytest.mark.asyncio
    async def test_type_text_without_page_raises(
        self, scraper: ConcreteScraper
    ) -> None:
        """Test type_text raises when page not initialized."""
        with pytest.raises(ScraperError, match="Page not initialized"):
            await scraper.type_text("input", "text")

    @pytest.mark.asyncio
    async def test_get_text_without_page_raises(self, scraper: ConcreteScraper) -> None:
        """Test get_text raises when page not initialized."""
        with pytest.raises(ScraperError, match="Page not initialized"):
            await scraper.get_text("span")

    @pytest.mark.asyncio
    async def test_screenshot_without_page_raises(
        self, scraper: ConcreteScraper
    ) -> None:
        """Test screenshot raises when page not initialized."""
        with pytest.raises(ScraperError, match="Page not initialized"):
            await scraper.screenshot("test.png")

    @pytest.mark.asyncio
    async def test_get_attribute_without_page_raises(
        self, scraper: ConcreteScraper
    ) -> None:
        """Test get_attribute raises when page not initialized."""
        with pytest.raises(ScraperError, match="Page not initialized"):
            await scraper.get_attribute("a", "href")

    @pytest.mark.asyncio
    async def test_query_selector_all_without_page_raises(
        self, scraper: ConcreteScraper
    ) -> None:
        """Test query_selector_all raises when page not initialized."""
        with pytest.raises(ScraperError, match="Page not initialized"):
            await scraper.query_selector_all("div")


class TestWithMockedPage:
    """Tests with mocked page object."""

    @pytest.fixture
    def mock_page(self) -> AsyncMock:
        """Create a mock page."""
        page = AsyncMock()
        page.goto = AsyncMock()
        page.wait_for_selector = AsyncMock()
        page.click = AsyncMock()
        page.fill = AsyncMock()
        page.type = AsyncMock()
        page.screenshot = AsyncMock()
        page.query_selector = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        return page

    @pytest.fixture
    def scraper_with_page(
        self, scraper: ConcreteScraper, mock_page: AsyncMock
    ) -> ConcreteScraper:
        """Create scraper with mocked page."""
        scraper._page = mock_page
        scraper._browser = MagicMock()
        return scraper

    @pytest.mark.asyncio
    async def test_navigate_calls_goto(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test navigate calls page.goto."""
        await scraper_with_page.navigate("https://example.com")

        mock_page.goto.assert_called_once_with(
            "https://example.com", wait_until="domcontentloaded"
        )

    @pytest.mark.asyncio
    async def test_navigate_with_custom_wait(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test navigate with custom wait_until."""
        await scraper_with_page.navigate(
            "https://example.com", wait_until="networkidle"
        )

        mock_page.goto.assert_called_once_with(
            "https://example.com", wait_until="networkidle"
        )

    @pytest.mark.asyncio
    async def test_navigate_raises_navigation_error_on_failure(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test navigate raises NavigationError on failure."""
        mock_page.goto.side_effect = Exception("Connection refused")

        with pytest.raises(NavigationError, match="Failed to navigate"):
            await scraper_with_page.navigate("https://example.com")

    @pytest.mark.asyncio
    async def test_wait_for_selector_calls_page_method(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test wait_for_selector calls page method."""
        await scraper_with_page.wait_for_selector("div.content")

        mock_page.wait_for_selector.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_for_selector_raises_element_not_found(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test wait_for_selector raises ElementNotFoundError."""
        mock_page.wait_for_selector.side_effect = Exception("Timeout")

        with pytest.raises(ElementNotFoundError, match="Element not found"):
            await scraper_with_page.wait_for_selector("div.missing")

    @pytest.mark.asyncio
    async def test_click_calls_page_click(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test click calls page.click."""
        await scraper_with_page.click("button.submit")

        mock_page.click.assert_called_once_with("button.submit")

    @pytest.mark.asyncio
    async def test_click_raises_element_not_found(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test click raises ElementNotFoundError on failure."""
        mock_page.click.side_effect = Exception("Element not found")

        with pytest.raises(ElementNotFoundError, match="Failed to click"):
            await scraper_with_page.click("button.missing")

    @pytest.mark.asyncio
    async def test_type_text_clears_and_types(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test type_text clears input and types text."""
        await scraper_with_page.type_text("input.search", "hello")

        mock_page.fill.assert_called_once_with("input.search", "")
        mock_page.type.assert_called_once_with("input.search", "hello", delay=50)

    @pytest.mark.asyncio
    async def test_type_text_with_custom_delay(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test type_text with custom delay."""
        await scraper_with_page.type_text("input", "text", delay_per_char=100)

        mock_page.type.assert_called_once_with("input", "text", delay=100)

    @pytest.mark.asyncio
    async def test_get_text_returns_content(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test get_text returns element text content."""
        mock_element = AsyncMock()
        mock_element.text_content = AsyncMock(return_value="Hello World")
        mock_page.query_selector.return_value = mock_element

        text = await scraper_with_page.get_text("span.title")

        assert text == "Hello World"

    @pytest.mark.asyncio
    async def test_get_text_returns_empty_for_none(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test get_text returns empty string for None content."""
        mock_element = AsyncMock()
        mock_element.text_content = AsyncMock(return_value=None)
        mock_page.query_selector.return_value = mock_element

        text = await scraper_with_page.get_text("span.empty")

        assert text == ""

    @pytest.mark.asyncio
    async def test_get_text_raises_for_missing_element(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test get_text raises ElementNotFoundError for missing element."""
        mock_page.query_selector.return_value = None

        with pytest.raises(ElementNotFoundError, match="Element not found"):
            await scraper_with_page.get_text("span.missing")

    @pytest.mark.asyncio
    async def test_screenshot_saves_to_path(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test screenshot saves to specified path."""
        await scraper_with_page.screenshot("test.png")

        mock_page.screenshot.assert_called_once_with(path="test.png", full_page=False)

    @pytest.mark.asyncio
    async def test_screenshot_full_page(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test screenshot with full_page option."""
        await scraper_with_page.screenshot("full.png", full_page=True)

        mock_page.screenshot.assert_called_once_with(path="full.png", full_page=True)

    @pytest.mark.asyncio
    async def test_get_attribute_returns_value(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test get_attribute returns attribute value."""
        mock_element = AsyncMock()
        mock_element.get_attribute = AsyncMock(return_value="https://example.com")
        mock_page.query_selector.return_value = mock_element

        value = await scraper_with_page.get_attribute("a.link", "href")

        assert value == "https://example.com"

    @pytest.mark.asyncio
    async def test_get_attribute_raises_for_missing_element(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test get_attribute raises for missing element."""
        mock_page.query_selector.return_value = None

        with pytest.raises(ElementNotFoundError, match="Element not found"):
            await scraper_with_page.get_attribute("a.missing", "href")

    @pytest.mark.asyncio
    async def test_query_selector_all_returns_list(
        self, scraper_with_page: ConcreteScraper, mock_page: AsyncMock
    ) -> None:
        """Test query_selector_all returns list of elements."""
        mock_elements = [MagicMock(), MagicMock()]
        mock_page.query_selector_all.return_value = mock_elements

        elements = await scraper_with_page.query_selector_all("div.item")

        assert elements == mock_elements

    @pytest.mark.asyncio
    async def test_is_connected_true_with_browser_and_page(
        self, scraper_with_page: ConcreteScraper
    ) -> None:
        """Test is_connected is True when browser and page exist."""
        assert scraper_with_page.is_connected is True


class TestBrowserSession:
    """Tests for browser_session context manager."""

    @pytest.mark.asyncio
    async def test_browser_session_context_manager(self) -> None:
        """Test browser_session sets up and tears down correctly."""
        scraper = ConcreteScraper()

        with patch.object(scraper, "_setup_browser", new_callable=AsyncMock) as setup:
            with patch.object(
                scraper, "_teardown_browser", new_callable=AsyncMock
            ) as teardown:
                # Mock page after setup
                async def set_page():
                    scraper._page = AsyncMock()

                setup.side_effect = set_page

                async with scraper.browser_session() as page:
                    assert page is not None
                    setup.assert_called_once()

                teardown.assert_called_once()

    @pytest.mark.asyncio
    async def test_browser_session_raises_if_page_not_set(self) -> None:
        """Test browser_session raises if page is None after setup."""
        scraper = ConcreteScraper()

        with patch.object(scraper, "_setup_browser", new_callable=AsyncMock):
            with patch.object(scraper, "_teardown_browser", new_callable=AsyncMock):
                with pytest.raises(ScraperError, match="Failed to initialize"):
                    async with scraper.browser_session():
                        pass


class TestExceptionClasses:
    """Tests for exception classes."""

    def test_scraper_error_is_exception(self) -> None:
        """Test ScraperError inherits from Exception."""
        assert issubclass(ScraperError, Exception)

    def test_navigation_error_is_scraper_error(self) -> None:
        """Test NavigationError inherits from ScraperError."""
        assert issubclass(NavigationError, ScraperError)

    def test_element_not_found_error_is_scraper_error(self) -> None:
        """Test ElementNotFoundError inherits from ScraperError."""
        assert issubclass(ElementNotFoundError, ScraperError)
