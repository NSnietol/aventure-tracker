"""Tests for image event extractor service."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aventure_tracker.services.image_event_extractor import (
    EXTRACTION_PROMPT,
    ExtractionConfig,
    ImageEventExtractor,
)


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock Anthropic client."""
    return MagicMock()


@pytest.fixture
def extractor(mock_client: MagicMock) -> ImageEventExtractor:
    """Create an extractor with mocked client."""
    with patch("aventure_tracker.services.image_event_extractor.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value = mock_client
        return ImageEventExtractor(api_key="test-key")


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """Create a sample image file (JPEG header)."""
    image_path = tmp_path / "calendar.jpg"
    image_path.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100)
    return image_path


@pytest.fixture
def sample_response() -> str:
    """Sample successful extraction response."""
    return json.dumps({
        "month_detected": "agosto",
        "is_cover_image": False,
        "events": [
            {
                "name": "Cavernas del Nus",
                "name_confidence": 0.95,
                "date_start_day": 1,
                "date_end_day": 1,
                "date_confidence": 0.9,
                "price": 195000,
                "price_confidence": 0.85,
                "price_raw": "$195.000",
                "sold_out": False,
            },
            {
                "name": "Tatacoa",
                "name_confidence": 0.9,
                "date_start_day": 21,
                "date_end_day": 23,
                "date_confidence": 0.95,
                "price": 490000,
                "price_confidence": 0.9,
                "price_raw": "$490.000",
                "sold_out": False,
            },
            {
                "name": "Popular Trip",
                "name_confidence": 0.85,
                "date_start_day": 15,
                "date_end_day": 15,
                "date_confidence": 0.8,
                "price": 300000,
                "price_confidence": 0.75,
                "price_raw": "$300.000",
                "sold_out": True,
                "notes": "Marked as AGOTADO",
            },
        ],
    })


@pytest.fixture
def cover_image_response() -> str:
    """Response for a cover image (no events)."""
    return json.dumps({
        "month_detected": "agosto",
        "is_cover_image": True,
        "events": [],
    })


