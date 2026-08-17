"""Tests for Activity Tracker Service."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aventure_tracker.models.activity import (
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
def destinations_config(tmp_path: Path) -> Path:
    """Create a temporary destinations config file (blacklist)."""
    config_path = tmp_path / "destinations.yaml"
    config_path.write_text(
        """
blacklist:
  ya_fue:
    - San Luis
    - Tatacoa
  playa:
    - Rincón del Mar
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
    """Create a test match result (not blacklisted - should notify)."""
    return MatchResult(
        is_blacklisted=False,
        matched_blacklist=None,
        blacklist_reason=None,
        match_score=0.9,
    )


@pytest.fixture
def match_result_blacklisted() -> MatchResult:
    """Create a test match result for blacklisted activity."""
    return MatchResult(
        is_blacklisted=True,
        matched_blacklist="San Luis",
        blacklist_reason="ya_fue",
        match_score=0.0,
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
def mock_history_manager_base() -> MagicMock:
    """Create a base mock history manager for main service fixture."""
    manager = MagicMock()
    manager.should_check.return_value = True
    manager.record_check = MagicMock()
    manager.save = MagicMock()
    manager.load = MagicMock()
    manager.get_account_history.return_value = []
    manager.get_skipped_count.return_value = 0
    return manager


@pytest.fixture
def service(
    accounts_config: Path,
    destinations_config: Path,
    mock_state_manager: MagicMock,
    mock_notifier: AsyncMock,
    mock_scraper: AsyncMock,
    mock_ocr: MagicMock,
    mock_history_manager_base: MagicMock,
) -> ActivityTrackerService:
    """Create an activity tracker service with mocked dependencies."""
    return ActivityTrackerService(
        accounts_config_path=accounts_config,
        destinations_config_path=destinations_config,
        state_manager=mock_state_manager,
        notifier=mock_notifier,
        scraper=mock_scraper,
        ocr_processor=mock_ocr,
        history_manager=mock_history_manager_base,
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
        # destination is None since it's not blacklisted
        assert alert.destination is None

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
        # destination shows blacklisted match (None if not blacklisted)
        assert alert.destination is None

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
        """Test check_account returns alerts for non-blacklisted activities."""
        # Mock inventory to return non-blacklisted (should_notify=True)
        with patch.object(
            service._inventory,
            "match_post",
            return_value=MatchResult(
                is_blacklisted=False,
                matched_blacklist=None,
                blacklist_reason=None,
                match_score=0.9,
            ),
        ):
            alerts = await service.check_account(account)

        assert len(alerts) == 1

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
    async def test_check_account_skips_blacklisted(
        self,
        service: ActivityTrackerService,
        account: InstagramAccountConfig,
    ) -> None:
        """Test check_account skips blacklisted activities."""
        with patch.object(
            service._inventory,
            "match_post",
            return_value=MatchResult(
                is_blacklisted=True,
                matched_blacklist="San Luis",
                blacklist_reason="ya_fue",
                match_score=0.0,
            ),
        ):
            alerts = await service.check_account(account)

        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_check_account_alerts_for_non_blacklisted(
        self,
        service: ActivityTrackerService,
        account: InstagramAccountConfig,
    ) -> None:
        """Test check_account generates alerts for non-blacklisted activities."""
        with patch.object(
            service._inventory,
            "match_post",
            return_value=MatchResult(
                is_blacklisted=False,
                matched_blacklist=None,
                blacklist_reason=None,
                match_score=0.9,
            ),
        ):
            alerts = await service.check_account(account)

        assert len(alerts) == 1
        assert alerts[0].match.should_notify is True


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
                is_blacklisted=True,  # Blacklisted - no alerts
                matched_blacklist="San Luis",
                blacklist_reason="ya_fue",
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
        """Test track_activities generates alerts for non-blacklisted activities."""
        with patch.object(
            service._inventory,
            "match_post",
            return_value=MatchResult(
                is_blacklisted=False,  # Not blacklisted - should alert
                matched_blacklist=None,
                blacklist_reason=None,
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
                is_blacklisted=False,
                matched_blacklist=None,
                blacklist_reason=None,
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
                is_blacklisted=True,
                matched_blacklist="San Luis",
                blacklist_reason="ya_fue",
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

    def test_get_blacklisted_destinations(
        self, service: ActivityTrackerService
    ) -> None:
        """Test get_blacklisted_destinations returns destinations."""
        destinations = service.get_blacklisted_destinations()

        # Destinations are normalized to lowercase
        assert "san luis" in destinations
        assert "tatacoa" in destinations
        assert "rincón del mar" in destinations


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
            posts_skipped=5,
            alerts_generated=3,
            notifications_sent=3,
            errors=[],
        )

        assert result.accounts_checked == 5
        assert result.posts_found == 50
        assert result.posts_skipped == 5
        assert result.alerts_generated == 3
        assert result.errors == []


class TestActivityAlertWithEventInfo:
    """Tests for ActivityAlert with event information."""

    def test_alert_with_event_info(
        self,
        post: InstagramPost,
        account: InstagramAccountConfig,
        match_result: MatchResult,
    ) -> None:
        """Test activity alert with event_id and event_name."""
        alert = ActivityAlert(
            post=post,
            account=account,
            extracted=None,
            match=match_result,
            event_id="2026-08-15-cocuy-trek",
            event_name="Cocuy Trek",
            event_date="2026-08-15",
        )

        assert alert.event_id == "2026-08-15-cocuy-trek"
        assert alert.event_name == "Cocuy Trek"
        assert alert.event_date == "2026-08-15"

    def test_alert_default_event_info(
        self,
        post: InstagramPost,
        account: InstagramAccountConfig,
        match_result: MatchResult,
    ) -> None:
        """Test activity alert with default event info values."""
        alert = ActivityAlert(
            post=post,
            account=account,
            extracted=None,
            match=match_result,
        )

        assert alert.event_id == ""
        assert alert.event_name == ""
        assert alert.event_date is None


class TestHistoryIntegration:
    """Tests for ActivityHistoryManager integration."""

    @pytest.fixture
    def mock_history_manager(self) -> MagicMock:
        """Create a mock history manager."""
        manager = MagicMock()
        manager.should_check.return_value = True
        manager.record_check = MagicMock()
        manager.save = MagicMock()
        manager.get_account_history.return_value = []
        manager.get_skipped_count.return_value = 0
        return manager

    @pytest.fixture
    def service_with_history(
        self,
        accounts_config: Path,
        destinations_config: Path,
        mock_state_manager: MagicMock,
        mock_notifier: AsyncMock,
        mock_scraper: AsyncMock,
        mock_ocr: MagicMock,
        mock_history_manager: MagicMock,
    ) -> ActivityTrackerService:
        """Create an activity tracker service with history manager."""
        return ActivityTrackerService(
            accounts_config_path=accounts_config,
            destinations_config_path=destinations_config,
            state_manager=mock_state_manager,
            notifier=mock_notifier,
            scraper=mock_scraper,
            ocr_processor=mock_ocr,
            history_manager=mock_history_manager,
            use_ocr=True,
        )

    @pytest.mark.asyncio
    async def test_track_skips_posts_at_history_limit(
        self,
        service_with_history: ActivityTrackerService,
        mock_history_manager: MagicMock,
    ) -> None:
        """Test posts at history limit are skipped."""
        # First post should be checked, second should be skipped
        mock_history_manager.should_check.side_effect = [False, False]

        with patch.object(
            service_with_history._inventory,
            "match_post",
            return_value=MatchResult(
                is_blacklisted=True,
                matched_blacklist="San Luis",
                blacklist_reason="ya_fue",
                match_score=0.0,
            ),
        ):
            result = await service_with_history.track_activities()

        # Both posts should be skipped (1 per enabled account = 2)
        assert result.posts_skipped == 2
        assert result.posts_processed == 0

    @pytest.mark.asyncio
    async def test_track_records_check_in_history(
        self,
        service_with_history: ActivityTrackerService,
        mock_history_manager: MagicMock,
    ) -> None:
        """Test track_activities records checks in history."""
        with patch.object(
            service_with_history._inventory,
            "match_post",
            return_value=MatchResult(
                is_blacklisted=False,
                matched_blacklist=None,
                blacklist_reason=None,
                match_score=0.9,
            ),
        ):
            await service_with_history.track_activities()

        # Should record check for each post
        mock_history_manager.record_check.assert_called()
        assert mock_history_manager.record_check.call_count == 2

    @pytest.mark.asyncio
    async def test_track_saves_history(
        self,
        service_with_history: ActivityTrackerService,
        mock_history_manager: MagicMock,
    ) -> None:
        """Test track_activities saves history after processing."""
        with patch.object(
            service_with_history._inventory,
            "match_post",
            return_value=MatchResult(
                is_blacklisted=True,
                matched_blacklist="San Luis",
                blacklist_reason="ya_fue",
                match_score=0.0,
            ),
        ):
            await service_with_history.track_activities()

        mock_history_manager.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_account_skips_history_limit(
        self,
        service_with_history: ActivityTrackerService,
        account: InstagramAccountConfig,
        mock_history_manager: MagicMock,
    ) -> None:
        """Test check_account respects history limit."""
        mock_history_manager.should_check.return_value = False

        alerts = await service_with_history.check_account(account)

        assert len(alerts) == 0
        mock_history_manager.record_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_account_records_and_saves_history(
        self,
        service_with_history: ActivityTrackerService,
        account: InstagramAccountConfig,
        mock_history_manager: MagicMock,
    ) -> None:
        """Test check_account records check and saves history."""
        with patch.object(
            service_with_history._inventory,
            "match_post",
            return_value=MatchResult(
                is_blacklisted=True,
                matched_blacklist="San Luis",
                blacklist_reason="ya_fue",
                match_score=0.0,
            ),
        ):
            await service_with_history.check_account(account)

        mock_history_manager.record_check.assert_called_once()
        mock_history_manager.save.assert_called_once()

    def test_get_account_history_stats(
        self,
        service_with_history: ActivityTrackerService,
        mock_history_manager: MagicMock,
    ) -> None:
        """Test getting history stats for an account."""
        # Mock some records
        mock_history_manager.get_account_history.return_value = [
            MagicMock(),
            MagicMock(),
            MagicMock(),
        ]
        mock_history_manager.get_skipped_count.return_value = 1

        stats = service_with_history.get_account_history_stats("test_account")

        assert stats["total"] == 3
        assert stats["skipped"] == 1
        assert stats["active"] == 2

    def test_get_account_history_stats_no_manager(self, accounts_config: Path) -> None:
        """Test history stats without manager returns zeros."""
        service = ActivityTrackerService(accounts_config_path=accounts_config)

        stats = service.get_account_history_stats("test_account")

        assert stats == {"total": 0, "skipped": 0, "active": 0}

    @pytest.mark.asyncio
    async def test_save_state_saves_history(
        self,
        service_with_history: ActivityTrackerService,
        mock_history_manager: MagicMock,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test save_state also saves history."""
        await service_with_history.save_state()

        mock_state_manager.save.assert_called_once()
        mock_history_manager.save.assert_called_once()


class TestEventInfoExtraction:
    """Tests for event info extraction during tracking."""

    @pytest.fixture
    def post_with_date(self) -> InstagramPost:
        """Create a post with date in caption."""
        return InstagramPost(
            id="12345",
            url="https://www.instagram.com/p/ABC123/",
            caption="Trek al Cocuy - 15 de agosto 2026",
            timestamp=datetime(2025, 1, 15, 10, 30),
            image_urls=["https://example.com/image1.jpg"],
        )

    @pytest.fixture
    def mock_history_for_event_test(self) -> MagicMock:
        """Create a mock history manager for event extraction test."""
        manager = MagicMock()
        manager.should_check.return_value = True
        manager.record_check = MagicMock()
        manager.save = MagicMock()
        manager.load = MagicMock()
        return manager

    @pytest.mark.asyncio
    async def test_alert_contains_event_info(
        self,
        accounts_config: Path,
        destinations_config: Path,
        mock_scraper: AsyncMock,
        post_with_date: InstagramPost,
        mock_history_for_event_test: MagicMock,
    ) -> None:
        """Test that alerts include extracted event info."""
        mock_scraper.scrape.return_value = [post_with_date]

        service = ActivityTrackerService(
            accounts_config_path=accounts_config,
            destinations_config_path=destinations_config,
            scraper=mock_scraper,
            history_manager=mock_history_for_event_test,
            use_ocr=False,
        )

        with patch.object(
            service._inventory,
            "match_post",
            return_value=MatchResult(
                is_blacklisted=False,  # Not blacklisted, should alert
                matched_blacklist=None,
                blacklist_reason=None,
                match_score=0.9,
            ),
        ):
            alerts = await service.check_account(
                InstagramAccountConfig(username="test", name="Test", enabled=True)
            )

        assert len(alerts) == 1
        alert = alerts[0]
        # Event info should be extracted from caption
        assert alert.event_date == "2026-08-15"
        assert "cocuy" in alert.event_id.lower()
