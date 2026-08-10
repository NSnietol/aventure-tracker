"""Tests for StateManager with GitHub Gist backend."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from aventure_tracker.infrastructure.state_manager import (
    GIST_FILENAME,
    GistAuthError,
    GistNotFoundError,
    StateManager,
    StateManagerError,
)
from aventure_tracker.models.state import StateData


@pytest.fixture
def state_manager() -> StateManager:
    """Create a StateManager instance for testing."""
    return StateManager(gist_id="test_gist_id", token="test_token")


@pytest.fixture
def mock_gist_response() -> dict:
    """Create a mock Gist API response."""
    state_data = StateData.empty()
    state_data.set_flight_state("BAQ-MDE-2025-03-15", 150000)
    state_data.mark_post_seen("testaccount", "ABC123")

    return {
        "id": "test_gist_id",
        "files": {
            GIST_FILENAME: {
                "filename": GIST_FILENAME,
                "content": json.dumps(state_data.to_dict()),
            }
        },
    }


@pytest.fixture
def empty_gist_response() -> dict:
    """Create a mock Gist API response with no state file."""
    return {
        "id": "test_gist_id",
        "files": {},
    }


class TestStateManagerInit:
    """Tests for StateManager initialization."""

    def test_init_creates_instance(self) -> None:
        """Test that StateManager initializes correctly."""
        manager = StateManager(gist_id="my_gist", token="my_token")

        assert manager._gist_id == "my_gist"
        assert manager._token == "my_token"
        assert "Authorization" in manager._headers

    def test_gist_url_property(self, state_manager: StateManager) -> None:
        """Test gist_url property returns correct URL."""
        assert state_manager.gist_url == "https://api.github.com/gists/test_gist_id"


class TestStateManagerRead:
    """Tests for StateManager.read()."""

    def test_read_loads_state_from_gist(
        self,
        state_manager: StateManager,
        mock_gist_response: dict,
    ) -> None:
        """Test reading state from Gist."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_gist_response
            mock_get.return_value = mock_response

            state = state_manager.read()

            assert state is not None
            assert state.get_flight_state("BAQ-MDE-2025-03-15") is not None
            assert state.is_post_seen("testaccount", "ABC123") is True

    def test_read_returns_empty_state_when_file_missing(
        self,
        state_manager: StateManager,
        empty_gist_response: dict,
    ) -> None:
        """Test returns empty state when state file doesn't exist."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = empty_gist_response
            mock_get.return_value = mock_response

            state = state_manager.read()

            assert state is not None
            assert len(state.flights) == 0
            assert len(state.instagram) == 0

    def test_read_returns_empty_state_on_invalid_json(
        self,
        state_manager: StateManager,
    ) -> None:
        """Test returns empty state when JSON is invalid."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "id": "test_gist_id",
                "files": {
                    GIST_FILENAME: {
                        "content": "invalid json {{{",
                    }
                },
            }
            mock_get.return_value = mock_response

            state = state_manager.read()

            assert state is not None
            assert len(state.flights) == 0

    def test_read_raises_auth_error_on_401(
        self,
        state_manager: StateManager,
    ) -> None:
        """Test raises GistAuthError on 401 response."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_get.return_value = mock_response

            with pytest.raises(GistAuthError):
                state_manager.read()

    def test_read_raises_not_found_on_404(
        self,
        state_manager: StateManager,
    ) -> None:
        """Test raises GistNotFoundError on 404 response."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            with pytest.raises(GistNotFoundError):
                state_manager.read()


class TestStateManagerWrite:
    """Tests for StateManager.write()."""

    def test_write_sends_state_to_gist(
        self,
        state_manager: StateManager,
    ) -> None:
        """Test writing state to Gist."""
        state = StateData.empty()
        state.set_flight_state("BAQ-MDE-2025-03-15", 150000)

        with patch("requests.patch") as mock_patch:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_patch.return_value = mock_response

            state_manager.write(state)

            mock_patch.assert_called_once()
            call_args = mock_patch.call_args
            assert GIST_FILENAME in call_args.kwargs["json"]["files"]

    def test_write_uses_internal_state_if_not_provided(
        self,
        state_manager: StateManager,
        mock_gist_response: dict,
    ) -> None:
        """Test write uses cached state if no argument provided."""
        # First read to populate internal state
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_gist_response
            mock_get.return_value = mock_response
            state_manager.read()

        # Now write without argument
        with patch("requests.patch") as mock_patch:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_patch.return_value = mock_response

            state_manager.write()

            mock_patch.assert_called_once()

    def test_write_raises_error_if_no_state(
        self,
        state_manager: StateManager,
    ) -> None:
        """Test write raises error if no state available."""
        with pytest.raises(StateManagerError, match="No state to write"):
            state_manager.write()

    def test_write_raises_auth_error_on_401(
        self,
        state_manager: StateManager,
    ) -> None:
        """Test raises GistAuthError on 401 response."""
        state = StateData.empty()

        with patch("requests.patch") as mock_patch:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_patch.return_value = mock_response

            with pytest.raises(GistAuthError):
                state_manager.write(state)


