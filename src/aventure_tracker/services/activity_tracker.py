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
from aventure_tracker.services.activity_history import ActivityHistoryManager
from aventure_tracker.services.event_extractor import extract_event_info
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
        event_id: Unique event identifier (date + name slug).
        event_name: Human-readable event name.
        event_date: Event date (ISO format) or None.
    """

    post: InstagramPost
    account: InstagramAccountConfig
    extracted: ExtractedActivity | None
    match: MatchResult
    event_id: str = ""
    event_name: str = ""
    event_date: str | None = None

    @property
    def destination(self) -> str | None:
        """Get the matched/blacklisted destination."""
        return self.match.matched_blacklist

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
        posts_skipped: Posts skipped due to history limit (max 3 checks).
        alerts_generated: Number of alerts for non-blacklisted activities.
        notifications_sent: Number of notifications sent.
        errors: List of error messages.
    """

    accounts_checked: int
    posts_found: int
    posts_processed: int
    posts_skipped: int
    alerts_generated: int
    notifications_sent: int
    errors: list[str]


class ActivityTrackerService:
    """Service for tracking Instagram adventure activities.

    Orchestrates Instagram scraping, OCR processing, blacklist filtering,
    and notification sending for adventure activities.

    Uses blacklist-only approach: all activities are shown EXCEPT those
    matching the blacklist (destinations you've visited or don't want).

    Tracks post history to avoid checking the same post more than 3 times.

    Attributes:
        accounts_config_path: Path to accounts.yaml configuration.
        destinations_config_path: Path to destinations.yaml (blacklist config).
        use_ocr: Whether to use OCR for image processing.
    """

    def __init__(
        self,
        accounts_config_path: Path,
        destinations_config_path: Path | None = None,
        state_manager: StateManager | None = None,
        notifier: TelegramNotifier | None = None,
        scraper: InstagramScraper | None = None,
        ocr_processor: OCRProcessor | None = None,
        history_manager: ActivityHistoryManager | None = None,
        use_ocr: bool = True,
        max_posts_per_account: int = 10,
        # Legacy params for backward compatibility
        wishlist_config_path: Path | None = None,
        done_config_path: Path | None = None,
    ) -> None:
        """Initialize the activity tracker service.

        Args:
            accounts_config_path: Path to accounts.yaml.
            destinations_config_path: Path to destinations.yaml (blacklist config).
            state_manager: StateManager for persistence (optional).
            notifier: TelegramNotifier for alerts (optional).
            scraper: InstagramScraper instance (optional).
            ocr_processor: OCRProcessor instance (optional).
            history_manager: ActivityHistoryManager for post history (optional).
            use_ocr: Whether to use OCR processing.
            max_posts_per_account: Maximum posts to fetch per account.
            wishlist_config_path: DEPRECATED - ignored.
            done_config_path: DEPRECATED - ignored.
        """
        self._accounts_config_path = accounts_config_path
        self._state_manager = state_manager
        self._notifier = notifier
        self._scraper = scraper
        self._ocr_processor = ocr_processor
        self._history_manager = history_manager
        self._use_ocr = use_ocr
        self._max_posts = max_posts_per_account

        # Log deprecation warnings for legacy params
        if wishlist_config_path:
            logger.warning("wishlist_config_path is deprecated, use destinations_config_path")
        if done_config_path:
            logger.warning("done_config_path is deprecated, use destinations_config_path")

        self._accounts: AccountsConfig | None = None
        self._inventory = InventoryManager(
            destinations_path=destinations_config_path,
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

    def _get_history_manager(self) -> ActivityHistoryManager | None:
        """Get or create the history manager."""
        if self._history_manager is None:
            self._history_manager = ActivityHistoryManager()
            self._history_manager.load()
        return self._history_manager

    async def track_activities(
        self,
        since: datetime | None = None,
    ) -> ActivityTrackerResult:
        """Run the activity tracking process.

        Scrapes Instagram accounts, processes images with OCR, matches
        against wishlist, and sends notifications for new activities.

        Posts are limited to 3 checks before being skipped permanently.

        Args:
            since: Only process posts newer than this datetime.

        Returns:
            ActivityTrackerResult with tracking statistics.
        """
        accounts = self._load_accounts()
        scraper = self._get_scraper()
        ocr = self._get_ocr_processor()
        history = self._get_history_manager()

        self._inventory.load()

        result = ActivityTrackerResult(
            accounts_checked=0,
            posts_found=0,
            posts_processed=0,
            posts_skipped=0,
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
                    # Check history limit (max 3 checks per post)
                    if history and not history.should_check(account.username, post.id):
                        logger.debug(
                            f"Skipping post {post.id} - already checked 3 times"
                        )
                        result.posts_skipped += 1
                        continue

                    # Skip if we've seen this post before (legacy state manager check)
                    if self._is_post_seen(post.id):
                        continue

                    result.posts_processed += 1

                    # Process with OCR if available and post has images
                    extracted = await self._process_post_ocr(post, ocr)

                    # Extract event info for history tracking
                    ocr_text = extracted.raw_text if extracted else None
                    event_info = extract_event_info(post.caption or "", ocr_text)

                    # Match against inventory
                    match = self._inventory.match_post(post, extracted)

                    # Record the check in history
                    if history:
                        history.record_check(
                            account=account.username,
                            post_id=post.id,
                            event_id=event_info.event_id,
                            event_name=event_info.event_name,
                            event_date=event_info.event_date,
                            matched_wishlist=match.should_notify,  # True if not blacklisted
                            destination=match.matched_blacklist,  # Blacklisted destination if any
                        )

                    # Generate alert if activity should be notified (not blacklisted)
                    if match.should_notify:
                        alert = ActivityAlert(
                            post=post,
                            account=account,
                            extracted=extracted,
                            match=match,
                            event_id=event_info.event_id,
                            event_name=event_info.event_name,
                            event_date=event_info.event_date,
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

        # Save history after processing
        if history:
            history.save()

        logger.info(
            f"Activity tracking complete: {result.accounts_checked} accounts, "
            f"{result.posts_found} posts, {result.posts_skipped} skipped, "
            f"{result.alerts_generated} alerts"
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
        history = self._get_history_manager()
        self._inventory.load()

        alerts: list[ActivityAlert] = []

        try:
            posts = await scraper.scrape(account, since)

            for post in posts:
                # Check history limit
                if history and not history.should_check(account.username, post.id):
                    continue

                if self._is_post_seen(post.id):
                    continue

                extracted = await self._process_post_ocr(post, ocr)
                ocr_text = extracted.raw_text if extracted else None
                event_info = extract_event_info(post.caption or "", ocr_text)
                match = self._inventory.match_post(post, extracted)

                # Record the check
                if history:
                    history.record_check(
                        account=account.username,
                        post_id=post.id,
                        event_id=event_info.event_id,
                        event_name=event_info.event_name,
                        event_date=event_info.event_date,
                        matched_wishlist=match.should_notify,  # True if not blacklisted
                        destination=match.matched_blacklist,  # Blacklisted destination if any
                    )

                # Generate alert if activity should be notified (not blacklisted)
                if match.should_notify:
                    alert = ActivityAlert(
                        post=post,
                        account=account,
                        extracted=extracted,
                        match=match,
                        event_id=event_info.event_id,
                        event_name=event_info.event_name,
                        event_date=event_info.event_date,
                    )
                    alerts.append(alert)

                self._mark_post_seen(post.id)

            # Save history after checking
            if history:
                history.save()

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

    def get_blacklisted_destinations(self) -> list[str]:
        """Get list of blacklisted destinations.

        Returns:
            List of blacklisted destination names.
        """
        self._inventory.load()
        return self._inventory.destinations.get_all_blacklisted()

    def get_account_history_stats(self, account: str) -> dict[str, int]:
        """Get history statistics for an account.

        Args:
            account: Instagram username.

        Returns:
            Dict with 'total', 'skipped', 'active' counts.
        """
        history = self._get_history_manager()
        if history is None:
            return {"total": 0, "skipped": 0, "active": 0}

        records = history.get_account_history(account)
        skipped = history.get_skipped_count(account)

        return {
            "total": len(records),
            "skipped": skipped,
            "active": len(records) - skipped,
        }

    async def save_state(self) -> None:
        """Save state to persistence."""
        if self._state_manager:
            await self._state_manager.save()

        # Also save inventory if modified
        self._inventory.save()

        # Save history
        if self._history_manager:
            self._history_manager.save()
