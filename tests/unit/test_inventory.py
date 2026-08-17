"""Unit tests for inventory manager (blacklist-only approach)."""

from datetime import datetime
from pathlib import Path

import pytest

from aventure_tracker.models.activity import InstagramPost
from aventure_tracker.services.inventory import InventoryManager, MatchResult
from aventure_tracker.services.ocr import ExtractedActivity


@pytest.fixture
def destinations_config(tmp_path: Path) -> Path:
    """Create a test destinations.yaml file."""
    config = tmp_path / "destinations.yaml"
    config.write_text("""
blacklist:
  ya_fue:
    - Guatapé
    - San Luis
    - Tatacoa
  playa:
    - Bahía Málaga
    - Rincón del Mar
  no_interesa:
    - avistamiento de ballenas
""")
    return config


@pytest.fixture
def manager(destinations_config: Path) -> InventoryManager:
    """Create an inventory manager with test config."""
    return InventoryManager(destinations_path=destinations_config)


class TestInventoryManagerInit:
    """Tests for InventoryManager initialization."""

    def test_init_with_path(self, destinations_config: Path) -> None:
        """Test initialization with destinations path."""
        manager = InventoryManager(destinations_path=destinations_config)
        assert manager._destinations_path == destinations_config

    def test_init_without_path(self) -> None:
        """Test initialization without any paths."""
        manager = InventoryManager()
        assert manager._destinations_path is None

    def test_load_creates_empty_config_when_no_path(self) -> None:
        """Test that load creates empty config when no path provided."""
        manager = InventoryManager()
        manager.load()
        assert len(manager.destinations.get_all_blacklisted()) == 0


class TestLoadConfigs:
    """Tests for loading configurations."""

    def test_load_destinations(self, manager: InventoryManager) -> None:
        """Test loading destinations config."""
        assert len(manager.destinations.get_all_blacklisted()) == 6
        assert "guatapé" in manager.destinations.get_all_blacklisted()

    def test_lazy_load_on_property_access(self, destinations_config: Path) -> None:
        """Test that config is lazily loaded on property access."""
        manager = InventoryManager(destinations_path=destinations_config)
        assert manager._destinations is None
        _ = manager.destinations  # Should trigger load
        assert manager._destinations is not None


class TestIsBlacklisted:
    """Tests for is_blacklisted method."""

    def test_exact_match(self, manager: InventoryManager) -> None:
        """Test exact blacklist match."""
        is_blocked, dest, reason = manager.is_blacklisted("Guatapé")
        assert is_blocked is True
        assert dest == "Guatapé"
        assert reason == "ya_fue"

    def test_case_insensitive_match(self, manager: InventoryManager) -> None:
        """Test case-insensitive blacklist matching."""
        is_blocked, dest, reason = manager.is_blacklisted("TATACOA")
        assert is_blocked is True
        assert dest == "Tatacoa"

    def test_partial_match(self, manager: InventoryManager) -> None:
        """Test partial text match against blacklist."""
        is_blocked, dest, reason = manager.is_blacklisted(
            "Tour a San Luis con Brutal Travel"
        )
        assert is_blocked is True
        assert dest == "San Luis"
        assert reason == "ya_fue"

    def test_no_match(self, manager: InventoryManager) -> None:
        """Test text that doesn't match blacklist."""
        is_blocked, dest, reason = manager.is_blacklisted("Rafting San Gil")
        assert is_blocked is False
        assert dest is None
        assert reason is None

    def test_playa_match(self, manager: InventoryManager) -> None:
        """Test playa category blacklist match."""
        is_blocked, dest, reason = manager.is_blacklisted("Viaje a Bahía Málaga")
        assert is_blocked is True
        assert reason == "playa"

    def test_no_interesa_match(self, manager: InventoryManager) -> None:
        """Test no_interesa category match."""
        is_blocked, dest, reason = manager.is_blacklisted(
            "Tour avistamiento de ballenas en el Pacífico"
        )
        assert is_blocked is True
        assert reason == "no_interesa"


class TestMatchActivity:
    """Tests for match_activity method."""

    def test_match_blacklisted_activity(self, manager: InventoryManager) -> None:
        """Test matching a blacklisted activity."""
        extracted = ExtractedActivity(
            raw_text="Tour a Guatapé este fin de semana",
            activity_name="Tour",
            location="Guatapé",
            confidence=0.8,
        )
        result = manager.match_activity(extracted)

        assert result.is_blacklisted is True
        assert result.matched_blacklist == "Guatapé"
        assert result.blacklist_reason == "ya_fue"
        assert result.should_notify is False

    def test_match_allowed_activity(self, manager: InventoryManager) -> None:
        """Test matching an activity that's NOT blacklisted."""
        extracted = ExtractedActivity(
            raw_text="Rafting en San Gil",
            activity_name="Rafting",
            location="San Gil",
            confidence=0.9,
        )
        result = manager.match_activity(extracted)

        assert result.is_blacklisted is False
        assert result.should_notify is True
        assert result.match_score == 0.9  # Uses confidence


