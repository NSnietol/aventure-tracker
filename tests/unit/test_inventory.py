"""Tests for Inventory Manager."""

from datetime import datetime
from pathlib import Path

import pytest

from aventure_tracker.models.activity import InstagramPost
from aventure_tracker.services.inventory import InventoryManager, MatchResult
from aventure_tracker.services.ocr import ExtractedActivity


@pytest.fixture
def wishlist_config(tmp_path: Path) -> Path:
    """Create a temporary wishlist config file."""
    config_path = tmp_path / "wishlist.yaml"
    config_path.write_text(
        """
destinations:
  - Guatapé
  - San Gil
  - Jardín
  - Tayrona
"""
    )
    return config_path


@pytest.fixture
def done_config(tmp_path: Path) -> Path:
    """Create a temporary done config file."""
    config_path = tmp_path / "done.yaml"
    config_path.write_text(
        """
activities:
  - "Guatapé - Agosto 2024"
  - "Bungee Medellín"
"""
    )
    return config_path


@pytest.fixture
def manager(wishlist_config: Path, done_config: Path) -> InventoryManager:
    """Create an inventory manager with test configs."""
    mgr = InventoryManager(
        wishlist_path=wishlist_config,
        done_path=done_config,
    )
    mgr.load()
    return mgr


@pytest.fixture
def sample_post() -> InstagramPost:
    """Create a sample Instagram post."""
    return InstagramPost(
        id="TEST123",
        url="https://instagram.com/p/TEST123/",
        image_urls=["https://example.com/img.jpg"],
        caption="Aventura en Jardín, Antioquia! Parapente y naturaleza",
        timestamp=datetime.now(),
    )


@pytest.fixture
def sample_extracted() -> ExtractedActivity:
    """Create a sample extracted activity."""
    return ExtractedActivity(
        raw_text="Parapente en Jardín\nPrecio: $150.000\n15 de marzo",
        activity_name="Parapente",
        location="Jardín",
        price=150000,
        confidence=0.8,
    )


class TestInventoryManagerInit:
    """Tests for inventory manager initialization."""

    def test_init_with_paths(
        self, wishlist_config: Path, done_config: Path
    ) -> None:
        """Test initialization with config paths."""
        manager = InventoryManager(
            wishlist_path=wishlist_config,
            done_path=done_config,
        )
        assert manager._wishlist_path == wishlist_config
        assert manager._done_path == done_config

    def test_init_without_paths(self) -> None:
        """Test initialization without config paths."""
        manager = InventoryManager()
        assert manager._wishlist_path is None
        assert manager._done_path is None

    def test_load_creates_empty_configs_when_no_paths(self) -> None:
        """Test load creates empty configs when no paths provided."""
        manager = InventoryManager()
        manager.load()
        assert manager.wishlist.destinations == []
        assert manager.done.activities == []


class TestLoadConfigs:
    """Tests for loading configurations."""

    def test_load_wishlist(self, manager: InventoryManager) -> None:
        """Test loading wishlist from file."""
        assert len(manager.wishlist.destinations) == 4
        assert "Guatapé" in manager.wishlist.destinations
        assert "San Gil" in manager.wishlist.destinations

    def test_load_done(self, manager: InventoryManager) -> None:
        """Test loading done activities from file."""
        assert len(manager.done.activities) == 2
        assert "Guatapé - Agosto 2024" in manager.done.activities

    def test_lazy_load_on_property_access(
        self, wishlist_config: Path, done_config: Path
    ) -> None:
        """Test configs are lazily loaded on property access."""
        manager = InventoryManager(
            wishlist_path=wishlist_config,
            done_path=done_config,
        )
        # Not loaded yet
        assert manager._wishlist is None

        # Accessing property triggers load
        _ = manager.wishlist
        assert manager._wishlist is not None


class TestIsInWishlist:
    """Tests for wishlist matching."""

    def test_exact_match(self, manager: InventoryManager) -> None:
        """Test exact destination match."""
        is_match, dest = manager.is_in_wishlist("Guatapé")
        assert is_match is True
        assert dest == "Guatapé"

    def test_case_insensitive_match(self, manager: InventoryManager) -> None:
        """Test case-insensitive matching."""
        is_match, dest = manager.is_in_wishlist("JARDÍN")
        assert is_match is True
        assert dest == "Jardín"

    def test_partial_match(self, manager: InventoryManager) -> None:
        """Test partial text matching."""
        is_match, dest = manager.is_in_wishlist(
            "Aventura en San Gil este fin de semana"
        )
        assert is_match is True
        assert dest == "San Gil"

    def test_no_match(self, manager: InventoryManager) -> None:
        """Test no match returns False."""
        is_match, dest = manager.is_in_wishlist("Medellín city tour")
        assert is_match is False
        assert dest is None


