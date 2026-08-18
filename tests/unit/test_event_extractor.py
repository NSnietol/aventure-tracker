"""Tests for event_extractor module."""

from datetime import date
from unittest.mock import patch

from aventure_tracker.services.instagram.extractor import (
    EventInfo,
    _clean_event_name,
    _infer_year,
    _remove_emojis,
    extract_date_from_text,
    extract_event_info,
    extract_event_name,
    slugify,
)


class TestSlugify:
    """Tests for slugify function."""

    def test_basic_text(self) -> None:
        """Test slugifying basic text."""
        assert slugify("Cocuy Trek") == "cocuy-trek"

    def test_accented_characters(self) -> None:
        """Test accented characters are normalized."""
        assert slugify("Páramo del Sumapáz") == "paramo-del-sumapaz"
        assert slugify("Guatapé") == "guatape"

    def test_special_characters(self) -> None:
        """Test special characters are removed."""
        assert slugify("Tour: 15 Agosto!") == "tour-15-agosto"
        assert slugify("Trek @ Cocuy #adventure") == "trek-cocuy-adventure"

    def test_multiple_spaces(self) -> None:
        """Test multiple spaces collapse to single hyphen."""
        assert slugify("Cocuy    Trek") == "cocuy-trek"

    def test_empty_string(self) -> None:
        """Test empty string."""
        assert slugify("") == ""

    def test_leading_trailing_hyphens(self) -> None:
        """Test leading/trailing hyphens are removed."""
        assert slugify("  Cocuy Trek  ") == "cocuy-trek"


class TestExtractDateFromText:
    """Tests for extract_date_from_text function."""

    def test_spanish_date_format(self) -> None:
        """Test '15 de agosto' format."""
        result, raw = extract_date_from_text("Salida 15 de agosto por la mañana")
        assert result is not None
        assert result.month == 8
        assert result.day == 15
        assert "15 de agosto" in raw

    def test_spanish_date_with_year(self) -> None:
        """Test '15 de agosto 2026' format."""
        result, raw = extract_date_from_text("Trek 15 de agosto 2026")
        assert result == date(2026, 8, 15)

    def test_abbreviated_month(self) -> None:
        """Test abbreviated month names."""
        result, _ = extract_date_from_text("Salida 20 ago")
        assert result is not None
        assert result.month == 8
        assert result.day == 20

    def test_month_first_format(self) -> None:
        """Test 'agosto 15' format."""
        result, _ = extract_date_from_text("agosto 15 salida confirmada")
        assert result is not None
        assert result.month == 8
        assert result.day == 15

    def test_numeric_format_slash(self) -> None:
        """Test '15/08/2026' format."""
        result, _ = extract_date_from_text("Fecha: 15/08/2026")
        assert result == date(2026, 8, 15)

    def test_numeric_format_dash(self) -> None:
        """Test '15-08-2026' format."""
        result, _ = extract_date_from_text("Salida 15-08-2026")
        assert result == date(2026, 8, 15)

    def test_numeric_format_short_year(self) -> None:
        """Test '15/08/26' format with 2-digit year."""
        result, _ = extract_date_from_text("Fecha 15/08/26")
        assert result == date(2026, 8, 15)

    def test_month_year_only(self) -> None:
        """Test 'agosto 2026' format (assumes day 1)."""
        result, _ = extract_date_from_text("Tour agosto 2026")
        assert result == date(2026, 8, 1)

    def test_no_date_found(self) -> None:
        """Test text with no date."""
        result, raw = extract_date_from_text("Gran aventura en el Cocuy!")
        assert result is None
        assert raw is None

    def test_invalid_day(self) -> None:
        """Test invalid day is rejected."""
        result, _ = extract_date_from_text("32 de agosto")
        assert result is None

    @patch("aventure_tracker.services.instagram.extractor.date")
    def test_infers_next_year_for_past_date(self, mock_date) -> None:
        """Test past dates infer next year."""
        # Mock today as August 20, 2026
        mock_date.today.return_value = date(2026, 8, 20)
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        # January 15 without year should be 2027 since it's past
        result, _ = extract_date_from_text("Salida 15 de enero próximo")
        assert result is not None
        assert result.year == 2027


class TestInferYear:
    """Tests for _infer_year function."""

    def test_future_date_same_year(self) -> None:
        """Test future date in same year stays same year."""
        today = date.today()
        # Use December, which is always in the future or current
        year = _infer_year(12, 31, today.year)
        if today.month == 12 and today.day > 31:
            assert year == today.year + 1
        else:
            assert year == today.year

    def test_none_month(self) -> None:
        """Test None month returns current year."""
        assert _infer_year(None, 15, 2026) == 2026


class TestRemoveEmojis:
    """Tests for _remove_emojis function."""

    def test_removes_emojis(self) -> None:
        """Test emojis are removed."""
        text = "🏔️ Trek al Cocuy 🥾"
        result = _remove_emojis(text)
        assert "Trek al Cocuy" in result
        assert "🏔" not in result
        assert "🥾" not in result

    def test_preserves_text(self) -> None:
        """Test regular text is preserved."""
        text = "Aventura en Colombia"
        assert _remove_emojis(text) == text


class TestCleanEventName:
    """Tests for _clean_event_name function."""

    def test_removes_special_chars(self) -> None:
        """Test special characters removed."""
        result = _clean_event_name("Trek: Cocuy!")
        assert result == "Trek Cocuy"

    def test_removes_stop_words_edges(self) -> None:
        """Test stop words removed from edges."""
        result = _clean_event_name("de la Expedición al Cocuy de")
        assert result == "Expedición al Cocuy"

    def test_keeps_accents(self) -> None:
        """Test accented characters preserved."""
        result = _clean_event_name("Páramo del Sumapáz")
        assert "Páramo" in result
        assert "Sumapáz" in result


