"""Tests for OCR Processor."""

from datetime import date
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from aventure_tracker.services.ocr import (
    ExtractedActivity,
    ImageDownloadError,
    OCRError,
    OCRProcessor,
    TesseractNotAvailableError,
)


@pytest.fixture
def sample_image() -> Image.Image:
    """Create a sample test image."""
    # Create a simple white image
    return Image.new("RGB", (100, 100), color="white")


@pytest.fixture
def mock_pytesseract():
    """Mock pytesseract module."""
    with patch("aventure_tracker.services.ocr.pytesseract") as mock:
        mock.get_tesseract_version.return_value = "5.0.0"
        mock.image_to_string.return_value = "Sample OCR text"
        yield mock


@pytest.fixture
def mock_tesseract_available():
    """Mock Tesseract as available."""
    with patch("aventure_tracker.services.ocr.TESSERACT_AVAILABLE", True):
        with patch("aventure_tracker.services.ocr.pytesseract") as mock:
            mock.get_tesseract_version.return_value = "5.0.0"
            mock.image_to_string.return_value = "Sample text"
            yield mock


class TestOCRProcessorInit:
    """Tests for OCR processor initialization."""

    def test_init_with_tesseract_available(self, mock_tesseract_available) -> None:
        """Test initialization with Tesseract available."""
        processor = OCRProcessor()
        assert processor._language == "spa"
        assert processor._preprocess is True

    def test_init_custom_language(self, mock_tesseract_available) -> None:
        """Test initialization with custom language."""
        processor = OCRProcessor(language="eng")
        assert processor._language == "eng"

    def test_init_without_preprocess(self, mock_tesseract_available) -> None:
        """Test initialization without preprocessing."""
        processor = OCRProcessor(preprocess=False)
        assert processor._preprocess is False

    def test_init_raises_when_tesseract_unavailable(self) -> None:
        """Test that init raises when Tesseract unavailable."""
        with patch("aventure_tracker.services.ocr.TESSERACT_AVAILABLE", False):
            with pytest.raises(TesseractNotAvailableError):
                OCRProcessor()


class TestExtractText:
    """Tests for text extraction methods."""

    def test_extract_text_calls_pytesseract(
        self, mock_tesseract_available, sample_image: Image.Image
    ) -> None:
        """Test extract_text calls pytesseract."""
        processor = OCRProcessor()
        mock_tesseract_available.image_to_string.return_value = "Hello World"

        result = processor.extract_text(sample_image)

        assert result == "Hello World"
        mock_tesseract_available.image_to_string.assert_called_once()

    def test_extract_text_strips_whitespace(
        self, mock_tesseract_available, sample_image: Image.Image
    ) -> None:
        """Test that extracted text is stripped."""
        processor = OCRProcessor()
        mock_tesseract_available.image_to_string.return_value = "  Text with spaces  \n"

        result = processor.extract_text(sample_image)

        assert result == "Text with spaces"


class TestPreprocessImage:
    """Tests for image preprocessing."""

    def test_preprocess_converts_to_grayscale(
        self, mock_tesseract_available, sample_image: Image.Image
    ) -> None:
        """Test preprocessing converts to grayscale."""
        processor = OCRProcessor()
        result = processor._preprocess_image(sample_image)

        assert result.mode == "L"

    def test_preprocess_resizes_small_images(self, mock_tesseract_available) -> None:
        """Test preprocessing resizes small images."""
        processor = OCRProcessor()
        small_image = Image.new("RGB", (100, 100), color="white")

        result = processor._preprocess_image(small_image)

        assert result.width >= 800

    def test_preprocess_preserves_large_images(self, mock_tesseract_available) -> None:
        """Test preprocessing doesn't shrink large images."""
        processor = OCRProcessor()
        large_image = Image.new("RGB", (1000, 1000), color="white")

        result = processor._preprocess_image(large_image)

        # Should still be roughly the same size (after grayscale conversion)
        assert result.width == 1000


class TestExtractActivityName:
    """Tests for activity name extraction."""

    def test_extract_parapente(self, mock_tesseract_available) -> None:
        """Test extracting parapente activity."""
        processor = OCRProcessor()
        result = processor._extract_activity_name("vuelo de parapente en medellín")
        assert result == "Parapente"

    def test_extract_bungee(self, mock_tesseract_available) -> None:
        """Test extracting bungee activity."""
        processor = OCRProcessor()
        result = processor._extract_activity_name("salto de bungee extremo")
        assert result == "Bungee"

    def test_extract_rafting(self, mock_tesseract_available) -> None:
        """Test extracting rafting activity."""
        processor = OCRProcessor()
        result = processor._extract_activity_name("rafting en el río")
        assert result == "Rafting"

    def test_extract_returns_none_for_unknown(self, mock_tesseract_available) -> None:
        """Test returns None for unknown activities."""
        processor = OCRProcessor()
        result = processor._extract_activity_name("fiesta de cumpleaños")
        assert result is None


