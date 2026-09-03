"""Tests for EmailNotifier and email sub-package."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from aventure_tracker.infrastructure.email.helpers import (
    EVENT_COLORS,
    event_emoji,
    now_colombia,
)
from aventure_tracker.infrastructure.email.templates.error_report import (
    build_error_html,
)
from aventure_tracker.infrastructure.email.templates.weekend_report import (
    build_weekend_report_html,
)
from aventure_tracker.infrastructure.email_notifier import EmailNotifier

# ---------------------------------------------------------------------------
# helpers.py
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_now_colombia_returns_utc_minus_5(self) -> None:
        t = now_colombia()
        assert t.utcoffset() == timedelta(hours=-5)

    def test_event_emoji_known_keywords(self) -> None:
        assert event_emoji("canyoning en el río") == "💦"
        assert event_emoji("rafting extremo") == "🌊"
        assert event_emoji("salto al vacío") == "🧗"
        assert event_emoji("ciclismo de montaña") == "🚵"
        assert event_emoji("nevado del ruiz") == "🏔"

    def test_event_emoji_unknown_returns_default(self) -> None:
        assert event_emoji("actividad desconocida") == "🏕"
        assert event_emoji("") == "🏕"

    def test_event_colors_has_entries(self) -> None:
        assert len(EVENT_COLORS) > 0


# ---------------------------------------------------------------------------
# error_report.py
# ---------------------------------------------------------------------------


class TestBuildErrorHtml:
    def test_returns_html_string(self) -> None:
        html = build_error_html(
            errors=["[TimeoutError] scraper failed"],
            mode="flights",
            duration_seconds=12.3,
            routes_checked=1,
            routes_total=2,
            alerts_generated=0,
            run_url="",
            generated_at="18 Aug 2026 · 08:00 Col",
        )
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html

    def test_includes_error_message(self) -> None:
        html = build_error_html(
            errors=["[PlaywrightTimeoutError] Page timeout"],
            mode="all",
            duration_seconds=5.0,
            routes_checked=0,
            routes_total=2,
            alerts_generated=0,
            run_url="",
            generated_at="18 Aug 2026",
        )
        assert "Page timeout" in html

    def test_includes_cta_when_run_url_provided(self) -> None:
        html = build_error_html(
            errors=["err"],
            mode="all",
            duration_seconds=1.0,
            routes_checked=0,
            routes_total=2,
            alerts_generated=0,
            run_url="https://github.com/actions/runs/123",
            generated_at="now",
        )
        assert "github.com/actions/runs/123" in html

    def test_no_cta_when_no_run_url(self) -> None:
        html = build_error_html(
            errors=["err"],
            mode="all",
            duration_seconds=1.0,
            routes_checked=0,
            routes_total=2,
            alerts_generated=0,
            run_url="",
            generated_at="now",
        )
        assert "Ver logs en GitHub Actions" not in html

    def test_first_error_is_critical(self) -> None:
        html = build_error_html(
            errors=["first error is always critical"],
            mode="all",
            duration_seconds=1.0,
            routes_checked=0,
            routes_total=2,
            alerts_generated=0,
            run_url="",
            generated_at="now",
        )
        assert "CRÍTICO" in html

    def test_warn_keyword_gives_warn_badge(self) -> None:
        html = build_error_html(
            errors=["critical first", "warning: skipping sync"],
            mode="all",
            duration_seconds=1.0,
            routes_checked=0,
            routes_total=2,
            alerts_generated=0,
            run_url="",
            generated_at="now",
        )
        assert "WARN" in html


# ---------------------------------------------------------------------------
# weekend_report.py
# ---------------------------------------------------------------------------


def _make_flight(
    travel_date, airline="LATAM", price=140_000, time="18:30", priority=True
):
    f = MagicMock()
    f.travel_date = travel_date
    f.airline = airline
    f.price = price
    f.departure_time = time
    f.is_priority = priority
    return f


def _make_pair(outbound_date, return_date=None, sunday_adv=False, return_only=False):

    out = _make_flight(outbound_date)
    pair = MagicMock()
    pair.outbound = out
    pair.sunday_adventure = sunday_adv
    pair.return_only = return_only
    pair.date_label = outbound_date.strftime("%d–%d %b %Y")
    pair.total_price = 280_000 if return_date else None
    pair.events = []

    if return_date:
        ret_flight = _make_flight(return_date, time="07:00")
        ro = MagicMock()
        ro.flight = ret_flight
        ro.is_recommended = True
        ro.savings_vs_priority = None
        pair.return_options = [ro]
        pair.recommended_return = ro
    else:
        pair.return_options = []
        pair.recommended_return = None

    return pair


class TestBuildWeekendReportHtml:
    def test_returns_html_string(self) -> None:
        from datetime import date

        pair = _make_pair(date(2026, 8, 27), date(2026, 8, 31))
        html = build_weekend_report_html([pair])
        assert "<!DOCTYPE html>" in html

    def test_includes_outbound_price(self) -> None:
        from datetime import date

        pair = _make_pair(date(2026, 8, 27), date(2026, 8, 31))
        html = build_weekend_report_html([pair])
        assert "140" in html  # price $140.000

    def test_sunday_note_shown_when_sunday_adventure(self) -> None:
        from datetime import date

        pair = _make_pair(date(2026, 8, 27), date(2026, 8, 31), sunday_adv=True)
        html = build_weekend_report_html([pair])
        assert "lunes temprano" in html

    def test_return_only_notice_shown(self) -> None:
        from datetime import date

        pair = _make_pair(date(2026, 8, 27), return_only=True)
        pair.return_options = []
        html = build_weekend_report_html([pair])
        assert "Vuelta barata encontrada" in html

    def test_multiple_pairs_have_divider(self) -> None:
        from datetime import date

        p1 = _make_pair(date(2026, 8, 27), date(2026, 8, 31))
        p2 = _make_pair(date(2026, 9, 3), date(2026, 9, 7))
        html = build_weekend_report_html([p1, p2])
        assert "Finde 1 de 2" in html
        assert "Finde 2 de 2" in html


# ---------------------------------------------------------------------------
# EmailNotifier (facade)
# ---------------------------------------------------------------------------


class TestEmailNotifier:
    def test_send_weekend_report_returns_false_for_empty_pairs(self) -> None:
        notifier = EmailNotifier(api_key="test", to_email="x@x.com")
        assert notifier.send_weekend_report([]) is False

    def test_send_weekend_report_calls_client(self) -> None:
        from datetime import date

        notifier = EmailNotifier(api_key="test", to_email="x@x.com")
        pair = _make_pair(date(2026, 8, 27), date(2026, 8, 31))
        pair.outbound.travel_date = date(2026, 8, 27)

        with patch.object(notifier._client, "send", return_value=True) as mock_send:
            result = notifier.send_weekend_report([pair])

        assert result is True
        mock_send.assert_called_once()
        subject = mock_send.call_args[0][0]
        assert "✈️" in subject

    def test_send_error_report_calls_client(self) -> None:
        notifier = EmailNotifier(api_key="test", to_email="x@x.com")

        with patch.object(notifier._client, "send", return_value=True) as mock_send:
            result = notifier.send_error_report(
                errors=["something broke"],
                mode="flights",
            )

        assert result is True
        mock_send.assert_called_once()
        subject = mock_send.call_args[0][0]
        assert "⚠️" in subject

    def test_send_test_message_calls_client(self) -> None:
        notifier = EmailNotifier(api_key="test", to_email="x@x.com")

        with patch.object(notifier._client, "send", return_value=True) as mock_send:
            result = notifier.send_test_message()

        assert result is True
        mock_send.assert_called_once()
