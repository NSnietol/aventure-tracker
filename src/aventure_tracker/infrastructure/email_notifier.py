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
            logger.info(f"Email sent to {self._to_email}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False

    def send_weekend_report(
        self,
        pairs: list,
    ) -> bool:
        """Send consolidated weekend report segmented by weekend pair.

        Each WeekendPair contains:
            outbound: FlightFound
            return_options: list[ReturnOption]  (top 3, first is recommended)
            events: list[MatchedEvent]
            sunday_adventure: bool
            window_start / window_end: date

        Args:
            pairs: List of WeekendPair objects.

        Returns:
            True if sent successfully.
        """
        if not pairs:
            return False

        all_dates = [p.outbound.travel_date for p in pairs]
        if all_dates:
            subject = (
                f"✈️ {len(pairs)} finde{'s' if len(pairs) > 1 else ''} barato{'s' if len(pairs) > 1 else ''}"
                f" · {min(all_dates).strftime('%d %b')}–{max(all_dates).strftime('%d %b %Y')}"
            )
        else:
            subject = "✈️ Finde barato detectado!"

        html = _build_html(pairs)
        return self._send(subject, html)

    def send_test_message(self) -> bool:
        """Send a test email to verify configuration."""
        return self._send(
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


# ---------------------------------------------------------------------------
# HTML builder — Maqueta 3 (Tropical / Adventure)
# ---------------------------------------------------------------------------

# Event accent colors cycling
_EVENT_COLORS = ["#e65100", "#7b1fa2", "#0277bd", "#2d6a4f", "#c62828", "#00695c"]

# Emojis by keyword match (best-effort)
_EVENT_EMOJIS = {
    "salto": "🧗", "canyoning": "💦", "torrentismo": "💦", "rafting": "🌊",
    "nocturno": "🌙", "río": "🏞", "rio": "🏞", "paramo": "🌿", "páramo": "🌿",
    "nevado": "🏔", "bosque": "🌲", "caverna": "🕳", "ciclismo": "🚵",
    "playa": "🏖", "isla": "🏝", "mar": "⛵", "pueblo": "🏘",
}


def _event_emoji(name: str) -> str:
    name_lower = name.lower()
    for key, emoji in _EVENT_EMOJIS.items():
        if key in name_lower:
            return emoji
    return "🏕"


def _build_html(pairs: list) -> str:
    """Build the Tropical/Adventure HTML email — one section per WeekendPair."""

    generated_at = datetime.now().strftime("%d %b %Y · %H:%M")
    n = len(pairs)
    all_dates = [p.outbound.travel_date for p in pairs]
    date_range = (
        f"{min(all_dates).strftime('%d %b')}–{max(all_dates).strftime('%d %b %Y')}"
        if all_dates else ""
    )

    pair_sections = ""
    for idx, pair in enumerate(pairs):
        label = pair.date_label
        outbound = pair.outbound
        events = pair.events
        sunday_flag = pair.sunday_adventure

        # --- Outbound row ---
        ds_out = outbound.travel_date.strftime("%A %d de %B").capitalize()
        star_out = " ★" if outbound.is_priority else ""
        price_out = f"${outbound.price:,}".replace(",", ".")
        outbound_row = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;background:#fff;border-radius:8px;border-left:4px solid #2d6a4f;">
          <tr><td style="padding:14px 18px;">
            <table width="100%"><tr>
              <td>
                <div style="font-size:15px;color:#333;margin-bottom:3px;">✈️ &nbsp;<strong>BAQ → MDE &nbsp;·&nbsp; {outbound.departure_time}</strong></div>
                <div style="font-size:12px;color:#888;font-family:Arial,sans-serif;">{ds_out} · {outbound.airline}{star_out}</div>
              </td>
              <td style="text-align:right;white-space:nowrap;vertical-align:top;">
                <div style="font-size:17px;font-weight:700;color:#2d6a4f;font-family:Arial,sans-serif;">{price_out}</div>
                <div style="font-size:11px;color:#aaa;font-family:Arial,sans-serif;">COP</div>
              </td>
            </tr></table>
          </td></tr>
        </table>"""

        # --- Return rows ---
        sunday_note = ""
        if sunday_flag:
            sunday_note = """
            <div style="background:#fff8e1;border-left:3px solid #f9a825;padding:8px 14px;border-radius:4px;margin-bottom:10px;font-size:12px;color:#7c5f00;font-family:Arial,sans-serif;">
              ⚠️ Hay planes el domingo — regreso recomendado el <strong>lunes temprano</strong>
            </div>"""

        return_rows = ""
        if pair.return_options:
            for i, ro in enumerate(pair.return_options):
                f = ro.flight
                ds_ret = f.travel_date.strftime("%A %d de %B").capitalize()
                star_ret = " ★" if f.is_priority else ""
                price_ret = f"${f.price:,}".replace(",", ".")

                if ro.is_recommended:
                    # Recommended — highlighted green border
                    savings_html = ""
                    if ro.savings_vs_priority and ro.savings_vs_priority > 0:
                        savings_str = f"${ro.savings_vs_priority:,}".replace(",", ".")
                        savings_html = f'<span style="font-size:11px;color:#2e7d32;font-family:Arial,sans-serif;"> ahorra {savings_str}</span>'
                    return_rows += f"""
                    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:8px;background:#f1f8e9;border-radius:8px;border-left:4px solid #2d6a4f;border:1px solid #c8e6c9;">
                      <tr><td style="padding:14px 18px;">
                        <table width="100%"><tr>
                          <td>
                            <div style="font-size:13px;color:#1b5e20;font-family:Arial,sans-serif;margin-bottom:2px;font-weight:700;">✅ Recomendado</div>
                            <div style="font-size:15px;color:#333;margin-bottom:3px;">🔄 &nbsp;<strong>MDE → BAQ &nbsp;·&nbsp; {f.departure_time}</strong></div>
                            <div style="font-size:12px;color:#888;font-family:Arial,sans-serif;">{ds_ret} · {f.airline}{star_ret}</div>
                          </td>
                          <td style="text-align:right;white-space:nowrap;vertical-align:top;">
                            <div style="font-size:17px;font-weight:700;color:#2d6a4f;font-family:Arial,sans-serif;">{price_ret}{savings_html}</div>
                            <div style="font-size:11px;color:#aaa;font-family:Arial,sans-serif;">COP</div>
                          </td>
                        </tr></table>
                      </td></tr>
                    </table>"""
                else:
                    # Alternative — grey, smaller
                    return_rows += f"""
                    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:6px;background:#fafafa;border-radius:6px;border-left:3px solid #bdbdbd;">
                      <tr><td style="padding:10px 14px;">
                        <table width="100%"><tr>
                          <td>
                            <div style="font-size:11px;color:#999;font-family:Arial,sans-serif;margin-bottom:2px;">Alternativa {i}</div>
                            <div style="font-size:13px;color:#555;">🔄 MDE → BAQ · {f.departure_time} · {f.airline}{star_ret}</div>
                            <div style="font-size:11px;color:#aaa;font-family:Arial,sans-serif;">{ds_ret}</div>
                          </td>
                          <td style="text-align:right;white-space:nowrap;vertical-align:top;">
                            <div style="font-size:14px;font-weight:600;color:#757575;font-family:Arial,sans-serif;">{price_ret}</div>
                            <div style="font-size:10px;color:#bbb;font-family:Arial,sans-serif;">COP</div>
                          </td>
                        </tr></table>
                      </td></tr>
                    </table>"""
        else:
            return_rows = "<p style='font-size:13px;color:#e65100;font-family:Arial,sans-serif;'>⚠️ Sin vuelos de regreso encontrados para este finde.</p>"

        # --- Total row ---
        total_row = ""
        if pair.total_price:
            total_str = f"${pair.total_price:,}".replace(",", ".")
            total_row = f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="margin:8px 0 20px;">
              <tr>
                <td style="font-size:13px;color:#888;font-family:Arial,sans-serif;">Ida + Vuelta recomendada</td>
                <td style="text-align:right;">
                  <span style="font-size:20px;font-weight:700;color:#1b4332;font-family:Arial,sans-serif;">{total_str}</span>
                  <span style="font-size:12px;color:#888;font-family:Arial,sans-serif;"> COP</span>
                </td>
              </tr>
            </table>"""

        # --- Events ---
        event_rows = ""
        if events:
            for i, ev in enumerate(events[:6]):
                color = _EVENT_COLORS[i % len(_EVENT_COLORS)]
                emoji = _event_emoji(ev.name)
                event_rows += f"""
                <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;background:#fff;border-radius:8px;border-left:4px solid {color};">
                  <tr><td style="padding:14px 18px;">
                    <table width="100%"><tr>
                      <td>
                        <div style="font-size:15px;color:#333;margin-bottom:3px;">{emoji} &nbsp;<strong>{ev.name}</strong></div>
                        <div style="font-size:12px;color:#888;font-family:Arial,sans-serif;">@{ev.agency} &nbsp;·&nbsp; {ev.date_label}</div>
                      </td>
                      <td style="text-align:right;white-space:nowrap;vertical-align:top;">
                        <div style="font-size:16px;font-weight:700;color:{color};font-family:Arial,sans-serif;">{ev.price_formatted}</div>
                      </td>
                    </tr></table>
                  </td></tr>
                </table>"""
        else:
            event_rows = "<p style='font-size:13px;color:#aaa;font-family:Arial,sans-serif;font-style:italic;'>Sin eventos confirmados para estas fechas.</p>"

        divider = '<hr style="border:none;border-top:2px dashed #d8f3dc;margin:32px 0;">' if idx < n - 1 else ""

        pair_sections += f"""
        <!-- WEEKEND {idx+1} -->
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;">
          <tr>
            <td style="border-left:4px solid #2d6a4f;padding-left:14px;">
              <div style="font-size:11px;color:#888;font-family:Arial,sans-serif;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:2px;">Finde {idx+1} de {n}</div>
              <div style="font-size:20px;color:#1b4332;font-weight:400;">📅 {label}</div>
            </td>
          </tr>
        </table>
        <div style="margin:12px 0 4px;">{outbound_row}</div>
        {sunday_note}
        {return_rows}
        {total_row}
        <div style="text-align:center;padding:12px 0 16px;">
          <span style="font-size:11px;color:#aaa;font-family:Arial,sans-serif;text-transform:uppercase;letter-spacing:2px;">— Planes ese finde —</span>
        </div>
        {event_rows}
        {divider}"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#fafaf8;font-family:Georgia,'Times New Roman',serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#fafaf8;padding:32px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

  <!-- HEADER -->
  <tr><td style="background:#1b4332;padding:12px 40px;border-radius:12px 12px 0 0;">
    <table width="100%"><tr>
      <td style="font-size:12px;color:#95d5b2;font-family:Arial,sans-serif;letter-spacing:2px;text-transform:uppercase;">Adventure Tracker</td>
      <td style="text-align:right;font-size:12px;color:#52b788;font-family:Arial,sans-serif;">{generated_at}</td>
    </tr></table>
  </td></tr>

  <!-- HERO -->
  <tr><td style="background:linear-gradient(180deg,#2d6a4f 0%,#40916c 60%,#52b788 100%);padding:48px 40px 36px;text-align:center;">
    <div style="font-size:44px;margin-bottom:12px;">🌄</div>
    <h1 style="margin:0 0 6px;font-size:34px;font-weight:400;color:#ffffff;font-style:italic;">¡A empacar!</h1>
    <p style="margin:0 0 24px;font-size:15px;color:#b7e4c7;font-family:Arial,sans-serif;">{n} finde{"s" if n > 1 else ""} barato{"s" if n > 1 else ""} encontrado{"s" if n > 1 else ""}</p>
    <table cellpadding="0" cellspacing="0" style="margin:0 auto;">
      <tr><td style="background:rgba(0,0,0,0.25);border-radius:50px;padding:8px 24px;">
        <span style="font-size:14px;color:#d8f3dc;font-family:Arial,sans-serif;font-weight:600;">📅 {date_range}</span>
      </td></tr>
    </table>
  </td></tr>

  <!-- BODY -->
  <tr><td style="background:#fafaf8;padding:36px 40px 40px;">
    {pair_sections}
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:32px;">
      <tr><td style="text-align:center;">
        <a href="https://www.google.com/travel/flights" style="display:inline-block;background:#1b4332;color:#d8f3dc;text-decoration:none;padding:14px 44px;border-radius:4px;font-size:14px;font-family:Arial,sans-serif;font-weight:600;letter-spacing:0.5px;">Ver vuelos en Google Flights →</a>
      </td></tr>
    </table>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:#1b4332;border-radius:0 0 12px 12px;padding:18px 40px;text-align:center;">
    <p style="margin:0;font-size:12px;color:#52b788;font-family:Arial,sans-serif;">Adventure Tracker · Solo te avisa cuando vale la pena ✌️</p>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""

    generated_at = datetime.now().strftime("%d %b %Y · %H:%M")
    n = len(weekends)
    date_range = ""
    all_dates = []
    for w in weekends:
        all_dates.extend([f.travel_date for f in w["outbound"] + w["returns"]])
    if all_dates:
        mn, mx = min(all_dates), max(all_dates)
        date_range = f"{mn.strftime('%d %b')}–{mx.strftime('%d %b %Y')}"

    # Build one section per weekend
    weekend_sections = ""
    for idx, w in enumerate(weekends):
        ws = w["window_start"]
        we = w["window_end"]
        label = f"{ws.strftime('%d')}–{we.strftime('%d %b %Y')}"
        outbound = w["outbound"]
        returns = w["returns"]
        events = w["events"]

        # Pair total for this weekend
        total = sum(f.price for f in outbound + returns)
        total_str = f"${total:,}".replace(",", ".") if total else ""

        # Flight rows
        flight_rows = ""
        for f in outbound:
            ds = f.travel_date.strftime("%A %d de %B").capitalize()
            star = " ★" if f.is_priority else ""
            price_str = f"${f.price:,}".replace(",", ".")
            flight_rows += f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;background:#fff;border-radius:8px;border-left:4px solid #2d6a4f;">
              <tr><td style="padding:14px 18px;">
                <table width="100%"><tr>
                  <td>
                    <div style="font-size:15px;color:#333;margin-bottom:3px;">✈️ &nbsp;<strong>BAQ → MDE &nbsp;·&nbsp; {f.departure_time}</strong></div>
                    <div style="font-size:12px;color:#888;font-family:Arial,sans-serif;">{ds} · {f.airline}{star}</div>
                  </td>
                  <td style="text-align:right;white-space:nowrap;vertical-align:top;">
                    <div style="font-size:17px;font-weight:700;color:#2d6a4f;font-family:Arial,sans-serif;">{price_str}</div>
                    <div style="font-size:11px;color:#aaa;font-family:Arial,sans-serif;">COP</div>
                  </td>
                </tr></table>
              </td></tr>
            </table>"""

        for f in returns:
            ds = f.travel_date.strftime("%A %d de %B").capitalize()
            star = " ★" if f.is_priority else ""
            price_str = f"${f.price:,}".replace(",", ".")
            flight_rows += f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;background:#fff;border-radius:8px;border-left:4px solid #40916c;">
              <tr><td style="padding:14px 18px;">
                <table width="100%"><tr>
                  <td>
                    <div style="font-size:15px;color:#333;margin-bottom:3px;">🔄 &nbsp;<strong>MDE → BAQ &nbsp;·&nbsp; {f.departure_time}</strong></div>
                    <div style="font-size:12px;color:#888;font-family:Arial,sans-serif;">{ds} · {f.airline}{star}</div>
                  </td>
                  <td style="text-align:right;white-space:nowrap;vertical-align:top;">
                    <div style="font-size:17px;font-weight:700;color:#40916c;font-family:Arial,sans-serif;">{price_str}</div>
                    <div style="font-size:11px;color:#aaa;font-family:Arial,sans-serif;">COP</div>
                  </td>
                </tr></table>
              </td></tr>
            </table>"""

        # Total for this weekend
        total_row = ""
        if total_str:
            total_row = f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="margin:4px 0 20px;">
              <tr>
                <td style="font-size:13px;color:#888;font-family:Arial,sans-serif;">Ida + Vuelta este finde</td>
                <td style="text-align:right;">
                  <span style="font-size:20px;font-weight:700;color:#1b4332;font-family:Arial,sans-serif;">{total_str}</span>
                  <span style="font-size:12px;color:#888;font-family:Arial,sans-serif;"> COP</span>
                </td>
              </tr>
            </table>"""

        # Event rows
        event_rows = ""
        if events:
            for i, ev in enumerate(events[:6]):
                color = _EVENT_COLORS[i % len(_EVENT_COLORS)]
                emoji = _event_emoji(ev.name)
                event_rows += f"""
                <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;background:#fff;border-radius:8px;border-left:4px solid {color};">
                  <tr><td style="padding:14px 18px;">
                    <table width="100%"><tr>
                      <td>
                        <div style="font-size:15px;color:#333;margin-bottom:3px;">{emoji} &nbsp;<strong>{ev.name}</strong></div>
                        <div style="font-size:12px;color:#888;font-family:Arial,sans-serif;">@{ev.agency} &nbsp;·&nbsp; {ev.date_label}</div>
                      </td>
                      <td style="text-align:right;white-space:nowrap;vertical-align:top;">
                        <div style="font-size:16px;font-weight:700;color:{color};font-family:Arial,sans-serif;">{ev.price_formatted}</div>
                      </td>
                    </tr></table>
                  </td></tr>
                </table>"""
        else:
            event_rows = "<p style='font-size:13px;color:#aaa;font-family:Arial,sans-serif;font-style:italic;'>Sin eventos confirmados para estas fechas.</p>"

        # Divider between weekends (not after last one)
        divider = '<hr style="border:none;border-top:2px dashed #d8f3dc;margin:32px 0;">' if idx < len(weekends) - 1 else ""

        weekend_sections += f"""
        <!-- WEEKEND {idx+1} -->
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:8px;">
          <tr>
            <td style="border-left:4px solid #2d6a4f;padding-left:14px;">
              <div style="font-size:11px;color:#888;font-family:Arial,sans-serif;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:2px;">Finde {idx+1} de {n}</div>
              <div style="font-size:20px;color:#1b4332;font-weight:400;">📅 {label}</div>
            </td>
          </tr>
        </table>
        <div style="margin:16px 0 8px;">{flight_rows}</div>
        {total_row}
        <div style="text-align:center;padding:12px 0 16px;">
          <span style="font-size:11px;color:#aaa;font-family:Arial,sans-serif;text-transform:uppercase;letter-spacing:2px;">— Planes ese finde —</span>
        </div>
        {event_rows}
        {divider}"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#fafaf8;font-family:Georgia,'Times New Roman',serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#fafaf8;padding:32px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

  <!-- HEADER -->
  <tr><td style="background:#1b4332;padding:12px 40px;border-radius:12px 12px 0 0;">
    <table width="100%"><tr>
      <td style="font-size:12px;color:#95d5b2;font-family:Arial,sans-serif;letter-spacing:2px;text-transform:uppercase;">Adventure Tracker</td>
      <td style="text-align:right;font-size:12px;color:#52b788;font-family:Arial,sans-serif;">{generated_at}</td>
    </tr></table>
  </td></tr>

  <!-- HERO -->
  <tr><td style="background:linear-gradient(180deg,#2d6a4f 0%,#40916c 60%,#52b788 100%);padding:48px 40px 36px;text-align:center;">
    <div style="font-size:44px;margin-bottom:12px;">🌄</div>
    <h1 style="margin:0 0 6px;font-size:34px;font-weight:400;color:#ffffff;font-style:italic;">¡A empacar!</h1>
    <p style="margin:0 0 24px;font-size:15px;color:#b7e4c7;font-family:Arial,sans-serif;">{n} finde{"s" if n > 1 else ""} barato{"s" if n > 1 else ""} encontrado{"s" if n > 1 else ""}</p>
    <table cellpadding="0" cellspacing="0" style="margin:0 auto;">
      <tr><td style="background:rgba(0,0,0,0.25);border-radius:50px;padding:8px 24px;">
        <span style="font-size:14px;color:#d8f3dc;font-family:Arial,sans-serif;font-weight:600;">📅 {date_range}</span>
      </td></tr>
    </table>
  </td></tr>

  <!-- BODY -->
  <tr><td style="background:#fafaf8;padding:36px 40px 40px;">
    {weekend_sections}

    <!-- CTA -->
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:32px;">
      <tr><td style="text-align:center;">
        <a href="https://www.google.com/travel/flights" style="display:inline-block;background:#1b4332;color:#d8f3dc;text-decoration:none;padding:14px 44px;border-radius:4px;font-size:14px;font-family:Arial,sans-serif;font-weight:600;letter-spacing:0.5px;">Ver vuelos en Google Flights →</a>
      </td></tr>
    </table>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:#1b4332;border-radius:0 0 12px 12px;padding:18px 40px;text-align:center;">
    <p style="margin:0;font-size:12px;color:#52b788;font-family:Arial,sans-serif;">Adventure Tracker · Solo te avisa cuando vale la pena ✌️</p>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""

    # --- total price ---
    total_price = sum(f.price for f in outbound_flights + return_flights)
    total_str = f"${total_price:,}".replace(",", ".") if total_price else ""

    # --- outbound rows ---
    ida_rows = ""
    for f in outbound_flights:
        date_str = f.travel_date.strftime("%A %d de %B").capitalize()
        star = " ★" if f.is_priority else ""
        price_str = f"${f.price:,}".replace(",", ".")
        ida_rows += f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:12px;background:#fff;border-radius:8px;border-left:4px solid #2d6a4f;">
          <tr><td style="padding:16px 20px;">
            <table width="100%"><tr>
              <td>
                <div style="font-size:16px;color:#333;margin-bottom:4px;">✈️ &nbsp;<strong>BAQ → MDE &nbsp;·&nbsp; {f.departure_time}</strong></div>
                <div style="font-size:13px;color:#888;font-family:Arial,sans-serif;">{date_str} · {f.airline}{star}</div>
              </td>
              <td style="text-align:right;white-space:nowrap;vertical-align:top;">
                <div style="font-size:18px;font-weight:700;color:#2d6a4f;font-family:Arial,sans-serif;">{price_str}</div>
                <div style="font-size:11px;color:#aaa;font-family:Arial,sans-serif;">COP</div>
              </td>
            </tr></table>
          </td></tr>
        </table>"""

    # --- return rows ---
    vuelta_rows = ""
    for f in return_flights:
        date_str = f.travel_date.strftime("%A %d de %B").capitalize()
        star = " ★" if f.is_priority else ""
        price_str = f"${f.price:,}".replace(",", ".")
        vuelta_rows += f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:12px;background:#fff;border-radius:8px;border-left:4px solid #40916c;">
          <tr><td style="padding:16px 20px;">
            <table width="100%"><tr>
              <td>
                <div style="font-size:16px;color:#333;margin-bottom:4px;">🔄 &nbsp;<strong>MDE → BAQ &nbsp;·&nbsp; {f.departure_time}</strong></div>
                <div style="font-size:13px;color:#888;font-family:Arial,sans-serif;">{date_str} · {f.airline}{star}</div>
              </td>
              <td style="text-align:right;white-space:nowrap;vertical-align:top;">
                <div style="font-size:18px;font-weight:700;color:#40916c;font-family:Arial,sans-serif;">{price_str}</div>
                <div style="font-size:11px;color:#aaa;font-family:Arial,sans-serif;">COP</div>
              </td>
            </tr></table>
          </td></tr>
        </table>"""

    # --- total row ---
    total_row = ""
    if total_str:
        total_row = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:4px;margin-bottom:0;">
          <tr>
            <td style="font-size:13px;color:#888;font-family:Arial,sans-serif;">Ida + Vuelta estimado</td>
            <td style="text-align:right;">
              <span style="font-size:22px;font-weight:700;color:#1b4332;font-family:Arial,sans-serif;">{total_str}</span>
              <span style="font-size:13px;color:#888;font-family:Arial,sans-serif;"> COP</span>
            </td>
          </tr>
        </table>"""

    # --- events rows ---
    events_html = ""
    has_any = any(m.has_events for m in weekend_matches)

    if has_any:
        for match in weekend_matches:
            if not match.has_events:
                continue
            for i, ev in enumerate(match.events[:6]):
                color = _EVENT_COLORS[i % len(_EVENT_COLORS)]
                emoji = _event_emoji(ev.name)
                date_str = ev.date_label
                agency = ev.agency or "brutaltravel"
                price_str = ev.price_formatted
                events_html += f"""
                <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:14px;background:#fff;border-radius:8px;border-left:4px solid {color};">
                  <tr><td style="padding:16px 20px;">
                    <table width="100%"><tr>
                      <td>
                        <div style="font-size:16px;color:#333;margin-bottom:4px;">{emoji} &nbsp;<strong>{ev.name}</strong></div>
                        <div style="font-size:13px;color:#888;font-family:Arial,sans-serif;">@{agency} &nbsp;·&nbsp; {date_str}</div>
                      </td>
                      <td style="text-align:right;white-space:nowrap;vertical-align:top;">
                        <div style="font-size:18px;font-weight:700;color:{color};font-family:Arial,sans-serif;">{price_str}</div>
                      </td>
                    </tr></table>
                  </td></tr>
                </table>"""
    else:
        events_html = """
        <p style="font-size:14px;color:#aaa;font-family:Arial,sans-serif;font-style:italic;text-align:center;padding:16px 0;">
          Sin eventos de agencias confirmados para esas fechas.
        </p>"""

    generated_at = datetime.now().strftime("%d %b %Y · %H:%M")

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#fafaf8;font-family:Georgia,'Times New Roman',serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#fafaf8;padding:32px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

  <!-- HEADER BAND -->
  <tr><td style="background:#1b4332;padding:12px 40px;border-radius:12px 12px 0 0;">
    <table width="100%"><tr>
      <td style="font-size:12px;color:#95d5b2;font-family:Arial,sans-serif;letter-spacing:2px;text-transform:uppercase;">Adventure Tracker</td>
      <td style="text-align:right;font-size:12px;color:#52b788;font-family:Arial,sans-serif;">{generated_at}</td>
    </tr></table>
  </td></tr>

  <!-- HERO BANNER -->
  <tr><td style="background:linear-gradient(180deg,#2d6a4f 0%,#40916c 60%,#52b788 100%);padding:52px 40px 40px;text-align:center;">
    <div style="font-size:48px;margin-bottom:16px;">🌄</div>
    <h1 style="margin:0 0 6px;font-size:38px;font-weight:400;color:#ffffff;font-style:italic;">¡A empacar!</h1>
    <p style="margin:0 0 28px;font-size:16px;color:#b7e4c7;font-family:Arial,sans-serif;">Encontramos vuelos baratos para este finde</p>
    <table cellpadding="0" cellspacing="0" style="margin:0 auto;">
      <tr><td style="background:rgba(0,0,0,0.25);border-radius:50px;padding:10px 28px;">
        <span style="font-size:15px;color:#d8f3dc;font-family:Arial,sans-serif;font-weight:600;">📅 {date_range}</span>
      </td></tr>
    </table>
  </td></tr>

  <!-- VUELOS -->
  <tr><td style="background:#ffffff;padding:36px 40px 28px;">
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      <tr>
        <td style="border-left:4px solid #2d6a4f;padding-left:14px;">
          <div style="font-size:11px;color:#888;font-family:Arial,sans-serif;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:4px;">Los vuelos</div>
          <div style="font-size:22px;color:#1b4332;font-weight:400;">Barranquilla ↔ Medellín</div>
        </td>
      </tr>
    </table>
    {ida_rows}
    {vuelta_rows}
    {total_row}
  </td></tr>

  <!-- EVENTOS -->
  <tr><td style="background:#fafaf8;padding:8px 40px 40px;">
    <div style="text-align:center;padding:28px 0 24px;">
      <span style="font-size:11px;color:#aaa;font-family:Arial,sans-serif;text-transform:uppercase;letter-spacing:3px;">— Qué hacer ese finde —</span>
    </div>
    {events_html}

    <!-- CTA -->
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:28px;">
      <tr><td style="text-align:center;">
        <a href="https://www.google.com/travel/flights" style="display:inline-block;background:#1b4332;color:#d8f3dc;text-decoration:none;padding:16px 48px;border-radius:4px;font-size:15px;font-family:Arial,sans-serif;font-weight:600;letter-spacing:0.5px;">Ver vuelos en Google Flights →</a>
      </td></tr>
    </table>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:#1b4332;border-radius:0 0 12px 12px;padding:20px 40px;text-align:center;">
    <p style="margin:0;font-size:12px;color:#52b788;font-family:Arial,sans-serif;">Adventure Tracker · Solo te avisa cuando vale la pena ✌️</p>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""
