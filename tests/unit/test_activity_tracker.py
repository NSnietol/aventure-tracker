"""Tests for Activity Tracker Service."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aventure_tracker.models.activity import (
    AccountsConfig,
    InstagramAccountConfig,
    InstagramPost,
)
from aventure_tracker.services.activity_tracker import (
    ActivityAlert,
    ActivityTrackerResult,
    ActivityTrackerService,
)
from aventure_tracker.services.inventory import MatchResult
from aventure_tracker.services.ocr import ExtractedActivity


@pytest.fixture
def accounts_config(tmp_path: Path) -> Path:
    """Create a temporary accounts config file."""
    config_path = tmp_path / "accounts.yaml"
    config_path.write_text(
        """
accounts:
  - username: adventure_co
    name: Adventure Company
    enabled: true
  - username: travel_deals
    name: Travel Deals
    enabled: true
  - username: disabled_account
    name: Disabled Account
    enabled: false
"""
    )
    return config_path


@pytest.fixture
def wishlist_config(tmp_path: Path) -> Path:
    """Create a temporary wishlist config file."""
    config_path = tmp_path / "wishlist.yaml"
    config_path.write_text(
        """
destinations:
  - Guatapé
  - Santa Marta
  - Cartagena
"""
    )
    return config_path


@pytest.fixture
def done_config(tmp_path: Path) -> Path:
    """Create a temporary done config file."""
    config_path = tmp_path / "done.yaml"
    config_path.write_text(
        """
done:
  - destination: Guatapé
    date: "2024-06-15"
