"""Image event extractor using local Tesseract OCR.

Extracts events from calendar images offline without external APIs.
"""

import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytesseract
from PIL import Image, ImageEnhance, ImageFilter

from aventure_tracker.models.extracted_event import (
    ExtractedEvent,
    ExtractionResult,
)

# Month name to number mapping
MONTH_MAP = {
    "ene": 1, "enero": 1,
    "feb": 2, "febrero": 2,
    "mar": 3, "marzo": 3,
    "abr": 4, "abril": 4,
    "may": 5, "mayo": 5,
    "jun": 6, "junio": 6,
    "jul": 7, "julio": 7,
    "ago": 8, "agosto": 8,
    "sep": 9, "sept": 9, "septiembre": 9,
    "oct": 10, "octubre": 10,
    "nov": 11, "noviembre": 11,
    "dic": 12, "diciembre": 12,
}

# Regex patterns for extraction
PRICE_PATTERN = re.compile(r"(\$\s*[\d.,]+|\b[\d]{3,}(?:\.\d{3})*)")
DATE_RANGE_PATTERN = re.compile(
    r"(\d{1,2})\s*(?:al|a|y|-)\s*(\d{1,2})\s*(?:de\s*)?(ago|sep|oct|nov|dic|agosto|septiembre|octubre|noviembre|diciembre)?",
    re.IGNORECASE,
)
SINGLE_DATE_PATTERN = re.compile(
    r"(\d{1,2})\s*(ago|sep|oct|nov|dic|agosto|septiembre|octubre|noviembre|diciembre)",
    re.IGNORECASE,
)


@dataclass
class ExtractionConfig:
    """Configuration for image extraction."""

    year: int = 2026
    default_month: str = "agosto"
    tesseract_lang: str = "spa"
    preprocess: bool = True
    confidence_threshold: int = 60  # Tesseract confidence threshold


