"""HTML template for the error report email."""

_WARN_KEYWORDS = ("warning", "warn", "failed to sync", "no response", "skipping")


def _severity(idx: int, msg: str) -> str:
    """Classify an error as 'critical' or 'warn'.

    The first error is always critical (it usually caused the cascade).
    Subsequent errors containing warn-like keywords are classified as warn.
    """
    if idx == 0:
        return "critical"
    if any(k in msg.lower() for k in _WARN_KEYWORDS):
        return "warn"
    return "critical"


def _error_row(idx: int, error: str) -> str:
    """Build an HTML table row for a single error entry."""
    sev = _severity(idx, error)
    if sev == "critical":
        border_color = "#dc2626"
        badge_bg = "#fee2e2"
        badge_color = "#dc2626"
        badge_text = "CRÍTICO"
        label_color = "#dc2626"
    else:
        border_color = "#f59e0b"
        badge_bg = "#fef3c7"
        badge_color = "#d97706"
        badge_text = "WARN"
        label_color = "#d97706"

    # Split "Module: message" if the error has that pattern
    module = ""
    message = error
    if ": " in error and len(error.split(": ", 1)[0]) < 40:
        parts = error.split(": ", 1)
        module_candidate = parts[0].strip()
        if " " not in module_candidate or len(module_candidate.split()) <= 3:
            module = module_candidate
            message = parts[1].strip()

    module_html = (
        f'<div style="font-size:11px;color:{label_color};font-family:Arial,sans-serif;'
        f'font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">'
        f"{module}</div>"
        if module
        else ""
    )

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:12px;background:#fff;border-radius:8px;border-left:4px solid {border_color};">
      <tr><td style="padding:18px 20px;">
        <table width="100%"><tr>
          <td>
            {module_html}
            <div style="font-size:14px;color:#1f2937;font-family:Arial,sans-serif;margin-bottom:4px;">{message}</div>
          </td>
          <td style="text-align:right;white-space:nowrap;vertical-align:top;padding-left:16px;">
            <div style="background:{badge_bg};border-radius:50px;padding:3px 10px;display:inline-block;">
              <span style="font-size:10px;color:{badge_color};font-family:Arial,sans-serif;font-weight:700;">{badge_text}</span>
            </div>
          </td>
        </tr></table>
      </td></tr>
    </table>"""


def build_error_html(
    errors: list[str],
    mode: str,
    duration_seconds: float,
    routes_checked: int,
    routes_total: int,
    alerts_generated: int,
    run_url: str,
    generated_at: str,
) -> str:
    """Build the error report HTML email in the tropical style.

    Args:
        errors: List of error message strings.
        mode: Execution mode (all, flights, activities).
        duration_seconds: Total run duration.
        routes_checked: Routes successfully checked.
        routes_total: Total configured routes.
        alerts_generated: Alerts generated before failure.
        run_url: GitHub Actions run URL for the CTA button.
        generated_at: Pre-formatted timestamp string.

    Returns:
        Complete HTML string for the error email.
    """
    error_count = len(errors)
    error_rows = "".join(_error_row(idx, err) for idx, err in enumerate(errors))

    duration_str = f"{duration_seconds:.1f}s"
    routes_str = f"{routes_checked} / {routes_total}"

    cta_html = (
        f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:28px;">
      <tr><td style="text-align:center;">
        <a href="{run_url}" style="display:inline-block;background:#1b4332;color:#d8f3dc;text-decoration:none;padding:14px 40px;border-radius:4px;font-size:14px;font-family:Arial,sans-serif;font-weight:600;letter-spacing:0.5px;">Ver logs en GitHub Actions →</a>
      </td></tr>
    </table>"""
        if run_url
        else ""
    )

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

  <!-- HERO — ERROR STATE -->
  <tr><td style="background:linear-gradient(180deg,#7f1d1d 0%,#991b1b 50%,#b91c1c 100%);padding:48px 40px 36px;text-align:center;">
    <div style="font-size:48px;margin-bottom:12px;">⚠️</div>
    <h1 style="margin:0 0 6px;font-size:32px;font-weight:400;color:#ffffff;font-style:italic;">Algo salió mal</h1>
    <p style="margin:0 0 24px;font-size:15px;color:#fca5a5;font-family:Arial,sans-serif;">El tracker encontró {error_count} error{"es" if error_count != 1 else ""} durante la ejecución</p>
    <table cellpadding="0" cellspacing="0" style="margin:0 auto;">
      <tr><td style="background:rgba(0,0,0,0.25);border-radius:50px;padding:8px 24px;">
        <span style="font-size:13px;color:#fecaca;font-family:Arial,sans-serif;font-weight:600;">🕐 {generated_at}</span>
      </td></tr>
    </table>
  </td></tr>

  <!-- BODY -->
  <tr><td style="background:#fafaf8;padding:36px 40px 40px;">

    <p style="margin:0 0 24px;font-size:14px;color:#555;font-family:Arial,sans-serif;line-height:1.6;">
      La ejecución en modo <strong>{mode}</strong> completó con errores.
      No se enviaron alertas de vuelos ni eventos en esta corrida.
    </p>

    {error_rows}

    <!-- Resumen -->
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;margin-bottom:4px;background:#f3f4f6;border-radius:8px;">
      <tr><td style="padding:20px 22px;">
        <div style="font-size:11px;color:#6b7280;font-family:Arial,sans-serif;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:16px;">Resumen de la corrida</div>
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="font-size:13px;color:#6b7280;font-family:Arial,sans-serif;padding-bottom:8px;">Modo</td>
            <td style="font-size:13px;color:#1f2937;font-family:Arial,sans-serif;font-weight:600;text-align:right;padding-bottom:8px;">{mode}</td>
          </tr>
          <tr>
            <td style="font-size:13px;color:#6b7280;font-family:Arial,sans-serif;padding-bottom:8px;">Duración</td>
            <td style="font-size:13px;color:#1f2937;font-family:Arial,sans-serif;font-weight:600;text-align:right;padding-bottom:8px;">{duration_str}</td>
          </tr>
          <tr>
            <td style="font-size:13px;color:#6b7280;font-family:Arial,sans-serif;padding-bottom:8px;">Rutas revisadas</td>
            <td style="font-size:13px;color:#1f2937;font-family:Arial,sans-serif;font-weight:600;text-align:right;padding-bottom:8px;">{routes_str}</td>
          </tr>
          <tr>
            <td style="font-size:13px;color:#6b7280;font-family:Arial,sans-serif;padding-bottom:8px;">Alertas generadas</td>
            <td style="font-size:13px;color:#1f2937;font-family:Arial,sans-serif;font-weight:600;text-align:right;padding-bottom:8px;">{alerts_generated}</td>
          </tr>
          <tr>
            <td style="font-size:13px;color:#6b7280;font-family:Arial,sans-serif;border-top:1px solid #e5e7eb;padding-top:8px;">Errores totales</td>
            <td style="font-size:14px;color:#dc2626;font-family:Arial,sans-serif;font-weight:700;text-align:right;border-top:1px solid #e5e7eb;padding-top:8px;">{error_count}</td>
          </tr>
        </table>
      </td></tr>
    </table>

    {cta_html}

  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:#1b4332;border-radius:0 0 12px 12px;padding:18px 40px;text-align:center;">
    <p style="margin:0;font-size:12px;color:#52b788;font-family:Arial,sans-serif;">Adventure Tracker · Solo te avisa cuando vale la pena ✌️</p>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""
