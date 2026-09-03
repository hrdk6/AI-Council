"""API client with retry logic and typed requests."""

import json
import logging
from collections.abc import Callable
from typing import Any, Self
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from frontend.api.models import (
    ApiError,
    CouncilResponse,
    HealthResponse,
)
from frontend.constants import (
    API_ASK_ENDPOINT,
    API_HEALTH_ENDPOINT,
    API_HISTORY_ENDPOINT,
    API_METRICS_ENDPOINT,
    API_PROVIDERS_ENDPOINT,
    API_STREAM_ENDPOINT,
    DEFAULT_TIMEOUT_CONNECT,
    DEFAULT_TIMEOUT_READ,
)

logger = logging.getLogger(__name__)


class CouncilApiClient:
    """Typed client for the AI Council backend API."""

    def __init__(self, base_url: str, timeout: tuple[int, int] | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout or (DEFAULT_TIMEOUT_CONNECT, DEFAULT_TIMEOUT_READ)
        self._session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a session with retry strategy."""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> requests.Response:
        """Make an HTTP request with error handling."""
        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        try:
            response = self._session.request(
                method=method,
                url=url,
                timeout=self.timeout,
                **kwargs,
            )
            response.raise_for_status()
            return response
        except requests.exceptions.ConnectionError as e:
            logger.error("Connection error to %s: %s", self.base_url, e)
            raise ApiError(
                f"Connection refused at {self.base_url}. Verify the backend service is running.",
                status_code=0,
            ) from e
        except requests.exceptions.Timeout as e:
            logger.error("Request timeout to %s", self.base_url)
            raise ApiError(
                f"Request timed out after {self.timeout[1]}s. The council did not respond in time.",
                status_code=0,
            ) from e
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else 0
            detail = ""
            try:
                detail = e.response.json().get("detail", e.response.text)
            except (ValueError, AttributeError):
                detail = getattr(e.response, "text", str(e))
            logger.error("HTTP error %s: %s", status, detail)
            raise ApiError(f"Error {status}: {detail}", status_code=status, detail=detail) from e
        except requests.exceptions.RequestException as e:
            logger.error("Request failed: %s", e)
            raise ApiError(f"Unexpected error: {e}") from e

    def health_check(self) -> HealthResponse:
        """Check backend health."""
        response = self._request("GET", API_HEALTH_ENDPOINT)
        return HealthResponse(**response.json())

    def ask(self, prompt: str, debate: bool = True, sources: str = "") -> CouncilResponse:
        """Submit a question to the council."""
        # Backend uses Form(...) fields — must send multipart/form-data, not JSON.
        form_data = {
            "prompt": prompt,
            "debate": str(debate).lower(),
            "sources": sources,
        }
        response = self._request("POST", API_ASK_ENDPOINT, data=form_data)
        return CouncilResponse(**response.json())

    def ask_stream(
        self, prompt: str, debate: bool = True, sources: str = "", on_event: Callable[[str, dict], None] | None = None,
    ) -> CouncilResponse:
        """Submit a decision and surface server-sent progress events."""
        url = urljoin(self.base_url + "/", API_STREAM_ENDPOINT.lstrip("/"))
        try:
            with self._session.post(
                url, data={"prompt": prompt, "debate": str(debate).lower(), "sources": sources},
                timeout=self.timeout, stream=True,
            ) as response:
                response.raise_for_status()
                event_name = "message"
                for raw_line in response.iter_lines(decode_unicode=True):
                    line = raw_line or ""
                    if line.startswith("event: "):
                        event_name = line[7:]
                    elif line.startswith("data: "):
                        payload = json.loads(line[6:])
                        if on_event:
                            on_event(event_name, payload)
                        if event_name == "complete":
                            return CouncilResponse(**payload)
                        if event_name == "error":
                            raise ApiError(payload.get("detail", "Council request failed."))
        except requests.exceptions.RequestException as error:
            raise ApiError(f"Unable to stream council progress: {error}") from error
        raise ApiError("Council stream ended before returning a result.")

    def history(self) -> list[dict[str, Any]]:
        return self._request("GET", API_HISTORY_ENDPOINT).json()

    def providers(self) -> dict[str, Any]:
        return self._request("GET", API_PROVIDERS_ENDPOINT).json()

    def metrics(self) -> dict[str, Any]:
        return self._request("GET", API_METRICS_ENDPOINT).json()

    def save_feedback(self, decision_id: str, rating: int | None, outcome_note: str) -> None:
        self._request("POST", f"{API_HISTORY_ENDPOINT}/{decision_id}/feedback", json={
            "rating": rating, "outcome_note": outcome_note,
        })

    def close(self) -> None:
        """Close the underlying session."""
        self._session.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
