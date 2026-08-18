"""Image event extractor using vision models.

Extracts events from calendar images using either:
- Gemini (cloud, fast, free tier available) - default
- Ollama (local, slower, requires local setup)
"""

import base64
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path

from aventure_tracker.models.extracted_event import (
    ExtractedEvent,
    ExtractionResult,
)

# Month name to number mapping
MONTH_MAP = {
    "ene": 1,
    "enero": 1,
    "feb": 2,
    "febrero": 2,
    "mar": 3,
    "marzo": 3,
    "abr": 4,
    "abril": 4,
    "may": 5,
    "mayo": 5,
    "jun": 6,
    "junio": 6,
    "jul": 7,
    "julio": 7,
    "ago": 8,
    "agosto": 8,
    "sep": 9,
    "sept": 9,
    "septiembre": 9,
    "oct": 10,
    "octubre": 10,
    "nov": 11,
    "noviembre": 11,
    "dic": 12,
    "diciembre": 12,
}

EXTRACTION_PROMPT = """Analiza esta imagen de un calendario de viajes de una agencia turística colombiana.

Extrae TODOS los eventos/viajes que veas. Para cada evento extrae:
- name: nombre del destino o viaje (ej: "Cavernas del Nus", "Tatacoa", "Río Claro")
- date_start: día de inicio (número)
- date_end: día de fin (número, mismo que inicio si es un día)
- month: mes (ej: "agosto", "septiembre")
- price: precio en pesos colombianos (número sin puntos ni $)
- sold_out: true si dice "AGOTADO" o "SOLD OUT", false si no

Responde SOLO con un JSON array. Si no hay eventos (es una portada), responde [].

Ejemplo de respuesta:
[
  {"name": "Cavernas del Nus", "date_start": 1, "date_end": 1, "month": "agosto", "price": 195000, "sold_out": false},
  {"name": "Tatacoa", "date_start": 21, "date_end": 23, "month": "agosto", "price": 490000, "sold_out": true}
]

JSON:"""


class ModelProvider(Enum):
    """Available model providers."""

    GEMINI = "gemini"
    OLLAMA = "ollama"


@dataclass
class ExtractionConfig:
    """Configuration for image extraction."""

    year: int = 2026
    default_month: str = "agosto"
    provider: ModelProvider = ModelProvider.GEMINI
    # Gemini settings
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_api_key: str | None = None
    # Ollama settings (fallback)
    ollama_model: str = "minicpm-v"
    ollama_url: str = "http://localhost:11434"
    timeout: int = 60  # seconds


