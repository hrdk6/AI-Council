import logging
import re
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
# Prefer backend/.env (the documented local setup), then fall back to root/.env.
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(PROJECT_DIR / ".env")

from .clients import check_provider_keys_present
from .config import cfg
from .config import CHAIRMAN, DECISION_ARCHITECT, EXPERT_LIBRARY
from .council import run_council
from .history import list_decisions, save_decision, save_feedback
from .observability import METRICS, setup_logging
from .schemas import CouncilResult, DecisionRecord, FeedbackInput, HealthResponse

setup_logging()
logger = logging.getLogger("main")

RATE_LIMIT = f"{cfg.rate_limit_requests}/{cfg.rate_limit_window}second"
limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT])

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:previous|above|all)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(?:previous|above|all)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+(?:now|an?)\s+(?:hacker|admin|root)", re.IGNORECASE),
    re.compile(r"<\|im_start\|>|<\|im_end\|>", re.IGNORECASE),
    re.compile(r"assistant\s*:\s*\|>", re.IGNORECASE),
    re.compile(r"<\|.*?\|>", re.IGNORECASE),  # Catch other special tokens
    re.compile(r"\[INST\].*?\[/INST\]", re.IGNORECASE | re.DOTALL),  # Llama-style instruction tags
    re.compile(r"<<SYS>>.*?<</SYS>>", re.IGNORECASE | re.DOTALL),  # System prompt markers
    re.compile(r"###\s*(?:Instruction|System|Human|Assistant)\s*:", re.IGNORECASE),  # Common prompt formats
    re.compile(r"forget\s+(?:everything|all|previous)", re.IGNORECASE),
    re.compile(r"pretend\s+(?:to be|you are)", re.IGNORECASE),
    re.compile(r"roleplay\s+as", re.IGNORECASE),
    re.compile(r"act\s+as\s+(?:a|an)\s+(?:hacker|admin|root|developer)", re.IGNORECASE),
]

def sanitize_prompt(prompt: str) -> str:
    if not prompt or not prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
    
    # Remove control characters except newlines and tabs
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", prompt)
    # Limit repeated characters (potential DoS)
    cleaned = re.sub(r"(.)\1{100,}", r"\1" * 100, cleaned)
    # Limit excessive newlines
    cleaned = re.sub(r"\n{10,}", "\n" * 10, cleaned)
    
    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(cleaned):
            logger.warning("Potential prompt injection detected: %s", pattern.pattern)
            raise HTTPException(status_code=400, detail="Invalid prompt: potential injection attempt detected.")
    return cleaned.strip()


@asynccontextmanager
async def lifespan(app: FastAPI):
    missing_keys = check_provider_keys_present()
    if missing_keys:
        logger.warning("Missing provider API keys: %s", missing_keys)
    else:
        logger.info("All provider API keys configured.")
    yield

app = FastAPI(title="AI Council", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

MAX_PROMPT_CHARS = cfg.max_prompt_chars


@app.get("/v1/health", response_model=HealthResponse)
async def health():
    missing_keys = check_provider_keys_present()
    status_val = "ok" if not missing_keys else "degraded"
    return HealthResponse(status=status_val, version="1.0.0", providers_missing=missing_keys)


@app.get("/v1/metrics")
async def metrics(request: Request):
    # Require API key for metrics in production
    if cfg.api_key and cfg.environment == "production":
        api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if api_key != cfg.api_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key.")
    return METRICS.snapshot()


@app.get("/v1/providers")
async def providers():
    """Expose safe provider readiness information; API keys are never returned."""
    missing = {item.split(" ", 1)[0] for item in check_provider_keys_present()}
    return {
        "providers": [
            {"name": name, "configured": name not in missing}
            for name in ("groq", "nvidia_nim", "gemini", "openrouter")
        ],
        "roles": [
            {"role": item.role_name, "provider": item.provider, "model": item.model}
            for item in [*EXPERT_LIBRARY.values(), DECISION_ARCHITECT, CHAIRMAN]
        ],
    }


@app.get("/v1/history", response_model=list[DecisionRecord])
async def history(limit: int = 30):
    return list_decisions(max(1, min(limit, 100)))


@app.post("/v1/history/{decision_id}/feedback")
async def feedback(decision_id: str, feedback_input: FeedbackInput):
    if not save_feedback(decision_id, feedback_input.rating, feedback_input.outcome_note):
        raise HTTPException(status_code=404, detail="Decision not found.")
    return {"status": "saved"}


def _parse_sources(raw_sources: str) -> list[str]:
    sources = [line.strip() for line in raw_sources.splitlines() if line.strip()]
    if len(sources) > 10:
        raise HTTPException(status_code=400, detail="Add up to 10 source links.")
    for source in sources:
        parsed = urlparse(source)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=400, detail="Each source must be a valid HTTP(S) URL.")
    return sources


async def _run_and_save(prompt: str, debate: bool, sources: list[str], on_event=None) -> CouncilResult:
    source_context = None
    if sources:
        source_context = (
            "USER-SUPPLIED SOURCES (cite only when directly supported; do not claim to have read a link):\n"
            + "\n".join(f"- {source}" for source in sources)
        )
    result = await run_council(prompt, context=source_context, debate=debate, on_event=on_event)
    result.sources = sources
    save_decision(result)
    return result


@app.post("/v1/ask", response_model=CouncilResult)
@limiter.limit(RATE_LIMIT)
async def ask(
    request: Request,
    prompt: str = Form(...),
    debate: bool = Form(False),
    sources: str = Form(""),
):
    # API key verification
    if cfg.api_key:
        api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if api_key != cfg.api_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key.")
    
    if len(prompt) > MAX_PROMPT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Prompt is too long. Limit it to {MAX_PROMPT_CHARS:,} characters.",
        )

    prompt = sanitize_prompt(prompt)

    parsed_sources = _parse_sources(sources)

    try:
        result = await _run_and_save(prompt, debate, parsed_sources)
    except Exception as e:
        logger.exception("Council run failed")
        detail = str(e) if cfg.environment == "development" else "Internal server error."
        raise HTTPException(status_code=502, detail=detail)

    return result


@app.post("/v1/ask/stream")
@limiter.limit(RATE_LIMIT)
async def ask_stream(
    request: Request, prompt: str = Form(...), debate: bool = Form(False), sources: str = Form(""),
):
    """Stream lifecycle events as SSE so clients can show deliberation progress."""
    if cfg.api_key and (request.headers.get("X-API-Key") != cfg.api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key.")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Prompt is too long. Limit it to {MAX_PROMPT_CHARS:,} characters.",
        )
    prompt = sanitize_prompt(prompt)
    parsed_sources = _parse_sources(sources)

    async def event_stream():
        queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()

        async def on_event(event: str, data: dict) -> None:
            await queue.put((event, data))

        task = asyncio.create_task(_run_and_save(prompt, debate, parsed_sources, on_event))
        try:
            while not task.done() or not queue.empty():
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=0.25)
                    yield f"event: {event}\ndata: {json.dumps(data)}\n\n"
                except TimeoutError:
                    continue
            result = await task
            yield f"event: complete\ndata: {result.model_dump_json()}\n\n"
        except Exception as error:
            logger.exception("Council stream failed")
            yield f"event: error\ndata: {json.dumps({'detail': str(error)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