"""
    )
    return config_path


@pytest.fixture
def account() -> InstagramAccountConfig:
    """Create a test account configuration."""
    return InstagramAccountConfig(
        username="adventure_co",
        name="Adventure Company",
        enabled=True,
    )


@pytest.fixture
def post() -> InstagramPost:
    """Create a test Instagram post."""
    return InstagramPost(
        id="12345",
        url="https://www.instagram.com/p/ABC123/",
        caption="Amazing trip to Guatapé! #travel",
        timestamp=datetime(2025, 1, 15, 10, 30),
        image_urls=["https://example.com/image1.jpg"],
    )


@pytest.fixture
def extracted_activity() -> ExtractedActivity:
    """Create a test extracted activity."""
    return ExtractedActivity(
        raw_text="Piedra del Peñol Tour - Guatapé $85.000",
        activity_name="Piedra del Peñol Tour",
        location="Guatapé",
        price=85000,
        date=None,
        contact_info="3001234567",
        confidence=0.85,
    )


@pytest.fixture
def match_result() -> MatchResult:
    """Create a test match result for wishlist match."""
    return MatchResult(
        is_wishlist_match=True,
        matched_destination="Guatapé",
        is_already_done=False,
        match_score=0.9,
    )


@pytest.fixture
def mock_state_manager() -> MagicMock:
    """Create a mock state manager."""
    manager = MagicMock()
    manager.is_post_seen.return_value = False
    manager.add_seen_post = MagicMock()
    manager.save = AsyncMock()
    return manager


@pytest.fixture
def mock_notifier() -> AsyncMock:
    """Create a mock notifier."""
    notifier = AsyncMock()
    notifier.send_activity_alert = AsyncMock()
    return notifier


@pytest.fixture
def mock_scraper(post: InstagramPost) -> AsyncMock:
    """Create a mock Instagram scraper."""
    scraper = AsyncMock()
    scraper.scrape = AsyncMock(return_value=[post])
    return scraper


@pytest.fixture
def mock_ocr(extracted_activity: ExtractedActivity) -> MagicMock:
    """Create a mock OCR processor."""
    ocr = MagicMock()
    ocr.extract_activity_from_url = MagicMock(return_value=extracted_activity)
    return ocr


@pytest.fixture
def service(
    accounts_config: Path,
    wishlist_config: Path,
    done_config: Path,
    mock_state_manager: MagicMock,
    mock_notifier: AsyncMock,
    mock_scraper: AsyncMock,
    mock_ocr: MagicMock,
) -> ActivityTrackerService:
    """Create an activity tracker service with mocked dependencies."""
    return ActivityTrackerService(
        accounts_config_path=accounts_config,
        wishlist_config_path=wishlist_config,
        done_config_path=done_config,
        state_manager=mock_state_manager,
        notifier=mock_notifier,
        scraper=mock_scraper,
        ocr_processor=mock_ocr,
        use_ocr=True,
        max_posts_per_account=10,
    )


class TestActivityTrackerServiceInit:
    """Tests for service initialization."""

    def test_init_with_paths(self, accounts_config: Path) -> None:
        """Test initialization with config paths."""
        service = ActivityTrackerService(
            accounts_config_path=accounts_config,
            max_posts_per_account=5,
        )
        assert service._accounts_config_path == accounts_config
        assert service._max_posts == 5

    def test_load_accounts(self, service: ActivityTrackerService) -> None:
        """Test accounts are loaded correctly."""
        accounts = service._load_accounts()

        assert len(accounts.accounts) == 3
        assert len(accounts.enabled_accounts) == 2


class TestActivityAlert:
    """Tests for ActivityAlert dataclass."""

    def test_create_activity_alert(
        self,
        post: InstagramPost,
        account: InstagramAccountConfig,
        extracted_activity: ExtractedActivity,
        match_result: MatchResult,
    ) -> None:
        """Test creating an activity alert."""
        alert = ActivityAlert(
            post=post,
            account=account,
            extracted=extracted_activity,
            match=match_result,
        )

        assert alert.post.id == "12345"
        assert alert.account.username == "adventure_co"
        assert alert.destination == "Guatapé"

    def test_activity_alert_properties(
        self,
        post: InstagramPost,
        account: InstagramAccountConfig,
        extracted_activity: ExtractedActivity,
        match_result: MatchResult,
    ) -> None:
        """Test activity alert properties."""
        alert = ActivityAlert(
            post=post,
            account=account,
            extracted=extracted_activity,
            match=match_result,
        )

        assert alert.activity_name == "Piedra del Peñol Tour"
        assert alert.price == 85000
        assert alert.destination == "Guatapé"

    def test_activity_alert_without_extracted(
        self,
        post: InstagramPost,
        account: InstagramAccountConfig,
        match_result: MatchResult,
    ) -> None:
        """Test activity alert without OCR extraction."""
        alert = ActivityAlert(
            post=post,
            account=account,
            extracted=None,
            match=match_result,
        )

        assert alert.activity_name is None
        assert alert.price is None


class TestCheckAccount:
    """Tests for checking individual accounts."""

    @pytest.mark.asyncio
    async def test_check_account_returns_alerts(
        self,
        service: ActivityTrackerService,
        account: InstagramAccountConfig,
    ) -> None:
        """Test check_account returns alerts for wishlist matches."""
        # Mock inventory to return wishlist match
        with patch.object(
            service._inventory,
            "match_post",
            return_value=MatchResult(
                is_wishlist_match=True,
                matched_destination="Guatapé",
                is_already_done=False,
                match_score=0.9,
            ),
        ):
            alerts = await service.check_account(account)

        assert len(alerts) == 1
        assert alerts[0].destination == "Guatapé"

    @pytest.mark.asyncio
    async def test_check_account_skips_seen_posts(
        self,
        service: ActivityTrackerService,
        account: InstagramAccountConfig,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test check_account skips already seen posts."""
        mock_state_manager.is_post_seen.return_value = True

        alerts = await service.check_account(account)

        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_check_account_skips_non_wishlist(
        self,
        service: ActivityTrackerService,
        account: InstagramAccountConfig,
    ) -> None:
        """Test check_account skips posts not matching wishlist."""
        with patch.object(
            service._inventory,
            "match_post",
            return_value=MatchResult(
                is_wishlist_match=False,
                matched_destination=None,
                is_already_done=False,
                match_score=0.0,
            ),
        ):
            alerts = await service.check_account(account)

        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_check_account_skips_already_done(
        self,
        service: ActivityTrackerService,
        account: InstagramAccountConfig,
    ) -> None:
        """Test check_account skips activities already done."""
        with patch.object(
            service._inventory,
            "match_post",
            return_value=MatchResult(
                is_wishlist_match=True,
                matched_destination="Guatapé",
                is_already_done=True,
                match_score=0.9,
            ),
        ):
            alerts = await service.check_account(account)

        assert len(alerts) == 0