class ImageEventExtractor:
    """Extracts events from calendar images using local Tesseract OCR."""

    def __init__(self, config: ExtractionConfig | None = None):
        """Initialize the extractor.

        Args:
            config: Extraction configuration.
        """
        self.config = config or ExtractionConfig()

    def extract_from_image(
        self,
        image_path: Path,
        agency: str,
        month: str | None = None,
    ) -> ExtractionResult:
        """Extract events from a single calendar image.

        Args:
            image_path: Path to the image file.
            agency: Agency name (normalized).
            month: Month name override (optional).

        Returns:
            ExtractionResult with extracted events.
        """
        image_path = Path(image_path)
        month = month or self.config.default_month
        start_time = time.time()

        try:
            # Load and preprocess image
            image = Image.open(image_path)

            if self.config.preprocess:
                image = self._preprocess_image(image)

            # Extract text with Tesseract
            ocr_data = pytesseract.image_to_data(
                image,
                lang=self.config.tesseract_lang,
                output_type=pytesseract.Output.DICT,
            )

            # Also get full text for parsing
            raw_text = pytesseract.image_to_string(
                image,
                lang=self.config.tesseract_lang,
            )

            # Parse events from text
            events = self._parse_events(raw_text, agency, month, image_path, ocr_data)

            processing_time = int((time.time() - start_time) * 1000)

            return ExtractionResult(
                source_image=image_path,
                agency=agency,
                month=month,
                year=self.config.year,
                events=events,
                raw_text=raw_text,
                processing_time_ms=processing_time,
                success=True,
            )

        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            return ExtractionResult(
                source_image=image_path,
                agency=agency,
                month=month,
                year=self.config.year,
                events=[],
                processing_time_ms=processing_time,
                success=False,
                error=f"OCR error: {e}",
            )

    def extract_from_directory(
        self,
        directory: Path,
        agency: str,
        month: str | None = None,
    ) -> list[ExtractionResult]:
        """Extract events from all images in a directory.

        Args:
            directory: Directory containing images.
            agency: Agency name.
            month: Month name override.

        Returns:
            List of ExtractionResult for each image.
        """
        directory = Path(directory)
        results: list[ExtractionResult] = []
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

        for image_path in sorted(directory.iterdir()):
            if image_path.suffix.lower() in image_extensions:
                result = self.extract_from_image(image_path, agency, month)
                results.append(result)

        return results

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """Preprocess image for better OCR.

        Args:
            image: PIL Image.

        Returns:
            Preprocessed image.
        """
        # Convert to RGB if needed
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Increase contrast
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)

        # Sharpen
        image = image.filter(ImageFilter.SHARPEN)

        # Convert to grayscale
        image = image.convert("L")

        # Binarize (threshold)
        threshold = 128
        image = image.point(lambda x: 255 if x > threshold else 0, "1")

        return image

    def _parse_events(
        self,
        raw_text: str,
        agency: str,
        month: str,
        source_image: Path,
        ocr_data: dict,
    ) -> list[ExtractedEvent]:
        """Parse events from OCR text.

        Args:
            raw_text: Full OCR text.
            agency: Agency name.
            month: Month name.
            source_image: Source image path.
            ocr_data: Tesseract OCR data with confidence.

        Returns:
            List of ExtractedEvent objects.
        """
        events: list[ExtractedEvent] = []
        lines = raw_text.strip().split("\n")

        # Calculate average confidence from OCR data
        confidences = [
            int(c) for c in ocr_data.get("conf", []) if str(c).isdigit() and int(c) > 0
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 50

        # Detect if this is a cover image (no table/events)
        if self._is_cover_image(raw_text):
            return []

        # Try to parse line by line
        current_event_name = None
        month_num = self._get_month_number(month)

        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue

            # Try to extract event info from line
            event = self._parse_line(
                line, agency, month_num, source_image, avg_confidence
            )
            if event:
                events.append(event)

        return events

    def _parse_line(
        self,
        line: str,
        agency: str,
        month_num: int,
        source_image: Path,
        base_confidence: float,
    ) -> ExtractedEvent | None:
        """Try to parse an event from a single line.

        Args:
            line: Text line to parse.
            agency: Agency name.
            month_num: Month number (1-12).
            source_image: Source image path.
            base_confidence: Base confidence from OCR.

        Returns:
            ExtractedEvent if successfully parsed, None otherwise.
        """
        # Look for price pattern
        price_match = PRICE_PATTERN.search(line)
        if not price_match:
            return None

        # Extract price
        price_str = price_match.group(1).replace("$", "").replace(".", "").replace(",", "").strip()
        try:
            price = int(price_str)
            # Sanity check - prices should be reasonable (10k - 10M COP)
            if price < 10000 or price > 10000000:
                return None
        except ValueError:
            return None

        # Look for date pattern
        date_start_day = None
        date_end_day = None

        # First try single date (1 AGO)
        single_date = SINGLE_DATE_PATTERN.search(line)
        if single_date:
            date_start_day = int(single_date.group(1))
            date_end_day = date_start_day
            if single_date.group(2):
                detected_month = single_date.group(2).lower()
                month_num = MONTH_MAP.get(detected_month[:3], month_num)
        
        # Then try date range (21 al 23 AGO)
        date_range_match = DATE_RANGE_PATTERN.search(line)
        if date_range_match:
            date_start_day = int(date_range_match.group(1))
            date_end_day = int(date_range_match.group(2))
            if date_range_match.group(3):
                detected_month = date_range_match.group(3).lower()
                month_num = MONTH_MAP.get(detected_month[:3], month_num)

        if date_start_day is None:
            return None

        # Extract event name (text before date/price patterns)
        date_match_for_name = date_range_match if date_range_match else single_date
        name = self._extract_name(line, price_match, date_match_for_name)
        if not name or len(name) < 3:
            return None

        # Create dates
        try:
            date_start = date(self.config.year, month_num, date_start_day)
            date_end = date(self.config.year, month_num, date_end_day)
        except ValueError:
            return None

        # Calculate confidence based on OCR quality and parsing success
        name_confidence = min(base_confidence / 100, 0.9)
        price_confidence = 0.7 if "." in price_match.group(0) else 0.5
        date_confidence = 0.8 if date_range_match else 0.6

        event = ExtractedEvent(
            name=name,
            date_start=date_start,
            date_end=date_end,
            price=price,
            agency=agency,
            sold_out=self._check_sold_out(line),
            source_image=source_image,
        )

        event.set_confidence("name", name_confidence, raw_value=name)
        event.set_confidence("price", price_confidence, raw_value=price_match.group(0))
        event.set_confidence("date_start", date_confidence)

        return event

    def _extract_name(
        self,
        line: str,
        price_match: re.Match | None,
        date_match: re.Match | None,
    ) -> str:
        """Extract event name from line.

        Args:
            line: Full line text.
            price_match: Price regex match.
            date_match: Date regex match.

        Returns:
            Extracted name.
        """
        # Remove price and date portions
        name = line

        if price_match:
            name = name[: price_match.start()] + name[price_match.end() :]

        if date_match:
            name = name[: date_match.start()] + name[date_match.end() :]

        # Also remove any single date pattern
        name = SINGLE_DATE_PATTERN.sub("", name)

        # Clean up
        name = re.sub(r"[\$\|\-\d]+$", "", name)  # Remove trailing numbers/symbols
        name = re.sub(r"^\s*[\|\-]\s*", "", name)  # Remove leading separators
        name = name.strip()

        return name

    def _check_sold_out(self, line: str) -> bool:
        """Check if event is sold out.

        Args:
            line: Text line.

        Returns:
            True if sold out indicators found.
        """
        sold_out_indicators = ["agotado", "sold out", "sold", "lleno", "completo"]
        line_lower = line.lower()
        return any(indicator in line_lower for indicator in sold_out_indicators)

    def _is_cover_image(self, text: str) -> bool:
        """Check if image is a cover/title image without events.

        Args:
            text: OCR text.

        Returns:
            True if likely a cover image.
        """
        text_lower = text.lower()

        # Cover images usually have month name prominently but few prices
        month_keywords = ["agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        has_month = any(m in text_lower for m in month_keywords)

        # Count price patterns
        price_count = len(PRICE_PATTERN.findall(text))

        # Cover images: have month name but very few prices (0-1)
        if has_month and price_count <= 1:
            # Also check for "experiencias" or agency branding
            if "experiencias" in text_lower or "brutal" in text_lower:
                return True

        return False

    def _get_month_number(self, month_name: str) -> int:
        """Convert month name to number.

        Args:
            month_name: Month name in Spanish.

        Returns:
            Month number (1-12).
        """
        month_lower = month_name.lower().strip()
        return MONTH_MAP.get(month_lower, 8)  # Default to August
