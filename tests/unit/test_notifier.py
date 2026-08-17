"""Tests for TelegramNotifier."""

import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from aventure_tracker.infrastructure.notifier import (
    MAX_MESSAGES_PER_MINUTE,
    TelegramNotifier,
)


@pytest.fixture
def notifier() -> TelegramNotifier:
    """Create a TelegramNotifier instance for testing."""
    return TelegramNotifier(bot_token="test_token", chat_id="test_chat_id")


@pytest.fixture
def mock_successful_response() -> MagicMock:
    """Create a mock successful Telegram API response."""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"ok": True, "result": {"message_id": 123}}
    return response


class TestTelegramNotifierInit:
    """Tests for TelegramNotifier initialization."""

    def test_init_creates_instance(self) -> None:
        """Test that notifier initializes correctly."""
        notifier = TelegramNotifier(bot_token="my_token", chat_id="my_chat")

        assert notifier._bot_token == "my_token"
        assert notifier._chat_id == "my_chat"

    def test_api_url_property(self, notifier: TelegramNotifier) -> None:
        """Test api_url property returns correct URL."""
        assert notifier.api_url == "https://api.telegram.org/bottest_token"


class TestSendFlightAlert:
    """Tests for send_flight_alert method."""

    def test_send_flight_alert_success(
        self,
        notifier: TelegramNotifier,
        mock_successful_response: MagicMock,
    ) -> None:
        """Test sending a flight alert successfully."""
        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_successful_response

            result = notifier.send_flight_alert(
                route="BAQ→MDE",
                price=145000,
                airline="Avianca",
                departure=datetime(2025, 3, 15, 18, 30),
                link="https://example.com/book",
            )

            assert result is True
            mock_post.assert_called_once()

            # Check message content
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert "VUELO ECONÓMICO" in payload["text"]
            assert "BAQ→MDE" in payload["text"]
            assert "145,000" in payload["text"]
            assert "Avianca" in payload["text"]

    def test_send_flight_alert_with_price_drop(
        self,
        notifier: TelegramNotifier,
        mock_successful_response: MagicMock,
    ) -> None:
        """Test flight alert includes price drop percentage."""
        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_successful_response

            notifier.send_flight_alert(
                route="BAQ→MDE",
                price=127500,  # 15% drop from 150000
                airline="Avianca",
                departure=datetime(2025, 3, 15, 18, 30),
                link="https://example.com/book",
                prev_price=150000,
            )

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert "↓15%" in payload["text"]
            assert "150,000" in payload["text"]

    def test_send_flight_alert_with_price_increase(
        self,
        notifier: TelegramNotifier,
        mock_successful_response: MagicMock,
    ) -> None:
        """Test flight alert includes price increase percentage."""
        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_successful_response

            notifier.send_flight_alert(
                route="BAQ→MDE",
                price=165000,  # 10% increase from 150000
                airline="Avianca",
                departure=datetime(2025, 3, 15, 18, 30),
                link="https://example.com/book",
                prev_price=150000,
            )

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert "↑10%" in payload["text"]


class TestSendActivityAlert:
    """Tests for send_activity_alert method."""

    def test_send_activity_alert_success(
        self,
        notifier: TelegramNotifier,
        mock_successful_response: MagicMock,
    ) -> None:
        """Test sending an activity alert successfully."""
        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_successful_response

            result = notifier.send_activity_alert(
                account="brutaltravel.co",
                post_url="https://instagram.com/p/ABC123",
                extracted_text="Viaje a Guatapé en Septiembre",
                matched_destination="Guatapé",
            )

            assert result is True
            mock_post.assert_called_once()

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert "NUEVA ACTIVIDAD" in payload["text"]
            assert "brutaltravel.co" in payload["text"]
            assert "Guatapé" in payload["text"]

    def test_send_activity_alert_truncates_long_text(
        self,
        notifier: TelegramNotifier,
        mock_successful_response: MagicMock,
    ) -> None:
        """Test that long extracted text is truncated."""
        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_successful_response

            long_text = "A" * 300  # Longer than max_text_length (200)

            notifier.send_activity_alert(
                account="brutaltravel.co",
                post_url="https://instagram.com/p/ABC123",
                extracted_text=long_text,
                matched_destination="Guatapé",
            )

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            # The "..." gets escaped to "\.\.\." in markdown
            assert "\\.\\.\\." in payload["text"]


