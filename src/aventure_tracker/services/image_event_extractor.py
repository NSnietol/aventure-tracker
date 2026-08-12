"""Image event extractor using Claude vision API.

Extracts events from calendar images with confidence scores for each field.
"""

import base64
import json
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import anthropic

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

EXTRACTION_PROMPT = """Analiza esta imagen de un calendario de eventos de una agencia de viajes de aventura.

INSTRUCCIONES:
1. Extrae TODOS los eventos visibles en la tabla/lista
2. Para cada evento, identifica:
   - name: Nombre del destino/evento
   - date_start: Fecha de inicio (formato: día del mes)
   - date_end: Fecha de fin (si es diferente, sino igual a date_start)
   - price: Precio en pesos colombianos (solo el número, sin símbolos)
   - sold_out: true si dice "AGOTADO", "SOLD OUT", o similar
3. Asigna un score de confianza (0.0-1.0) para cada campo:
   - 1.0 = completamente seguro, texto claro
   - 0.8-0.9 = bastante seguro, pequeña incertidumbre
   - 0.5-0.7 = parcialmente legible, podría haber error
   - <0.5 = muy incierto, posible error de lectura

IMPORTANTE:
- Si la imagen es una PORTADA sin tabla de eventos (solo dice el mes), responde con events: []
- El año es 2026 para todos los eventos
- Los precios en Colombia usan punto como separador de miles (ej: $195.000 = 195000)
- Si un precio dice "desde $X", usa X como el precio
- Si no puedes leer un campo claramente, indica el valor más probable y baja confianza

Responde SOLO con JSON válido en este formato exacto:
{
  "month_detected": "agosto",
  "is_cover_image": false,
  "events": [
    {
      "name": "Nombre del Evento",
      "name_confidence": 0.95,
      "date_start_day": 15,
      "date_end_day": 17,
      "date_confidence": 0.9,
      "price": 195000,
      "price_confidence": 0.85,
      "price_raw": "$195.000",
      "sold_out": false,
      "notes": "opcional - cualquier observación"
    }
  ]
}"""


@dataclass
class ExtractionConfig:
    """Configuration for image extraction."""

    year: int = 2026
    default_month: str = "agosto"
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    timeout: float = 60.0


class ImageEventExtractor:
    """Extracts events from calendar images using Claude vision."""

    def __init__(
        self,
        api_key: str | None = None,
        config: ExtractionConfig | None = None,
    ):
        """Initialize the extractor.

        Args:
            api_key: Anthropic API key. If None, uses ANTHROPIC_API_KEY env var.
            config: Extraction configuration.
        """
        self.client = anthropic.Anthropic(api_key=api_key)
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
            # Read and encode image
            image_data = self._encode_image(image_path)
            media_type = self._get_media_type(image_path)

            # Call Claude API
            response = self._call_claude_vision(image_data, media_type)

            # Parse response
            events = self._parse_response(response, agency, month, image_path)

            processing_time = int((time.time() - start_time) * 1000)

            return ExtractionResult(
                source_image=image_path,
                agency=agency,
                month=month,
                year=self.config.year,
                events=events,
                raw_text=response,
                processing_time_ms=processing_time,
                success=True,
            )

        except anthropic.APIError as e:
            processing_time = int((time.time() - start_time) * 1000)
            return ExtractionResult(
                source_image=image_path,
                agency=agency,
                month=month,
                year=self.config.year,
                events=[],
                processing_time_ms=processing_time,
                success=False,
                error=f"API error: {e}",
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
        directory = Path(directory)
        results: list[ExtractionResult] = []
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

        for image_path in sorted(directory.iterdir()):
            if image_path.suffix.lower() in image_extensions:
                result = self.extract_from_image(image_path, agency, month)
                results.append(result)

        return results

    def _encode_image(self, image_path: Path) -> str:
        """Encode image to base64.

        Args:
            image_path: Path to image file.

        Returns:
            Base64 encoded string.
        """
        with open(image_path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode("utf-8")

    def _get_media_type(self, image_path: Path) -> str:
        """Get media type from file extension.

        Args:
            image_path: Path to image file.

        Returns:
            Media type string.
        """
        ext = image_path.suffix.lower()
        media_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return media_types.get(ext, "image/jpeg")

    def _call_claude_vision(self, image_data: str, media_type: str) -> str:
        """Call Claude API with vision.

        Args:
            image_data: Base64 encoded image.
            media_type: Image media type.

        Returns:
            Response text from Claude.
        """
        message = self.client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": EXTRACTION_PROMPT,
                        },
                    ],
                }
            ],
        )

        return message.content[0].text

    def _parse_response(
        self,
        response: str,
        agency: str,
        month: str,
        source_image: Path,
    ) -> list[ExtractedEvent]:
        """Parse Claude's JSON response into ExtractedEvent objects.

        Args:
            response: JSON response from Claude.
            agency: Agency name.
            month: Month name.
            source_image: Source image path.

        Returns:
            List of ExtractedEvent objects.
        """
        # Extract JSON from response (handle markdown code blocks)
        json_str = response.strip()
        if json_str.startswith("```"):
            # Remove markdown code block
            json_str = re.sub(r"^```(?:json)?\s*", "", json_str)
            json_str = re.sub(r"\s*```$", "", json_str)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response: {e}")

        # Check if it's a cover image
        if data.get("is_cover_image", False) or not data.get("events"):
            return []

        # Detect month from response if available
        detected_month = data.get("month_detected", month)
        month_num = self._get_month_number(detected_month)

        events: list[ExtractedEvent] = []

        for event_data in data.get("events", []):
            try:
                event = self._parse_event(
                    event_data, agency, month_num, source_image
                )
                events.append(event)
            except (KeyError, ValueError) as e:
                # Log but continue with other events
                continue

        return events

    def _parse_event(
        self,
        data: dict[str, Any],
        agency: str,
        month_num: int,
        source_image: Path,
    ) -> ExtractedEvent:
        """Parse a single event from response data.

        Args:
            data: Event data from response.
            agency: Agency name.
            month_num: Month number (1-12).
            source_image: Source image path.

        Returns:
            ExtractedEvent object.
        """
        # Parse dates
        start_day = data["date_start_day"]
        end_day = data.get("date_end_day", start_day)

        # Handle month rollover (e.g., event spans into next month)
        start_month = month_num
        end_month = month_num
        if end_day < start_day:
            end_month = month_num + 1 if month_num < 12 else 1

        date_start = date(self.config.year, start_month, start_day)
        date_end = date(self.config.year, end_month, end_day)

        # Create event
        event = ExtractedEvent(
            name=data["name"],
            date_start=date_start,
            date_end=date_end,
            price=data["price"],
            agency=agency,
            sold_out=data.get("sold_out", False),
            source_image=source_image,
        )

        # Set confidence scores
        event.set_confidence(
            "name",
            score=data.get("name_confidence", 0.8),
        )

        event.set_confidence(
            "date_start",
            score=data.get("date_confidence", 0.8),
        )

        event.set_confidence(
            "price",
            score=data.get("price_confidence", 0.8),
            raw_value=data.get("price_raw"),
            notes=data.get("notes"),
        )

        return event

    def _get_month_number(self, month_name: str) -> int:
        """Convert month name to number.

        Args:
            month_name: Month name in Spanish.

        Returns:
            Month number (1-12).
        """
        month_lower = month_name.lower().strip()
        return MONTH_MAP.get(month_lower, 8)  # Default to August
