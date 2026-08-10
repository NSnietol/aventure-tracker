"""Instagram scraper using Instaloader with Playwright fallback."""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from aventure_tracker.models.activity import InstagramAccountConfig, InstagramPost
from aventure_tracker.scrapers.base import BaseScraper, ScraperError

# Try to import instaloader
try:
    import instaloader
    from instaloader import Profile, Post

    INSTALOADER_AVAILABLE = True
except ImportError:
    INSTALOADER_AVAILABLE = False
    instaloader = None  # type: ignore

logger = logging.getLogger(__name__)


class InstagramScraperError(ScraperError):
    """Instagram-specific scraper error."""

    pass


class RateLimitError(InstagramScraperError):
    """Rate limit reached on Instagram."""

    pass


class LoginRequiredError(InstagramScraperError):
    """Login is required to access content."""

    pass


class InstagramScraper(BaseScraper):
    """Scraper for Instagram posts using Instaloader and Playwright fallback.

    Uses Instaloader as the primary method (faster, no browser needed).
    Falls back to Playwright when Instaloader fails (rate limits, login walls).

    Attributes:
        max_posts: Maximum number of posts to fetch per account.
    """

    # Instagram profile URL pattern
    PROFILE_URL = "https://www.instagram.com/{username}/"

    # CSS selectors for Playwright fallback
    POST_LINK_SELECTOR = "a[href*='/p/']"
    POST_IMAGE_SELECTOR = "img[src*='instagram']"
    LOGIN_WALL_SELECTOR = "[role='dialog'] button, [class*='LoginButton']"

    def __init__(
        self,
        max_posts: int = 10,
        session_file: Path | None = None,
        headless: bool = True,
    ) -> None:
        """Initialize Instagram scraper.

        Args:
            max_posts: Maximum posts to fetch per account.
            session_file: Path to Instaloader session file for authenticated requests.
            headless: Run Playwright in headless mode.
        """
        super().__init__(headless=headless)
        self._max_posts = max_posts
        self._session_file = session_file
        self._loader: Any = None

        if INSTALOADER_AVAILABLE:
            self._init_instaloader()

    def _init_instaloader(self) -> None:
        """Initialize Instaloader instance."""
        self._loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            quiet=True,
        )

        # Load session if available
        if self._session_file and self._session_file.exists():
            try:
                self._loader.load_session_from_file(
                    username=None,
                    filename=str(self._session_file),
                )
                logger.info("Loaded Instaloader session")
            except Exception as e:
                logger.warning(f"Could not load session: {e}")

    async def scrape(
        self,
        account: InstagramAccountConfig,
        since: datetime | None = None,
    ) -> list[InstagramPost]:
        """Scrape posts from an Instagram account.

        Args:
            account: Account configuration.
            since: Only get posts newer than this datetime.

        Returns:
            List of InstagramPost objects.

        Raises:
            InstagramScraperError: If scraping fails.
        """
        logger.info(f"Scraping Instagram: @{account.username}")

        # Try Instaloader first
        if INSTALOADER_AVAILABLE and self._loader:
            try:
                posts = await self._scrape_with_instaloader(account, since)
                if posts:
                    return posts
            except RateLimitError:
                logger.warning("Instaloader rate limited, trying Playwright")
            except LoginRequiredError:
                logger.warning("Login required, trying Playwright")
            except Exception as e:
                logger.warning(f"Instaloader failed: {e}, trying Playwright")

        # Fallback to Playwright
        return await self._scrape_with_playwright(account, since)

    async def _scrape_with_instaloader(
        self,
        account: InstagramAccountConfig,
        since: datetime | None = None,
    ) -> list[InstagramPost]:
        """Scrape using Instaloader library.

        Args:
            account: Account configuration.
            since: Only get posts newer than this datetime.

        Returns:
            List of InstagramPost objects.
        """
        posts: list[InstagramPost] = []

        try:
            profile = Profile.from_username(
                self._loader.context,
                account.username,
            )

            count = 0
            for post in profile.get_posts():
                if count >= self._max_posts:
                    break

                # Skip old posts
                if since and post.date_utc < since:
                    continue

                instagram_post = self._convert_instaloader_post(post)
                posts.append(instagram_post)
                count += 1

            logger.info(f"Instaloader: found {len(posts)} posts for @{account.username}")

        except instaloader.exceptions.ProfileNotExistsException:
            raise InstagramScraperError(f"Profile not found: @{account.username}")
        except instaloader.exceptions.LoginRequiredException:
            raise LoginRequiredError(f"Login required for @{account.username}")
        except instaloader.exceptions.TooManyRequestsException:
            raise RateLimitError("Instagram rate limit reached")
        except Exception as e:
            logger.error(f"Instaloader error: {e}")
            raise InstagramScraperError(f"Instaloader failed: {e}") from e

        return posts

    def _convert_instaloader_post(self, post: Any) -> InstagramPost:
        """Convert Instaloader Post to InstagramPost.

        Args:
            post: Instaloader Post object.

        Returns:
            InstagramPost dataclass.
        """
        # Get image URLs
        image_urls: list[str] = []
        if post.typename == "GraphSidecar":
            # Multiple images
            for node in post.get_sidecar_nodes():
                if not node.is_video:
                    image_urls.append(node.display_url)
        elif not post.is_video:
            image_urls.append(post.url)

        return InstagramPost(
            id=post.shortcode,
            url=f"https://www.instagram.com/p/{post.shortcode}/",
            image_urls=image_urls,
            caption=post.caption or "",
            timestamp=post.date_utc,
        )

    async def _scrape_with_playwright(
        self,
        account: InstagramAccountConfig,
        since: datetime | None = None,
    ) -> list[InstagramPost]:
        """Fallback scraping using Playwright.

        Note: This method has limitations due to Instagram's anti-scraping measures.
        It may not get full post details.

        Args:
            account: Account configuration.
            since: Only get posts newer than this datetime (not fully supported).

        Returns:
            List of InstagramPost objects.
        """
        posts: list[InstagramPost] = []

        async with self.browser_session() as page:
            try:
                profile_url = self.PROFILE_URL.format(username=account.username)
                await self.navigate(profile_url, wait_until="networkidle")

                # Check for login wall
                login_wall = await page.query_selector(self.LOGIN_WALL_SELECTOR)
                if login_wall:
                    # Try to dismiss by clicking outside
                    await page.keyboard.press("Escape")
                    await self._add_human_delay(500, 1000)

                # Wait for posts to load
                await self._add_human_delay(1000, 2000)

                # Extract post links
                post_links = await page.query_selector_all(self.POST_LINK_SELECTOR)

                seen_shortcodes: set[str] = set()
                for link in post_links[: self._max_posts * 2]:  # Get extra in case of duplicates
                    if len(posts) >= self._max_posts:
                        break

                    try:
                        href = await link.get_attribute("href")
                        if not href or "/p/" not in href:
                            continue

                        # Extract shortcode from URL
                        shortcode = self._extract_shortcode(href)
                        if not shortcode or shortcode in seen_shortcodes:
                            continue

                        seen_shortcodes.add(shortcode)

                        # Get basic post info
                        post = InstagramPost(
                            id=shortcode,
                            url=f"https://www.instagram.com/p/{shortcode}/",
                            image_urls=[],  # Would need to navigate to each post
                            caption="",
                            timestamp=datetime.now(),  # Timestamp not available without navigating
                        )
                        posts.append(post)

                    except Exception as e:
                        logger.debug(f"Error extracting post: {e}")
                        continue

                logger.info(
                    f"Playwright: found {len(posts)} posts for @{account.username}"
                )

            except Exception as e:
                logger.error(f"Playwright scraping failed: {e}")
                raise InstagramScraperError(f"Playwright failed: {e}") from e

        return posts

    def _extract_shortcode(self, url: str) -> str | None:
        """Extract post shortcode from URL.

        Args:
            url: Instagram URL like /p/ABC123/ or https://instagram.com/p/ABC123/

        Returns:
            Shortcode string or None.
        """
        match = re.search(r"/p/([A-Za-z0-9_-]+)", url)
        return match.group(1) if match else None

    async def get_post_details(
        self,
        shortcode: str,
    ) -> InstagramPost | None:
        """Get detailed information for a specific post.

        Args:
            shortcode: Instagram post shortcode.

        Returns:
            InstagramPost with full details or None.
        """
        if INSTALOADER_AVAILABLE and self._loader:
            try:
                post = Post.from_shortcode(self._loader.context, shortcode)
                return self._convert_instaloader_post(post)
            except Exception as e:
                logger.warning(f"Could not get post details: {e}")

        # Fallback: return basic post info
        return InstagramPost(
            id=shortcode,
            url=f"https://www.instagram.com/p/{shortcode}/",
            image_urls=[],
            caption="",
            timestamp=datetime.now(),
        )

    async def get_recent_posts(
        self,
        accounts: list[InstagramAccountConfig],
        since: datetime | None = None,
    ) -> dict[str, list[InstagramPost]]:
        """Get recent posts from multiple accounts.

        Args:
            accounts: List of account configurations.
            since: Only get posts newer than this datetime.

        Returns:
            Dictionary mapping usernames to lists of posts.
        """
        results: dict[str, list[InstagramPost]] = {}

        for account in accounts:
            if not account.enabled:
                continue

            try:
                posts = await self.scrape(account, since)
                results[account.username] = posts
            except Exception as e:
                logger.error(f"Failed to scrape @{account.username}: {e}")
                results[account.username] = []

            # Add delay between accounts to avoid rate limiting
            await self._add_human_delay(2000, 5000)

        return results

    def is_instaloader_available(self) -> bool:
        """Check if Instaloader is available and configured."""
        return INSTALOADER_AVAILABLE and self._loader is not None