class ImageEventExtractor:
    """Extracts events from calendar images using vision models."""

    def __init__(self, config: ExtractionConfig | None = None):
        """Initialize the extractor.

        Args:
            config: Extraction configuration.
        """
        self.config = config or ExtractionConfig()
        self._gemini_model = None

        # Auto-detect API key from environment
        if self.config.gemini_api_key is None:
            self.config.gemini_api_key = os.getenv("GEMINI_API_KEY")

    def _get_gemini_client(self):
        """Lazy-load Gemini client."""
        if self._gemini_model is None:
            from google import genai

            if not self.config.gemini_api_key:
                raise ValueError("GEMINI_API_KEY not set")

            self._gemini_model = genai.Client(api_key=self.config.gemini_api_key)

        return self._gemini_model

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

        if self.config.provider == ModelProvider.GEMINI:
            return self._extract_with_gemini(image_path, agency, month)
        else:
            return self._extract_with_ollama(image_path, agency, month)

    def _extract_with_gemini(
        self,
        image_path: Path,
        agency: str,
        month: str,
    ) -> ExtractionResult:
        """Extract using Google Gemini API."""
        start_time = time.time()

        try:
            from google.genai import types

            client = self._get_gemini_client()

            # Read image as bytes
            with open(image_path, "rb") as f:
                image_bytes = f.read()

            # Detect mime type
            mime_type = "image/jpeg"
            if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
                mime_type = "image/png"

            # Call Gemini
            response = client.models.generate_content(
                model=self.config.gemini_model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    EXTRACTION_PROMPT,
                ],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=2048,
                ),
            )

            raw_text = response.text

            # Parse events from response
            events = self._parse_response(raw_text, agency, month, image_path)

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
                error=f"Gemini error: {e}",
            )

    def _extract_with_ollama(
        self,
        image_path: Path,
        agency: str,
        month: str,
    ) -> ExtractionResult:
        """Extract using local Ollama API."""
        import requests

        start_time = time.time()

        try:
            # Read and encode image
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            # Call Ollama API
            response = requests.post(
                f"{self.config.ollama_url}/api/generate",
                json={
                    "model": self.config.ollama_model,
                    "prompt": EXTRACTION_PROMPT,
                    "images": [image_data],
                    "stream": False,
                },
                timeout=self.config.timeout,
            )
            response.raise_for_status()

            result = response.json()
            raw_text = result.get("response", "")

            # Parse events from response
            events = self._parse_response(raw_text, agency, month, image_path)

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

        except requests.exceptions.ConnectionError:
            processing_time = int((time.time() - start_time) * 1000)
            return ExtractionResult(
                source_image=image_path,
                agency=agency,
                month=month,
                year=self.config.year,
                events=[],
                processing_time_ms=processing_time,
                success=False,
                error="Ollama not running. Start with: ollama serve",
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
                error=f"Extraction error: {e}",
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
        from aventure_tracker.services.extraction.organizer import detect_file_type

        directory = Path(directory)
        results: list[ExtractionResult] = []

        for image_path in sorted(directory.iterdir()):
            if image_path.name.startswith("."):
                continue
            # Use magic bytes detection
            if detect_file_type(image_path):
                result = self.extract_from_image(image_path, agency, month)
                results.append(result)

        return results

    def _parse_response(
        self,
        raw_text: str,
        agency: str,
        month: str,
        source_image: Path,
    ) -> list[ExtractedEvent]:
        """Parse events from model response.

        Args:
            raw_text: Raw response from model.
            agency: Agency name.
            month: Default month name.
            source_image: Source image path.

        Returns:
            List of ExtractedEvent objects.
        """
        events: list[ExtractedEvent] = []

        # Try to extract JSON from response
        json_match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if not json_match:
            return events

        try:
            data = json.loads(json_match.group())
            if not isinstance(data, list):
                return events

            for item in data:
                event = self._create_event(item, agency, month, source_image)
                if event:
                    events.append(event)

        except json.JSONDecodeError:
            pass

        return events

    def _create_event(
        self,
        item: dict,
        agency: str,
        default_month: str,
        source_image: Path,
    ) -> ExtractedEvent | None:
        """Create an ExtractedEvent from parsed data.

        Args:
            item: Parsed event data.
            agency: Agency name.
            default_month: Default month if not specified.
            source_image: Source image path.

        Returns:
            ExtractedEvent or None if invalid.
        """
        try:
            name = item.get("name", "").strip()
            if not name or len(name) < 2:
                return None

            date_start_day = int(item.get("date_start", 0))
            date_end_day = int(item.get("date_end", date_start_day))
            if date_start_day < 1 or date_start_day > 31:
                return None

            month_name = item.get("month", default_month).lower().strip()
            month_num = self._get_month_number(month_name)

            price = item.get("price", 0)
            if isinstance(price, str):
                price = int(re.sub(r"[^\d]", "", price) or 0)
            price = int(price)

            if price < 10000 or price > 10000000:
                # Set a default reasonable price if invalid
                price = 0

            sold_out = bool(item.get("sold_out", False))

            date_start = date(self.config.year, month_num, date_start_day)
            date_end = date(self.config.year, month_num, min(date_end_day, 31))

            event = ExtractedEvent(
                name=name,
                date_start=date_start,
                date_end=date_end,
                price=price,
                agency=agency,
                sold_out=sold_out,
                source_image=source_image,
            )

            # Set confidence based on completeness
            event.set_confidence("name", 0.85, raw_value=name)
            event.set_confidence("price", 0.8 if price > 0 else 0.3)
            event.set_confidence("date_start", 0.85)

            return event

        except (ValueError, KeyError, TypeError):
            return None

    def _get_month_number(self, month_name: str) -> int:
        """Convert month name to number.

        Args:
            month_name: Month name in Spanish.

        Returns:
            Month number (1-12).
        """
        month_lower = month_name.lower().strip()
        # Try direct match first
        if month_lower in MONTH_MAP:
            return MONTH_MAP[month_lower]
        # Try prefix match
        for key, value in MONTH_MAP.items():
            if month_lower.startswith(key[:3]):
                return value
        return 8  # Default to August