class TestIsAlreadyDone:
    """Tests for done activity matching."""

    def test_exact_match(self, manager: InventoryManager) -> None:
        """Test exact activity match."""
        is_done, activity = manager.is_already_done("Guatapé - Agosto 2024")
        assert is_done is True
        assert activity == "Guatapé - Agosto 2024"

    def test_partial_match_in_done(self, manager: InventoryManager) -> None:
        """Test partial match when done contains search text."""
        is_done, activity = manager.is_already_done("Guatapé")
        assert is_done is True
        assert "Guatapé" in activity  # type: ignore

    def test_partial_match_in_search(self, manager: InventoryManager) -> None:
        """Test partial match when search text contains done."""
        is_done, activity = manager.is_already_done(
            "Bungee Medellín fue increíble!"
        )
        assert is_done is True
        assert activity == "Bungee Medellín"

    def test_no_match(self, manager: InventoryManager) -> None:
        """Test no match returns False."""
        is_done, activity = manager.is_already_done("Rafting San Gil")
        assert is_done is False
        assert activity is None


class TestMatchActivity:
    """Tests for activity matching."""

    def test_match_wishlist_activity(
        self, manager: InventoryManager, sample_extracted: ExtractedActivity
    ) -> None:
        """Test matching activity against wishlist."""
        result = manager.match_activity(sample_extracted)

        assert result.is_wishlist_match is True
        assert result.matched_destination == "Jardín"
        assert result.is_already_done is False
        assert result.match_score > 0

    def test_match_done_activity(self, manager: InventoryManager) -> None:
        """Test matching activity that's already done."""
        extracted = ExtractedActivity(
            raw_text="Tour a Guatapé con piedra del peñol",
            location="Guatapé",
            confidence=0.7,
        )

        result = manager.match_activity(extracted)

        assert result.is_wishlist_match is True
        assert result.is_already_done is True
        assert result.matched_done is not None

    def test_match_unknown_activity(self, manager: InventoryManager) -> None:
        """Test matching activity not in wishlist."""
        extracted = ExtractedActivity(
            raw_text="City tour por Bogotá",
            location="Bogotá",
            confidence=0.6,
        )

        result = manager.match_activity(extracted)

        assert result.is_wishlist_match is False
        assert result.match_score == 0.0


class TestMatchPost:
    """Tests for post matching."""

    def test_match_post_with_extracted(
        self,
        manager: InventoryManager,
        sample_post: InstagramPost,
        sample_extracted: ExtractedActivity,
    ) -> None:
        """Test matching post with OCR results."""
        result = manager.match_post(sample_post, sample_extracted)

        assert result.is_wishlist_match is True
        assert result.matched_destination == "Jardín"

    def test_match_post_without_extracted(
        self, manager: InventoryManager, sample_post: InstagramPost
    ) -> None:
        """Test matching post using only caption."""
        result = manager.match_post(sample_post)

        assert result.is_wishlist_match is True
        assert result.matched_destination == "Jardín"

    def test_match_post_no_match(self, manager: InventoryManager) -> None:
        """Test matching post with no wishlist match."""
        post = InstagramPost(
            id="XYZ",
            url="https://instagram.com/p/XYZ/",
            image_urls=[],
            caption="Beach day in Cartagena",
            timestamp=datetime.now(),
        )

        result = manager.match_post(post)

        assert result.is_wishlist_match is False


class TestAddRemove:
    """Tests for adding and removing items."""

    def test_add_to_done(self, manager: InventoryManager) -> None:
        """Test adding activity to done list."""
        manager.add_to_done("San Gil - Marzo 2025")

        assert "San Gil - Marzo 2025" in manager.done.activities

    def test_add_duplicate_to_done(self, manager: InventoryManager) -> None:
        """Test adding duplicate doesn't create duplicates."""
        original_count = len(manager.done.activities)
        manager.add_to_done("Guatapé - Agosto 2024")  # Already exists

        assert len(manager.done.activities) == original_count

    def test_add_to_wishlist(self, manager: InventoryManager) -> None:
        """Test adding destination to wishlist."""
        manager.add_to_wishlist("Cartagena")

        assert "Cartagena" in manager.wishlist.destinations

    def test_remove_from_wishlist(self, manager: InventoryManager) -> None:
        """Test removing destination from wishlist."""
        result = manager.remove_from_wishlist("Guatapé")

        assert result is True
        assert "Guatapé" not in manager.wishlist.destinations

    def test_remove_nonexistent_from_wishlist(
        self, manager: InventoryManager
    ) -> None:
        """Test removing nonexistent destination returns False."""
        result = manager.remove_from_wishlist("Nonexistent")

        assert result is False


