"""API client with retry logic and typed requests."""

import logging
import time
from typing import Any
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from frontend.api.models import (
    AskRequest,
    CouncilResponse,
    HealthResponse,
    ApiError,
)
from frontend.constants import (
    API_ASK_ENDPOINT,
    API_HEALTH_ENDPOINT,
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

    def ask(self, prompt: str, debate: bool = True) -> CouncilResponse:
        """Submit a question to the council."""
        request = AskRequest(prompt=prompt, debate=debate)
        response = self._request("POST", API_ASK_ENDPOINT, data=request.model_dump())
        return CouncilResponse(**response.json())

    def close(self) -> None:
        """Close the underlying session."""
        self._session.close()

    def __enter__(self) -> "CouncilApiClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()