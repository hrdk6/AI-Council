\
\
\
\
\
\
\
\
\


import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("council")


@dataclass
class Metrics:
    total_requests: int = 0
    total_request_failures: int = 0
    total_cache_hits: int = 0
    total_tokens: int = 0
    total_llm_calls: int = 0
    total_llm_failures: int = 0
    total_latency_s: float = 0.0
    provider_calls: dict = field(default_factory=dict)
    provider_failures: dict = field(default_factory=dict)
    provider_tokens: dict = field(default_factory=dict)

    def record_llm_call(self, provider: str, tokens: int, latency_s: float, success: bool) -> None:
        self.total_llm_calls += 1
        self.total_tokens += tokens
        self.total_latency_s += latency_s
        self.provider_calls[provider] = self.provider_calls.get(provider, 0) + 1
        self.provider_tokens[provider] = self.provider_tokens.get(provider, 0) + tokens
        if not success:
            self.total_llm_failures += 1
            self.provider_failures[provider] = self.provider_failures.get(provider, 0) + 1

    def record_request(self, success: bool, cached: bool) -> None:
        self.total_requests += 1
        if cached:
            self.total_cache_hits += 1
        if not success:
            self.total_request_failures += 1

    def snapshot(self) -> dict:
        avg_latency = round(self.total_latency_s / self.total_llm_calls, 3) if self.total_llm_calls else 0.0
        return {
            "requests": {
                "total": self.total_requests,
                "failures": self.total_request_failures,
                "cache_hits": self.total_cache_hits,
                "cache_hit_rate": round(self.total_cache_hits / self.total_requests, 3) if self.total_requests else 0.0,
            },
            "llm_calls": {
                "total": self.total_llm_calls,
                "failures": self.total_llm_failures,
                "total_tokens": self.total_tokens,
                "avg_latency_s": avg_latency,
                "by_provider": {
                    provider: {
                        "calls": self.provider_calls.get(provider, 0),
                        "failures": self.provider_failures.get(provider, 0),
                        "tokens": self.provider_tokens.get(provider, 0),
                    }
                    for provider in self.provider_calls
                },
            },
        }


METRICS = Metrics()


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


class StageTimer:


    def __init__(self, request_id: str, label: str):
        self.request_id = request_id
        self.label = label
        self._start: Optional[float] = None

    def __enter__(self) -> "StageTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        elapsed = time.perf_counter() - (self._start or time.perf_counter())
        if exc:
            logger.warning("[%s] %s failed after %.2fs: %s", self.request_id, self.label, elapsed, exc)
        else:
            logger.info("[%s] %s completed in %.2fs", self.request_id, self.label, elapsed)