class TestExtractLocation:
    """Tests for location extraction."""

    def test_extract_medellin(self, mock_tesseract_available) -> None:
        """Test extracting Medellín location."""
        processor = OCRProcessor()
        result = processor._extract_location("vuelo en medellín")
        assert result == "Medellín"

    def test_extract_san_gil(self, mock_tesseract_available) -> None:
        """Test extracting San Gil location."""
        processor = OCRProcessor()
        result = processor._extract_location("aventura en san gil")
        assert result == "San Gil"

    def test_extract_guatape(self, mock_tesseract_available) -> None:
        """Test extracting Guatapé location."""
        processor = OCRProcessor()
        result = processor._extract_location("tour a guatapé")
        assert result == "Guatapé"

    def test_extract_returns_none_for_unknown(self, mock_tesseract_available) -> None:
        """Test returns None for unknown locations."""
        processor = OCRProcessor()
        result = processor._extract_location("aventura en el campo")
        assert result is None


class TestExtractPrice:
    """Tests for price extraction."""

    def test_extract_cop_format(self, mock_tesseract_available) -> None:
        """Test extracting COP format price."""
        processor = OCRProcessor()
        assert processor._extract_price("Precio: $150.000 COP") == 150000

    def test_extract_comma_format(self, mock_tesseract_available) -> None:
        """Test extracting comma format price."""
        processor = OCRProcessor()
        assert processor._extract_price("Valor: $250,000") == 250000

    def test_extract_plain_number(self, mock_tesseract_available) -> None:
        """Test extracting plain number price."""
        processor = OCRProcessor()
        assert processor._extract_price("costo 180000 pesos") == 180000

    def test_extract_with_thousands_separator(self, mock_tesseract_available) -> None:
        """Test extracting price with thousands separator."""
        processor = OCRProcessor()
        assert processor._extract_price("precio 85.000") == 85000

    def test_extract_returns_none_for_invalid(self, mock_tesseract_available) -> None:
        """Test returns None for invalid prices."""
        processor = OCRProcessor()
        assert processor._extract_price("sin precio") is None

    def test_extract_rejects_unreasonable_prices(
        self, mock_tesseract_available
    ) -> None:
        """Test rejects unreasonably small prices."""
        processor = OCRProcessor()
        # Too small (less than 10000)
        assert processor._extract_price("precio: $500") is None


class TestExtractDate:
    """Tests for date extraction."""

    def test_extract_spanish_month_full(self, mock_tesseract_available) -> None:
        """Test extracting Spanish full month format."""
        processor = OCRProcessor()
        result = processor._extract_date("15 de marzo")
        assert result is not None
        assert result.month == 3
        assert result.day == 15

    def test_extract_spanish_month_abbrev(self, mock_tesseract_available) -> None:
        """Test extracting Spanish abbreviated month."""
        processor = OCRProcessor()
        result = processor._extract_date("20 de dic")
        assert result is not None
        assert result.month == 12
        assert result.day == 20

    def test_extract_numeric_format(self, mock_tesseract_available) -> None:
        """Test extracting numeric date format."""
        processor = OCRProcessor()
        result = processor._extract_date("fecha: 15/03")
        assert result is not None
        assert result.month == 3
        assert result.day == 15

    def test_extract_numeric_with_year(self, mock_tesseract_available) -> None:
        """Test extracting numeric date with year."""
        processor = OCRProcessor()
        result = processor._extract_date("15/03/2025")
        assert result is not None
        assert result.year == 2025
        assert result.month == 3

    def test_extract_returns_none_for_invalid(self, mock_tesseract_available) -> None:
        """Test returns None for invalid dates."""
        processor = OCRProcessor()
        assert processor._extract_date("sin fecha") is None


class TestExtractContact:
    """Tests for contact extraction."""

    def test_extract_colombian_phone(self, mock_tesseract_available) -> None:
        """Test extracting Colombian phone number."""
        processor = OCRProcessor()
        result = processor._extract_contact("Tel: 300 123 4567")
        assert result is not None
        assert "3001234567" in result

    def test_extract_phone_with_country_code(self, mock_tesseract_available) -> None:
        """Test extracting phone with country code."""
        processor = OCRProcessor()
        result = processor._extract_contact("WhatsApp: +57 311 234 5678")
        assert result is not None
        assert len(result) >= 10

    def test_extract_email(self, mock_tesseract_available) -> None:
        """Test extracting email address."""
        processor = OCRProcessor()
        result = processor._extract_contact("info@aventura.co")
        assert result == "info@aventura.co"

    def test_extract_returns_none_for_missing(self, mock_tesseract_available) -> None:
        """Test returns None when no contact found."""
        processor = OCRProcessor()
        assert processor._extract_contact("sin contacto") is None


