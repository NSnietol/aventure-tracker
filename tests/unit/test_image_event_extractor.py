"""Tests for image event extractor with local Tesseract OCR."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aventure_tracker.services.image_event_extractor import (
    ExtractionConfig,
    ImageEventExtractor,
)


@pytest.fixture
def extractor() -> ImageEventExtractor:
    """Create an extractor instance."""
    return ImageEventExtractor()


@pytest.fixture
def sample_ocr_data() -> dict:
    """Sample Tesseract OCR data."""
    return {
        "text": ["CAVERNAS", "DEL", "NUS", "1", "AGO", "$195.000"],
        "conf": [85, 90, 88, 95, 92, 80],
    }


class TestExtractionConfig:
    """Tests for ExtractionConfig."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        config = ExtractionConfig()
        assert config.year == 2026
        assert config.default_month == "agosto"
        assert config.tesseract_lang == "spa"
        assert config.preprocess is True

    def test_custom_values(self) -> None:
        """Should accept custom values."""
        config = ExtractionConfig(year=2025, default_month="septiembre")
        assert config.year == 2025
        assert config.default_month == "septiembre"


class TestImageEventExtractor:
    """Tests for ImageEventExtractor."""

    def test_get_month_number(self, extractor: ImageEventExtractor) -> None:
        """Should convert month names to numbers."""
        assert extractor._get_month_number("agosto") == 8
        assert extractor._get_month_number("AGOSTO") == 8
        assert extractor._get_month_number("septiembre") == 9
        assert extractor._get_month_number("sep") == 9
        assert extractor._get_month_number("enero") == 1
        assert extractor._get_month_number("diciembre") == 12
        assert extractor._get_month_number("unknown") == 8  # Default

    def test_check_sold_out(self, extractor: ImageEventExtractor) -> None:
        """Should detect sold out indicators."""
        assert extractor._check_sold_out("Evento AGOTADO") is True
        assert extractor._check_sold_out("SOLD OUT") is True
        assert extractor._check_sold_out("Cupos llenos") is True
        assert extractor._check_sold_out("Trip completo") is True
        assert extractor._check_sold_out("Disponible") is False

    def test_is_cover_image(self, extractor: ImageEventExtractor) -> None:
        """Should detect cover images."""
        cover_text = "AGOSTO\nEXPERIENCIAS BRUTAL\n2026"
        assert extractor._is_cover_image(cover_text) is True

        event_text = "CAVERNAS $195.000\nTATACOA $490.000"
        assert extractor._is_cover_image(event_text) is False

    def test_extract_name(self, extractor: ImageEventExtractor) -> None:
        """Should extract event name from line."""
        import re

        line = "CAVERNAS DEL NUS 1 AGO $195.000"
        price_match = re.search(r"\$[\d.]+", line)
        date_match = re.search(r"\d+\s*AGO", line)

        name = extractor._extract_name(line, price_match, date_match)
        assert "CAVERNAS" in name

    def test_parse_line_with_price_and_date(
        self, extractor: ImageEventExtractor
    ) -> None:
        """Should parse line with price and date."""
        line = "CAVERNAS DEL NUS 1 AGO $195.000"

        event = extractor._parse_line(
            line,
            agency="brutaltravel",
            month_num=8,
            source_image=Path("test.jpg"),
            base_confidence=85,
        )

        assert event is not None
        assert event.price == 195000
        assert event.date_start.day == 1
        assert event.date_start.month == 8

    def test_parse_line_date_range(self, extractor: ImageEventExtractor) -> None:
        """Should parse date ranges."""
        line = "TATACOA 21 al 23 AGO $490.000"

        event = extractor._parse_line(
            line,
            agency="brutaltravel",
            month_num=8,
            source_image=Path("test.jpg"),
            base_confidence=85,
        )

        assert event is not None
        assert event.date_start.day == 21
        assert event.date_end.day == 23
        assert event.is_multi_day is True

    def test_parse_line_no_price(self, extractor: ImageEventExtractor) -> None:
        """Should return None if no price found."""
        line = "CAVERNAS DEL NUS 1 AGO"

        event = extractor._parse_line(
            line,
            agency="brutaltravel",
            month_num=8,
            source_image=Path("test.jpg"),
            base_confidence=85,
        )

        assert event is None

    def test_parse_line_sets_confidence(self, extractor: ImageEventExtractor) -> None:
        """Should set confidence scores."""
        line = "CAVERNAS DEL NUS 1 AGO $195.000"

        event = extractor._parse_line(
            line,
            agency="brutaltravel",
            month_num=8,
            source_image=Path("test.jpg"),
            base_confidence=85,
        )

        assert event is not None
        assert event.get_confidence("name") is not None
        assert event.get_confidence("price") is not None
        assert event.get_confidence("date_start") is not None

    @patch("aventure_tracker.services.image_event_extractor.pytesseract")
    @patch("aventure_tracker.services.image_event_extractor.ImageEnhance")
    @patch("aventure_tracker.services.image_event_extractor.Image")
    def test_extract_from_image_success(
        self,
        mock_image: MagicMock,
        mock_enhance: MagicMock,
        mock_tesseract: MagicMock,
        extractor: ImageEventExtractor,
        tmp_path: Path,
    ) -> None:
        """Should extract events from image."""
        # Setup mocks - return a real-ish mock that can be processed
        mock_img = MagicMock()
        mock_img.mode = "RGB"
        mock_img.convert.return_value = mock_img
        mock_img.filter.return_value = mock_img
        mock_img.point.return_value = mock_img
        mock_image.open.return_value = mock_img
        
        # Mock ImageEnhance.Contrast
        mock_contrast = MagicMock()
        mock_contrast.enhance.return_value = mock_img
        mock_enhance.Contrast.return_value = mock_contrast

        mock_tesseract.image_to_string.return_value = (
            "CAVERNAS DEL NUS 1 AGO $195.000\n"
            "TATACOA 21 al 23 AGO $490.000"
        )
        mock_tesseract.image_to_data.return_value = {
            "conf": [85, 90, 88, 95, 80],
        }
        mock_tesseract.Output.DICT = "dict"

        image_path = tmp_path / "calendar.jpg"
        image_path.write_bytes(b"fake image")

        result = extractor.extract_from_image(
            image_path, agency="brutaltravel", month="agosto"
        )

        assert result.success is True
        assert len(result.events) >= 1

    @patch("aventure_tracker.services.image_event_extractor.pytesseract")
    @patch("aventure_tracker.services.image_event_extractor.ImageEnhance")
    @patch("aventure_tracker.services.image_event_extractor.Image")
    def test_extract_from_image_cover(
        self,
        mock_image: MagicMock,
        mock_enhance: MagicMock,
        mock_tesseract: MagicMock,
        extractor: ImageEventExtractor,
        tmp_path: Path,
    ) -> None:
        """Should return empty for cover images."""
        mock_img = MagicMock()
        mock_img.mode = "RGB"
        mock_img.convert.return_value = mock_img
        mock_img.filter.return_value = mock_img
        mock_img.point.return_value = mock_img
        mock_image.open.return_value = mock_img
        
        # Mock ImageEnhance.Contrast
        mock_contrast = MagicMock()
        mock_contrast.enhance.return_value = mock_img
        mock_enhance.Contrast.return_value = mock_contrast

        mock_tesseract.image_to_string.return_value = (
            "AGOSTO\nEXPERIENCIAS BRUTAL\n2026"
        )
        mock_tesseract.image_to_data.return_value = {"conf": [90, 85, 88]}
        mock_tesseract.Output.DICT = "dict"

        image_path = tmp_path / "cover.jpg"
        image_path.write_bytes(b"fake image")

        result = extractor.extract_from_image(
            image_path, agency="brutaltravel", month="agosto"
        )

        assert result.success is True
        assert len(result.events) == 0

    @patch("aventure_tracker.services.image_event_extractor.pytesseract")
    @patch("aventure_tracker.services.image_event_extractor.Image")
    def test_extract_from_image_error(
        self,
        mock_image: MagicMock,
        mock_tesseract: MagicMock,
        extractor: ImageEventExtractor,
        tmp_path: Path,
    ) -> None:
        """Should handle OCR errors gracefully."""
        mock_image.open.side_effect = Exception("Cannot open image")

        image_path = tmp_path / "bad.jpg"
        image_path.write_bytes(b"not an image")

        result = extractor.extract_from_image(
            image_path, agency="brutaltravel", month="agosto"
        )

        assert result.success is False
        assert "OCR error" in result.error

    @patch("aventure_tracker.services.image_event_extractor.pytesseract")
    @patch("aventure_tracker.services.image_event_extractor.ImageEnhance")
    @patch("aventure_tracker.services.image_event_extractor.Image")
    def test_extract_from_directory(
        self,
        mock_image: MagicMock,
        mock_enhance: MagicMock,
        mock_tesseract: MagicMock,
        extractor: ImageEventExtractor,
        tmp_path: Path,
    ) -> None:
        """Should process all images in directory."""
        mock_img = MagicMock()
        mock_img.mode = "RGB"
        mock_img.convert.return_value = mock_img
        mock_img.filter.return_value = mock_img
        mock_img.point.return_value = mock_img
        mock_image.open.return_value = mock_img
        
        # Mock ImageEnhance.Contrast
        mock_contrast = MagicMock()
        mock_contrast.enhance.return_value = mock_img
        mock_enhance.Contrast.return_value = mock_contrast

        mock_tesseract.image_to_string.return_value = "EVENT 1 AGO $100.000"
        mock_tesseract.image_to_data.return_value = {"conf": [85]}
        mock_tesseract.Output.DICT = "dict"

        # Create test images
        (tmp_path / "cal1.jpg").write_bytes(b"img1")
        (tmp_path / "cal2.jpg").write_bytes(b"img2")
        (tmp_path / "readme.txt").write_text("not an image")

        results = extractor.extract_from_directory(
            tmp_path, agency="brutaltravel", month="agosto"
        )

        assert len(results) == 2  # Only .jpg files

    def test_preprocess_disabled(self, tmp_path: Path) -> None:
        """Should skip preprocessing when disabled."""
        config = ExtractionConfig(preprocess=False)
        extractor = ImageEventExtractor(config=config)

        assert extractor.config.preprocess is False
