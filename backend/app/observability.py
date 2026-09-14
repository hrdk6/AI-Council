"""Observability: structured logging, metrics, and request tracing."""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Self

# Correlation ID of the HTTP request being handled; "-" outside a request.
REQUEST_ID: ContextVar[str] = ContextVar("request_id", default="-")

_EXTRA_FIELDS = ("request_id", "provider", "tokens", "latency_s", "success", "method", "path", "status", "duration_ms")


class RequestIdFilter(logging.Filter):
    """Attach the current HTTP request ID to every log record that lacks one."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = REQUEST_ID.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for name in _EXTRA_FIELDS:
            if hasattr(record, name):
                log_obj[name] = getattr(record, name)
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)


def setup_logging(config=None) -> None:
    """Configure application logging. Call once at application startup."""
    if config is None:
        from .config import cfg
    else:
        cfg = config
    level = getattr(logging, cfg.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    if cfg.environment in ("production", "staging"):
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(request_id)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        ))
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
    # Access logs are emitted by our own middleware with request IDs; avoid duplicates.
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False


# Logger instance - setup_logging() must be called before use
logger = logging.getLogger("council")


@dataclass
class Metrics:
    started_at: float = field(default_factory=time.time)
    total_requests: int = 0
    total_request_failures: int = 0
    total_cache_hits: int = 0
    total_tokens: int = 0
    total_llm_calls: int = 0
    total_llm_failures: int = 0
    total_latency_s: float = 0.0
    provider_calls: dict[str, int] = field(default_factory=dict)
    provider_failures: dict[str, int] = field(default_factory=dict)
    provider_tokens: dict[str, int] = field(default_factory=dict)
    http_responses: dict[str, int] = field(default_factory=dict)

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

    def record_http_response(self, status_code: int) -> None:
        bucket = f"{status_code // 100}xx"
        self.http_responses[bucket] = self.http_responses.get(bucket, 0) + 1

    def snapshot(self) -> dict:
        avg_latency = round(self.total_latency_s / self.total_llm_calls, 3) if self.total_llm_calls else 0.0
        return {
            "uptime_s": round(time.time() - self.started_at, 1),
            "requests": {
                "total": self.total_requests,
                "failures": self.total_request_failures,
                "cache_hits": self.total_cache_hits,
                "cache_hit_rate": round(self.total_cache_hits / self.total_requests, 3) if self.total_requests else 0.0,
            },
            "http_responses": dict(self.http_responses),
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
    """Context manager that logs elapsed time for a named pipeline stage."""

    def __init__(self, request_id: str, label: str):
        self.request_id = request_id
        self.label = label
        self._start: float = 0.0

    def __enter__(self) -> Self:
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        elapsed = time.perf_counter() - self._start
        extra = {"request_id": self.request_id}
        if exc:
            logger.warning("%s failed after %.2fs: %s", self.label, elapsed, exc, extra=extra)
        else:
            logger.info("%s completed in %.2fs", self.label, elapsed, extra=extra)