class TestMatchPost:
    """Tests for match_post method."""

    def test_match_post_with_extracted(self, manager: InventoryManager) -> None:
        """Test matching a post with extracted activity info."""
        post = InstagramPost(
            id="123",
            url="https://instagram.com/p/123",
            image_urls=["img.jpg"],
            caption="Plan a Guatapé",
            timestamp=datetime.now(),
        )
        extracted = ExtractedActivity(
            raw_text="Tour Guatapé $150.000",
            location="Guatapé",
            confidence=0.7,
        )

        result = manager.match_post(post, extracted)
        assert result.is_blacklisted is True
        assert result.should_notify is False

    def test_match_post_without_extracted(self, manager: InventoryManager) -> None:
        """Test matching a post using only caption."""
        post = InstagramPost(
            id="123",
            url="https://instagram.com/p/123",
            image_urls=[],
            caption="Plan a Tatacoa este puente",
            timestamp=datetime.now(),
        )

        result = manager.match_post(post)
        assert result.is_blacklisted is True
        assert result.matched_blacklist == "Tatacoa"

    def test_match_post_allowed(self, manager: InventoryManager) -> None:
        """Test matching a post that's not blacklisted."""
        post = InstagramPost(
            id="123",
            url="https://instagram.com/p/123",
            image_urls=[],
            caption="Aventura en Ciudad Perdida",
            timestamp=datetime.now(),
        )

        result = manager.match_post(post)
        assert result.is_blacklisted is False
        assert result.should_notify is True


class TestAddToBlacklist:
    """Tests for add_to_blacklist method."""

    def test_add_to_blacklist(self, manager: InventoryManager) -> None:
        """Test adding a destination to blacklist."""
        manager.add_to_blacklist("Ciudad Perdida", reason="ya_fue")
        assert "ciudad perdida" in manager.destinations.get_all_blacklisted()

    def test_add_to_new_reason(self, manager: InventoryManager) -> None:
        """Test adding to a new reason category."""
        manager.add_to_blacklist("Algo", reason="otro")
        assert "algo" in manager.destinations.get_all_blacklisted()
        assert "Algo" in manager.destinations.get_by_reason("otro")


class TestSave:
    """Tests for save method."""

    def test_save_destinations(self, manager: InventoryManager, tmp_path: Path) -> None:
        """Test saving destinations config."""
        manager.add_to_blacklist("Nuevo Destino", "ya_fue")
        manager.save()

        # Reload and verify
        manager2 = InventoryManager(destinations_path=manager._destinations_path)
        assert "nuevo destino" in manager2.destinations.get_all_blacklisted()


class TestGetStats:
    """Tests for get_stats method."""

    def test_get_stats(self, manager: InventoryManager) -> None:
        """Test getting inventory statistics."""
        stats = manager.get_stats()

        assert stats["blacklist_count"] == 6
        assert stats["ya_fue_count"] == 3
        assert stats["playa_count"] == 2
        assert stats["no_interesa_count"] == 1


class TestFilterNewActivities:
    """Tests for filter_new_activities method."""

    def test_filter_excludes_blacklisted(self, manager: InventoryManager) -> None:
        """Test that filter excludes blacklisted activities."""
        posts = [
            InstagramPost(
                id="1",
                url="url1",
                image_urls=[],
                caption="Aventura en San Gil",  # NOT blacklisted
                timestamp=datetime.now(),
            ),
            InstagramPost(
                id="2",
                url="url2",
                image_urls=[],
                caption="Tour Guatapé",  # BLACKLISTED
                timestamp=datetime.now(),
            ),
            InstagramPost(
                id="3",
                url="url3",
                image_urls=[],
                caption="City tour Bogotá",  # NOT blacklisted
                timestamp=datetime.now(),
            ),
        ]

        results = manager.filter_new_activities(posts)

        # Should return 2 posts (San Gil and Bogotá), excluding Guatapé
        assert len(results) == 2
        captions = [post.caption for post, _ in results]
        assert "Tour Guatapé" not in captions
        assert "Aventura en San Gil" in captions

    def test_filter_with_extracted_activities(self, manager: InventoryManager) -> None:
        """Test filter with extracted activity info."""
        posts = [
            InstagramPost(
                id="1",
                url="url1",
                image_urls=[],
                caption="Plan especial",
                timestamp=datetime.now(),
            ),
        ]
        extracted = {
            "1": ExtractedActivity(
                raw_text="Plan Bahía Málaga",  # BLACKLISTED (playa)
                location="Bahía Málaga",
                confidence=0.8,
            )
        }

        results = manager.filter_new_activities(posts, extracted)
        assert len(results) == 0  # Should be filtered out


class TestMatchResultDataclass:
    """Tests for MatchResult dataclass."""

    def test_create_match_result(self) -> None:
        """Test creating a MatchResult."""
        result = MatchResult(
            is_blacklisted=True,
            matched_blacklist="Guatapé",
            blacklist_reason="ya_fue",
            match_score=0.8,
        )

        assert result.is_blacklisted is True
        assert result.matched_blacklist == "Guatapé"
        assert result.should_notify is False

    def test_match_result_defaults(self) -> None:
        """Test MatchResult default values."""
        result = MatchResult()

        assert result.is_blacklisted is False
        assert result.matched_blacklist is None
        assert result.blacklist_reason is None
        assert result.match_score == 1.0
        assert result.should_notify is True