class TestExtractEventName:
    """Tests for extract_event_name function."""

    def test_first_line_of_caption(self) -> None:
        """Test extracts first line of caption."""
        caption = """Trek al Nevado del Cocuy
        Salida 15 de agosto
        #aventura #colombia"""
        result = extract_event_name(caption)
        assert "Cocuy" in result or "Trek" in result

    def test_from_hashtag(self) -> None:
        """Test extracts from hashtag when no other option."""
        caption = "¡Vamos! #NevadoDelCocuy"
        result = extract_event_name(caption)
        assert "Cocuy" in result or "Nevado" in result

    def test_empty_caption(self) -> None:
        """Test handles empty caption."""
        result = extract_event_name("")
        assert result == "Unknown Event"

    def test_only_emojis(self) -> None:
        """Test handles caption with only emojis."""
        result = extract_event_name("🏔️🥾⛰️")
        assert result == "Unknown Event"

    def test_pattern_matching(self) -> None:
        """Test pattern matching for trek/tour."""
        caption = "Próxima expedición al Páramo de Sumapáz"
        result = extract_event_name(caption)
        # Should extract something meaningful
        assert len(result) > 3


class TestExtractEventInfo:
    """Tests for extract_event_info function."""

    def test_full_extraction(self) -> None:
        """Test complete extraction with date and name."""
        caption = """Trek al Nevado del Cocuy
        Salida 15 de agosto 2026
        Incluye transporte y guía"""

        result = extract_event_info(caption)

        assert result.event_date == "2026-08-15"
        assert result.year == 2026
        assert "cocuy" in result.event_id.lower() or "trek" in result.event_id.lower()
        assert result.event_id.startswith("2026-08-15-")

    def test_no_date_extraction(self) -> None:
        """Test extraction without date."""
        caption = "Gran aventura en el Cocuy próximamente"

        result = extract_event_info(caption)

        assert result.event_date is None
        assert result.year is None
        # event_id should just be the slug
        assert "-" in result.event_id or result.event_id == slugify(result.event_name)

    def test_with_ocr_text(self) -> None:
        """Test extraction using OCR when caption lacks date."""
        caption = "Próximo tour al Cocuy"
        ocr_text = "Salida 20 de septiembre 2026"

        result = extract_event_info(caption, ocr_text)

        assert result.event_date == "2026-09-20"

    def test_event_id_format(self) -> None:
        """Test event_id has correct format."""
        caption = "Trek Cocuy 15 agosto 2026"

        result = extract_event_info(caption)

        # Should be date-slug format
        parts = result.event_id.split("-")
        assert len(parts) >= 4  # YYYY-MM-DD-slug
        assert parts[0] == "2026"
        assert parts[1] == "08"
        assert parts[2] == "15"

    def test_long_name_truncated(self) -> None:
        """Test very long event names are truncated in event_id."""
        caption = (
            "Esta es una expedición increíble al páramo más hermoso "
            "de Colombia con vistas espectaculares del amanecer"
        )

        result = extract_event_info(caption)

        # event_id slug should be max 50 chars
        if "-" in result.event_id:
            slug_parts = result.event_id.split("-")
            if len(slug_parts) > 3:  # Has date
                slug = "-".join(slug_parts[3:])
            else:
                slug = result.event_id
        else:
            slug = result.event_id

        assert len(slug) <= 50


class TestEventInfo:
    """Tests for EventInfo dataclass."""

    def test_create_event_info(self) -> None:
        """Test creating EventInfo instance."""
        info = EventInfo(
            event_date="2026-08-15",
            event_name="Cocuy Trek",
            event_id="2026-08-15-cocuy-trek",
            raw_date_text="15 de agosto 2026",
            year=2026,
        )

        assert info.event_date == "2026-08-15"
        assert info.event_name == "Cocuy Trek"
        assert info.event_id == "2026-08-15-cocuy-trek"
        assert info.year == 2026

    def test_default_values(self) -> None:
        """Test default values."""
        info = EventInfo(
            event_date=None,
            event_name="Test",
            event_id="test",
        )

        assert info.raw_date_text is None
        assert info.year is None


class TestRealWorldCaptions:
    """Tests with realistic Instagram captions."""

    def test_brutal_travel_style(self) -> None:
        """Test typical BrutalTravel caption format."""
        caption = """🏔️ NEVADO DEL COCUY 🏔️

📅 15 de Agosto 2026
💰 $850.000 COP
📍 Salida desde Bogotá

Incluye:
- Transporte
- Guía certificado
- Alimentación

#cocuy #colombia #trekking"""

        result = extract_event_info(caption)

        assert result.event_date == "2026-08-15"
        assert "cocuy" in result.event_id.lower()

    def test_medellin_bungee_style(self) -> None:
        """Test Medellin bungee caption."""
        caption = """Salto en Bungee 🪂

Próxima salida: 20/09/2026
Lugar: Puente de Occidente

Reservas al WhatsApp"""

        result = extract_event_info(caption)

        assert result.event_date == "2026-09-20"
        assert "bungee" in result.event_id.lower() or "salto" in result.event_id.lower()

    def test_minimal_caption(self) -> None:
        """Test minimal caption."""
        caption = "Agosto 15 - Cocuy"

        result = extract_event_info(caption)

        assert result.event_date is not None
        assert result.event_date.endswith("-08-15")
