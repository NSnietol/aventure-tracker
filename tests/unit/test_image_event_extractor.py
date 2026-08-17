"""Tests for image event extractor with vision models."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aventure_tracker.services.image_event_extractor import (
    ExtractionConfig,
    ImageEventExtractor,
    ModelProvider,
)


@pytest.fixture
def extractor() -> ImageEventExtractor:
    """Create an extractor instance with Ollama provider for testing."""
    config = ExtractionConfig(provider=ModelProvider.OLLAMA)
    return ImageEventExtractor(config=config)


class TestExtractionConfig:
    """Tests for ExtractionConfig."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        config = ExtractionConfig()
        assert config.year == 2026
        assert config.default_month == "agosto"
        assert config.provider == ModelProvider.GEMINI  # Default to cloud
        assert config.gemini_model == "gemini-3.5-flash-lite"
        assert config.ollama_model == "minicpm-v"
        assert config.ollama_url == "http://localhost:11434"
        assert config.timeout == 60

    def test_custom_values(self) -> None:
        """Should accept custom values."""
        config = ExtractionConfig(
            year=2025,
            default_month="septiembre",
            provider=ModelProvider.OLLAMA,
            ollama_model="llava",
        )
        assert config.year == 2025
        assert config.default_month == "septiembre"
        assert config.provider == ModelProvider.OLLAMA
        assert config.ollama_model == "llava"


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

    def test_create_event_valid(self, extractor: ImageEventExtractor) -> None:
        """Should create event from valid data."""
        item = {
            "name": "Cavernas del Nus",
            "date_start": 15,
            "date_end": 17,
            "month": "agosto",
            "price": 195000,
            "sold_out": False,
        }
        event = extractor._create_event(
            item, agency="brutal", default_month="agosto", source_image=Path("test.jpg")
        )
        assert event is not None
        assert event.name == "Cavernas del Nus"
        assert event.date_start == date(2026, 8, 15)
        assert event.date_end == date(2026, 8, 17)
        assert event.price == 195000
        assert event.sold_out is False

    def test_create_event_invalid_name(self, extractor: ImageEventExtractor) -> None:
        """Should return None for invalid name."""
        item = {"name": "", "date_start": 15, "price": 195000}
        event = extractor._create_event(
            item, agency="brutal", default_month="agosto", source_image=Path("test.jpg")
        )
        assert event is None

    def test_create_event_invalid_date(self, extractor: ImageEventExtractor) -> None:
        """Should return None for invalid date."""
        item = {"name": "Test", "date_start": 0, "price": 195000}
        event = extractor._create_event(
            item, agency="brutal", default_month="agosto", source_image=Path("test.jpg")
        )
        assert event is None

    def test_create_event_string_price(self, extractor: ImageEventExtractor) -> None:
        """Should handle string price."""
        item = {
            "name": "Test Event",
            "date_start": 10,
            "month": "agosto",
            "price": "$195.000",
        }
        event = extractor._create_event(
            item, agency="brutal", default_month="agosto", source_image=Path("test.jpg")
        )
        assert event is not None
        assert event.price == 195000

    def test_create_event_sets_confidence(self, extractor: ImageEventExtractor) -> None:
        """Should set confidence scores."""
        item = {
            "name": "Test",
            "date_start": 10,
            "month": "agosto",
            "price": 195000,
        }
        event = extractor._create_event(
            item, agency="brutal", default_month="agosto", source_image=Path("test.jpg")
        )
        assert event is not None
        assert event.get_confidence("name") is not None
        assert event.get_confidence("price") is not None
        assert event.get_confidence("date_start") is not None

    def test_parse_response_valid_json(self, extractor: ImageEventExtractor) -> None:
        """Should parse valid JSON response."""
        raw_text = """
        [
            {"name": "Cavernas", "date_start": 1, "month": "agosto", "price": 195000},
            {"name": "Tatacoa", "date_start": 21, "date_end": 23, "month": "agosto", "price": 490000}
        ]
        """
        events = extractor._parse_response(
            raw_text, agency="brutal", month="agosto", source_image=Path("test.jpg")
        )
        assert len(events) == 2
        assert events[0].name == "Cavernas"
        assert events[1].name == "Tatacoa"

    def test_parse_response_empty_array(self, extractor: ImageEventExtractor) -> None:
        """Should handle empty array (cover image)."""
        raw_text = "[]"
        events = extractor._parse_response(
            raw_text, agency="brutal", month="agosto", source_image=Path("test.jpg")
        )
        assert len(events) == 0

    def test_parse_response_invalid_json(self, extractor: ImageEventExtractor) -> None:
        """Should handle invalid JSON gracefully."""
        raw_text = "This is not JSON"
        events = extractor._parse_response(
            raw_text, agency="brutal", month="agosto", source_image=Path("test.jpg")
        )
        assert len(events) == 0

    def test_parse_response_json_in_text(self, extractor: ImageEventExtractor) -> None:
        """Should extract JSON from surrounding text."""
        raw_text = """
        Here are the events I found:
        [{"name": "Test", "date_start": 5, "month": "agosto", "price": 100000}]
        That's all!
        """
        events = extractor._parse_response(
            raw_text, agency="brutal", month="agosto", source_image=Path("test.jpg")
        )
        assert len(events) == 1

    @patch("requests.post")
    def test_extract_from_image_success_ollama(
        self,
        mock_post: MagicMock,
        extractor: ImageEventExtractor,
        tmp_path: Path,
    ) -> None:
        """Should extract events from image using Ollama."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": '[{"name": "Test Event", "date_start": 10, "month": "agosto", "price": 150000}]'
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        # Create test image
        image_path = tmp_path / "calendar.jpg"
        image_path.write_bytes(b"fake image data")

        result = extractor.extract_from_image(
            image_path, agency="brutaltravel", month="agosto"
        )

        assert result.success is True
        assert len(result.events) == 1
        assert result.events[0].name == "Test Event"

    @patch("requests.post")
    def test_extract_from_image_cover(
        self,
        mock_post: MagicMock,
        extractor: ImageEventExtractor,
        tmp_path: Path,
    ) -> None:
        """Should return empty for cover images."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "[]"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        image_path = tmp_path / "cover.jpg"
        image_path.write_bytes(b"fake image")

        result = extractor.extract_from_image(
            image_path, agency="brutaltravel", month="agosto"
        )

        assert result.success is True
        assert len(result.events) == 0

    @patch("requests.post")
    def test_extract_from_image_connection_error(
        self,
        mock_post: MagicMock,
        extractor: ImageEventExtractor,
        tmp_path: Path,
    ) -> None:
        """Should handle Ollama not running."""
        import requests

        mock_post.side_effect = requests.exceptions.ConnectionError()

        image_path = tmp_path / "test.jpg"
        image_path.write_bytes(b"fake image")

        result = extractor.extract_from_image(
            image_path, agency="brutaltravel", month="agosto"
        )

        assert result.success is False
        assert "Ollama not running" in result.error

    @patch("requests.post")
    def test_extract_from_image_error(
        self,
        mock_post: MagicMock,
        extractor: ImageEventExtractor,
        tmp_path: Path,
    ) -> None:
        """Should handle extraction errors gracefully."""
        mock_post.side_effect = Exception("API Error")

        image_path = tmp_path / "bad.jpg"
        image_path.write_bytes(b"not an image")

        result = extractor.extract_from_image(
            image_path, agency="brutaltravel", month="agosto"
        )

        assert result.success is False
        assert "Extraction error" in result.error

    @patch("requests.post")
    def test_extract_from_directory(
        self,
        mock_post: MagicMock,
        extractor: ImageEventExtractor,
        tmp_path: Path,
    ) -> None:
        """Should process all images in directory."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": '[{"name": "Event", "date_start": 1, "month": "agosto", "price": 100000}]'
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        # Create test images with JPEG magic bytes (including .txt which may be renamed jpegs)
        jpeg_magic = b"\xff\xd8\xff\xe0"
        (tmp_path / "cal1.jpg").write_bytes(jpeg_magic + b"img1")
        (tmp_path / "cal2.txt").write_bytes(
            jpeg_magic + b"img2"
        )  # .txt with JPEG magic bytes
        (tmp_path / "readme.md").write_text("not an image")

        results = extractor.extract_from_directory(
            tmp_path, agency="brutaltravel", month="agosto"
        )

        assert len(results) == 2  # .jpg and .txt files with JPEG magic bytes

    def test_custom_config(self, tmp_path: Path) -> None:
        """Should use custom config."""
        config = ExtractionConfig(
            year=2025,
            default_month="septiembre",
            provider=ModelProvider.OLLAMA,
            ollama_model="llava",
            timeout=30,
        )
        extractor = ImageEventExtractor(config=config)

        assert extractor.config.year == 2025
        assert extractor.config.provider == ModelProvider.OLLAMA
        assert extractor.config.ollama_model == "llava"
