import logging
import os
from collections.abc import Iterable
from functools import cache
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

logger = logging.getLogger("council")


# Prefer backend/.env and support a root-level .env for container deployments.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(_BACKEND_DIR / ".env")
load_dotenv(_BACKEND_DIR.parent / ".env")

PROVIDER_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "nvidia_nim": "https://integrate.api.nvidia.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openrouter": "https://openrouter.ai/api/v1",
}

PROVIDER_ENV_KEYS = {
    "groq": "GROQ_API_KEY",
    "nvidia_nim": "NVIDIA_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


@cache
def get_client(provider: str) -> AsyncOpenAI:
    if provider not in PROVIDER_BASE_URLS:
        raise ValueError(f"Unknown provider '{provider}'. Known: {list(PROVIDER_BASE_URLS)}")

    env_key = PROVIDER_ENV_KEYS[provider]
    api_key = os.getenv(env_key)
    if not api_key:
        raise RuntimeError(
            f"Missing API key for provider '{provider}'. "
            f"Set {env_key} in your .env file (see .env.example)."
        )

    return AsyncOpenAI(
        base_url=PROVIDER_BASE_URLS[provider],
        api_key=api_key,
        max_retries=0,
        timeout=60.0,  # Default timeout for all providers
    )


async def close_clients() -> None:
    """Close pooled HTTP connections for every client created so far."""
    for provider in PROVIDER_BASE_URLS:
        try:
            if os.getenv(PROVIDER_ENV_KEYS[provider]):
                await get_client(provider).close()
        except Exception:
            logger.debug("Failed to close %s client", provider, exc_info=True)
    get_client.cache_clear()


def check_provider_keys_present(providers: Iterable[str] | None = None) -> list[str]:
    """Return ``"provider (ENV_KEY)"`` entries for providers whose API key is missing.

    Pass ``providers`` to check only the providers actually in use.
    """
    selected = PROVIDER_ENV_KEYS.keys() if providers is None else providers
    missing = []
    for provider in selected:
        env_key = PROVIDER_ENV_KEYS[provider]
        if not os.getenv(env_key):
            missing.append(f"{provider} ({env_key})")
    return missing
