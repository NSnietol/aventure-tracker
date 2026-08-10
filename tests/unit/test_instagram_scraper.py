"""Tests for Instagram Scraper."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aventure_tracker.models.activity import InstagramAccountConfig, InstagramPost
from aventure_tracker.scrapers.instagram import InstagramScraper
from aventure_tracker.scrapers.instagram.scraper import (
    InstagramScraperError,
    LoginRequiredError,
    RateLimitError,
)


@pytest.fixture
def scraper() -> InstagramScraper:
    """Create an Instagram scraper instance."""
    return InstagramScraper(max_posts=5, headless=True)


@pytest.fixture
def account() -> InstagramAccountConfig:
    """Create a test account configuration."""
    return InstagramAccountConfig(
        username="testaccount",
        name="Test Account",
        enabled=True,
    )


@pytest.fixture
def mock_post() -> MagicMock:
    """Create a mock Instaloader post."""
    post = MagicMock()
    post.shortcode = "ABC123xyz"
    post.typename = "GraphImage"
    post.is_video = False
    post.url = "https://instagram.com/image.jpg"
    post.caption = "Test caption #adventure"
    post.date_utc = datetime(2025, 3, 15, 10, 30)
    return post


@pytest.fixture
def mock_page() -> AsyncMock:
    """Create a mock page object."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    return page


class TestInstagramScraperInit:
    """Tests for scraper initialization."""

    def test_default_initialization(self) -> None:
        """Test default initialization."""
        scraper = InstagramScraper()
        assert scraper._max_posts == 10
        assert scraper._headless is True
        assert scraper._session_file is None

    def test_custom_initialization(self) -> None:
        """Test custom initialization."""
        session_file = Path("/tmp/session.json")
        scraper = InstagramScraper(
            max_posts=20,
            session_file=session_file,
            headless=False,
        )
        assert scraper._max_posts == 20
        assert scraper._session_file == session_file
        assert scraper._headless is False

    def test_is_instaloader_available(self) -> None:
        """Test Instaloader availability check."""
        scraper = InstagramScraper()
        # Result depends on whether instaloader is installed
        result = scraper.is_instaloader_available()
        assert isinstance(result, bool)


class TestExtractShortcode:
    """Tests for shortcode extraction."""

    def test_extract_from_full_url(self, scraper: InstagramScraper) -> None:
        """Test extracting shortcode from full URL."""
        url = "https://www.instagram.com/p/ABC123xyz/"
        assert scraper._extract_shortcode(url) == "ABC123xyz"

    def test_extract_from_relative_url(self, scraper: InstagramScraper) -> None:
        """Test extracting shortcode from relative URL."""
        url = "/p/XYZ789abc/"
        assert scraper._extract_shortcode(url) == "XYZ789abc"

    def test_extract_with_query_params(self, scraper: InstagramScraper) -> None:
        """Test extracting shortcode with query parameters."""
        url = "/p/TEST123/?utm_source=ig_web"
        assert scraper._extract_shortcode(url) == "TEST123"

    def test_extract_with_underscores_and_dashes(
        self, scraper: InstagramScraper
    ) -> None:
        """Test extracting shortcode with underscores and dashes."""
        url = "/p/A-B_C-123/"
        assert scraper._extract_shortcode(url) == "A-B_C-123"

    def test_extract_invalid_url_returns_none(
        self, scraper: InstagramScraper
    ) -> None:
        """Test invalid URL returns None."""
        assert scraper._extract_shortcode("/profile/user/") is None
        assert scraper._extract_shortcode("https://instagram.com/") is None


class TestConvertInstaloaderPost:
    """Tests for converting Instaloader posts."""

    def test_convert_single_image_post(
        self, scraper: InstagramScraper, mock_post: MagicMock
    ) -> None:
        """Test converting single image post."""
        result = scraper._convert_instaloader_post(mock_post)

        assert result.id == "ABC123xyz"
        assert result.url == "https://www.instagram.com/p/ABC123xyz/"
        assert len(result.image_urls) == 1
        assert result.caption == "Test caption #adventure"
        assert result.timestamp == datetime(2025, 3, 15, 10, 30)

    def test_convert_video_post_no_images(
        self, scraper: InstagramScraper, mock_post: MagicMock
    ) -> None:
        """Test converting video post has no images."""
        mock_post.is_video = True
        result = scraper._convert_instaloader_post(mock_post)

        assert result.image_urls == []

    def test_convert_carousel_post(
        self, scraper: InstagramScraper, mock_post: MagicMock
    ) -> None:
        """Test converting carousel (sidecar) post."""
        mock_post.typename = "GraphSidecar"

        # Mock sidecar nodes
        node1 = MagicMock()
        node1.is_video = False
        node1.display_url = "https://instagram.com/image1.jpg"

        node2 = MagicMock()
        node2.is_video = True  # Video node, should be skipped

        node3 = MagicMock()
        node3.is_video = False
        node3.display_url = "https://instagram.com/image3.jpg"

        mock_post.get_sidecar_nodes.return_value = [node1, node2, node3]

        result = scraper._convert_instaloader_post(mock_post)

        assert len(result.image_urls) == 2
        assert "image1.jpg" in result.image_urls[0]
        assert "image3.jpg" in result.image_urls[1]

    def test_convert_post_without_caption(
        self, scraper: InstagramScraper, mock_post: MagicMock
    ) -> None:
        """Test converting post with None caption."""
        mock_post.caption = None
        result = scraper._convert_instaloader_post(mock_post)

        assert result.caption == ""


