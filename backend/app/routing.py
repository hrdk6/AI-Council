"""Model routing: which models to try for a role, and shared model health across concurrent calls.

Each role has an ordered list of candidate models: its configured model, then the rest of its
provider's fallback chain, then any cross-provider ``BACKUP_MODELS`` whose provider has an API key.

A process-wide registry remembers rate limits and outages. When one council member is throttled,
the members running alongside it skip that model straight away instead of each collecting a 429.
"""

import os
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import openai

from .clients import PROVIDER_ENV_KEYS
from .config import GROQ_FALLBACK_CHAIN, VALID_PROVIDERS, ModelConfig, cfg

# How long a model or provider is skipped after each kind of failure.
AUTH_COOLDOWN_S = 60.0          # credentials rejected: the whole provider is skipped
MODEL_GONE_COOLDOWN_S = 600.0   # model not found / decommissioned
TRANSIENT_COOLDOWN_S = 20.0     # repeated 5xx, timeouts, or empty answers
FAILURES_BEFORE_COOLDOWN = 2
MAX_RATE_LIMIT_COOLDOWN_S = 3600.0  # daily token limits can ask for hours; don't trust longer hints

# Groq phrases retry hints as "try again in 4.25s", "1m2.5s", or "2h3m".
_TRY_AGAIN_RE = re.compile(
    r"try again in\s+(?:(?P<h>\d+(?:\.\d+)?)h)?\s*(?:(?P<m>\d+(?:\.\d+)?)m(?!s))?\s*(?:(?P<s>\d+(?:\.\d+)?)s)?",
    re.IGNORECASE,
)
_RETRIABLE_STATUS_CODES = frozenset({408, 409, 500, 502, 503, 504})
_TRANSIENT_MARKERS = ("timeout", "timed out", "overloaded", "connection", "temporarily")

REASON_TEXT = {
    "rate_limit": "rate-limited",
    "auth": "rejected the API key",
    "not_found": "unavailable",
    "bad_request": "rejected the request",
    "transient": "unavailable",
    "empty": "returned an empty answer",
}


@dataclass(frozen=True)
class ModelRef:
    provider: str
    model: str

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


def parse_model_ref(value: str) -> ModelRef:
    """Parse ``provider:model`` (the model part may itself contain colons, e.g. OpenRouter's ``:free``)."""
    provider, separator, model = value.strip().partition(":")
    if not separator or provider not in VALID_PROVIDERS or not model.strip():
        raise ValueError(
            f"Invalid backup model '{value}'. Use provider:model with a provider from {sorted(VALID_PROVIDERS)}."
        )
    return ModelRef(provider, model.strip())


def provider_has_key(provider: str) -> bool:
    return bool(os.getenv(PROVIDER_ENV_KEYS.get(provider, "")))


def candidates_for(model_cfg: ModelConfig) -> list[ModelRef]:
    """Ordered, de-duplicated models to try for a role."""
    ordered = [ModelRef(model_cfg.provider, model_cfg.model)]
    if model_cfg.provider == "groq":
        ordered += [ModelRef("groq", model) for model in GROQ_FALLBACK_CHAIN]
    for entry in cfg.backup_models:
        ref = parse_model_ref(entry)
        if provider_has_key(ref.provider):
            ordered.append(ref)
    return list(dict.fromkeys(ordered))


def retry_after_seconds(error: BaseException) -> float | None:
    """The provider's own retry hint, from the Retry-After header or the error message."""
    if isinstance(error, openai.APIStatusError):
        header = error.response.headers.get("retry-after")
        if header:
            try:
                return max(0.0, float(header))
            except ValueError:
                pass
    match = _TRY_AGAIN_RE.search(str(error))
    if match and any(match.group(unit) for unit in ("h", "m", "s")):
        hours, minutes, seconds = (float(match.group(unit) or 0) for unit in ("h", "m", "s"))
        return hours * 3600 + minutes * 60 + seconds
    return None


def status_code_of(error: BaseException | None) -> int | None:
    while error is not None:
        if isinstance(error, openai.APIStatusError):
            return error.status_code
        error = error.__cause__
    return None


def classify_error(error: BaseException) -> str:
    """Bucket a failure: rate_limit, auth, not_found, bad_request, transient, or empty."""
    from .council import EmptyResponseError  # local import: council imports this module

    if isinstance(error, EmptyResponseError):
        return "empty"
    if isinstance(error, openai.APIConnectionError):  # includes timeouts
        return "transient"
    status = status_code_of(error)
    text = str(error).lower()
    if status == 429 or "rate limit" in text or "rate_limit" in text:
        return "rate_limit"
    if status in (401, 403) or "invalid api key" in text or "missing api key" in text:
        return "auth"
    if status == 404 or ("model" in text and ("not found" in text or "decommissioned" in text)):
        return "not_found"
    if status in (400, 413, 422):
        return "bad_request"
    if status in _RETRIABLE_STATUS_CODES or any(marker in text for marker in _TRANSIENT_MARKERS):
        return "transient"
    return "bad_request" if status is not None else "transient"


class ModelHealth:
    """Remembers which models and providers to skip, and until when. Shared by every request."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._models: dict[ModelRef, tuple[float, str]] = {}
        self._providers: dict[str, tuple[float, str]] = {}
        self._failures: dict[ModelRef, int] = {}

    def reset(self) -> None:
        self._models.clear()
        self._providers.clear()
        self._failures.clear()

    def _extend(self, table: dict, key, seconds: float, reason: str) -> None:
        until = self._clock() + seconds
        current = table.get(key)
        if current is None or current[0] < until:
            table[key] = (until, reason)

    def rate_limited(self, ref: ModelRef, seconds: float) -> None:
        self._extend(self._models, ref, min(seconds, MAX_RATE_LIMIT_COOLDOWN_S), "rate_limit")

    def unavailable(self, ref: ModelRef, seconds: float, reason: str) -> None:
        self._extend(self._models, ref, seconds, reason)

    def provider_unavailable(self, provider: str, seconds: float, reason: str) -> None:
        self._extend(self._providers, provider, seconds, reason)

    def failed(self, ref: ModelRef, reason: str) -> None:
        """Count a transient failure; repeated ones bench the model briefly."""
        self._failures[ref] = self._failures.get(ref, 0) + 1
        if self._failures[ref] >= FAILURES_BEFORE_COOLDOWN:
            self._extend(self._models, ref, TRANSIENT_COOLDOWN_S, reason)
            self._failures[ref] = 0

    def succeeded(self, ref: ModelRef) -> None:
        self._failures.pop(ref, None)
        self._models.pop(ref, None)

    def cooldown(self, ref: ModelRef) -> tuple[float, str | None]:
        """Seconds until the model may be used again (0 when usable), and why it's paused."""
        now = self._clock()
        remaining, reason = 0.0, None
        for entry in (self._models.get(ref), self._providers.get(ref.provider)):
            if entry and entry[0] - now > remaining:
                remaining, reason = entry[0] - now, entry[1]
        return remaining, reason

    def snapshot(self, refs: Iterable[ModelRef]) -> list[dict]:
        rows = []
        for ref in dict.fromkeys(refs):
            remaining, reason = self.cooldown(ref)
            rows.append({
                "provider": ref.provider,
                "model": ref.model,
                "key_configured": provider_has_key(ref.provider),
                "status": "ok" if remaining == 0 else "paused",
                "reason": REASON_TEXT.get(reason or "", reason),
                "retry_in_s": round(remaining, 1) if remaining else 0,
            })
        return rows


MODEL_HEALTH = ModelHealth()
