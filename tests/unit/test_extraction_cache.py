"""Tests for extraction cache to avoid reprocessing images."""

from datetime import date, datetime
from pathlib import Path

import pytest

from aventure_tracker.models.extracted_event import (
    ExtractedEvent,
    ExtractionResult,
)
from aventure_tracker.services.extraction_cache import (
    CacheEntry,
    ExtractionCache,
)


@pytest.fixture
def cache_file(tmp_path: Path) -> Path:
    """Create a temporary cache file path."""
    return tmp_path / "test_cache.yaml"


@pytest.fixture
def cache(cache_file: Path) -> ExtractionCache:
    """Create a cache instance with temporary file."""
    return ExtractionCache(cache_file)


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """Create a sample image file."""
    image_path = tmp_path / "sample.jpg"
    image_path.write_bytes(b"\xff\xd8\xff\xe0sample image content")
    return image_path


@pytest.fixture
def sample_result(sample_image: Path) -> ExtractionResult:
    """Create a sample extraction result."""
    event = ExtractedEvent(
        name="Test Event",
        date_start=date(2026, 8, 15),
        date_end=date(2026, 8, 15),
        price=150000,
        agency="test-agency",
        sold_out=False,
    )
    return ExtractionResult(
        source_image=sample_image,
        agency="test-agency",
        month="agosto",
        year=2026,
        events=[event],
        success=True,
    )


