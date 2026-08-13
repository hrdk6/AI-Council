"""Constants and configuration for the AI Council frontend."""

from typing import Final

# Session state keys
SESSION_BACKEND_URL: Final[str] = "backend_url"
SESSION_COUNCIL_RESULT: Final[str] = "council_result"
SESSION_COUNCIL_ERROR: Final[str] = "council_error"
SESSION_COUNCIL_PROMPT: Final[str] = "council_prompt"

# API endpoints
API_ASK_ENDPOINT: Final[str] = "/ask"
API_HEALTH_ENDPOINT: Final[str] = "/health"

# Request defaults
DEFAULT_TIMEOUT_CONNECT: Final[int] = 10
DEFAULT_TIMEOUT_READ: Final[int] = 240
DEFAULT_BACKEND_URL: Final[str] = "https://ai-council-t8zv.onrender.com"

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