"""Base scraper with Playwright stealth for anti-detection."""

import logging
import random
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

# Try to import playwright_stealth, but make it optional
# Some Python versions have issues with pkg_resources dependency
try:
    from playwright_stealth import stealth_async

    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    stealth_async = None  # type: ignore

logger = logging.getLogger(__name__)

# Default user agents for rotation
DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

# Default viewport sizes for variation
DEFAULT_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
]

# Default timeouts
DEFAULT_TIMEOUT_MS = 30000
DEFAULT_NAVIGATION_TIMEOUT_MS = 60000


class ScraperError(Exception):
    """Base exception for scraper errors."""

    pass


class NavigationError(ScraperError):
    """Error during page navigation."""

    pass


class ElementNotFoundError(ScraperError):
    """Element not found on the page."""

    pass


class ScraperTimeoutError(ScraperError):
    """Timeout during scraping operation."""

    pass


class BaseScraper(ABC):
    """Base class for all scrapers with Playwright stealth support.

    Provides common functionality for browser automation including:
    - Stealth mode to avoid detection
    - User agent rotation
    - Viewport randomization
    - Human-like delays
    - Screenshot capture on errors
    - Configurable timeouts
    - Trace recording for debugging

    Subclasses must implement the `scrape` method.
    """

    def __init__(
        self,
        headless: bool = True,
        slow_mo: int = 0,
        user_agents: list[str] | None = None,
        viewports: list[dict] | None = None,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        navigation_timeout_ms: int = DEFAULT_NAVIGATION_TIMEOUT_MS,
        trace_enabled: bool = False,
        trace_dir: Path | None = None,
    ) -> None:
        """Initialize the base scraper.

        Args:
            headless: Run browser in headless mode.
            slow_mo: Slow down operations by specified ms (useful for debugging).
            user_agents: List of user agents to rotate through.
            viewports: List of viewport sizes to use.
            timeout_ms: Default timeout for actions in milliseconds.
            navigation_timeout_ms: Timeout for page navigation in milliseconds.
            trace_enabled: Enable Playwright trace recording for debugging.
            trace_dir: Directory to save trace files (default: /tmp/playwright-traces).
        """
        self._headless = headless
        self._slow_mo = slow_mo
        self._user_agents = user_agents or DEFAULT_USER_AGENTS
        self._viewports = viewports or DEFAULT_VIEWPORTS
        self._timeout_ms = timeout_ms
        self._navigation_timeout_ms = navigation_timeout_ms
        self._trace_enabled = trace_enabled
        self._trace_dir = trace_dir or Path("/tmp/playwright-traces")

        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._trace_path: Path | None = None

    @property
    def page(self) -> Page | None:
        """Get the current page instance."""
        return self._page

    @property
    def is_connected(self) -> bool:
        """Check if browser is connected and page is available."""
        return self._browser is not None and self._page is not None

    @property
    def last_trace_path(self) -> Path | None:
        """Get the path to the last saved trace file."""
        return self._trace_path

    def _get_random_user_agent(self) -> str:
        """Get a random user agent from the list."""
        return random.choice(self._user_agents)

    def _get_random_viewport(self) -> dict:
        """Get a random viewport size from the list."""
        return random.choice(self._viewports)

    async def _add_human_delay(
        self,
        min_ms: int = 100,
        max_ms: int = 500,
    ) -> None:
        """Add a random delay to simulate human behavior.

        Args:
            min_ms: Minimum delay in milliseconds.
            max_ms: Maximum delay in milliseconds.
        """
        import asyncio

        delay = random.randint(min_ms, max_ms) / 1000
        await asyncio.sleep(delay)

    async def _setup_browser(self) -> None:
        """Set up the browser with stealth configuration."""
        playwright = await async_playwright().start()

        self._browser = await playwright.chromium.launch(
            headless=self._headless,
            slow_mo=self._slow_mo,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )

        viewport = self._get_random_viewport()
        user_agent = self._get_random_user_agent()

        self._context = await self._browser.new_context(
            viewport=viewport,
            user_agent=user_agent,
            locale="es-CO",
            timezone_id="America/Bogota",
            geolocation={"latitude": 10.9685, "longitude": -74.7813},  # Barranquilla
            permissions=["geolocation"],
        )

        self._context.set_default_timeout(self._timeout_ms)
        self._context.set_default_navigation_timeout(self._navigation_timeout_ms)

        self._page = await self._context.new_page()

        # Apply stealth mode if available
        if STEALTH_AVAILABLE and stealth_async is not None:
            await stealth_async(self._page)
            logger.debug("Stealth mode applied")
        else:
            logger.warning("playwright_stealth not available, running without stealth")

        # Start trace recording if enabled
        if self._trace_enabled:
            self._trace_dir.mkdir(parents=True, exist_ok=True)
            await self._context.tracing.start(
                screenshots=True,
                snapshots=True,
                sources=True,
            )
            logger.info("Trace recording started")

        logger.info(
            f"Browser setup complete: headless={self._headless}, "
            f"viewport={viewport['width']}x{viewport['height']}"
        )

    async def _teardown_browser(self) -> None:
        """Clean up browser resources."""
        # Stop trace recording if enabled
        if self._trace_enabled and self._context:
            try:
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                self._trace_path = self._trace_dir / f"trace-{timestamp}.zip"
                await self._context.tracing.stop(path=str(self._trace_path))
                logger.info(f"Trace saved to: {self._trace_path}")
            except Exception as e:
                logger.warning(f"Failed to save trace: {e}")

        if self._page:
            await self._page.close()
            self._page = None

        if self._context:
            await self._context.close()
            self._context = None

        if self._browser:
            await self._browser.close()
            self._browser = None

        logger.info("Browser teardown complete")

    @asynccontextmanager
    async def browser_session(self) -> AsyncGenerator[Page, None]:
        """Context manager for browser sessions.

        Automatically sets up and tears down the browser.

        Yields:
            The browser page instance.

        Raises:
            ScraperError: If browser setup fails.
        """
        try:
            await self._setup_browser()
            if self._page is None:
                raise ScraperError("Failed to initialize browser page")
            yield self._page
        finally:
            await self._teardown_browser()

    async def navigate(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
    ) -> None:
        """Navigate to a URL with error handling.

        Args:
            url: URL to navigate to.
            wait_until: When to consider navigation complete.
                Options: "commit", "domcontentloaded", "load", "networkidle"

        Raises:
            NavigationError: If navigation fails.
            ScraperError: If page is not initialized.
        """
        if self._page is None:
            raise ScraperError("Page not initialized. Use browser_session context.")

        try:
            await self._page.goto(url, wait_until=wait_until)
            await self._add_human_delay(200, 800)
            logger.debug(f"Navigated to: {url}")
        except Exception as e:
            logger.error(f"Navigation failed for {url}: {e}")
            raise NavigationError(f"Failed to navigate to {url}: {e}") from e

    async def wait_for_selector(
        self,
        selector: str,
        timeout_ms: int | None = None,
        state: str = "visible",
    ) -> None:
        """Wait for an element to be present.

        Args:
            selector: CSS selector to wait for.
            timeout_ms: Timeout in milliseconds.
            state: Element state to wait for.

        Raises:
            ElementNotFoundError: If element not found within timeout.
            ScraperError: If page is not initialized.
        """
        if self._page is None:
            raise ScraperError("Page not initialized. Use browser_session context.")

        try:
            await self._page.wait_for_selector(
                selector,
                timeout=timeout_ms or self._timeout_ms,
                state=state,
            )
        except Exception as e:
            logger.warning(f"Element not found: {selector}")
            raise ElementNotFoundError(f"Element not found: {selector}") from e

    async def click(
        self,
        selector: str,
        delay_before_ms: int = 100,
        delay_after_ms: int = 300,
    ) -> None:
        """Click an element with human-like delays.

        Args:
            selector: CSS selector to click.
            delay_before_ms: Delay before clicking.
            delay_after_ms: Delay after clicking.

        Raises:
            ElementNotFoundError: If element not found.
            ScraperError: If page is not initialized.
        """
        if self._page is None:
            raise ScraperError("Page not initialized. Use browser_session context.")

        await self._add_human_delay(delay_before_ms, delay_before_ms + 200)

        try:
            await self._page.click(selector)
            await self._add_human_delay(delay_after_ms, delay_after_ms + 200)
        except Exception as e:
            logger.warning(f"Failed to click: {selector}")
            raise ElementNotFoundError(f"Failed to click: {selector}") from e

    async def type_text(
        self,
        selector: str,
        text: str,
        delay_per_char: int = 50,
    ) -> None:
        """Type text into an element with human-like delay.

        Args:
            selector: CSS selector of the input.
            text: Text to type.
            delay_per_char: Delay between keystrokes in ms.

        Raises:
            ElementNotFoundError: If element not found.
            ScraperError: If page is not initialized.
        """
        if self._page is None:
            raise ScraperError("Page not initialized. Use browser_session context.")

        try:
            await self._page.fill(selector, "")  # Clear first
            await self._page.type(selector, text, delay=delay_per_char)
        except Exception as e:
            logger.warning(f"Failed to type in: {selector}")
            raise ElementNotFoundError(f"Failed to type in: {selector}") from e

    async def get_text(self, selector: str) -> str:
        """Get text content of an element.

        Args:
            selector: CSS selector of the element.

        Returns:
            Text content of the element.

        Raises:
            ElementNotFoundError: If element not found.
            ScraperError: If page is not initialized.
        """
        if self._page is None:
            raise ScraperError("Page not initialized. Use browser_session context.")

        try:
            element = await self._page.query_selector(selector)
            if element is None:
                raise ElementNotFoundError(f"Element not found: {selector}")
            text = await element.text_content()
            return text or ""
        except ElementNotFoundError:
            raise
        except Exception as e:
            logger.warning(f"Failed to get text from: {selector}")
            raise ElementNotFoundError(f"Failed to get text from: {selector}") from e

    async def screenshot(self, path: str, full_page: bool = False) -> None:
        """Take a screenshot of the current page.

        Args:
            path: File path to save screenshot.
            full_page: Whether to capture the full page.

        Raises:
            ScraperError: If page is not initialized or screenshot fails.
        """
        if self._page is None:
            raise ScraperError("Page not initialized. Use browser_session context.")

        try:
            await self._page.screenshot(path=path, full_page=full_page)
            logger.info(f"Screenshot saved to: {path}")
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            raise ScraperError(f"Screenshot failed: {e}") from e

    async def get_attribute(self, selector: str, attribute: str) -> str | None:
        """Get an attribute value from an element.

        Args:
            selector: CSS selector of the element.
            attribute: Attribute name to get.

        Returns:
            Attribute value or None if not found.

        Raises:
            ElementNotFoundError: If element not found.
            ScraperError: If page is not initialized.
        """
        if self._page is None:
            raise ScraperError("Page not initialized. Use browser_session context.")

        try:
            element = await self._page.query_selector(selector)
            if element is None:
                raise ElementNotFoundError(f"Element not found: {selector}")
            return await element.get_attribute(attribute)
        except ElementNotFoundError:
            raise
        except Exception as e:
            logger.warning(f"Failed to get attribute from: {selector}")
            raise ElementNotFoundError(f"Failed to get attribute: {attribute}") from e

    async def query_selector_all(self, selector: str) -> list:
        """Get all elements matching a selector.

        Args:
            selector: CSS selector.

        Returns:
            List of matching elements.

        Raises:
            ScraperError: If page is not initialized.
        """
        if self._page is None:
            raise ScraperError("Page not initialized. Use browser_session context.")

        return await self._page.query_selector_all(selector)

    @abstractmethod
    async def scrape(self, *args, **kwargs):
        """Main scraping method to be implemented by subclasses.

        Subclasses should implement this method with their specific
        scraping logic.
        """
        pass