class TestCalculateConfidence:
    """Tests for confidence calculation."""

    def test_full_confidence(self, mock_tesseract_available) -> None:
        """Test confidence with all fields."""
        processor = OCRProcessor()
        confidence = processor._calculate_confidence(
            activity="Parapente",
            location="Medellín",
            price=150000,
            date_found=date(2025, 3, 15),
            contact="3001234567",
        )
        assert confidence == 1.0

    def test_partial_confidence(self, mock_tesseract_available) -> None:
        """Test confidence with some fields."""
        processor = OCRProcessor()
        confidence = processor._calculate_confidence(
            activity="Parapente",
            location="Medellín",
            price=None,
            date_found=None,
            contact=None,
        )
        assert 0.4 <= confidence <= 0.6

    def test_zero_confidence(self, mock_tesseract_available) -> None:
        """Test confidence with no fields."""
        processor = OCRProcessor()
        confidence = processor._calculate_confidence(
            activity=None,
            location=None,
            price=None,
            date_found=None,
            contact=None,
        )
        assert confidence == 0.0


class TestExtractActivity:
    """Tests for full activity extraction."""

    def test_extract_activity_parses_all_fields(
        self, mock_tesseract_available, sample_image: Image.Image
    ) -> None:
        """Test extract_activity returns ExtractedActivity."""
        processor = OCRProcessor()
        mock_tesseract_available.image_to_string.return_value = (
            "Parapente en Medellín\nPrecio: $150.000\n15 de marzo\nTel: 300 123 4567"
        )

        result = processor.extract_activity(sample_image)

        assert isinstance(result, ExtractedActivity)
        assert result.activity_name == "Parapente"
        assert result.location == "Medellín"
        assert result.price == 150000
        assert result.date is not None
        assert result.contact_info is not None
        assert result.confidence > 0


class TestDownloadImage:
    """Tests for image downloading."""

    def test_download_image_success(self, mock_tesseract_available) -> None:
        """Test successful image download."""
        processor = OCRProcessor()

        # Create a simple PNG image
        img = Image.new("RGB", (10, 10), color="red")
        img_bytes = BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = img_bytes.getvalue()
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            result = processor._download_image("https://example.com/image.png")

            assert isinstance(result, Image.Image)
            assert result.mode == "RGB"

    def test_download_image_failure(self, mock_tesseract_available) -> None:
        """Test image download failure."""
        processor = OCRProcessor()

        with patch("requests.get") as mock_get:
            import requests

            mock_get.side_effect = requests.exceptions.ConnectionError()

            with pytest.raises(ImageDownloadError):
                processor._download_image("https://example.com/image.png")


class TestExceptionClasses:
    """Tests for exception classes."""

    def test_ocr_error_is_exception(self) -> None:
        """Test OCRError inherits from Exception."""
        assert issubclass(OCRError, Exception)

    def test_tesseract_not_available_error(self) -> None:
        """Test TesseractNotAvailableError."""
        error = TesseractNotAvailableError("Not installed")
        assert str(error) == "Not installed"
        assert isinstance(error, OCRError)

    def test_image_download_error(self) -> None:
        """Test ImageDownloadError."""
        error = ImageDownloadError("Download failed")
        assert str(error) == "Download failed"
        assert isinstance(error, OCRError)


class TestExtractedActivityDataclass:
    """Tests for ExtractedActivity dataclass."""

    def test_create_extracted_activity(self) -> None:
        """Test creating ExtractedActivity."""
        activity = ExtractedActivity(
            raw_text="Sample text",
            activity_name="Parapente",
            location="Medellín",
            price=150000,
            date=date(2025, 3, 15),
            contact_info="3001234567",
            confidence=0.8,
        )

        assert activity.raw_text == "Sample text"
        assert activity.activity_name == "Parapente"
        assert activity.location == "Medellín"
        assert activity.price == 150000
        assert activity.confidence == 0.8

    def test_extracted_activity_defaults(self) -> None:
        """Test ExtractedActivity default values."""
        activity = ExtractedActivity(raw_text="Text only")

        assert activity.activity_name is None
        assert activity.location is None
        assert activity.price is None
        assert activity.date is None
        assert activity.contact_info is None
        assert activity.confidence == 0.0
