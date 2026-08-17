"""Event information extractor from captions and OCR results.

This module extracts event_id from Instagram post captions and OCR text.
The event_id format is: {event_date}-{event_name_slug}
Example: "2026-08-15-cocuy-trek"
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime

logger = logging.getLogger(__name__)

# Spanish month names and abbreviations
MONTH_MAP: dict[str, int] = {
    # Full names
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
    # Abbreviations
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}

# Common words to exclude from event names
STOP_WORDS = {
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "en",
    "con",
    "para",
    "por",
    "y",
    "a",
    "al",
    "un",
    "una",
    "tu",
    "te",
    "que",
    "es",
    "se",
    "no",
    "si",
    "mas",
    "solo",
    "como",
    "desde",
    "hasta",
    "incluye",
    "incluido",
    "info",
    "reserva",
    "reservas",
    "cupos",
    "disponibles",
    "disponible",
    "salida",
    "salidas",
    "fecha",
    "fechas",
}


@dataclass
class EventInfo:
    """Extracted event information.

    Attributes:
        event_date: Event date as ISO string (YYYY-MM-DD) or None.
        event_name: Human-readable event name.
        event_id: Unique identifier in format {date}-{slug} or {slug} if no date.
        raw_date_text: Original date text found.
        year: Extracted year (may be inferred).
    """

    event_date: str | None
    event_name: str
    event_id: str
    raw_date_text: str | None = None
    year: int | None = None


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug.

    Args:
        text: Input text.

    Returns:
        Lowercase slug with hyphens.
    """
    # Normalize unicode (convert accented chars)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    # Lowercase and replace non-alphanumeric with hyphens
    text = re.sub(r"[^a-z0-9]+", "-", text.lower())

    # Remove leading/trailing hyphens and collapse multiple hyphens
    text = re.sub(r"-+", "-", text).strip("-")

    return text


def extract_date_from_text(text: str) -> tuple[date | None, str | None]:
    """Extract date from Spanish text.

    Supports formats like:
    - "15 de agosto"
    - "15 de agosto 2026"
    - "agosto 15"
    - "15/08/2026"
    - "15-08-2026"
    - "15 ago"
    - "agosto 2026" (assumes day 1)

    Args:
        text: Text to search for dates.

    Returns:
        Tuple of (extracted date, raw date text) or (None, None).
    """
    text_lower = text.lower()
    current_year = datetime.now().year

    # Pattern 1: "15 de agosto", "15 de agosto 2026", "15 de ago"
    pattern1 = (
        r"(\d{1,2})\s*(?:de\s*)?"
        r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|"
        r"ene|feb|mar|abr|may|jun|jul|ago|sep|sept|oct|nov|dic)"
        r"(?:\s*(?:de|del)?\s*(\d{4}))?"
    )
    match = re.search(pattern1, text_lower)
    if match:
        day = int(match.group(1))
        month = MONTH_MAP.get(match.group(2))
        year = (
            int(match.group(3))
            if match.group(3)
            else _infer_year(month, day, current_year)
        )

        if month and 1 <= day <= 31:
            try:
                result_date = date(year, month, day)
                return result_date, match.group(0)
            except ValueError:
                pass

    # Pattern 2: "agosto 15", "agosto 15 2026"
    # Use \b to ensure day is a standalone number, not part of year
    pattern2 = (
        r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|"
        r"ene|feb|mar|abr|may|jun|jul|ago|sep|sept|oct|nov|dic)"
        r"\s+(\d{1,2})\b(?:\s*(?:de|del)?\s*(\d{4}))?"
    )
    match = re.search(pattern2, text_lower)
    if match:
        month = MONTH_MAP.get(match.group(1))
        day = int(match.group(2))
        year = (
            int(match.group(3))
            if match.group(3)
            else _infer_year(month, day, current_year)
        )

        # Ensure day is reasonable (not part of a year like "agosto 2026" -> day=20)
        if month and 1 <= day <= 31:
            try:
                result_date = date(year, month, day)
                return result_date, match.group(0)
            except ValueError:
                pass

    # Pattern 3: "15/08/2026", "15-08-2026", "15/08"
    pattern3 = r"(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?"
    match = re.search(pattern3, text)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = current_year
        if match.group(3):
            year = int(match.group(3))
            if year < 100:
                year += 2000

        if 1 <= day <= 31 and 1 <= month <= 12:
            # Infer year if not provided and date is in past
            if not match.group(3):
                year = _infer_year(month, day, current_year)
            try:
                result_date = date(year, month, day)
                return result_date, match.group(0)
            except ValueError:
                pass

    # Pattern 4: "agosto 2026" (month + year, assume day 1)
    # Use word boundary to avoid matching partial words like "Tour" -> "20"
    pattern4 = (
        r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
        r"\s*(?:de|del)?\s*(\d{4})\b"
    )
    match = re.search(pattern4, text_lower)
    if match:
        month = MONTH_MAP.get(match.group(1))
        year = int(match.group(2))
        if month:
            try:
                result_date = date(year, month, 1)
                return result_date, match.group(0)
            except ValueError:
                pass

    return None, None


def _infer_year(month: int | None, day: int, current_year: int) -> int:
    """Infer year for a date, assuming future events.

    If the date (month/day) has already passed this year, assume next year.

    Args:
        month: Month number (1-12).
        day: Day of month.
        current_year: Current year.

    Returns:
        Inferred year.
    """
    if month is None:
        return current_year

    today = date.today()
    try:
        test_date = date(current_year, month, day)
        if test_date < today:
            return current_year + 1
    except ValueError:
        pass

    return current_year