class TestSave:
    """Tests for saving configurations."""

    def test_save_wishlist(self, manager: InventoryManager, tmp_path: Path) -> None:
        """Test saving wishlist to file."""
        manager.add_to_wishlist("Cartagena")
        manager.save()

        # Verify file was updated
        content = manager._wishlist_path.read_text()  # type: ignore
        assert "Cartagena" in content

    def test_save_done(self, manager: InventoryManager, tmp_path: Path) -> None:
        """Test saving done to file."""
        manager.add_to_done("Rafting San Gil")
        manager.save()

        # Verify file was updated
        content = manager._done_path.read_text()  # type: ignore
        assert "Rafting San Gil" in content


class TestGetStats:
    """Tests for statistics."""

    def test_get_stats(self, manager: InventoryManager) -> None:
        """Test getting inventory statistics."""
        stats = manager.get_stats()

        assert stats["wishlist_count"] == 4
        assert stats["done_count"] == 2


class TestFilterNewActivities:
    """Tests for filtering new activities."""

    def test_filter_returns_new_wishlist_matches(
        self, manager: InventoryManager
    ) -> None:
        """Test filter returns posts matching wishlist but not done."""
        posts = [
            InstagramPost(
                id="1",
                url="url1",
                image_urls=[],
                caption="Aventura en San Gil",  # In wishlist, not done
                timestamp=datetime.now(),
            ),
            InstagramPost(
                id="2",
                url="url2",
                image_urls=[],
                caption="Tour Guatapé",  # In wishlist, but done
                timestamp=datetime.now(),
            ),
            InstagramPost(
                id="3",
                url="url3",
                image_urls=[],
                caption="City tour Bogotá",  # Not in wishlist
                timestamp=datetime.now(),
            ),
        ]

        results = manager.filter_new_activities(posts)

        assert len(results) == 1
        assert results[0][0].id == "1"

    def test_filter_with_extracted_activities(
        self, manager: InventoryManager
    ) -> None:
        """Test filter with OCR extracted activities."""
        posts = [
            InstagramPost(
                id="1",
                url="url1",
                image_urls=[],
                caption="",
                timestamp=datetime.now(),
            ),
        ]

        extracted = {
            "1": ExtractedActivity(
                raw_text="Parapente en Jardín",
                location="Jardín",
                confidence=0.9,
            )
        }

        results = manager.filter_new_activities(posts, extracted)

        assert len(results) == 1
        assert results[0][1].matched_destination == "Jardín"

    def test_filter_sorts_by_score(self, manager: InventoryManager) -> None:
        """Test filter results are sorted by match score."""
        posts = [
            InstagramPost(
                id="1",
                url="url1",
                image_urls=[],
                caption="San Gil",
                timestamp=datetime.now(),
            ),
            InstagramPost(
                id="2",
                url="url2",
                image_urls=[],
                caption="Tayrona",
                timestamp=datetime.now(),
            ),
        ]

        extracted = {
            "1": ExtractedActivity(
                raw_text="San Gil",
                location="San Gil",
                confidence=0.5,
            ),
            "2": ExtractedActivity(
                raw_text="Tayrona",
                location="Tayrona",
                price=200000,  # Has price = higher score
                confidence=0.8,
            ),
        }

        results = manager.filter_new_activities(posts, extracted)

        # Higher scored post should be first
        assert len(results) == 2
        assert results[0][1].match_score >= results[1][1].match_score


class TestMatchResultDataclass:
    """Tests for MatchResult dataclass."""

    def test_create_match_result(self) -> None:
        """Test creating MatchResult."""
        result = MatchResult(
            is_wishlist_match=True,
            is_already_done=False,
            matched_destination="Jardín",
            match_score=0.85,
        )

        assert result.is_wishlist_match is True
        assert result.is_already_done is False
        assert result.matched_destination == "Jardín"
        assert result.match_score == 0.85

    def test_match_result_defaults(self) -> None:
        """Test MatchResult default values."""
        result = MatchResult(
            is_wishlist_match=False,
            is_already_done=False,
        )

        assert result.matched_destination is None
        assert result.matched_done is None
        assert result.match_score == 0.0
