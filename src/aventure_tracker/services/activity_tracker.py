"""Activity tracker service for monitoring Instagram adventure posts."""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aventure_tracker.infrastructure.notifier import TelegramNotifier
from aventure_tracker.infrastructure.state_manager import StateManager
from aventure_tracker.models.activity import (
    AccountsConfig,
    InstagramAccountConfig,
    InstagramPost,
)
from aventure_tracker.scrapers.instagram import InstagramScraper
from aventure_tracker.services.inventory import InventoryManager, MatchResult
from aventure_tracker.services.ocr import ExtractedActivity, OCRProcessor

logger = logging.getLogger(__name__)


@dataclass
class ActivityAlert:
    """Alert for a new adventure activity.

    Attributes:
        post: The Instagram post.
        account: Account that posted.
        extracted: OCR extracted information (if available).
        match: Inventory match result.
    """

    post: InstagramPost
    account: InstagramAccountConfig
    extracted: ExtractedActivity | None
    match: MatchResult

    @property
    def destination(self) -> str | None:
        """Get the matched destination."""
        return self.match.matched_destination

    @property
    def activity_name(self) -> str | None:
        """Get the activity name from OCR."""
        return self.extracted.activity_name if self.extracted else None

    @property
    def price(self) -> int | None:
        """Get the price from OCR."""
        return self.extracted.price if self.extracted else None


@dataclass
class ActivityTrackerResult:
    """Result of an activity tracking run.

    Attributes:
        accounts_checked: Number of accounts checked.
        posts_found: Total posts found across all accounts.
        posts_processed: Posts processed with OCR.
        alerts_generated: Number of alerts for wishlist matches.
        notifications_sent: Number of notifications sent.
        errors: List of error messages.
    """

    accounts_checked: int
    posts_found: int
    posts_processed: int
    alerts_generated: int
    notifications_sent: int
    errors: list[str]


