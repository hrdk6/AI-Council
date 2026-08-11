"""
Every provider used in this project exposes an OpenAI-compatible
`/chat/completions` endpoint, so we use ONE client class (openai.AsyncOpenAI)
pointed at different base_urls instead of maintaining separate SDKs per
provider. This keeps council.py and ingestion.py provider-agnostic.
"""

import logging
import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv
from openai import AsyncOpenAI

logger = logging.getLogger("council")

# Load the .env file from the project root
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

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


@lru_cache(maxsize=None)
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
        max_retries=0,  # disable the SDK's own internal auto-retry-on-5xx —
        # we already handle retries/timeouts ourselves in council.py, and the
        # SDK's internal retries were stacking silently on top of our timeout,
        # turning a 30s cap into 60s+ waits when a provider returned 503.
    )


def check_provider_keys_present() -> list[str]:
    """Return the list of providers referenced by config.py that are missing
    their API key. Called once at startup so a misconfigured deployment fails
    fast and loud instead of surfacing as a mysterious 502 on first request."""
    missing = []
    for provider, env_key in PROVIDER_ENV_KEYS.items():
        if not os.getenv(env_key):
            missing.append(f"{provider} ({env_key})")
    return missing