class TestExtractionConfig:
    """Tests for ExtractionConfig."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        config = ExtractionConfig()
        assert config.year == 2026
        assert config.default_month == "agosto"
        assert "claude" in config.model.lower()

    def test_custom_values(self) -> None:
        """Should accept custom values."""
        config = ExtractionConfig(year=2025, default_month="septiembre")
        assert config.year == 2025
        assert config.default_month == "septiembre"


class TestImageEventExtractor:
    """Tests for ImageEventExtractor."""

    def test_extract_from_image_success(
        self,
        extractor: ImageEventExtractor,
        mock_client: MagicMock,
        sample_image: Path,
        sample_response: str,
    ) -> None:
        """Should extract events from image successfully."""
        # Setup mock
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=sample_response)]
        mock_client.messages.create.return_value = mock_message

        result = extractor.extract_from_image(
            sample_image, agency="brutaltravel", month="agosto"
        )

        assert result.success is True
        assert result.error is None
        assert len(result.events) == 3
        assert result.agency == "brutaltravel"
        assert result.month == "agosto"
        assert result.year == 2026

    def test_extract_parses_single_day_event(
        self,
        extractor: ImageEventExtractor,
        mock_client: MagicMock,
        sample_image: Path,
        sample_response: str,
    ) -> None:
        """Should parse single-day event correctly."""
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=sample_response)]
        mock_client.messages.create.return_value = mock_message

        result = extractor.extract_from_image(
            sample_image, agency="brutaltravel"
        )

        cavernas = next(e for e in result.events if "Cavernas" in e.name)
        assert cavernas.date_start == date(2026, 8, 1)
        assert cavernas.date_end == date(2026, 8, 1)
        assert cavernas.is_multi_day is False

    def test_extract_parses_multi_day_event(
        self,
        extractor: ImageEventExtractor,
        mock_client: MagicMock,
        sample_image: Path,
        sample_response: str,
    ) -> None:
        """Should parse multi-day event correctly."""
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=sample_response)]
        mock_client.messages.create.return_value = mock_message

        result = extractor.extract_from_image(
            sample_image, agency="brutaltravel"
        )

        tatacoa = next(e for e in result.events if "Tatacoa" in e.name)
        assert tatacoa.date_start == date(2026, 8, 21)
        assert tatacoa.date_end == date(2026, 8, 23)
        assert tatacoa.is_multi_day is True
        assert tatacoa.duration_days == 3

    def test_extract_parses_sold_out_event(
        self,
        extractor: ImageEventExtractor,
        mock_client: MagicMock,
        sample_image: Path,
        sample_response: str,
    ) -> None:
        """Should parse sold_out flag correctly."""
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=sample_response)]
        mock_client.messages.create.return_value = mock_message

        result = extractor.extract_from_image(
            sample_image, agency="brutaltravel"
        )

        sold_out = next(e for e in result.events if e.sold_out)
        assert sold_out.name == "Popular Trip"
        assert sold_out.sold_out is True

    def test_extract_parses_confidence_scores(
        self,
        extractor: ImageEventExtractor,
        mock_client: MagicMock,
        sample_image: Path,
        sample_response: str,
    ) -> None:
        """Should parse confidence scores for each field."""
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=sample_response)]
        mock_client.messages.create.return_value = mock_message

        result = extractor.extract_from_image(
            sample_image, agency="brutaltravel"
        )

        cavernas = next(e for e in result.events if "Cavernas" in e.name)

        name_conf = cavernas.get_confidence("name")
        assert name_conf is not None
        assert name_conf.score == 0.95

        price_conf = cavernas.get_confidence("price")
        assert price_conf is not None
        assert price_conf.score == 0.85
        assert price_conf.raw_value == "$195.000"

    def test_extract_parses_notes(
        self,
        extractor: ImageEventExtractor,
        mock_client: MagicMock,
        sample_image: Path,
        sample_response: str,
    ) -> None:
        """Should preserve notes in confidence."""
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=sample_response)]
        mock_client.messages.create.return_value = mock_message

        result = extractor.extract_from_image(
            sample_image, agency="brutaltravel"
        )

        sold_out = next(e for e in result.events if e.sold_out)
        price_conf = sold_out.get_confidence("price")
        assert price_conf is not None
        assert price_conf.notes == "Marked as AGOTADO"

    def test_extract_cover_image_returns_empty(
        self,
        extractor: ImageEventExtractor,
        mock_client: MagicMock,
        sample_image: Path,
        cover_image_response: str,
    ) -> None:
        """Should return empty events for cover images."""
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=cover_image_response)]
        mock_client.messages.create.return_value = mock_message

        result = extractor.extract_from_image(
            sample_image, agency="brutaltravel"
        )

        assert result.success is True
        assert len(result.events) == 0

    def test_extract_handles_markdown_code_block(
        self,
        extractor: ImageEventExtractor,
        mock_client: MagicMock,
        sample_image: Path,
        sample_response: str,
    ) -> None:
        """Should handle JSON wrapped in markdown code blocks."""
        wrapped_response = f"```json\n{sample_response}\n```"

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=wrapped_response)]
        mock_client.messages.create.return_value = mock_message

        result = extractor.extract_from_image(
            sample_image, agency="brutaltravel"
        )

        assert result.success is True
        assert len(result.events) == 3

    def test_extract_handles_api_error(
        self,
        extractor: ImageEventExtractor,
        mock_client: MagicMock,
        sample_image: Path,
    ) -> None:
        """Should handle API errors gracefully."""
        import anthropic

        mock_client.messages.create.side_effect = anthropic.APIError(
            message="Rate limited",
            request=MagicMock(),
            body=None,
        )

        result = extractor.extract_from_image(
            sample_image, agency="brutaltravel"
        )

        assert result.success is False
        assert "API error" in result.error
        assert len(result.events) == 0

    def test_extract_handles_invalid_json(
        self,
        extractor: ImageEventExtractor,
        mock_client: MagicMock,
        sample_image: Path,
    ) -> None:
        """Should handle invalid JSON response."""
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="not valid json {")]
        mock_client.messages.create.return_value = mock_message

        result = extractor.extract_from_image(
            sample_image, agency="brutaltravel"
        )

        assert result.success is False
        assert "Invalid JSON" in result.error or "Extraction error" in result.error

    def test_extract_records_processing_time(
        self,
        extractor: ImageEventExtractor,
        mock_client: MagicMock,
        sample_image: Path,
        sample_response: str,
    ) -> None:
        """Should record processing time."""
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=sample_response)]
        mock_client.messages.create.return_value = mock_message

        result = extractor.extract_from_image(
            sample_image, agency="brutaltravel"
        )

        assert result.processing_time_ms >= 0

    def test_extract_stores_raw_response(
        self,
        extractor: ImageEventExtractor,
        mock_client: MagicMock,
        sample_image: Path,
        sample_response: str,
    ) -> None:
        """Should store raw response text."""
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=sample_response)]
        mock_client.messages.create.return_value = mock_message

        result = extractor.extract_from_image(
            sample_image, agency="brutaltravel"
        )

        assert result.raw_text == sample_response

    def test_extract_stores_source_image(
        self,
        extractor: ImageEventExtractor,
        mock_client: MagicMock,
        sample_image: Path,
        sample_response: str,
    ) -> None:
        """Should store source image path in events."""
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=sample_response)]
        mock_client.messages.create.return_value = mock_message

        result = extractor.extract_from_image(
            sample_image, agency="brutaltravel"
        )

        for event in result.events:
            assert event.source_image == sample_image

    def test_extract_from_directory(
        self,
        extractor: ImageEventExtractor,
        mock_client: MagicMock,
        tmp_path: Path,
        sample_response: str,
        cover_image_response: str,
    ) -> None:
        """Should extract from all images in directory."""
        # Create test images
        (tmp_path / "cal1.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
        (tmp_path / "cal2.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
        (tmp_path / "cover.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
        (tmp_path / "readme.txt").write_text("not an image")

        # Setup mock to return different responses
        responses = [sample_response, sample_response, cover_image_response]
        mock_messages = []
        for resp in responses:
            mock_msg = MagicMock()
            mock_msg.content = [MagicMock(text=resp)]
            mock_messages.append(mock_msg)

        mock_client.messages.create.side_effect = mock_messages

        results = extractor.extract_from_directory(
            tmp_path, agency="brutaltravel", month="agosto"
        )

        assert len(results) == 3  # Only image files
        assert sum(r.event_count for r in results) == 6  # 3 + 3 + 0

    def test_get_media_type(self, extractor: ImageEventExtractor) -> None:
        """Should return correct media type for extensions."""
        assert extractor._get_media_type(Path("test.jpg")) == "image/jpeg"
        assert extractor._get_media_type(Path("test.jpeg")) == "image/jpeg"
        assert extractor._get_media_type(Path("test.png")) == "image/png"
        assert extractor._get_media_type(Path("test.gif")) == "image/gif"
        assert extractor._get_media_type(Path("test.webp")) == "image/webp"
        assert extractor._get_media_type(Path("test.unknown")) == "image/jpeg"

    def test_get_month_number(self, extractor: ImageEventExtractor) -> None:
        """Should convert month names to numbers."""
        assert extractor._get_month_number("agosto") == 8
        assert extractor._get_month_number("AGOSTO") == 8
        assert extractor._get_month_number("septiembre") == 9
        assert extractor._get_month_number("sep") == 9
        assert extractor._get_month_number("enero") == 1
        assert extractor._get_month_number("diciembre") == 12
        assert extractor._get_month_number("unknown") == 8  # Default

    def test_custom_config(
        self,
        mock_client: MagicMock,
        sample_image: Path,
        sample_response: str,
    ) -> None:
        """Should use custom configuration."""
        config = ExtractionConfig(year=2025, default_month="septiembre")

        with patch("aventure_tracker.services.image_event_extractor.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value = mock_client
            extractor = ImageEventExtractor(api_key="test", config=config)

            mock_message = MagicMock()
            mock_message.content = [MagicMock(text=sample_response)]
            mock_client.messages.create.return_value = mock_message

            result = extractor.extract_from_image(sample_image, agency="test")

            assert result.year == 2025

    def test_extraction_prompt_content(self) -> None:
        """Should have comprehensive extraction prompt."""
        assert "AGOTADO" in EXTRACTION_PROMPT
        assert "SOLD OUT" in EXTRACTION_PROMPT
        assert "2026" in EXTRACTION_PROMPT
        assert "confianza" in EXTRACTION_PROMPT.lower()
        assert "JSON" in EXTRACTION_PROMPT