class ActivityTrackerService:
    """Service for tracking Instagram adventure activities.

    Orchestrates Instagram scraping, OCR processing, inventory matching,
    and notification sending for adventure activities.

    Attributes:
        accounts_config_path: Path to accounts.yaml configuration.
        wishlist_config_path: Path to wishlist.yaml configuration.
        done_config_path: Path to done.yaml configuration.
        use_ocr: Whether to use OCR for image processing.
    """

    def __init__(
        self,
        accounts_config_path: Path,
        wishlist_config_path: Path | None = None,
        done_config_path: Path | None = None,
        state_manager: StateManager | None = None,
        notifier: TelegramNotifier | None = None,
        scraper: InstagramScraper | None = None,
        ocr_processor: OCRProcessor | None = None,
        use_ocr: bool = True,
        max_posts_per_account: int = 10,
    ) -> None:
        """Initialize the activity tracker service.

        Args:
            accounts_config_path: Path to accounts.yaml.
            wishlist_config_path: Path to wishlist.yaml.
            done_config_path: Path to done.yaml.
            state_manager: StateManager for persistence (optional).
            notifier: TelegramNotifier for alerts (optional).
            scraper: InstagramScraper instance (optional).
            ocr_processor: OCRProcessor instance (optional).
            use_ocr: Whether to use OCR processing.
            max_posts_per_account: Maximum posts to fetch per account.
        """
        self._accounts_config_path = accounts_config_path
        self._state_manager = state_manager
        self._notifier = notifier
        self._scraper = scraper
        self._ocr_processor = ocr_processor
        self._use_ocr = use_ocr
        self._max_posts = max_posts_per_account

        self._accounts: AccountsConfig | None = None
        self._inventory = InventoryManager(
            wishlist_path=wishlist_config_path,
            done_path=done_config_path,
        )

    def _load_accounts(self) -> AccountsConfig:
        """Load accounts configuration."""
        if self._accounts is None:
            self._accounts = AccountsConfig.from_yaml(self._accounts_config_path)
            logger.info(f"Loaded {len(self._accounts.accounts)} accounts")
        return self._accounts

    def _get_scraper(self) -> InstagramScraper:
        """Get or create the Instagram scraper."""
        if self._scraper is None:
            self._scraper = InstagramScraper(
                max_posts=self._max_posts,
                headless=True,
            )
        return self._scraper

    def _get_ocr_processor(self) -> OCRProcessor | None:
        """Get or create the OCR processor."""
        if not self._use_ocr:
            return None

        if self._ocr_processor is None:
            try:
                self._ocr_processor = OCRProcessor()
            except Exception as e:
                logger.warning(f"OCR not available: {e}")
                self._use_ocr = False
                return None

        return self._ocr_processor

    async def track_activities(
        self,
        since: datetime | None = None,
    ) -> ActivityTrackerResult:
        """Run the activity tracking process.

        Scrapes Instagram accounts, processes images with OCR, matches
        against wishlist, and sends notifications for new activities.

        Args:
            since: Only process posts newer than this datetime.

        Returns:
            ActivityTrackerResult with tracking statistics.
        """
        accounts = self._load_accounts()
        scraper = self._get_scraper()
        ocr = self._get_ocr_processor()

        self._inventory.load()

        result = ActivityTrackerResult(
            accounts_checked=0,
            posts_found=0,
            posts_processed=0,
            alerts_generated=0,
            notifications_sent=0,
            errors=[],
        )

        for account in accounts.enabled_accounts:
            logger.info(f"Checking account: @{account.username}")
            result.accounts_checked += 1

            try:
                posts = await scraper.scrape(account, since)
                result.posts_found += len(posts)

                for post in posts:
                    # Skip if we've seen this post before
                    if self._is_post_seen(post.id):
                        continue

                    result.posts_processed += 1

                    # Process with OCR if available and post has images
                    extracted = await self._process_post_ocr(post, ocr)

                    # Match against inventory
                    match = self._inventory.match_post(post, extracted)

                    # Generate alert if it's a new wishlist match
                    if match.is_wishlist_match and not match.is_already_done:
                        alert = ActivityAlert(
                            post=post,
                            account=account,
                            extracted=extracted,
                            match=match,
                        )
                        result.alerts_generated += 1

                        # Send notification
                        sent = await self._send_notification(alert)
                        if sent:
                            result.notifications_sent += 1

                    # Mark post as seen
                    self._mark_post_seen(post.id)

            except Exception as e:
                error_msg = f"Error processing @{account.username}: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        logger.info(
            f"Activity tracking complete: {result.accounts_checked} accounts, "
            f"{result.posts_found} posts, {result.alerts_generated} alerts"
        )

        return result

    async def check_account(
        self,
        account: InstagramAccountConfig,
        since: datetime | None = None,
    ) -> list[ActivityAlert]:
        """Check a specific account for new activities.

        Args:
            account: Account configuration.
            since: Only process posts newer than this datetime.

        Returns:
            List of ActivityAlert for wishlist matches.
        """
        scraper = self._get_scraper()
        ocr = self._get_ocr_processor()
        self._inventory.load()

        alerts: list[ActivityAlert] = []

        try:
            posts = await scraper.scrape(account, since)

            for post in posts:
                if self._is_post_seen(post.id):
                    continue

                extracted = await self._process_post_ocr(post, ocr)
                match = self._inventory.match_post(post, extracted)

                if match.is_wishlist_match and not match.is_already_done:
                    alert = ActivityAlert(
                        post=post,
                        account=account,
                        extracted=extracted,
                        match=match,
                    )
                    alerts.append(alert)

                self._mark_post_seen(post.id)

        except Exception as e:
            logger.error(f"Error checking @{account.username}: {e}")

        return alerts

    async def _process_post_ocr(
        self,
        post: InstagramPost,
        ocr: OCRProcessor | None,
    ) -> ExtractedActivity | None:
        """Process post images with OCR.

        Args:
            post: Instagram post.
            ocr: OCR processor (may be None).

        Returns:
            ExtractedActivity or None if OCR not available/failed.
        """
        if ocr is None or not post.has_images:
            return None

        try:
            # Process first image
            image_url = post.first_image_url
            if image_url:
                return ocr.extract_activity_from_url(image_url)
        except Exception as e:
            logger.warning(f"OCR failed for post {post.id}: {e}")

        return None

    def _is_post_seen(self, post_id: str) -> bool:
        """Check if a post has been seen before.

        Args:
            post_id: Instagram post ID.

        Returns:
            True if post was already processed.
        """
        if self._state_manager is None:
            return False

        return self._state_manager.is_post_seen(post_id)

    def _mark_post_seen(self, post_id: str) -> None:
        """Mark a post as seen.

        Args:
            post_id: Instagram post ID.
        """
        if self._state_manager is None:
            return

        self._state_manager.add_seen_post(post_id)

    async def _send_notification(self, alert: ActivityAlert) -> bool:
        """Send notification for an activity alert.

        Args:
            alert: Activity alert to notify about.

        Returns:
            True if notification was sent successfully.
        """
        if self._notifier is None:
            logger.info(
                f"Would notify: {alert.destination} from @{alert.account.username}"
            )
            return False

        try:
            await self._notifier.send_activity_alert(
                account=alert.account.username,
                destination=alert.destination or "Unknown",
                activity=alert.activity_name,
                price=alert.price,
                post_url=alert.post.url,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False

    def get_enabled_accounts(self) -> list[InstagramAccountConfig]:
        """Get list of enabled accounts.

        Returns:
            List of enabled account configurations.
        """
        accounts = self._load_accounts()
        return accounts.enabled_accounts

    def get_wishlist_destinations(self) -> list[str]:
        """Get list of wishlist destinations.

        Returns:
            List of destination names.
        """
        self._inventory.load()
        return self._inventory.wishlist.destinations

    async def save_state(self) -> None:
        """Save state to persistence."""
        if self._state_manager:
            await self._state_manager.save()

        # Also save inventory if modified
        self._inventory.save()
