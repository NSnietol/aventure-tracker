"""Tests for ActivityHistoryManager."""

from pathlib import Path

import pytest
import yaml

from aventure_tracker.services.activity_history import (
    MAX_CHECK_COUNT,
    ActivityHistoryManager,
    ActivityRecord,
)


@pytest.fixture
def history_path(tmp_path: Path) -> Path:
    """Create a temporary history file path."""
    return tmp_path / "data" / "activity_history.yaml"


@pytest.fixture
def manager(history_path: Path) -> ActivityHistoryManager:
    """Create a history manager with temp path."""
    return ActivityHistoryManager(history_path=history_path)


@pytest.fixture
def sample_history(history_path: Path) -> Path:
    """Create a sample history file."""
    history_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "posts": {
            "brutaltravel.co": {
                "ABC123": {
                    "event_id": "2026-08-15-cocuy-trek",
                    "event_name": "Cocuy Trek",
                    "event_date": "2026-08-15",
                    "first_seen": "2026-08-10",
                    "times_checked": 2,
                    "matched_wishlist": True,
                    "destination": "Cocuy",
                },
                "XYZ789": {
                    "event_id": "2026-09-01-guatape",
                    "event_name": "Guatapé Tour",
                    "event_date": "2026-09-01",
                    "first_seen": "2026-08-10",
                    "times_checked": 3,
                    "matched_wishlist": False,
                    "destination": None,
                },
            },
            "medellinbungee": {
                "DEF456": {
                    "event_id": "2026-08-20-bungee",
                    "event_name": "Bungee Jump",
                    "event_date": "2026-08-20",
                    "first_seen": "2026-08-11",
                    "times_checked": 1,
                    "matched_wishlist": False,
                    "destination": None,
                },
            },
        }
    }

    with open(history_path, "w") as f:
        yaml.dump(data, f)

    return history_path


class TestActivityRecord:
    """Tests for ActivityRecord dataclass."""

    def test_create_record(self) -> None:
        """Test creating an activity record."""
        record = ActivityRecord(
            post_id="ABC123",
            event_id="2026-08-15-cocuy",
            event_name="Cocuy Trek",
            event_date="2026-08-15",
        )

        assert record.post_id == "ABC123"
        assert record.event_id == "2026-08-15-cocuy"
        assert record.times_checked == 1
        assert record.matched_wishlist is False

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        record = ActivityRecord(
            post_id="ABC123",
            event_id="2026-08-15-cocuy",
            event_name="Cocuy Trek",
            matched_wishlist=True,
            destination="Cocuy",
        )

        data = record.to_dict()

        assert data["event_id"] == "2026-08-15-cocuy"
        assert data["event_name"] == "Cocuy Trek"
        assert data["matched_wishlist"] is True
        assert data["destination"] == "Cocuy"
        assert "post_id" not in data  # post_id is the key, not in value

    def test_from_dict(self) -> None:
        """Test creating from dictionary."""
        data = {
            "event_id": "2026-08-15-cocuy",
            "event_name": "Cocuy Trek",
            "times_checked": 2,
            "matched_wishlist": True,
        }

        record = ActivityRecord.from_dict("ABC123", data)

        assert record.post_id == "ABC123"
        assert record.event_id == "2026-08-15-cocuy"
        assert record.times_checked == 2


class TestActivityHistoryManagerInit:
    """Tests for manager initialization."""

    def test_default_path(self) -> None:
        """Test default history path."""
        manager = ActivityHistoryManager()

        assert manager.history_path == Path("data/activity_history.yaml")

    def test_custom_path(self, history_path: Path) -> None:
        """Test custom history path."""
        manager = ActivityHistoryManager(history_path=history_path)

        assert manager.history_path == history_path

    def test_custom_max_checks(self) -> None:
        """Test custom max checks."""
        manager = ActivityHistoryManager(max_checks=5)

        assert manager._max_checks == 5


class TestLoadHistory:
    """Tests for loading history."""

    def test_load_empty(self, manager: ActivityHistoryManager) -> None:
        """Test loading when file doesn't exist."""
        manager.load()

        assert manager.total_records == 0

    def test_load_existing(self, history_path: Path, sample_history: Path) -> None:
        """Test loading existing history file."""
        manager = ActivityHistoryManager(history_path=history_path)
        manager.load()

        assert manager.total_records == 3
        assert manager.get_check_count("brutaltravel.co", "ABC123") == 2
        assert manager.get_check_count("brutaltravel.co", "XYZ789") == 3

    def test_load_corrupted_file(self, history_path: Path) -> None:
        """Test loading corrupted file doesn't crash."""
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text("invalid: yaml: content: [")

        manager = ActivityHistoryManager(history_path=history_path)
        manager.load()

        assert manager.total_records == 0


class TestSaveHistory:
    """Tests for saving history."""

    def test_save_creates_directory(self, history_path: Path) -> None:
        """Test save creates parent directory."""
        manager = ActivityHistoryManager(history_path=history_path)
        manager.load()
        manager.record_check(
            account="test",
            post_id="ABC",
            event_id="2026-08-test",
            event_name="Test Event",
        )
        manager.save()

        assert history_path.exists()

    def test_save_and_reload(self, history_path: Path) -> None:
        """Test saving and reloading preserves data."""
        manager = ActivityHistoryManager(history_path=history_path)
        manager.load()

        manager.record_check(
            account="brutaltravel.co",
            post_id="ABC123",
            event_id="2026-08-15-cocuy",
            event_name="Cocuy Trek",
            matched_wishlist=True,
            destination="Cocuy",
        )

        manager.save()

        # Reload
        manager2 = ActivityHistoryManager(history_path=history_path)
        manager2.load()

        record = manager2.get_record("brutaltravel.co", "ABC123")
        assert record is not None
        assert record.event_name == "Cocuy Trek"
        assert record.matched_wishlist is True