class TestStateManagerRetry:
    """Tests for retry logic."""

    def test_retries_on_timeout(
        self,
        state_manager: StateManager,
        mock_gist_response: dict,
    ) -> None:
        """Test retries on timeout errors."""
        with patch("requests.get") as mock_get:
            # First call times out, second succeeds
            mock_success = MagicMock()
            mock_success.status_code = 200
            mock_success.json.return_value = mock_gist_response

            mock_get.side_effect = [
                requests.exceptions.Timeout("timeout"),
                mock_success,
            ]

            with patch("time.sleep"):  # Don't actually sleep in tests
                state = state_manager.read()

            assert state is not None
            assert mock_get.call_count == 2

    def test_retries_on_connection_error(
        self,
        state_manager: StateManager,
        mock_gist_response: dict,
    ) -> None:
        """Test retries on connection errors."""
        with patch("requests.get") as mock_get:
            mock_success = MagicMock()
            mock_success.status_code = 200
            mock_success.json.return_value = mock_gist_response

            mock_get.side_effect = [
                requests.exceptions.ConnectionError("connection failed"),
                mock_success,
            ]

            with patch("time.sleep"):
                state = state_manager.read()

            assert state is not None
            assert mock_get.call_count == 2

    def test_raises_after_max_retries(
        self,
        state_manager: StateManager,
    ) -> None:
        """Test raises error after max retries exceeded."""
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout("timeout")

            with patch("time.sleep"):
                with pytest.raises(StateManagerError, match="Request failed after"):
                    state_manager.read()


class TestStateManagerConvenience:
    """Tests for convenience methods."""

    def test_get_state_loads_if_not_cached(
        self,
        state_manager: StateManager,
        mock_gist_response: dict,
    ) -> None:
        """Test get_state loads from Gist if not cached."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_gist_response
            mock_get.return_value = mock_response

            state = state_manager.get_state()

            assert state is not None
            mock_get.assert_called_once()

    def test_get_state_returns_cached(
        self,
        state_manager: StateManager,
        mock_gist_response: dict,
    ) -> None:
        """Test get_state returns cached state on subsequent calls."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_gist_response
            mock_get.return_value = mock_response

            state_manager.get_state()
            state_manager.get_state()

            # Should only call API once
            mock_get.assert_called_once()

    def test_get_last_flight_price(
        self,
        state_manager: StateManager,
        mock_gist_response: dict,
    ) -> None:
        """Test getting last flight price."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_gist_response
            mock_get.return_value = mock_response

            price = state_manager.get_last_flight_price("BAQ-MDE-2025-03-15")
            assert price == 150000

            no_price = state_manager.get_last_flight_price("CTG-MDE-2025-03-15")
            assert no_price is None

    def test_set_flight_price(
        self,
        state_manager: StateManager,
        mock_gist_response: dict,
    ) -> None:
        """Test setting flight price."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_gist_response
            mock_get.return_value = mock_response

            state_manager.set_flight_price("CTG-MDE-2025-03-20", 120000)
            price = state_manager.get_last_flight_price("CTG-MDE-2025-03-20")

            assert price == 120000

    def test_seen_posts_methods(
        self,
        state_manager: StateManager,
        mock_gist_response: dict,
    ) -> None:
        """Test Instagram seen posts methods."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_gist_response
            mock_get.return_value = mock_response

            # Check existing
            assert state_manager.is_post_seen("testaccount", "ABC123") is True
            assert state_manager.is_post_seen("testaccount", "XYZ789") is False

            # Add new
            state_manager.add_seen_post("testaccount", "XYZ789")
            assert state_manager.is_post_seen("testaccount", "XYZ789") is True

            # Get all seen
            seen = state_manager.get_seen_posts("testaccount")
            assert "ABC123" in seen
            assert "XYZ789" in seen

    def test_save_alias(
        self,
        state_manager: StateManager,
        mock_gist_response: dict,
    ) -> None:
        """Test save() is alias for write()."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_gist_response
            mock_get.return_value = mock_response
            state_manager.read()

        with patch("requests.patch") as mock_patch:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_patch.return_value = mock_response

            state_manager.save()

            mock_patch.assert_called_once()