class TestTrackActivities:
    """Tests for the main tracking flow."""

    @pytest.mark.asyncio
    async def test_track_activities_returns_result(
        self, service: ActivityTrackerService
    ) -> None:
        """Test track_activities returns ActivityTrackerResult."""
        with patch.object(
            service._inventory,
            "match_post",
            return_value=MatchResult(
                is_wishlist_match=False,
                matched_destination=None,
                is_already_done=False,
                match_score=0.0,
            ),
        ):
            result = await service.track_activities()

        assert isinstance(result, ActivityTrackerResult)
        assert result.accounts_checked == 2  # 2 enabled accounts
        assert result.posts_found == 2  # 1 post per account

    @pytest.mark.asyncio
    async def test_track_activities_generates_alerts(
        self,
        service: ActivityTrackerService,
    ) -> None:
        """Test track_activities generates alerts for wishlist matches."""
        with patch.object(
            service._inventory,
            "match_post",
            return_value=MatchResult(
                is_wishlist_match=True,
                matched_destination="Guatapé",
                is_already_done=False,
                match_score=0.9,
            ),
        ):
            result = await service.track_activities()

        assert result.alerts_generated == 2  # 1 per enabled account

    @pytest.mark.asyncio
    async def test_track_activities_sends_notifications(
        self,
        service: ActivityTrackerService,
        mock_notifier: AsyncMock,
    ) -> None:
        """Test track_activities sends notifications for alerts."""
        with patch.object(
            service._inventory,
            "match_post",
            return_value=MatchResult(
                is_wishlist_match=True,
                matched_destination="Guatapé",
                is_already_done=False,
                match_score=0.9,
            ),
        ):
            result = await service.track_activities()

        assert result.notifications_sent == 2
        mock_notifier.send_activity_alert.assert_called()

    @pytest.mark.asyncio
    async def test_track_activities_handles_scraper_error(
        self,
        service: ActivityTrackerService,
        mock_scraper: AsyncMock,
    ) -> None:
        """Test track_activities handles scraper errors."""
        mock_scraper.scrape.side_effect = Exception("Scraper failed")

        result = await service.track_activities()

        assert len(result.errors) == 2  # Error for each account
        assert "Scraper failed" in result.errors[0]

    @pytest.mark.asyncio
    async def test_track_activities_marks_posts_seen(
        self,
        service: ActivityTrackerService,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test track_activities marks posts as seen."""
        with patch.object(
            service._inventory,
            "match_post",
            return_value=MatchResult(
                is_wishlist_match=False,
                matched_destination=None,
                is_already_done=False,
                match_score=0.0,
            ),
        ):
            await service.track_activities()

        mock_state_manager.add_seen_post.assert_called()


class TestProcessPostOCR:
    """Tests for OCR processing."""

    @pytest.mark.asyncio
    async def test_process_post_with_ocr(
        self,
        service: ActivityTrackerService,
        post: InstagramPost,
        mock_ocr: MagicMock,
    ) -> None:
        """Test OCR processing of post images."""
        result = await service._process_post_ocr(post, mock_ocr)

        assert result is not None
        assert result.activity_name == "Piedra del Peñol Tour"
        mock_ocr.extract_activity_from_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_post_without_ocr(
        self,
        service: ActivityTrackerService,
        post: InstagramPost,
    ) -> None:
        """Test processing without OCR returns None."""
        result = await service._process_post_ocr(post, None)

        assert result is None

    @pytest.mark.asyncio
    async def test_process_post_without_images(
        self,
        service: ActivityTrackerService,
        mock_ocr: MagicMock,
    ) -> None:
        """Test processing post without images returns None."""
        post_no_images = InstagramPost(
            id="12345",
            url="https://www.instagram.com/p/ABC123/",
            caption="No images here",
            timestamp=datetime(2025, 1, 15),
            image_urls=[],
        )

        result = await service._process_post_ocr(post_no_images, mock_ocr)

        assert result is None
        mock_ocr.extract_activity_from_url.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_post_ocr_handles_error(
        self,
        service: ActivityTrackerService,
        post: InstagramPost,
        mock_ocr: MagicMock,
    ) -> None:
        """Test OCR error is handled gracefully."""
        mock_ocr.extract_activity_from_url.side_effect = Exception("OCR failed")

        result = await service._process_post_ocr(post, mock_ocr)

        assert result is None


class TestPostSeenTracking:
    """Tests for seen post tracking."""

    def test_is_post_seen_with_manager(
        self,
        service: ActivityTrackerService,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test checking if post is seen."""
        mock_state_manager.is_post_seen.return_value = True

        assert service._is_post_seen("12345") is True
        mock_state_manager.is_post_seen.assert_called_with("12345")

    def test_is_post_seen_without_manager(self, accounts_config: Path) -> None:
        """Test is_post_seen returns False without manager."""
        service = ActivityTrackerService(accounts_config_path=accounts_config)

        assert service._is_post_seen("12345") is False

    def test_mark_post_seen(
        self,
        service: ActivityTrackerService,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test marking post as seen."""
        service._mark_post_seen("12345")

        mock_state_manager.add_seen_post.assert_called_with("12345")


class TestSendNotification:
    """Tests for notification sending."""

    @pytest.mark.asyncio
    async def test_send_notification_calls_notifier(
        self,
        service: ActivityTrackerService,
        post: InstagramPost,
        account: InstagramAccountConfig,
        extracted_activity: ExtractedActivity,
        match_result: MatchResult,
        mock_notifier: AsyncMock,
    ) -> None:
        """Test notification is sent via notifier."""
        alert = ActivityAlert(
            post=post,
            account=account,
            extracted=extracted_activity,
            match=match_result,
        )

        result = await service._send_notification(alert)

        assert result is True
        mock_notifier.send_activity_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_notification_handles_error(
        self,
        service: ActivityTrackerService,
        post: InstagramPost,
        account: InstagramAccountConfig,
        match_result: MatchResult,
        mock_notifier: AsyncMock,
    ) -> None:
        """Test notification error is handled."""
        mock_notifier.send_activity_alert.side_effect = Exception("Send failed")

        alert = ActivityAlert(
            post=post,
            account=account,
            extracted=None,
            match=match_result,
        )

        result = await service._send_notification(alert)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_without_notifier(
        self,
        accounts_config: Path,
        post: InstagramPost,
        account: InstagramAccountConfig,
        match_result: MatchResult,
    ) -> None:
        """Test no notification sent without notifier."""
        service = ActivityTrackerService(accounts_config_path=accounts_config)

        alert = ActivityAlert(
            post=post,
            account=account,
            extracted=None,
            match=match_result,
        )

        result = await service._send_notification(alert)

        assert result is False


class TestHelperMethods:
    """Tests for helper methods."""

    def test_get_enabled_accounts(self, service: ActivityTrackerService) -> None:
        """Test get_enabled_accounts returns correct list."""
        accounts = service.get_enabled_accounts()

        assert len(accounts) == 2
        assert all(a.enabled for a in accounts)

    def test_get_wishlist_destinations(self, service: ActivityTrackerService) -> None:
        """Test get_wishlist_destinations returns destinations."""
        destinations = service.get_wishlist_destinations()

        assert "Guatapé" in destinations
        assert "Santa Marta" in destinations


class TestSaveState:
    """Tests for state persistence."""

    @pytest.mark.asyncio
    async def test_save_state_calls_manager(
        self, service: ActivityTrackerService, mock_state_manager: MagicMock
    ) -> None:
        """Test save_state calls state manager."""
        await service.save_state()

        mock_state_manager.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_state_without_manager(self, accounts_config: Path) -> None:
        """Test save_state handles no state manager."""
        service = ActivityTrackerService(accounts_config_path=accounts_config)

        # Should not raise
        await service.save_state()


class TestActivityTrackerResultDataclass:
    """Tests for ActivityTrackerResult dataclass."""

    def test_create_result(self) -> None:
        """Test creating ActivityTrackerResult."""
        result = ActivityTrackerResult(
            accounts_checked=5,
            posts_found=50,
            posts_processed=45,
            alerts_generated=3,
            notifications_sent=3,
            errors=[],
        )

        assert result.accounts_checked == 5
        assert result.posts_found == 50
        assert result.alerts_generated == 3
        assert result.errors == []
