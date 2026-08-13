"""Tests for the CouncilApiClient using mocked HTTP responses."""

from unittest import mock

import pytest

from frontend.api.client import CouncilApiClient
from frontend.api.models import ApiError


class _FakeResponse:
    def __init__(self, status_code: int, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data

    def raise_for_status(self):
        import requests

        if self.status_code >= 400:
            error = requests.exceptions.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error


def _mock_request(monkeypatch, response):
    client = CouncilApiClient("https://example.com")

    def fake_request(method, url, timeout=None, **kwargs):
        assert method in ("GET", "POST")
        return response

    monkeypatch.setattr(client._session, "request", fake_request)
    return client


class TestAsk:
    def test_ask_returns_typed_response(self, monkeypatch):
        payload = {
            "question": "q",
            "final_answer": "a",
            "round1": [{"key": "m1", "success": True}],
        }
        client = _mock_request(monkeypatch, _FakeResponse(200, payload))

        result = client.ask("Should we?", debate=True)
        assert result.question == "q"
        assert result.final_answer == "a"
        assert len(result.round_one) == 1


class TestHealth:
    def test_health_ok(self, monkeypatch):
        client = _mock_request(monkeypatch, _FakeResponse(200, {"status": "ok"}))
        health = client.health_check()
        assert health.status == "ok"


class TestErrors:
    def test_connection_error_raises_api_error(self, monkeypatch):
        import requests

        client = CouncilApiClient("https://example.com")

        def fake_request(method, url, timeout=None, **kwargs):
            raise requests.exceptions.ConnectionError("boom")

        monkeypatch.setattr(client._session, "request", fake_request)

        with pytest.raises(ApiError) as exc_info:
            client.ask("q")
        assert "Connection refused" in str(exc_info.value)

    def test_timeout_raises_api_error(self, monkeypatch):
        import requests

        client = CouncilApiClient("https://example.com")

        def fake_request(method, url, timeout=None, **kwargs):
            raise requests.exceptions.Timeout("slow")

        monkeypatch.setattr(client._session, "request", fake_request)

        with pytest.raises(ApiError) as exc_info:
            client.ask("q")
        assert "timed out" in str(exc_info.value)

    def test_http_error_includes_detail(self, monkeypatch):
        import requests

        client = CouncilApiClient("https://example.com")

        def fake_request(method, url, timeout=None, **kwargs):
            error = requests.exceptions.HTTPError("HTTP 500")
            error.response = _FakeResponse(500, {"detail": "boom detail"})
            raise error

        monkeypatch.setattr(client._session, "request", fake_request)

        with pytest.raises(ApiError) as exc_info:
            client.ask("q")
        assert "boom detail" in str(exc_info.value)
        assert exc_info.value.status_code == 500
