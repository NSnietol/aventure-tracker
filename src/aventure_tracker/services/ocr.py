"""OCR processor for extracting text from images using Tesseract."""

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageEnhance, ImageFilter

# Try to import pytesseract
try:
    import pytesseract

    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    pytesseract = None  # type: ignore

logger = logging.getLogger(__name__)

# Default timeout for image downloads
DOWNLOAD_TIMEOUT_SECONDS = 30


class OCRError(Exception):
    """Base exception for OCR errors."""

    pass


class TesseractNotAvailableError(OCRError):
    """Tesseract is not installed or not configured."""

    pass


class ImageDownloadError(OCRError):
    """Failed to download image."""

    pass


@dataclass
class ExtractedActivity:
    """Activity information extracted from an image.

    Attributes:
        raw_text: Full extracted text from OCR.
        activity_name: Detected activity name (e.g., "Parapente").
        location: Detected location if found.
        price: Detected price in COP if found.
        date: Detected date if found.
        contact_info: Detected phone/email if found.
        confidence: Overall confidence score (0-1).
    """

    raw_text: str
    activity_name: str | None = None
    location: str | None = None
    price: int | None = None
    date: date | None = None
    contact_info: str | None = None
    confidence: float = 0.0


class OCRProcessor:
    """Processor for extracting activity information from images using Tesseract.

    Uses Tesseract OCR with Spanish language support to extract text from
    Instagram post images and parse activity details like prices, dates,
    and locations.

    Attributes:
        language: Tesseract language code (default: "spa" for Spanish).
        preprocess: Whether to preprocess images before OCR.
    """

    # Common activity keywords in Spanish
    ACTIVITY_KEYWORDS = [
        "parapente",
        "parapentismo",
        "bungee",
        "rafting",
        "rappel",
        "rapel",
        "escalada",
        "senderismo",
        "caminata",
        "kayak",
        "canopy",
        "torrentismo",
        "canyoning",
        "buceo",
        "snorkel",
        "surf",
        "kitesurf",
        "ciclismo",
        "mtb",
        "tour",
        "expedición",
        "aventura",
    ]

    # Colombian city/location keywords
    LOCATION_KEYWORDS = [
        "medellín",
        "medellin",
        "bogotá",
        "bogota",
        "cali",
        "cartagena",
        "santa marta",
        "barranquilla",
        "san gil",
        "guatapé",
        "guatape",
        "jardín",
        "jardin",
        "salento",
        "manizales",
        "pereira",
        "armenia",
        "villavicencio",
        "bucaramanga",
        "la calera",
        "san félix",
        "san felix",
        "rionegro",
        "girardota",
        "copacabana",
        "la estrella",
        "envigado",
        "sabaneta",
        "bello",
    ]

    def __init__(
        self,
        language: str = "spa",
        preprocess: bool = True,
        tesseract_cmd: str | None = None,
    ) -> None:
        """Initialize the OCR processor.

        Args:
            language: Tesseract language code.
            preprocess: Whether to preprocess images before OCR.
            tesseract_cmd: Path to tesseract executable if not in PATH.

        Raises:
            TesseractNotAvailableError: If Tesseract is not available.
        """
        if not TESSERACT_AVAILABLE:
            raise TesseractNotAvailableError(
                "pytesseract is not installed. Install with: pip install pytesseract"
            )

        self._language = language
        self._preprocess = preprocess

        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        # Verify Tesseract is working
        try:
            pytesseract.get_tesseract_version()
        except Exception as e:
            raise TesseractNotAvailableError(
                f"Tesseract is not properly installed: {e}"
            ) from e

    def extract_text(self, image: Image.Image) -> str:
        """Extract text from a PIL Image.

        Args:
            image: PIL Image object.

        Returns:
            Extracted text string.
        """
        if self._preprocess:
            image = self._preprocess_image(image)

        config = f"--oem 3 --psm 6 -l {self._language}"
        text = pytesseract.image_to_string(image, config=config)

        return text.strip()

    def extract_text_from_url(self, url: str) -> str:
        """Extract text from an image URL.

        Args:
            url: URL of the image.

        Returns:
            Extracted text string.

        Raises:
            ImageDownloadError: If image download fails.
        """
        image = self._download_image(url)
        return self.extract_text(image)

    def extract_text_from_file(self, path: Path) -> str:
        """Extract text from an image file.

        Args:
            path: Path to the image file.

        Returns:
            Extracted text string.

        Raises:
            FileNotFoundError: If file doesn't exist.
        """
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {path}")

        image = Image.open(path)
        return self.extract_text(image)

    def extract_activity(self, image: Image.Image) -> ExtractedActivity:
        """Extract activity information from an image.

        Args:
            image: PIL Image object.

        Returns:
            ExtractedActivity with parsed information.
        """
        raw_text = self.extract_text(image)
        return self._parse_activity_text(raw_text)

    def extract_activity_from_url(self, url: str) -> ExtractedActivity:
        """Extract activity information from an image URL.

        Args:
            url: URL of the image.

        Returns:
            ExtractedActivity with parsed information.
        """
        image = self._download_image(url)
        return self.extract_activity(image)

    def _download_image(self, url: str) -> Image.Image:
        """Download image from URL.

        Args:
            url: Image URL.

        Returns:
            PIL Image object.

        Raises:
            ImageDownloadError: If download fails.
        """
        try:
            response = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
            response.raise_for_status()

            image = Image.open(BytesIO(response.content))
            return image.convert("RGB")

        except requests.exceptions.RequestException as e:
            raise ImageDownloadError(f"Failed to download image: {e}") from e
        except Exception as e:
            raise ImageDownloadError(f"Failed to process image: {e}") from e

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """Preprocess image for better OCR results.

        Args:
            image: Original image.

        Returns:
            Preprocessed image.
        """
        # Convert to RGB if necessary
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Convert to grayscale
        image = image.convert("L")

        # Increase contrast
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)

        # Sharpen
        image = image.filter(ImageFilter.SHARPEN)

        # Resize if too small (OCR works better with larger images)
        min_width = 800
        if image.width < min_width:
            ratio = min_width / image.width
            new_size = (int(image.width * ratio), int(image.height * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        return image

    def _parse_activity_text(self, text: str) -> ExtractedActivity:
        """Parse extracted text to find activity details.

        Args:
            text: Raw OCR text.

        Returns:
            ExtractedActivity with parsed fields.
        """
        text_lower = text.lower()

        # Extract activity name
        activity_name = self._extract_activity_name(text_lower)

        # Extract location
        location = self._extract_location(text_lower)

        # Extract price
        price = self._extract_price(text)

        # Extract date
        extracted_date = self._extract_date(text)

        # Extract contact info
        contact_info = self._extract_contact(text)

        # Calculate confidence based on what was found
        confidence = self._calculate_confidence(
            activity_name, location, price, extracted_date, contact_info
        )

        return ExtractedActivity(
            raw_text=text,
            activity_name=activity_name,
            location=location,
            price=price,
            date=extracted_date,
            contact_info=contact_info,
            confidence=confidence,
        )

    def _extract_activity_name(self, text: str) -> str | None:
        """Extract activity name from text.

        Args:
            text: Lowercase text.

        Returns:
            Activity name or None.
        """
        for keyword in self.ACTIVITY_KEYWORDS:
            if keyword in text:
                return keyword.capitalize()
        return None

    def _extract_location(self, text: str) -> str | None:
        """Extract location from text.

        Args:
            text: Lowercase text.

        Returns:
            Location name or None.
        """
        for location in self.LOCATION_KEYWORDS:
            if location in text:
                return location.title()
        return None

    def _extract_price(self, text: str) -> int | None:
        """Extract price from text.

        Args:
            text: Raw text.

        Returns:
            Price in COP or None.
        """
        # Common price patterns in Colombian format
        patterns = [
            r"\$\s*([\d.,]+)\s*(?:cop|pesos)?",  # $150.000 or $150,000
            r"([\d.,]+)\s*(?:cop|pesos)",  # 150.000 COP
            r"precio[:\s]*([\d.,]+)",  # Precio: 150.000
            r"valor[:\s]*([\d.,]+)",  # Valor: 150.000
            r"costo[:\s]*([\d.,]+)",  # Costo: 150.000
            r"([\d]{2,3})[.,]?([\d]{3})\b",  # 150.000 or 150,000
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Clean and parse the number
                price_str = match.group(1)
                if len(match.groups()) > 1 and match.group(2):
                    price_str = match.group(1) + match.group(2)

                price_str = price_str.replace(".", "").replace(",", "")
                try:
                    price = int(price_str)
                    # Sanity check: reasonable Colombian price range
                    if 10000 <= price <= 10000000:
                        return price
                except ValueError:
                    continue

        return None

    def _extract_date(self, text: str) -> date | None:
        """Extract date from text.

        Args:
            text: Raw text.

        Returns:
            Extracted date or None.
        """
        # Common date patterns
        patterns = [
            # 15 de marzo, 15 de mar
            r"(\d{1,2})\s*de\s*(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)",
            # 15/03, 15-03
            r"(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?",
        ]

        month_map = {
            "enero": 1,
            "ene": 1,
            "febrero": 2,
            "feb": 2,
            "marzo": 3,
            "mar": 3,
            "abril": 4,
            "abr": 4,
            "mayo": 5,
            "may": 5,
            "junio": 6,
            "jun": 6,
            "julio": 7,
            "jul": 7,
            "agosto": 8,
            "ago": 8,
            "septiembre": 9,
            "sep": 9,
            "octubre": 10,
            "oct": 10,
            "noviembre": 11,
            "nov": 11,
            "diciembre": 12,
            "dic": 12,
        }

        # Try Spanish month format
        match = re.search(patterns[0], text, re.IGNORECASE)
        if match:
            day = int(match.group(1))
            month_str = match.group(2).lower()
            month = month_map.get(month_str)
            if month and 1 <= day <= 31:
                year = datetime.now().year
                try:
                    return date(year, month, day)
                except ValueError:
                    pass

        # Try numeric format
        match = re.search(patterns[1], text)
        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            year = datetime.now().year
            if match.group(3):
                year = int(match.group(3))
                if year < 100:
                    year += 2000

            if 1 <= day <= 31 and 1 <= month <= 12:
                try:
                    return date(year, month, day)
                except ValueError:
                    pass

        return None

    def _extract_contact(self, text: str) -> str | None:
        """Extract contact information from text.

        Args:
            text: Raw text.

        Returns:
            Contact info or None.
        """
        # Phone patterns (Colombian format)
        phone_patterns = [
            r"(?:tel|teléfono|celular|cel|whatsapp|wsp)?[:\s]*(\+?57)?[\s.-]?(\d{3})[\s.-]?(\d{3})[\s.-]?(\d{4})",
            r"(\d{10})",  # 10 digit number
        ]

        for pattern in phone_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Clean up phone number
                groups = [g for g in match.groups() if g]
                phone = "".join(groups)
                if len(phone) >= 10:
                    return phone

        # Email pattern
        email_match = re.search(
            r"[\w.+-]+@[\w-]+\.[\w.-]+",
            text,
        )
        if email_match:
            return email_match.group(0)

        return None

    def _calculate_confidence(
        self,
        activity: str | None,
        location: str | None,
        price: int | None,
        date_found: date | None,
        contact: str | None,
    ) -> float:
        """Calculate confidence score based on extracted fields.

        Args:
            activity: Extracted activity name.
            location: Extracted location.
            price: Extracted price.
            date_found: Extracted date.
            contact: Extracted contact info.

        Returns:
            Confidence score from 0 to 1.
        """
        score = 0.0
        max_score = 5.0

        if activity:
            score += 1.5  # Activity name is most important
        if location:
            score += 1.0
        if price:
            score += 1.0
        if date_found:
            score += 1.0
        if contact:
            score += 0.5

        return round(score / max_score, 2)

    def is_available(self) -> bool:
        """Check if Tesseract OCR is available."""
        return TESSERACT_AVAILABLE
