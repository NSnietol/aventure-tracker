"""Email notification service — facade over the email sub-package."""

import logging

from aventure_tracker.infrastructure.email.client import ResendClient
from aventure_tracker.infrastructure.email.helpers import now_colombia
from aventure_tracker.infrastructure.email.templates.error_report import (
    build_error_html,
)
from aventure_tracker.infrastructure.email.templates.weekend_report import (
    build_weekend_report_html,
)

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Send formatted notifications via Resend email API.

    Args:
        api_key: Resend API key.
        to_email: Recipient email address.
    """

    def __init__(self, api_key: str, to_email: str) -> None:
        self._client = ResendClient(api_key=api_key, to_email=to_email)

    def send_weekend_report(self, pairs: list) -> bool:
        """Send the consolidated weekend report.

        Args:
            pairs: List of WeekendPair objects.

        Returns:
            True if sent successfully.
        """
        if not pairs:
            return False

        all_dates = [p.outbound.travel_date for p in pairs]
        subject = (
            f"✈️ {len(pairs)} finde{'s' if len(pairs) > 1 else ''} "
            f"barato{'s' if len(pairs) > 1 else ''}"
            f" · {min(all_dates).strftime('%d %b')}–{max(all_dates).strftime('%d %b %Y')}"
            if all_dates
            else "✈️ Finde barato detectado!"
        )
        return self._client.send(subject, build_weekend_report_html(pairs))

    def send_error_report(
        self,
        errors: list[str],
        mode: str = "all",
        duration_seconds: float = 0.0,
        routes_checked: int = 0,
        routes_total: int = 2,
        alerts_generated: int = 0,
        run_url: str = "",
    ) -> bool:
        """Send an error report email.

        Args:
            errors: Error messages collected during the run.
            mode: Execution mode (all, flights, activities).
            duration_seconds: Total run duration in seconds.
            routes_checked: Routes successfully checked.
            routes_total: Total configured routes.
            alerts_generated: Alerts generated before failure.
            run_url: GitHub Actions run URL for the CTA button.

        Returns:
            True if sent successfully.
        """
        now = now_colombia()
        generated_at = now.strftime("%d %b %Y · %H:%M Col")
        error_count = len(errors)
        subject = (
            f"⚠️ Adventure Tracker falló · {error_count} "
            f"error{'es' if error_count != 1 else ''} · {now.strftime('%d %b %Y')}"
        )
        html = build_error_html(
            errors=errors,
            mode=mode,
            duration_seconds=duration_seconds,
            routes_checked=routes_checked,
            routes_total=routes_total,
            alerts_generated=alerts_generated,
            run_url=run_url,
            generated_at=generated_at,
        )
        return self._client.send(subject, html)

    def send_test_message(self) -> bool:
        """Send a test email to verify configuration."""
        return self._client.send(
            subject="🧪 Adventure Tracker — Test de conexión",
            html="""
            <html><body style="font-family:Georgia,serif;max-width:600px;margin:40px auto;padding:32px;background:#fafaf8;">
              <div style="background:#1b4332;padding:12px 24px;border-radius:8px 8px 0 0;">
                <span style="font-size:12px;color:#95d5b2;font-family:Arial,sans-serif;letter-spacing:2px;text-transform:uppercase;">Adventure Tracker</span>
              </div>
              <div style="background:#fff;padding:32px 24px;border-radius:0 0 8px 8px;border:1px solid #e8f5e9;">
                <p style="font-size:18px;color:#1b4332;">✅ Conexión verificada</p>
                <p style="font-size:14px;color:#555;font-family:Arial,sans-serif;">Adventure Tracker está configurado correctamente y enviará alertas cuando encuentre vuelos baratos.</p>
              </div>
            </body></html>
            """,
        )