def extract_event_name(caption: str, ocr_text: str | None = None) -> str:
    """Extract event name from caption and/or OCR text.

    Uses heuristics to find the most likely event name:
    - First line of caption (often the title)
    - Text before a date
    - Activity + location combination
    - Hashtags

    Args:
        caption: Instagram post caption.
        ocr_text: Optional OCR extracted text.

    Returns:
        Best guess at event name.
    """
    # Combine caption and OCR, prioritizing caption
    combined = caption
    if ocr_text:
        combined = f"{caption}\n{ocr_text}"

    # Strategy 1: First meaningful line of caption
    lines = [line.strip() for line in caption.split("\n") if line.strip()]
    if lines:
        first_line = lines[0]
        # Remove emojis and clean up
        first_line = _remove_emojis(first_line)
        # If first line is short enough and not just hashtags, use it
        if 3 <= len(first_line) <= 100 and not first_line.startswith("#"):
            # Clean it up
            name = _clean_event_name(first_line)
            if name and len(name) >= 3:
                return name

    # Strategy 2: Look for known patterns
    patterns = [
        r"(?:trek|trekking|caminata|expedición|tour|salida)\s+(?:a|al|hacia)?\s*([A-Za-záéíóúñÁÉÍÓÚÑ\s]+)",
        r"([A-Za-záéíóúñÁÉÍÓÚÑ\s]+)\s+(?:trek|trekking|tour)",
        r"nevado\s+(?:del?\s+)?([A-Za-záéíóúñÁÉÍÓÚÑ\s]+)",
        r"páramo\s+(?:del?\s+)?([A-Za-záéíóúñÁÉÍÓÚÑ\s]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            name = _clean_event_name(match.group(1))
            if name:
                return name

    # Strategy 3: Extract from hashtags
    hashtags = re.findall(r"#([A-Za-z0-9áéíóúñÁÉÍÓÚÑ]+)", combined)
    for tag in hashtags:
        # Skip common non-descriptive hashtags
        if tag.lower() not in {"colombia", "travel", "adventure", "turismo", "viajes"}:
            if len(tag) >= 4:
                # Convert CamelCase to spaces
                name = re.sub(r"([a-z])([A-Z])", r"\1 \2", tag)
                return name.title()

    # Strategy 4: Just use first 50 chars of caption
    clean_caption = _remove_emojis(caption)
    clean_caption = re.sub(r"#\S+", "", clean_caption)  # Remove hashtags
    clean_caption = clean_caption.strip()
    if clean_caption:
        return clean_caption[:50].strip()

    return "Unknown Event"


def _remove_emojis(text: str) -> str:
    """Remove emojis from text.

    Args:
        text: Input text.

    Returns:
        Text without emojis.
    """
    # Emoji unicode ranges
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # emoticons
        "\U0001f300-\U0001f5ff"  # symbols & pictographs
        "\U0001f680-\U0001f6ff"  # transport & map symbols
        "\U0001f700-\U0001f77f"  # alchemical symbols
        "\U0001f780-\U0001f7ff"  # Geometric Shapes Extended
        "\U0001f800-\U0001f8ff"  # Supplemental Arrows-C
        "\U0001f900-\U0001f9ff"  # Supplemental Symbols and Pictographs
        "\U0001fa00-\U0001fa6f"  # Chess Symbols
        "\U0001fa70-\U0001faff"  # Symbols and Pictographs Extended-A
        "\U00002702-\U000027b0"  # Dingbats
        "\U000024c2-\U0001f251"
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub("", text)


def _clean_event_name(text: str) -> str:
    """Clean event name text.

    Args:
        text: Raw event name.

    Returns:
        Cleaned event name.
    """
    # Remove emojis
    text = _remove_emojis(text)

    # Remove special characters but keep accented letters
    text = re.sub(r"[^\w\sáéíóúñÁÉÍÓÚÑ]", " ", text)

    # Collapse whitespace
    text = " ".join(text.split())

    # Remove stop words from beginning/end
    words = text.split()
    while words and words[0].lower() in STOP_WORDS:
        words.pop(0)
    while words and words[-1].lower() in STOP_WORDS:
        words.pop()

    return " ".join(words).strip()


def extract_event_info(caption: str, ocr_text: str | None = None) -> EventInfo:
    """Extract complete event information from caption and OCR.

    Extracts date and name to generate a unique event_id.

    Args:
        caption: Instagram post caption.
        ocr_text: Optional OCR extracted text.

    Returns:
        EventInfo with extracted data and generated event_id.
    """
    # Try to extract date from caption first, then OCR
    event_date, raw_date_text = extract_date_from_text(caption)
    if not event_date and ocr_text:
        event_date, raw_date_text = extract_date_from_text(ocr_text)

    # Extract event name
    event_name = extract_event_name(caption, ocr_text)

    # Generate event_id
    name_slug = slugify(event_name)
    if not name_slug:
        name_slug = "unknown"

    # Truncate slug if too long
    if len(name_slug) > 50:
        name_slug = name_slug[:50].rstrip("-")

    if event_date:
        event_id = f"{event_date.isoformat()}-{name_slug}"
        event_date_str = event_date.isoformat()
        year = event_date.year
    else:
        event_id = name_slug
        event_date_str = None
        year = None

    return EventInfo(
        event_date=event_date_str,
        event_name=event_name,
        event_id=event_id,
        raw_date_text=raw_date_text,
        year=year,
    )