class TestSendErrorAlert:
    """Tests for send_error_alert method."""

    def test_send_error_alert_success(
        self,
        notifier: TelegramNotifier,
        mock_successful_response: MagicMock,
    ) -> None:
        """Test sending an error alert successfully."""
        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_successful_response

            result = notifier.send_error_alert(
                source="Instagram",
                message="Failed to load profile",
            )

            assert result is True

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert "ERROR EN TRACKER" in payload["text"]
            assert "Instagram" in payload["text"]


class TestSendSummary:
    """Tests for send_summary method."""

    def test_send_summary_success(
        self,
        notifier: TelegramNotifier,
        mock_successful_response: MagicMock,
    ) -> None:
        """Test sending a summary successfully."""
        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_successful_response

            result = notifier.send_summary(
                flights_checked=10,
                flights_notified=2,
                activities_checked=5,
                activities_notified=1,
                errors=[],
            )

            assert result is True

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert "RESUMEN" in payload["text"]
            assert "✅" in payload["text"]  # Success emoji

    def test_send_summary_with_errors(
        self,
        notifier: TelegramNotifier,
        mock_successful_response: MagicMock,
    ) -> None:
        """Test summary includes errors when present."""
        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_successful_response

            notifier.send_summary(
                flights_checked=10,
                flights_notified=0,
                activities_checked=5,
                activities_notified=0,
                errors=["Error 1", "Error 2"],
            )

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert "⚠️" in payload["text"]  # Warning emoji
            assert "Errores: 2" in payload["text"]


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    def test_rate_limit_enforced(
        self,
        notifier: TelegramNotifier,
        mock_successful_response: MagicMock,
    ) -> None:
        """Test that rate limit is enforced."""
        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_successful_response

            # Send max messages
            for _ in range(MAX_MESSAGES_PER_MINUTE):
                notifier.send_test_message()

            # Next message should be rate limited
            result = notifier.send_test_message()
            assert result is False

    def test_rate_limit_resets_after_minute(
        self,
        notifier: TelegramNotifier,
        mock_successful_response: MagicMock,
    ) -> None:
        """Test that rate limit resets after a minute."""
        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_successful_response

            # Manually set old timestamps
            old_time = time.time() - 61  # Over a minute ago
            notifier._message_times = [old_time] * MAX_MESSAGES_PER_MINUTE

            # Should be able to send now
            result = notifier.send_test_message()
            assert result is True

    def test_messages_sent_last_minute_property(
        self,
        notifier: TelegramNotifier,
        mock_successful_response: MagicMock,
    ) -> None:
        """Test messages_sent_last_minute property."""
        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_successful_response

            assert notifier.messages_sent_last_minute == 0

            notifier.send_test_message()
            notifier.send_test_message()

            assert notifier.messages_sent_last_minute == 2


class TestErrorHandling:
    """Tests for error handling."""

    def test_handles_api_error_gracefully(
        self,
        notifier: TelegramNotifier,
    ) -> None:
        """Test that API errors are handled gracefully."""
        with patch("requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = '{"ok": false, "description": "Bad Request"}'
            mock_response.json.return_value = {
                "ok": False,
                "description": "Bad Request",
            }
            mock_post.return_value = mock_response

            result = notifier.send_test_message()

            assert result is False  # Should return False, not raise

    def test_handles_timeout_gracefully(
        self,
        notifier: TelegramNotifier,
    ) -> None:
        """Test that timeouts are handled gracefully."""
        with patch("requests.post") as mock_post:
            mock_post.side_effect = requests.exceptions.Timeout("timeout")

            result = notifier.send_test_message()

            assert result is False

    def test_handles_connection_error_gracefully(
        self,
        notifier: TelegramNotifier,
    ) -> None:
        """Test that connection errors are handled gracefully."""
        with patch("requests.post") as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError("failed")

            result = notifier.send_test_message()

            assert result is False


class TestMarkdownEscaping:
    """Tests for Markdown escaping."""

    def test_escape_markdown_special_chars(self) -> None:
        """Test that special characters are escaped."""
        text = "Hello *world* _test_ [link](url)"
        escaped = TelegramNotifier._escape_markdown(text)

        assert "\\*" in escaped
        assert "\\_" in escaped
        assert "\\[" in escaped
        assert "\\]" in escaped
        assert "\\(" in escaped
        assert "\\)" in escaped

    def test_activity_alert_escapes_extracted_text(
        self,
        notifier: TelegramNotifier,
        mock_successful_response: MagicMock,
    ) -> None:
        """Test that extracted text with special chars is escaped."""
        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_successful_response

            notifier.send_activity_alert(
                account="test",
                post_url="https://example.com",
                extracted_text="Price: $100 (50% off!)",
                matched_destination="Test",
            )

            # Should not raise parsing errors
            mock_post.assert_called_once()