class TestExceptions:
    """Tests for exception classes."""

    def test_instagram_scraper_error_is_scraper_error(self) -> None:
        """Test InstagramScraperError inherits from ScraperError."""
        from aventure_tracker.scrapers.base import ScraperError

        assert issubclass(InstagramScraperError, ScraperError)

    def test_rate_limit_error(self) -> None:
        """Test RateLimitError."""
        error = RateLimitError("Rate limited")
        assert str(error) == "Rate limited"
        assert isinstance(error, InstagramScraperError)

    def test_login_required_error(self) -> None:
        """Test LoginRequiredError."""
        error = LoginRequiredError("Login required")
        assert str(error) == "Login required"
        assert isinstance(error, InstagramScraperError)


class TestScrapeWithPlaywright:
    """Tests for Playwright fallback scraping."""

    @pytest.mark.asyncio
    async def test_scrape_extracts_post_links(
        self,
        scraper: InstagramScraper,
        account: InstagramAccountConfig,
        mock_page: AsyncMock,
    ) -> None:
        """Test Playwright scraping extracts post links."""
        # Mock post links
        mock_link1 = AsyncMock()
        mock_link1.get_attribute.return_value = "/p/POST123/"

        mock_link2 = AsyncMock()
        mock_link2.get_attribute.return_value = "/p/POST456/"

        mock_page.query_selector_all.return_value = [mock_link1, mock_link2]

        with patch.object(scraper, "browser_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_page
            mock_session.return_value.__aexit__.return_value = None

            with patch.object(scraper, "navigate", new_callable=AsyncMock):
                with patch.object(scraper, "_add_human_delay", new_callable=AsyncMock):
                    posts = await scraper._scrape_with_playwright(account)

        assert len(posts) == 2
        assert posts[0].id == "POST123"
        assert posts[1].id == "POST456"

    @pytest.mark.asyncio
    async def test_scrape_handles_login_wall(
        self,
        scraper: InstagramScraper,
        account: InstagramAccountConfig,
        mock_page: AsyncMock,
    ) -> None:
        """Test Playwright handles login wall."""
        # Mock login wall present
        mock_page.query_selector.return_value = MagicMock()  # Login wall found
        mock_page.query_selector_all.return_value = []  # No posts

        with patch.object(scraper, "browser_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_page
            mock_session.return_value.__aexit__.return_value = None

            with patch.object(scraper, "navigate", new_callable=AsyncMock):
                with patch.object(scraper, "_add_human_delay", new_callable=AsyncMock):
                    posts = await scraper._scrape_with_playwright(account)

        # Should have tried to dismiss login wall
        mock_page.keyboard.press.assert_called_with("Escape")
        assert posts == []

    @pytest.mark.asyncio
    async def test_scrape_deduplicates_posts(
        self,
        scraper: InstagramScraper,
        account: InstagramAccountConfig,
        mock_page: AsyncMock,
    ) -> None:
        """Test Playwright deduplicates posts."""
        # Mock duplicate links
        mock_link1 = AsyncMock()
        mock_link1.get_attribute.return_value = "/p/SAME123/"

        mock_link2 = AsyncMock()
        mock_link2.get_attribute.return_value = "/p/SAME123/"  # Duplicate

        mock_page.query_selector_all.return_value = [mock_link1, mock_link2]

        with patch.object(scraper, "browser_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_page
            mock_session.return_value.__aexit__.return_value = None

            with patch.object(scraper, "navigate", new_callable=AsyncMock):
                with patch.object(scraper, "_add_human_delay", new_callable=AsyncMock):
                    posts = await scraper._scrape_with_playwright(account)

        assert len(posts) == 1


class TestScrapeMethod:
    """Tests for main scrape method."""

    @pytest.mark.asyncio
    async def test_scrape_uses_instaloader_first(
        self,
        scraper: InstagramScraper,
        account: InstagramAccountConfig,
    ) -> None:
        """Test scrape prefers Instaloader."""
        mock_posts = [
            InstagramPost(
                id="TEST1",
                url="https://instagram.com/p/TEST1/",
                image_urls=["https://img.com/1.jpg"],
                caption="Test",
                timestamp=datetime.now(),
            )
        ]

        with patch.object(
            scraper, "_scrape_with_instaloader", new_callable=AsyncMock
        ) as mock_insta:
            mock_insta.return_value = mock_posts

            posts = await scraper.scrape(account)

            mock_insta.assert_called_once()
            assert posts == mock_posts

    @pytest.mark.asyncio
    async def test_scrape_falls_back_to_playwright_on_rate_limit(
        self,
        scraper: InstagramScraper,
        account: InstagramAccountConfig,
    ) -> None:
        """Test scrape falls back to Playwright on rate limit."""
        playwright_posts = [
            InstagramPost(
                id="PW1",
                url="https://instagram.com/p/PW1/",
                image_urls=[],
                caption="",
                timestamp=datetime.now(),
            )
        ]

        with patch.object(
            scraper, "_scrape_with_instaloader", new_callable=AsyncMock
        ) as mock_insta:
            mock_insta.side_effect = RateLimitError("Rate limited")

            with patch.object(
                scraper, "_scrape_with_playwright", new_callable=AsyncMock
            ) as mock_pw:
                mock_pw.return_value = playwright_posts

                posts = await scraper.scrape(account)

                mock_insta.assert_called_once()
                mock_pw.assert_called_once()
                assert posts == playwright_posts


class TestGetRecentPosts:
    """Tests for get_recent_posts method."""

    @pytest.mark.asyncio
    async def test_get_recent_posts_multiple_accounts(
        self, scraper: InstagramScraper
    ) -> None:
        """Test getting posts from multiple accounts."""
        accounts = [
            InstagramAccountConfig(
                username="account1", name="Account 1", enabled=True
            ),
            InstagramAccountConfig(
                username="account2", name="Account 2", enabled=True
            ),
        ]

        posts_account1 = [
            InstagramPost(
                id="A1P1",
                url="https://instagram.com/p/A1P1/",
                image_urls=[],
                caption="",
                timestamp=datetime.now(),
            )
        ]
        posts_account2 = [
            InstagramPost(
                id="A2P1",
                url="https://instagram.com/p/A2P1/",
                image_urls=[],
                caption="",
                timestamp=datetime.now(),
            )
        ]

        with patch.object(scraper, "scrape", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = [posts_account1, posts_account2]

            with patch.object(scraper, "_add_human_delay", new_callable=AsyncMock):
                results = await scraper.get_recent_posts(accounts)

        assert "account1" in results
        assert "account2" in results
        assert results["account1"] == posts_account1
        assert results["account2"] == posts_account2

    @pytest.mark.asyncio
    async def test_get_recent_posts_skips_disabled(
        self, scraper: InstagramScraper
    ) -> None:
        """Test that disabled accounts are skipped."""
        accounts = [
            InstagramAccountConfig(
                username="enabled", name="Enabled", enabled=True
            ),
            InstagramAccountConfig(
                username="disabled", name="Disabled", enabled=False
            ),
        ]

        with patch.object(scraper, "scrape", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = []

            with patch.object(scraper, "_add_human_delay", new_callable=AsyncMock):
                results = await scraper.get_recent_posts(accounts)

        assert mock_scrape.call_count == 1  # Only enabled account
        assert "disabled" not in results or results["disabled"] == []

    @pytest.mark.asyncio
    async def test_get_recent_posts_handles_errors(
        self, scraper: InstagramScraper
    ) -> None:
        """Test error handling for individual accounts."""
        accounts = [
            InstagramAccountConfig(
                username="good", name="Good", enabled=True
            ),
            InstagramAccountConfig(
                username="bad", name="Bad", enabled=True
            ),
        ]

        with patch.object(scraper, "scrape", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = [
                [InstagramPost("G1", "url", [], "", datetime.now())],
                InstagramScraperError("Failed"),
            ]

            with patch.object(scraper, "_add_human_delay", new_callable=AsyncMock):
                results = await scraper.get_recent_posts(accounts)

        assert len(results["good"]) == 1
        assert results["bad"] == []


class TestGetPostDetails:
    """Tests for get_post_details method."""

    @pytest.mark.asyncio
    async def test_get_post_details_fallback(
        self, scraper: InstagramScraper
    ) -> None:
        """Test get_post_details returns basic info on failure."""
        # Force Instaloader to fail
        scraper._loader = None

        post = await scraper.get_post_details("TEST123")

        assert post is not None
        assert post.id == "TEST123"
        assert post.url == "https://www.instagram.com/p/TEST123/"
