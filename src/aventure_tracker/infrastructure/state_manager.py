"""State persistence using GitHub Gist as backend storage."""

import json
import logging
import time
from typing import Any

import requests

from aventure_tracker.models.state import StateData

logger = logging.getLogger(__name__)

# GitHub API constants
GITHUB_API_BASE = "https://api.github.com"
GIST_FILENAME = "adventure_tracker_state.json"
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2


class StateManagerError(Exception):
    """Base exception for state manager errors."""

    pass


class GistNotFoundError(StateManagerError):
    """Raised when the Gist is not found."""

    pass


class GistAuthError(StateManagerError):
    """Raised when authentication fails."""

    pass


class StateManager:
    """Manages shared state persistence using a GitHub Gist.

    This class provides read/write access to a JSON document stored in a
    GitHub Gist, enabling state sharing between local and CI environments.

    Attributes:
        gist_id: The GitHub Gist ID.
        token: GitHub Personal Access Token with gist scope.
    """

    def __init__(self, gist_id: str, token: str) -> None:
        """Initialize the state manager.

        Args:
            gist_id: The GitHub Gist ID.
            token: GitHub PAT with gist scope.
        """
        self._gist_id = gist_id
        self._token = token
        self._headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._state: StateData | None = None

    @property
    def gist_url(self) -> str:
        """Get the Gist API URL."""
        return f"{GITHUB_API_BASE}/gists/{self._gist_id}"

    def _make_request(
        self,
        method: str,
        url: str,
        data: dict[str, Any] | None = None,
        retries: int = MAX_RETRIES,
    ) -> requests.Response:
        """Make an HTTP request with retry logic.

        Args:
            method: HTTP method (GET, PATCH).
            url: Request URL.
            data: JSON data for the request body.
            retries: Number of retry attempts.

        Returns:
            Response object.

        Raises:
            GistAuthError: If authentication fails.
            GistNotFoundError: If the Gist is not found.
            StateManagerError: For other errors.
        """
        last_error: Exception | None = None

        for attempt in range(retries):
            try:
                if method.upper() == "GET":
                    response = requests.get(url, headers=self._headers, timeout=30)
                elif method.upper() == "PATCH":
                    response = requests.patch(
                        url, headers=self._headers, json=data, timeout=30
                    )
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                # Check for specific error codes
                if response.status_code == 401:
                    raise GistAuthError(
                        "Invalid GitHub token or insufficient permissions"
                    )
                if response.status_code == 404:
                    raise GistNotFoundError(f"Gist not found: {self._gist_id}")
                if response.status_code == 403:
                    # Rate limit or forbidden
                    raise GistAuthError(
                        f"Access forbidden: {response.json().get('message', 'Unknown')}"
                    )

                response.raise_for_status()
                return response

            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning(
                    f"Request timeout (attempt {attempt + 1}/{retries}): {e}"
                )
            except requests.exceptions.ConnectionError as e:
                last_error = e
                logger.warning(
                    f"Connection error (attempt {attempt + 1}/{retries}): {e}"
                )
            except (GistAuthError, GistNotFoundError):
                # Don't retry auth or not found errors
                raise

            if attempt < retries - 1:
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))

        raise StateManagerError(
            f"Request failed after {retries} attempts: {last_error}"
        )

    def read(self) -> StateData:
        """Read state from the GitHub Gist.

        Returns:
            StateData loaded from the Gist.

        Raises:
            StateManagerError: If reading fails.
        """
        logger.debug(f"Reading state from Gist: {self._gist_id}")

        try:
            response = self._make_request("GET", self.gist_url)
            gist_data = response.json()

            # Get the state file content
            files = gist_data.get("files", {})
            state_file = files.get(GIST_FILENAME)

            if not state_file:
                logger.info("State file not found in Gist, returning empty state")
                self._state = StateData.empty()
                return self._state

            content = state_file.get("content", "{}")

            try:
                data = json.loads(content)
                self._state = StateData.from_dict(data)
                logger.info(
                    f"Loaded state: {len(self._state.flights)} flights, "
                    f"{len(self._state.instagram)} Instagram accounts"
                )
                return self._state

            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in Gist, returning empty state: {e}")
                self._state = StateData.empty()
                return self._state

        except (GistAuthError, GistNotFoundError):
            raise
        except Exception as e:
            raise StateManagerError(f"Failed to read state: {e}") from e

    def write(self, state: StateData | None = None) -> None:
        """Write state to the GitHub Gist.

        Args:
            state: StateData to write. Uses internal state if not provided.

        Raises:
            StateManagerError: If writing fails.
        """
        if state is not None:
            self._state = state
        elif self._state is None:
            raise StateManagerError("No state to write")

        logger.debug(f"Writing state to Gist: {self._gist_id}")

        try:
            content = json.dumps(self._state.to_dict(), indent=2, default=str)

            data = {
                "files": {
                    GIST_FILENAME: {
                        "content": content,
                    }
                }
            }

            self._make_request("PATCH", self.gist_url, data=data)
            logger.info("State written successfully")

        except (GistAuthError, GistNotFoundError):
            raise
        except Exception as e:
            raise StateManagerError(f"Failed to write state: {e}") from e

    def get_state(self) -> StateData:
        """Get the current state, loading from Gist if not cached.

        Returns:
            Current StateData.
        """
        if self._state is None:
            return self.read()
        return self._state

    def get_last_flight_price(self, route_key: str) -> int | None:
        """Get the last seen price for a flight route.

        Args:
            route_key: Route key like "BAQ-MDE-2025-03-15".

        Returns:
            Last price in COP, or None if not tracked.
        """
        state = self.get_state()
        flight_state = state.get_flight_state(route_key)
        return flight_state.last_price if flight_state else None

    def set_flight_price(
        self,
        route_key: str,
        price: int,
        notified: bool = False,
    ) -> None:
        """Set the price for a flight route.

        Args:
            route_key: Route key like "BAQ-MDE-2025-03-15".
            price: Current price in COP.
            notified: Whether a notification was sent.
        """
        state = self.get_state()
        state.set_flight_state(route_key, price, notified)

    def get_seen_posts(self, username: str) -> set[str]:
        """Get set of seen post IDs for an Instagram account.

        Args:
            username: Instagram username.

        Returns:
            Set of seen post IDs.
        """
        state = self.get_state()
        ig_state = state.get_instagram_state(username)
        return ig_state.get_seen_set()

    def add_seen_post(self, username: str, post_id: str) -> None:
        """Mark an Instagram post as seen.

        Args:
            username: Instagram username.
            post_id: Post ID to mark as seen.
        """
        state = self.get_state()
        state.mark_post_seen(username, post_id)

    def is_post_seen(self, username: str, post_id: str) -> bool:
        """Check if an Instagram post has been seen.

        Args:
            username: Instagram username.
            post_id: Post ID to check.

        Returns:
            True if the post was already seen.
        """
        state = self.get_state()
        return state.is_post_seen(username, post_id)

    def save(self) -> None:
        """Save the current state to the Gist.

        This is an alias for write() with no arguments.
        """
        self.write()
