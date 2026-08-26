"""Constants and configuration for the AI Council frontend."""

import os
import re
from typing import Final

# Session state keys
SESSION_BACKEND_URL: Final[str] = "backend_url"
SESSION_COUNCIL_RESULT: Final[str] = "council_result"
SESSION_COUNCIL_ERROR: Final[str] = "council_error"
SESSION_COUNCIL_PROMPT: Final[str] = "council_prompt"

# API endpoints (v1)
API_ASK_ENDPOINT: Final[str] = "/v1/ask"
API_HEALTH_ENDPOINT: Final[str] = "/v1/health"
API_STREAM_ENDPOINT: Final[str] = "/v1/ask/stream"
API_HISTORY_ENDPOINT: Final[str] = "/v1/history"
API_PROVIDERS_ENDPOINT: Final[str] = "/v1/providers"
API_METRICS_ENDPOINT: Final[str] = "/v1/metrics"

# Request defaults
DEFAULT_TIMEOUT_CONNECT: Final[int] = int(os.getenv("FRONTEND_TIMEOUT_CONNECT", "10"))
DEFAULT_TIMEOUT_READ: Final[int] = int(os.getenv("FRONTEND_TIMEOUT_READ", "240"))
DEFAULT_BACKEND_URL: Final[str] = os.getenv("DEFAULT_BACKEND_URL", "http://localhost:8000")
ALLOWED_BACKEND_DOMAINS: Final[tuple[str, ...]] = tuple(
    d.strip() for d in os.getenv("ALLOWED_BACKEND_DOMAINS", "localhost").split(",")
)

# Directive section headings (must match backend output)
DIRECTIVE_HEADINGS: Final[tuple[str, ...]] = (
    "Recommendation",
    "Why this wins",
    "Execution plan",
    "Guardrails and reversal triggers",
    "Confidence and key uncertainty",
)

# Regex for parsing directive sections
DIRECTIVE_HEADING_PATTERN: Final[str] = (
    r"^(Recommendation|Why this wins|Execution plan|Guardrails and reversal triggers|Confidence and key uncertainty)\s*:?\s*$"
)

# UI constants
MAX_ANIMATION_DELAY: Final[float] = 0.42
ANIMATION_DELAY_STEP: Final[float] = 0.07
MEMBER_CARDS_PER_ROW: Final[int] = 3

# Export
EXPORT_FILENAME: Final[str] = "ai-council-decision-brief.txt"
EXPORT_MIME_TYPE: Final[str] = "text/plain"

# Fallback strings
FALLBACK_ROLE_NAME: Final[str] = "Council member"
FALLBACK_PROVIDER: Final[str] = "Provider"
FALLBACK_MODEL: Final[str] = "Model"
FALLBACK_CONTENT: Final[str] = "No analysis returned."
FALLBACK_REVISED_CONTENT: Final[str] = "No final position returned."
FALLBACK_ERROR: Final[str] = "This member could not complete its analysis."
FALLBACK_REVISED_ERROR: Final[str] = "This member could not revise its position."
FALLBACK_QUESTION: Final[str] = "Not recorded"
FALLBACK_CHARTER: Final[str] = "Not returned by the backend."
FALLBACK_FINAL_ANSWER: Final[str] = "No final answer was returned."
FALLBACK_AUDIT: Final[str] = "No individual deliberation record was returned for this request."

# URL validation
_URL_REGEX = re.compile(
    r"^https?://"  
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  
    r"localhost|"  
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  
    r"(?::\d+)?"  
    r"(?:/?|[/?]\S+)$", re.IGNORECASE
)

_PRIVATE_IP_REGEX = re.compile(
    r"^(?:10\.|172\.(?:1[6-9]|2[0-9]|3[0-1])\.|192\.168\.|127\.|169\.254\.|::1$|fe80::)"
)


def validate_backend_url(url: str) -> tuple[bool, str]:
    """Validate backend URL for SSRF protection."""
    if not url:
        return False, "Backend URL is required."
    if not _URL_REGEX.match(url):
        return False, "Invalid URL format. Must be a valid HTTP/HTTPS URL."

    # Check against allowed domains first — explicitly allowed hosts bypass the
    # private-IP block so that local development (localhost) works out of the box.
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        is_allowed_domain = any(
            hostname == d or hostname.endswith("." + d) for d in ALLOWED_BACKEND_DOMAINS
        )
        if not is_allowed_domain:
            # Only block private IPs for hosts that are NOT in the allow-list.
            if _PRIVATE_IP_REGEX.search(url):
                return False, "Private/local IP addresses are not allowed."
            return False, f"Backend domain not allowed. Allowed: {', '.join(ALLOWED_BACKEND_DOMAINS)}"
    except Exception:
        return False, "Invalid URL format."

    return True, ""