class TestShouldCheck:
    """Tests for should_check logic."""

    def test_should_check_new_post(self, manager: ActivityHistoryManager) -> None:
        """Test new post should be checked."""
        manager.load()

        assert manager.should_check("account", "new_post") is True

    def test_should_check_under_limit(
        self, history_path: Path, sample_history: Path
    ) -> None:
        """Test post under limit should be checked."""
        manager = ActivityHistoryManager(history_path=history_path)
        manager.load()

        # ABC123 has times_checked=2, limit is 3
        assert manager.should_check("brutaltravel.co", "ABC123") is True

    def test_should_not_check_at_limit(
        self, history_path: Path, sample_history: Path
    ) -> None:
        """Test post at limit should not be checked."""
        manager = ActivityHistoryManager(history_path=history_path)
        manager.load()

        # XYZ789 has times_checked=3
        assert manager.should_check("brutaltravel.co", "XYZ789") is False

    def test_should_check_unknown_account(
        self, history_path: Path, sample_history: Path
    ) -> None:
        """Test unknown account returns True."""
        manager = ActivityHistoryManager(history_path=history_path)
        manager.load()

        assert manager.should_check("unknown_account", "any_post") is True


class TestRecordCheck:
    """Tests for recording checks."""

    def test_record_new_check(self, manager: ActivityHistoryManager) -> None:
        """Test recording a new post check."""
        manager.load()

        record = manager.record_check(
            account="brutaltravel.co",
            post_id="NEW123",
            event_id="2026-09-01-new-event",
            event_name="New Event",
            event_date="2026-09-01",
            matched_wishlist=True,
            destination="Somewhere",
        )

        assert record.post_id == "NEW123"
        assert record.times_checked == 1
        assert record.matched_wishlist is True

    def test_record_increments_count(
        self, history_path: Path, sample_history: Path
    ) -> None:
        """Test recording increments check count."""
        manager = ActivityHistoryManager(history_path=history_path)
        manager.load()

        initial_count = manager.get_check_count("brutaltravel.co", "ABC123")

        manager.record_check(
            account="brutaltravel.co",
            post_id="ABC123",
            event_id="2026-08-15-cocuy-trek",
            event_name="Cocuy Trek",
        )

        assert manager.get_check_count("brutaltravel.co", "ABC123") == initial_count + 1

    def test_record_updates_wishlist_match(
        self, history_path: Path, sample_history: Path
    ) -> None:
        """Test recording updates wishlist match status."""
        manager = ActivityHistoryManager(history_path=history_path)
        manager.load()

        # XYZ789 originally has matched_wishlist=False
        manager.record_check(
            account="brutaltravel.co",
            post_id="XYZ789",
            event_id="2026-09-01-guatape",
            event_name="Guatapé Tour",
            matched_wishlist=True,
            destination="Guatapé",
        )

        record = manager.get_record("brutaltravel.co", "XYZ789")
        assert record is not None
        assert record.matched_wishlist is True
        assert record.destination == "Guatapé"


class TestGetAccountHistory:
    """Tests for account history retrieval."""

    def test_get_account_history(
        self, history_path: Path, sample_history: Path
    ) -> None:
        """Test getting all records for an account."""
        manager = ActivityHistoryManager(history_path=history_path)
        manager.load()

        records = manager.get_account_history("brutaltravel.co")

        assert len(records) == 2
        post_ids = {r.post_id for r in records}
        assert "ABC123" in post_ids
        assert "XYZ789" in post_ids

    def test_get_account_history_unknown(self, manager: ActivityHistoryManager) -> None:
        """Test getting history for unknown account."""
        manager.load()

        records = manager.get_account_history("unknown")

        assert records == []


class TestGetSkippedCount:
    """Tests for skipped count."""

    def test_get_skipped_count(self, history_path: Path, sample_history: Path) -> None:
        """Test counting posts that will be skipped."""
        manager = ActivityHistoryManager(history_path=history_path)
        manager.load()

        # brutaltravel.co has 1 post at limit (XYZ789 with times_checked=3)
        assert manager.get_skipped_count("brutaltravel.co") == 1

    def test_get_skipped_count_none(
        self, history_path: Path, sample_history: Path
    ) -> None:
        """Test skipped count for account with no skipped posts."""
        manager = ActivityHistoryManager(history_path=history_path)
        manager.load()

        # medellinbungee has only 1 post with times_checked=1
        assert manager.get_skipped_count("medellinbungee") == 0


class TestClear:
    """Tests for clearing history."""

    def test_clear_account(self, history_path: Path, sample_history: Path) -> None:
        """Test clearing a specific account."""
        manager = ActivityHistoryManager(history_path=history_path)
        manager.load()

        manager.clear_account("brutaltravel.co")

        assert manager.get_account_history("brutaltravel.co") == []
        assert len(manager.get_account_history("medellinbungee")) == 1

    def test_clear_all(self, history_path: Path, sample_history: Path) -> None:
        """Test clearing all history."""
        manager = ActivityHistoryManager(history_path=history_path)
        manager.load()

        manager.clear_all()

        assert manager.total_records == 0


class TestMaxCheckCount:
    """Tests for MAX_CHECK_COUNT constant."""

    def test_default_max_check_count(self) -> None:
        """Test default max check count is 3."""
        assert MAX_CHECK_COUNT == 3
