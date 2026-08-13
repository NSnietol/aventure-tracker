"""Cache for image extraction results to avoid reprocessing.

Uses SHA256 hash of image content to identify unique images,
regardless of filename or location.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from aventure_tracker.models.extracted_event import ExtractionResult


@dataclass
class CacheEntry:
    """A cached extraction result.

    Attributes:
        image_hash: SHA256 hash of the image content.
        agency: Agency name.
        month: Month extracted for.
        year: Year extracted for.
        events_count: Number of events extracted.
        is_cover: Whether this was identified as a cover/no events.
        processed_at: When the extraction was performed.
        source_path: Original path (for reference only).
        events_data: Serialized event data.
    """

    image_hash: str
    agency: str
    month: str
    year: int
    events_count: int
    is_cover: bool
    processed_at: datetime
    source_path: str
    events_data: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "image_hash": self.image_hash,
            "agency": self.agency,
            "month": self.month,
            "year": self.year,
            "events_count": self.events_count,
            "is_cover": self.is_cover,
            "processed_at": self.processed_at.isoformat(),
            "source_path": self.source_path,
            "events_data": self.events_data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CacheEntry":
        """Create CacheEntry from dictionary."""
        processed_at = data["processed_at"]
        if isinstance(processed_at, str):
            processed_at = datetime.fromisoformat(processed_at)

        return cls(
            image_hash=data["image_hash"],
            agency=data["agency"],
            month=data["month"],
            year=data["year"],
            events_count=data["events_count"],
            is_cover=data.get("is_cover", False),
            processed_at=processed_at,
            source_path=data.get("source_path", ""),
            events_data=data.get("events_data", []),
        )

    @classmethod
    def from_extraction_result(
        cls,
        result: ExtractionResult,
        image_hash: str,
    ) -> "CacheEntry":
        """Create CacheEntry from an ExtractionResult."""
        return cls(
            image_hash=image_hash,
            agency=result.agency,
            month=result.month,
            year=result.year,
            events_count=result.event_count,
            is_cover=result.event_count == 0 and result.success,
            processed_at=datetime.now(),
            source_path=str(result.source_image),
            events_data=[e.to_dict(include_confidence=False) for e in result.events],
        )


class ExtractionCache:
    """Cache for tracking processed images and their extraction results.

    Uses content-based hashing to identify images, so the same image
    processed from different locations won't be re-extracted.
    """

    def __init__(self, cache_path: Path | None = None):
        """Initialize the cache.

        Args:
            cache_path: Path to cache file. Defaults to data/extraction_cache.yaml.
        """
        if cache_path is None:
            cache_path = Path("data/extraction_cache.yaml")
        self.cache_path = cache_path
        self._entries: dict[str, CacheEntry] = {}
        self._load()

    def _load(self) -> None:
        """Load cache from disk."""
        if not self.cache_path.exists():
            self._entries = {}
            return

        try:
            with open(self.cache_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            self._entries = {}
            for hash_key, entry_data in data.get("entries", {}).items():
                self._entries[hash_key] = CacheEntry.from_dict(entry_data)

        except Exception:
            # If cache is corrupted, start fresh
            self._entries = {}

    def _save(self) -> None:
        """Save cache to disk."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": 1,
            "updated_at": datetime.now().isoformat(),
            "total_entries": len(self._entries),
            "entries": {
                hash_key: entry.to_dict()
                for hash_key, entry in self._entries.items()
            },
        }

        with open(self.cache_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

    @staticmethod
    def compute_hash(file_path: Path) -> str:
        """Compute SHA256 hash of a file's content.

        Args:
            file_path: Path to the file.

        Returns:
            Hex string of SHA256 hash.
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read in chunks for large files
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def is_processed(self, file_path: Path) -> bool:
        """Check if an image has already been processed.

        Args:
            file_path: Path to the image file.

        Returns:
            True if image was already processed.
        """
        image_hash = self.compute_hash(file_path)
        return image_hash in self._entries

    def get_cached(self, file_path: Path) -> CacheEntry | None:
        """Get cached result for an image.

        Args:
            file_path: Path to the image file.

        Returns:
            CacheEntry if found, None otherwise.
        """
        image_hash = self.compute_hash(file_path)
        return self._entries.get(image_hash)

    def add(self, result: ExtractionResult) -> str:
        """Add an extraction result to the cache.

        Args:
            result: The extraction result to cache.

        Returns:
            The image hash used as key.
        """
        image_hash = self.compute_hash(result.source_image)
        entry = CacheEntry.from_extraction_result(result, image_hash)
        self._entries[image_hash] = entry
        self._save()
        return image_hash

    def remove(self, file_path: Path) -> bool:
        """Remove a cached entry by file path.

        Args:
            file_path: Path to the image file.

        Returns:
            True if entry was removed, False if not found.
        """
        image_hash = self.compute_hash(file_path)
        if image_hash in self._entries:
            del self._entries[image_hash]
            self._save()
            return True
        return False

    def clear(self) -> int:
        """Clear all cached entries.

        Returns:
            Number of entries cleared.
        """
        count = len(self._entries)
        self._entries = {}
        self._save()
        return count

    def clear_agency(self, agency: str) -> int:
        """Clear cached entries for a specific agency.

        Args:
            agency: Agency name to clear.

        Returns:
            Number of entries cleared.
        """
        to_remove = [
            h for h, e in self._entries.items()
            if e.agency == agency
        ]
        for h in to_remove:
            del self._entries[h]
        if to_remove:
            self._save()
        return len(to_remove)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats.
        """
        by_agency: dict[str, int] = {}
        total_events = 0
        covers = 0

        for entry in self._entries.values():
            by_agency[entry.agency] = by_agency.get(entry.agency, 0) + 1
            total_events += entry.events_count
            if entry.is_cover:
                covers += 1

        return {
            "total_images": len(self._entries),
            "total_events": total_events,
            "covers": covers,
            "by_agency": by_agency,
        }

    def __len__(self) -> int:
        """Get number of cached entries."""
        return len(self._entries)

    def __contains__(self, file_path: Path) -> bool:
        """Check if file is in cache."""
        return self.is_processed(file_path)
