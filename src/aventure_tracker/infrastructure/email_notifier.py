"""Email notification service using Resend API."""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

RESEND_FROM = "Adventure Tracker <onboarding@resend.dev>"


class EmailNotifier:
    """Send formatted notifications via Resend email API.

    Attributes:
        api_key: Resend API key.
        to_email: Recipient email address.
    """

    def __init__(self, api_key: str, to_email: str) -> None:
        """Initialize the notifier.

        Args:
            api_key: Resend API key.
            to_email: Recipient email address.
        """
        import resend
        resend.api_key = api_key
        self._resend = resend
        self._to_email = to_email

    def _send(self, subject: str, html: str) -> bool:
        """Send an email via Resend.

        Args:
            subject: Email subject.
            html: HTML body.

        Returns:
            True if sent successfully.
        """
        try:
            self._resend.Emails.send({
                "from": RESEND_FROM,
                "to": self._to_email,
                "subject": subject,
                "html": html,
            })
            logger.info(f"Email sent: {subject}")
            return True
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False

    def send_weekend_report(
        self,
        outbound_flights: list,
        return_flights: list,
        weekend_matches: list,
    ) -> bool:
        """Send consolidated weekend report: cheap flights + available events.

        Args:
            outbound_flights: List of FlightFound for outbound (BAQ→MDE).
            return_flights: List of FlightFound for return (MDE→BAQ).
            weekend_matches: List of WeekendMatch with matched events.

        Returns:
            True if sent successfully.
        """
        subject = "✈️ Finde barato detectado!"
        html = _build_weekend_report_html(
            outbound_flights, return_flights, weekend_matches
        )
        return self._send(subject, html)

    def send_test_message(self) -> bool:
        """Send a test email to verify configuration."""
        return self._send(
            subject="🧪 Adventure Tracker — Test de conexión",
            html="<p>Adventure Tracker está configurado correctamente.</p>",
        )


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

def _build_weekend_report_html(
    outbound_flights: list,
    return_flights: list,
    weekend_matches: list,
) -> str:
    """Build HTML email body for the weekend report."""

    rows_ida = ""
    for f in outbound_flights:
        date_str = f.travel_date.strftime("%a %d %b")
        star = "★" if f.is_priority else ""
        rows_ida += (
            f"<tr><td>{date_str}</td><td>{f.departure_time}</td>"
            f"<td>{f.airline}{star}</td>"
            f"<td><strong>${f.price:,} COP</strong></td></tr>"
        )

    rows_vuelta = ""
    for f in return_flights:
        date_str = f.travel_date.strftime("%a %d %b")
        star = "★" if f.is_priority else ""
        rows_vuelta += (
            f"<tr><td>{date_str}</td><td>{f.departure_time}</td>"
            f"<td>{f.airline}{star}</td>"
            f"<td><strong>${f.price:,} COP</strong></td></tr>"
        )

    flights_section = ""
    if rows_ida:
        flights_section += f"""
        <h3>✈️ Ida (BAQ→MDE)</h3>
        <table border="0" cellpadding="6" style="border-collapse:collapse;width:100%">
          <thead><tr style="background:#f0f0f0">
            <th align="left">Fecha</th><th align="left">Hora</th>
            <th align="left">Aerolínea</th><th align="left">Precio</th>
          </tr></thead>
          <tbody>{rows_ida}</tbody>
        </table>"""

    if rows_vuelta:
        flights_section += f"""
        <h3>✈️ Vuelta (MDE→BAQ)</h3>
        <table border="0" cellpadding="6" style="border-collapse:collapse;width:100%">
          <thead><tr style="background:#f0f0f0">
            <th align="left">Fecha</th><th align="left">Hora</th>
            <th align="left">Aerolínea</th><th align="left">Precio</th>
          </tr></thead>
          <tbody>{rows_vuelta}</tbody>
        </table>"""

    events_section = ""
    has_any_events = any(m.has_events for m in weekend_matches)
    if has_any_events:
        for match in weekend_matches:
            if not match.has_events:
                continue
            rows_ev = ""
            for ev in match.events[:8]:
                rows_ev += (
                    f"<tr><td>{ev.name}</td><td>{ev.date_label}</td>"
                    f"<td>{ev.price_formatted}</td></tr>"
                )
            events_section += f"""
            <h3>🏔️ Planes ese finde ({match.date_label})</h3>
            <table border="0" cellpadding="6" style="border-collapse:collapse;width:100%">
              <thead><tr style="background:#f0f0f0">
                <th align="left">Plan</th>
                <th align="left">Fecha</th>
                <th align="left">Precio</th>
              </tr></thead>
              <tbody>{rows_ev}</tbody>
            </table>"""
    else:
        events_section = "<p><em>Sin eventos de agencias para esas fechas.</em></p>"

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px">
      <h2 style="color:#1a73e8">✈️ Finde Barato Detectado</h2>
      {flights_section}
      <hr>
      {events_section}
      <hr>
      <p style="color:#888;font-size:12px">Generado por Adventure Tracker · {generated_at}</p>
    </body></html>
    """
