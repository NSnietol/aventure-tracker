"""Inbox processor — scans inbox/ for new images and extracts events into cache."""

import logging
import os
from pathlib import Path

from aventure_tracker.services.extraction.cache import ExtractionCache
from aventure_tracker.services.extraction.extractor import (
    ExtractionConfig,
    ImageEventExtractor,
    ModelProvider,
)
from aventure_tracker.services.extraction.organizer import detect_file_type

logger = logging.getLogger(__name__)


def run_inbox_extraction(
    inbox_path: Path | None = None,
    cache_path: Path | None = None,
    gemini_api_key: str | None = None,
) -> tuple[int, int]:
    """Process new images from inbox/ and update the extraction cache.

    Skips images already present in the cache (content-based deduplication).
    Auto-detects Gemini vs. Ollama based on GEMINI_API_KEY availability.

    Directory structure expected::

        inbox/
        └── <agency>/
            ├── image1.jpg
            └── image2.png

    Args:
        inbox_path: Path to the inbox directory. Defaults to ``Path("inbox")``.
        cache_path: Path to the extraction cache YAML. Defaults to
            ``Path("data/extraction_cache.yaml")``.
        gemini_api_key: Gemini API key. When None, falls back to the
            ``GEMINI_API_KEY`` environment variable, then to Ollama.

    Returns:
        Tuple of (total_new_images, total_events_extracted).
    """
    inbox_path = inbox_path or Path("inbox")
    cache_path = cache_path or Path("data/extraction_cache.yaml")

    if not inbox_path.exists():
        logger.info("No inbox/ directory found, skipping image extraction")
        return 0, 0

    key = gemini_api_key or os.getenv("GEMINI_API_KEY", "")
    provider = ModelProvider.GEMINI if key else ModelProvider.OLLAMA

    cache = ExtractionCache(cache_path)
    extractor = ImageEventExtractor(config=ExtractionConfig(provider=provider))

    total_new = 0
    total_events = 0

    for agency_dir in sorted(inbox_path.iterdir()):
        if not agency_dir.is_dir() or agency_dir.name.startswith("."):
            continue
        agency = agency_dir.name

        for image_path in sorted(agency_dir.iterdir()):
            if image_path.name.startswith("."):
                continue
            if not detect_file_type(image_path):
                continue
            if cache.is_processed(image_path):
                continue

            logger.info(f"  Extracting: {agency}/{image_path.name}")
            result = extractor.extract_from_image(image_path, agency)

            if result.success:
                cache.add(result)
                total_new += 1
                total_events += len(result.events)
                logger.info(
                    f"  → {len(result.events)} events extracted "
                    f"({result.processing_time_ms}ms)"
                )
            else:
                logger.warning(f"  → Failed: {result.error}")

    if total_new > 0:
        logger.info(
            f"Inbox extraction complete: {total_new} new images, {total_events} events"
        )
    else:
        logger.info("Inbox extraction: all images already cached")

    return total_new, total_events
