"""HTML template for the weekend flight report email."""

from aventure_tracker.infrastructure.email.helpers import (
    EVENT_COLORS,
    event_emoji,
    now_colombia,
)


def _outbound_row(outbound: object, return_only: bool) -> str:
    """Build the outbound flight row (or return-only notice)."""
    if return_only:
        return """
            <div style="background:#fff8e1;border-left:3px solid #f9a825;padding:10px 14px;border-radius:6px;margin-bottom:10px;font-size:13px;color:#7c5f00;font-family:Arial,sans-serif;">
              💡 <strong>Vuelta barata encontrada.</strong> No hay vuelo de ida bajo el umbral por ahora — monitorea los próximos días.
            </div>"""

    ds_out = outbound.travel_date.strftime("%A %d de %B").capitalize()  # type: ignore[attr-defined]
    star_out = " ★" if outbound.is_priority else ""  # type: ignore[attr-defined]
    price_out = f"${outbound.price:,}".replace(",", ".")  # type: ignore[attr-defined]
    return f"""
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


def _sunday_note_html(sunday_flag: bool) -> str:
    """Build the sunday-adventure warning banner."""
    if not sunday_flag:
        return ""
    return """
            <div style="background:#fff8e1;border-left:3px solid #f9a825;padding:8px 14px;border-radius:4px;margin-bottom:10px;font-size:12px;color:#7c5f00;font-family:Arial,sans-serif;">
              ⚠️ Hay planes el domingo — regreso recomendado el <strong>lunes temprano</strong>
            </div>"""


def _return_rows_html(pair: object) -> str:
    """Build return-flight rows (recommended + alternatives)."""
    if not pair.return_options:  # type: ignore[attr-defined]
        return "<p style='font-size:13px;color:#e65100;font-family:Arial,sans-serif;'>⚠️ Sin vuelos de regreso encontrados para este finde.</p>"

    rows = ""
    for i, ro in enumerate(pair.return_options):  # type: ignore[attr-defined]
        f = ro.flight
        ds_ret = f.travel_date.strftime("%A %d de %B").capitalize()
        star_ret = " ★" if f.is_priority else ""
        price_ret = f"${f.price:,}".replace(",", ".")

        if ro.is_recommended:
            savings_html = ""
            if ro.savings_vs_priority and ro.savings_vs_priority > 0:
                savings_str = f"${ro.savings_vs_priority:,}".replace(",", ".")
                savings_html = f'<span style="font-size:11px;color:#2e7d32;font-family:Arial,sans-serif;"> ahorra {savings_str}</span>'
            rows += f"""
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
            rows += f"""
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
    return rows


def _total_row_html(pair: object, return_only: bool) -> str:
    """Build the total (outbound + recommended return) price row."""
    if not pair.total_price or return_only:  # type: ignore[attr-defined]
        return ""
    total_str = f"${pair.total_price:,}".replace(",", ".")  # type: ignore[attr-defined]
    return f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="margin:8px 0 20px;">
              <tr>
                <td style="font-size:13px;color:#888;font-family:Arial,sans-serif;">Ida + Vuelta recomendada</td>
                <td style="text-align:right;">
                  <span style="font-size:20px;font-weight:700;color:#1b4332;font-family:Arial,sans-serif;">{total_str}</span>
                  <span style="font-size:12px;color:#888;font-family:Arial,sans-serif;"> COP</span>
                </td>
              </tr>
            </table>"""


def _events_html(events: list) -> str:
    """Build event rows for a weekend pair."""
    if not events:
        return "<p style='font-size:13px;color:#aaa;font-family:Arial,sans-serif;font-style:italic;'>Sin eventos confirmados para estas fechas.</p>"

    rows = ""
    for i, ev in enumerate(events[:6]):
        color = EVENT_COLORS[i % len(EVENT_COLORS)]
        emoji = event_emoji(ev.name)
        is_manual = getattr(ev, "is_manual", False)
        manual_badge = (
            '<span style="font-size:10px;background:#e8f5e9;color:#2d6a4f;'
            "border-radius:4px;padding:2px 6px;font-family:Arial,sans-serif;"
            'font-weight:700;margin-left:6px;">📌 manual</span>'
            if is_manual
            else ""
        )
        price_display = (
            '<div style="font-size:13px;color:#aaa;font-family:Arial,sans-serif;">—</div>'
            if ev.price == 0
            else f'<div style="font-size:16px;font-weight:700;color:{color};font-family:Arial,sans-serif;">{ev.price_formatted}</div>'
        )
        rows += f"""
                <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;background:#fff;border-radius:8px;border-left:4px solid {color};">
                  <tr><td style="padding:14px 18px;">
                    <table width="100%"><tr>
                      <td>
                        <div style="font-size:15px;color:#333;margin-bottom:3px;">{emoji} &nbsp;<strong>{ev.name}</strong>{manual_badge}</div>
                        <div style="font-size:12px;color:#888;font-family:Arial,sans-serif;">@{ev.agency} &nbsp;·&nbsp; {ev.date_label}</div>
                      </td>
                      <td style="text-align:right;white-space:nowrap;vertical-align:top;">
                        {price_display}
                      </td>
                    </tr></table>
                  </td></tr>
                </table>"""
    return rows


def build_weekend_report_html(pairs: list) -> str:
    """Build the Tropical/Adventure HTML email — one section per WeekendPair.

    Args:
        pairs: List of WeekendPair objects. Each must expose:
            outbound, return_options, events, sunday_adventure,
            date_label, total_price, return_only (optional attr).

    Returns:
        Complete HTML string for the weekend report email.
    """
    generated_at = now_colombia().strftime("%d %b %Y · %H:%M Col")
    n = len(pairs)
    all_dates = [p.outbound.travel_date for p in pairs]
    date_range = (
        f"{min(all_dates).strftime('%d %b')}–{max(all_dates).strftime('%d %b %Y')}"
        if all_dates
        else ""
    )

    pair_sections = ""
    for idx, pair in enumerate(pairs):
        return_only = getattr(pair, "return_only", False)

        outbound_row = _outbound_row(pair.outbound, return_only)
        sunday_note = _sunday_note_html(pair.sunday_adventure)
        return_rows = _return_rows_html(pair)
        total_row = _total_row_html(pair, return_only)
        event_rows = _events_html(pair.events)

        divider = (
            '<hr style="border:none;border-top:2px dashed #d8f3dc;margin:32px 0;">'
            if idx < n - 1
            else ""
        )

        pair_sections += f"""
        <!-- WEEKEND {idx + 1} -->
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;">
          <tr>
            <td style="border-left:4px solid #2d6a4f;padding-left:14px;">
              <div style="font-size:11px;color:#888;font-family:Arial,sans-serif;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:2px;">Finde {idx + 1} de {n}</div>
              <div style="font-size:20px;color:#1b4332;font-weight:400;">📅 {pair.date_label}</div>
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
