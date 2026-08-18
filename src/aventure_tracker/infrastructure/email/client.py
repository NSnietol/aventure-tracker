"""Resend API client — thin wrapper around the resend SDK."""

import logging

from aventure_tracker.infrastructure.email.helpers import RESEND_FROM

logger = logging.getLogger(__name__)


class ResendClient:
    """Send emails via the Resend API.

    Args:
        api_key: Resend API key.
        to_email: Recipient email address.
    """

    def __init__(self, api_key: str, to_email: str) -> None:
        import resend

        resend.api_key = api_key
        self._resend = resend
        self._to_email = to_email

    def send(self, subject: str, html: str) -> bool:
        """Send an email.

        Args:
            subject: Email subject line.
            html: Full HTML body.

        Returns:
            True if the email was sent successfully, False otherwise.
        """
        try:
            self._resend.Emails.send(
                {
                    "from": RESEND_FROM,
                    "to": self._to_email,
                    "subject": subject,
                    "html": html,
                }
            )
            logger.info(f"Email sent to {self._to_email}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False
