"""Telegram notification service."""

import logging
import time
from datetime import datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Telegram API constants
TELEGRAM_API_BASE = "https://api.telegram.org"
MAX_MESSAGES_PER_MINUTE = 20
MESSAGE_TIMEOUT_SECONDS = 30


class NotifierError(Exception):
    """Base exception for notifier errors."""

    pass


class RateLimitExceeded(NotifierError):
    """Raised when rate limit is exceeded."""

    pass


class TelegramNotifier:
    """Send formatted notifications via Telegram Bot API.

    Implements rate limiting to avoid hitting Telegram's limits.
    Messages are formatted with emojis and Markdown.

    Attributes:
        bot_token: Telegram bot token from @BotFather.
        chat_id: Target chat ID for notifications.
    """

    def __init__(self, bot_token: str, chat_id: str) -> None:
        """Initialize the notifier.

        Args:
            bot_token: Telegram bot token.
            chat_id: Target chat ID.
        """
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._message_times: list[float] = []

    @property
    def api_url(self) -> str:
        """Get the Telegram API base URL for this bot."""
        return f"{TELEGRAM_API_BASE}/bot{self._bot_token}"

    def _check_rate_limit(self) -> None:
        """Check and enforce rate limiting.

        Raises:
            RateLimitExceeded: If too many messages sent recently.
        """
        now = time.time()
        minute_ago = now - 60

        # Remove old timestamps
        self._message_times = [t for t in self._message_times if t > minute_ago]

        if len(self._message_times) >= MAX_MESSAGES_PER_MINUTE:
            raise RateLimitExceeded(
                f"Rate limit exceeded: {MAX_MESSAGES_PER_MINUTE} messages per minute"
            )

    def _record_message(self) -> None:
        """Record that a message was sent."""
        self._message_times.append(time.time())

    def _send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a message via Telegram API.

        Args:
            text: Message text.
            parse_mode: Telegram parse mode (Markdown or HTML).

        Returns:
            True if message was sent successfully.
        """
        try:
            self._check_rate_limit()
        except RateLimitExceeded:
            logger.warning("Rate limit exceeded, skipping message")
            return False

        url = f"{self.api_url}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        }

        try:
            response = requests.post(url, json=payload, timeout=MESSAGE_TIMEOUT_SECONDS)

            if response.status_code == 200:
                self._record_message()
                logger.debug("Message sent successfully")
                return True

            # Log error but don't raise - notifications are best-effort
            error_data = response.json() if response.text else {}
            logger.error(
                f"Telegram API error: {response.status_code} - "
                f"{error_data.get('description', 'Unknown error')}"
            )
            return False

        except requests.exceptions.Timeout:
            logger.error("Telegram API timeout")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Telegram API request failed: {e}")
            return False

    def send_flight_alert(
        self,
        route: str,
        price: int,
        airline: str,
        departure: datetime,
        link: str,
        prev_price: int | None = None,
    ) -> bool:
        """Send a flight price alert.

        Args:
            route: Route string (e.g., "BAQ→MDE").
            price: Current price in COP.
            airline: Airline name.
            departure: Departure datetime.
            link: Booking link.
            prev_price: Previous price for comparison.

        Returns:
            True if message was sent successfully.
        """
        # Calculate price change if previous price exists
        price_change = ""
        if prev_price is not None and prev_price > 0:
            diff = prev_price - price
            pct = (diff / prev_price) * 100
            if diff > 0:
                price_change = f" (↓{pct:.0f}% desde ${prev_price:,})"
            elif diff < 0:
                price_change = f" (↑{abs(pct):.0f}% desde ${prev_price:,})"

        # Format departure date
        date_str = departure.strftime("%a %d %b")
        time_str = departure.strftime("%H:%M")

        message = (
            f"✈️ *VUELO ECONÓMICO*\n\n"
            f"🛫 *Ruta:* {route}\n"
            f"💰 *Precio:* ${price:,} COP{price_change}\n"
            f"🏢 *Aerolínea:* {airline}\n"
            f"📅 *Fecha:* {date_str}\n"
            f"🕐 *Hora:* {time_str}\n\n"
            f"🔗 [Reservar ahora]({link})"
        )

        logger.info(f"Sending flight alert: {route} @ ${price:,}")
        return self._send_message(message)

    def send_activity_alert(
        self,
        account: str,
        post_url: str,
        extracted_text: str,
        matched_destination: str,
    ) -> bool:
        """Send an activity alert from Instagram.

        Args:
            account: Instagram account username.
            post_url: URL to the Instagram post.
            extracted_text: Text extracted from the post image.
            matched_destination: Destination that matched the wishlist.

        Returns:
            True if message was sent successfully.
        """
        # Truncate extracted text if too long
        max_text_length = 200
        display_text = extracted_text[:max_text_length]
        if len(extracted_text) > max_text_length:
            display_text += "..."

        # Escape markdown special characters in extracted text
        display_text = self._escape_markdown(display_text)

        message = (
            f"🏔️ *NUEVA ACTIVIDAD*\n\n"
            f"📸 *Cuenta:* @{account}\n"
            f"🎯 *Destino:* {matched_destination}\n"
            f"📝 *Texto detectado:*\n_{display_text}_\n\n"
            f"🔗 [Ver publicación]({post_url})"
        )

        logger.info(f"Sending activity alert: {account} - {matched_destination}")
        return self._send_message(message)

    def send_error_alert(self, source: str, message: str) -> bool:
        """Send an error notification.

        Args:
            source: Source of the error (e.g., "Instagram", "Google Flights").
            message: Error description.

        Returns:
            True if message was sent successfully.
        """
        # Escape markdown in error message
        safe_message = self._escape_markdown(message)

        text = (
            f"⚠️ *ERROR EN TRACKER*\n\n"
            f"🔧 *Origen:* {source}\n"
            f"❌ *Error:* {safe_message}\n\n"
            f"_Revisa manualmente si es necesario_"
        )

        logger.warning(f"Sending error alert: {source} - {message}")
        return self._send_message(text)

    def send_summary(
        self,
        flights_checked: int,
        flights_notified: int,
        activities_checked: int,
        activities_notified: int,
        errors: list[str],
    ) -> bool:
        """Send a summary of the tracker run.

        Args:
            flights_checked: Number of flights checked.
            flights_notified: Number of flight notifications sent.
            activities_checked: Number of activities checked.
            activities_notified: Number of activity notifications sent.
            errors: List of errors encountered.

        Returns:
            True if message was sent successfully.
        """
        status_emoji = "✅" if not errors else "⚠️"

        message = (
            f"{status_emoji} *RESUMEN DE EJECUCIÓN*\n\n"
            f"✈️ Vuelos revisados: {flights_checked}\n"
            f"📢 Alertas de vuelos: {flights_notified}\n"
            f"🏔️ Actividades revisadas: {activities_checked}\n"
            f"📢 Alertas de actividades: {activities_notified}\n"
        )

        if errors:
            message += f"\n⚠️ Errores: {len(errors)}\n"
            for error in errors[:3]:  # Show max 3 errors
                safe_error = self._escape_markdown(error[:50])
                message += f"  • {safe_error}\n"
            if len(errors) > 3:
                message += f"  _...y {len(errors) - 3} más_\n"

        return self._send_message(message)

    def send_test_message(self) -> bool:
        """Send a test message to verify configuration.

        Returns:
            True if message was sent successfully.
        """
        message = (
            "🧪 *TEST DE CONEXIÓN*\n\n"
            "Adventure Tracker está configurado correctamente.\n"
            f"Chat ID: `{self._chat_id}`"
        )

        logger.info("Sending test message")
        return self._send_message(message)

    @staticmethod
    def _escape_markdown(text: str) -> str:
        """Escape Markdown special characters.

        Args:
            text: Text to escape.

        Returns:
            Escaped text safe for Markdown.
        """
        # Characters that need escaping in Markdown
        special_chars = ["_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]

        for char in special_chars:
            text = text.replace(char, f"\\{char}")

        return text

    @property
    def messages_sent_last_minute(self) -> int:
        """Get number of messages sent in the last minute."""
        now = time.time()
        minute_ago = now - 60
        return len([t for t in self._message_times if t > minute_ago])
