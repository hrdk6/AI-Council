"""Tests for clients module."""

import os
from unittest.mock import patch

import pytest

from app.clients import (
    PROVIDER_BASE_URLS,
    check_provider_keys_present,
    get_client,
)


def test_get_client_unknown_provider():
    with pytest.raises(ValueError, match="Unknown provider"):
        get_client("unknown_provider")


def test_get_client_missing_key():
    with patch.dict(os.environ, {}, clear=True), pytest.raises(RuntimeError, match="Missing API key"):
        get_client("groq")


def test_get_client_returns_async_openai():
    with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
        client = get_client("groq")
        from openai import AsyncOpenAI
        assert isinstance(client, AsyncOpenAI)
        assert str(client.base_url).rstrip("/") == PROVIDER_BASE_URLS["groq"]
        assert client.api_key == "test-key"


def test_check_provider_keys_present_all_missing():
    with patch.dict(os.environ, {}, clear=True):
        missing = check_provider_keys_present()
        assert len(missing) == 4
        assert "groq (GROQ_API_KEY)" in missing
        assert "nvidia_nim (NVIDIA_API_KEY)" in missing
        assert "gemini (GEMINI_API_KEY)" in missing
        assert "openrouter (OPENROUTER_API_KEY)" in missing


def test_check_provider_keys_present_some_present():
    with patch.dict(os.environ, {"GROQ_API_KEY": "test", "GEMINI_API_KEY": "test"}, clear=True):
        missing = check_provider_keys_present()
        assert len(missing) == 2
        assert "groq (GROQ_API_KEY)" not in missing
        assert "gemini (GEMINI_API_KEY)" not in missing
        assert "nvidia_nim (NVIDIA_API_KEY)" in missing
        assert "openrouter (OPENROUTER_API_KEY)" in missing