class TestExtractionCache:
    """Tests for ExtractionCache."""

    def test_compute_hash_consistent(self, sample_image: Path) -> None:
        """Same file should always produce same hash."""
        hash1 = ExtractionCache.compute_hash(sample_image)
        hash2 = ExtractionCache.compute_hash(sample_image)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 produces 64 hex chars

    def test_compute_hash_different_content(self, tmp_path: Path) -> None:
        """Different content should produce different hashes."""
        file1 = tmp_path / "file1.jpg"
        file2 = tmp_path / "file2.jpg"
        file1.write_bytes(b"content 1")
        file2.write_bytes(b"content 2")

        hash1 = ExtractionCache.compute_hash(file1)
        hash2 = ExtractionCache.compute_hash(file2)
        assert hash1 != hash2

    def test_is_processed_false_for_new_image(
        self, cache: ExtractionCache, sample_image: Path
    ) -> None:
        """New images should not be marked as processed."""
        assert cache.is_processed(sample_image) is False

    def test_is_processed_true_after_add(
        self, cache: ExtractionCache, sample_result: ExtractionResult
    ) -> None:
        """Images should be marked as processed after adding to cache."""
        cache.add(sample_result)
        assert cache.is_processed(sample_result.source_image) is True

    def test_get_cached_returns_none_for_new(
        self, cache: ExtractionCache, sample_image: Path
    ) -> None:
        """Getting cached result for new image should return None."""
        assert cache.get_cached(sample_image) is None

    def test_get_cached_returns_entry(
        self, cache: ExtractionCache, sample_result: ExtractionResult
    ) -> None:
        """Getting cached result after add should return entry."""
        cache.add(sample_result)
        entry = cache.get_cached(sample_result.source_image)

        assert entry is not None
        assert entry.agency == "test-agency"
        assert entry.events_count == 1
        assert entry.is_cover is False

    def test_cache_persists_to_disk(
        self, cache_file: Path, sample_result: ExtractionResult
    ) -> None:
        """Cache should persist to disk and load back."""
        # Create cache and add entry
        cache1 = ExtractionCache(cache_file)
        cache1.add(sample_result)

        # Create new cache instance pointing to same file
        cache2 = ExtractionCache(cache_file)

        assert cache2.is_processed(sample_result.source_image) is True

    def test_remove_entry(
        self, cache: ExtractionCache, sample_result: ExtractionResult
    ) -> None:
        """Should be able to remove cached entries."""
        cache.add(sample_result)
        assert cache.is_processed(sample_result.source_image) is True

        removed = cache.remove(sample_result.source_image)
        assert removed is True
        assert cache.is_processed(sample_result.source_image) is False

    def test_remove_nonexistent(
        self, cache: ExtractionCache, sample_image: Path
    ) -> None:
        """Removing non-existent entry should return False."""
        removed = cache.remove(sample_image)
        assert removed is False

    def test_clear_all(
        self, cache: ExtractionCache, sample_result: ExtractionResult
    ) -> None:
        """Should be able to clear all entries."""
        cache.add(sample_result)
        assert len(cache) == 1

        count = cache.clear()
        assert count == 1
        assert len(cache) == 0

    def test_clear_agency(
        self, cache: ExtractionCache, sample_result: ExtractionResult, tmp_path: Path
    ) -> None:
        """Should be able to clear entries for a specific agency."""
        # Add first result
        cache.add(sample_result)

        # Create second result with different agency
        image2 = tmp_path / "other.jpg"
        image2.write_bytes(b"other content")
        event2 = ExtractedEvent(
            name="Other Event",
            date_start=date(2026, 8, 20),
            date_end=date(2026, 8, 20),
            price=200000,
            agency="other-agency",
        )
        result2 = ExtractionResult(
            source_image=image2,
            agency="other-agency",
            month="agosto",
            year=2026,
            events=[event2],
            success=True,
        )
        cache.add(result2)

        assert len(cache) == 2

        # Clear only test-agency
        count = cache.clear_agency("test-agency")
        assert count == 1
        assert len(cache) == 1
        assert cache.is_processed(image2) is True

    def test_get_stats(
        self, cache: ExtractionCache, sample_result: ExtractionResult
    ) -> None:
        """Should return cache statistics."""
        cache.add(sample_result)
        stats = cache.get_stats()

        assert stats["total_images"] == 1
        assert stats["total_events"] == 1
        assert stats["covers"] == 0
        assert stats["by_agency"]["test-agency"] == 1

    def test_cover_detection(self, cache: ExtractionCache, sample_image: Path) -> None:
        """Empty results should be marked as cover pages."""
        result = ExtractionResult(
            source_image=sample_image,
            agency="test-agency",
            month="agosto",
            year=2026,
            events=[],  # No events = cover page
            success=True,
        )
        cache.add(result)

        entry = cache.get_cached(sample_image)
        assert entry is not None
        assert entry.is_cover is True
        assert entry.events_count == 0

        stats = cache.get_stats()
        assert stats["covers"] == 1

    def test_contains_operator(
        self,
        cache: ExtractionCache,
        sample_image: Path,
        sample_result: ExtractionResult,
    ) -> None:
        """Should support 'in' operator."""
        assert sample_image not in cache

        cache.add(sample_result)
        assert sample_result.source_image in cache


class TestCacheEntry:
    """Tests for CacheEntry."""

    def test_to_dict_round_trip(self) -> None:
        """Entry should serialize and deserialize correctly."""
        entry = CacheEntry(
            image_hash="abc123",
            agency="test-agency",
            month="agosto",
            year=2026,
            events_count=3,
            is_cover=False,
            processed_at=datetime(2026, 8, 1, 12, 0, 0),
            source_path="/path/to/image.jpg",
            events_data=[{"name": "Event 1"}],
        )

        data = entry.to_dict()
        restored = CacheEntry.from_dict(data)

        assert restored.image_hash == entry.image_hash
        assert restored.agency == entry.agency
        assert restored.events_count == entry.events_count
        assert restored.is_cover == entry.is_cover

    def test_from_extraction_result(self, sample_result: ExtractionResult) -> None:
        """Should create entry from extraction result."""
        image_hash = "test_hash_123"
        entry = CacheEntry.from_extraction_result(sample_result, image_hash)

        assert entry.image_hash == image_hash
        assert entry.agency == "test-agency"
        assert entry.events_count == 1
        assert entry.is_cover is False
        assert len(entry.events_data) == 1
