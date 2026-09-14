import asyncio
import contextlib
import hmac
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Security, UploadFile, status
from fastapi import Path as PathParam
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
# Prefer backend/.env (the documented local setup), then fall back to root/.env.
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(PROJECT_DIR / ".env")

from . import __version__
from .attachments import (
    AttachmentError,
    build_evidence_context,
    max_bytes,
    process_attachments,
    sanitize_filename,
    validate_upload,
)
from .clients import PROVIDER_ENV_KEYS, check_provider_keys_present, close_clients
from .config import CHAIRMAN, EXPERT_LIBRARY, all_role_configs, cfg, providers_in_use
from .council import CouncilUnavailableError, run_council
from .history import check_database, get_decision, list_decisions, save_decision, save_feedback
from .observability import METRICS, REQUEST_ID, new_request_id, setup_logging
from .routing import MODEL_HEALTH, ModelRef, candidates_for
from .schemas import CouncilResult, DecisionRecord, FeedbackInput, HealthResponse

setup_logging()
logger = logging.getLogger("main")
access_logger = logging.getLogger("access")

RATE_LIMIT = f"{cfg.rate_limit_requests}/{cfg.rate_limit_window}second"
limiter = Limiter(key_func=get_remote_address)

MAX_PROMPT_CHARS = cfg.max_prompt_chars
MAX_SOURCES = 10
GENERIC_FAILURE_DETAIL = "The council could not complete this request. Please retry shortly."

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:previous|above|all)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(?:previous|above|all)\s+instructions", re.IGNORECASE),
    # Only flag attempts to extract or override the system prompt, not questions about writing one.
    re.compile(r"(?:reveal|show|print|repeat|output|leak|ignore|override)\s+(?:me\s+)?(?:your|the)\s+system\s+prompt",
               re.IGNORECASE),
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

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "frame-ancestors 'none'",
}
UI_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
# Every upload at its maximum size, plus room for the form fields.
MAX_REQUEST_BYTES = cfg.max_upload_files * max(max_bytes("pdf"), max_bytes("image")) + 1_048_576
REQUEST_TOO_LARGE_DETAIL = "The upload is too large. Remove some files and try again."
_INCOMING_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._-]{8,64}")
_QUIET_PATHS = frozenset({"/v1/health", "/v1/ready"})


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


class RequestContextMiddleware:
    """Assign a request ID, add security headers, and emit one access log line per request.

    Implemented as pure ASGI (not BaseHTTPMiddleware) so streaming responses are not buffered.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_headers = dict(scope["headers"])
        incoming = request_headers.get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _INCOMING_REQUEST_ID_RE.fullmatch(incoming) else new_request_id()
        token = REQUEST_ID.set(request_id)
        started = time.perf_counter()
        status_code = 500
        path = scope["path"]
        is_ui = not path.startswith(("/v1/", "/docs", "/redoc", "/openapi.json"))

        async def send_with_headers(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if is_ui:
                    headers["Content-Security-Policy"] = UI_CONTENT_SECURITY_POLICY
                    headers.setdefault("Cache-Control", "no-cache")
            await send(message)

        # Reject oversized uploads before the multipart body is parsed.
        body_limited = scope["method"] == "POST" and path.startswith("/v1/ask")
        received_bytes = 0

        async def receive_with_limit() -> Message:
            nonlocal received_bytes
            message = await receive()
            if body_limited and message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > MAX_REQUEST_BYTES:
                    raise HTTPException(status_code=413, detail=REQUEST_TOO_LARGE_DETAIL)
            return message

        try:
            declared = request_headers.get(b"content-length", b"")
            if body_limited and declared.isdigit() and int(declared) > MAX_REQUEST_BYTES:
                response = JSONResponse({"detail": REQUEST_TOO_LARGE_DETAIL}, status_code=413)
                await response(scope, receive, send_with_headers)
            else:
                await self.app(scope, receive_with_limit, send_with_headers)
        finally:
            METRICS.record_http_response(status_code)
            if scope["path"] not in _QUIET_PATHS:
                duration_ms = round((time.perf_counter() - started) * 1000, 1)
                access_logger.info(
                    "%s %s -> %s in %.1fms", scope["method"], scope["path"], status_code, duration_ms,
                    extra={"method": scope["method"], "path": scope["path"], "status": status_code,
                           "duration_ms": duration_ms},
                )
            REQUEST_ID.reset(token)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    missing_keys = check_provider_keys_present(providers_in_use())
    if missing_keys:
        logger.warning("Missing API keys for providers in use: %s", missing_keys)
    else:
        logger.info("API keys configured for all providers in use: %s", providers_in_use())
    if not cfg.api_key:
        logger.warning("API_KEY is not set: the API is unauthenticated. Set API_KEY outside local development.")
    if not await asyncio.to_thread(check_database):
        logger.error("Decision history database at %s is not writable.", cfg.database_path)
    logger.info("AI Council backend v%s started (environment=%s)", __version__, cfg.environment)
    yield
    await close_clients()


app = FastAPI(
    title="AI Council",
    version=__version__,
    description="Multi-agent decision council that returns a structured directive with guardrails.",
    lifespan=lifespan,
    docs_url=None if cfg.is_production else "/docs",
    redoc_url=None if cfg.is_production else "/redoc",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RequestContextMiddleware)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str | None = Security(api_key_header)) -> None:
    """Enforce the X-API-Key header when API_KEY is configured (constant-time comparison)."""
    if not cfg.api_key:
        return
    if not api_key or not hmac.compare_digest(api_key.encode("utf-8"), cfg.api_key.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def _public_error_detail(error: Exception) -> str:
    if isinstance(error, CouncilUnavailableError):
        return str(error)
    return str(error) if cfg.environment == "development" else GENERIC_FAILURE_DETAIL


@app.get("/v1/health", response_model=HealthResponse, tags=["system"])
async def health():
    """Liveness check. ``degraded`` means a provider in use has no API key."""
    missing_keys = check_provider_keys_present(providers_in_use())
    status_val = "ok" if not missing_keys else "degraded"
    return HealthResponse(status=status_val, version=__version__, providers_missing=missing_keys)


@app.get("/v1/ready", tags=["system"])
async def ready():
    """Readiness check: returns 503 until provider keys and the history database are usable."""
    checks = {
        "providers": not check_provider_keys_present(providers_in_use()),
        "database": await asyncio.to_thread(check_database),
    }
    ready_now = all(checks.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if ready_now else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if ready_now else "not_ready", "checks": checks},
    )


@app.get("/v1/metrics", tags=["system"], dependencies=[Depends(require_api_key)])
async def metrics():
    return METRICS.snapshot()


@app.get("/v1/providers", tags=["system"])
async def providers():
    """Expose safe provider readiness information; API keys are never returned."""
    in_use = set(providers_in_use())
    missing = {item.split(" ", 1)[0] for item in check_provider_keys_present()}
    return {
        "providers": [
            {"name": name, "configured": name not in missing, "in_use": name in in_use}
            for name in PROVIDER_ENV_KEYS
        ],
        "roles": [
            {
                "role": item.role_name, "provider": item.provider, "model": item.model,
                "backups": [str(ref) for ref in candidates_for(item)[1:]],
            }
            for item in all_role_configs()
        ],
        # Current state of every model the council may use; paused models are skipped automatically.
        "models": MODEL_HEALTH.snapshot(
            [ref for item in all_role_configs() for ref in candidates_for(item)]
            + [ModelRef(cfg.vision_provider, model) for model in cfg.vision_models]
        ),
    }


@app.get("/v1/config", tags=["system"])
async def public_config():
    """Everything the web interface needs to render before the user signs in; contains no secrets."""
    return {
        "version": __version__,
        "auth_required": bool(cfg.api_key),
        "members": [{"key": key, "role_name": role.role_name} for key, role in EXPERT_LIBRARY.items()],
        "chairman": {"key": "chairman", "role_name": CHAIRMAN.role_name},
        "limits": {
            "max_prompt_chars": cfg.max_prompt_chars,
            "max_files": cfg.max_upload_files,
            "max_pdf_mb": cfg.max_pdf_mb,
            "max_image_mb": cfg.max_image_mb,
            "max_pdf_pages": cfg.max_pdf_pages,
        },
    }


@app.get(
    "/v1/history", response_model=list[DecisionRecord], tags=["history"], dependencies=[Depends(require_api_key)]
)
async def history(limit: int = Query(30, ge=1, le=100)):
    return await asyncio.to_thread(list_decisions, limit)


@app.get(
    "/v1/history/{decision_id}", response_model=DecisionRecord, tags=["history"],
    dependencies=[Depends(require_api_key)],
)
async def history_item(decision_id: str = PathParam(..., max_length=64)):
    record = await asyncio.to_thread(get_decision, decision_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Decision not found.")
    return record


@app.post("/v1/history/{decision_id}/feedback", tags=["history"], dependencies=[Depends(require_api_key)])
async def feedback(feedback_input: FeedbackInput, decision_id: str = PathParam(..., max_length=64)):
    saved = await asyncio.to_thread(save_feedback, decision_id, feedback_input.rating, feedback_input.outcome_note)
    if not saved:
        raise HTTPException(status_code=404, detail="Decision not found.")
    return {"status": "saved"}


def _parse_sources(raw_sources: str) -> list[str]:
    sources = [line.strip() for line in raw_sources.splitlines() if line.strip()]
    if len(sources) > MAX_SOURCES:
        raise HTTPException(status_code=400, detail=f"Add up to {MAX_SOURCES} source links.")
    for source in sources:
        parsed = urlparse(source)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or len(source) > 2048:
            raise HTTPException(status_code=400, detail="Each source must be a valid HTTP(S) URL.")
    return sources


def _validate_submission(prompt: str, sources: str) -> tuple[str, list[str]]:
    if len(prompt) > MAX_PROMPT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Prompt is too long. Limit it to {MAX_PROMPT_CHARS:,} characters.",
        )
    return sanitize_prompt(prompt), _parse_sources(sources)


async def _read_uploads(files: list[UploadFile] | None) -> list[tuple[str, str, bytes]]:
    """Read and validate uploads before any model work starts, so bad files fail fast with a 4xx."""
    uploads = [upload for upload in files or [] if upload.filename or upload.size]
    if len(uploads) > cfg.max_upload_files:
        raise HTTPException(status_code=400, detail=f"Attach up to {cfg.max_upload_files} files.")
    validated = []
    for upload in uploads:
        filename = sanitize_filename(upload.filename)
        data = await upload.read(max(max_bytes("pdf"), max_bytes("image")) + 1)
        await upload.close()
        try:
            kind = validate_upload(filename, data)
        except AttachmentError as error:
            status_code = 413 if "limited to" in str(error) else 415 if "supported" in str(error) else 400
            raise HTTPException(status_code=status_code, detail=str(error)) from error
        validated.append((filename, kind, data))
    return validated


async def _run_and_save(
        prompt: str,
        debate: bool,
        sources: list[str],
        on_event=None,
        uploads: list[tuple[str, str, bytes]] | None = None,
) -> CouncilResult:
    contexts = []
    if sources:
        contexts.append(
            "USER-SUPPLIED SOURCES (cite only when directly supported; do not claim to have read a link):\n"
            + "\n".join(f"- {source}" for source in sources)
        )
    attachments = await process_attachments(uploads, on_event, REQUEST_ID.get()) if uploads else []
    if evidence := build_evidence_context(attachments):
        contexts.append(evidence)

    result = await run_council(
        prompt, context="\n\n".join(contexts) or None, debate=debate, on_event=on_event
    )
    result.sources = sources
    result.attachments = [attachment.summary() for attachment in attachments]
    try:
        await asyncio.to_thread(save_decision, result)
    except Exception:
        logger.exception("Failed to persist decision %s", result.request_id)
    return result


def _sse(event: str, payload: str) -> str:
    return f"event: {event}\ndata: {payload}\n\n"


@app.post("/v1/ask", response_model=CouncilResult, tags=["council"], dependencies=[Depends(require_api_key)])
@limiter.limit(RATE_LIMIT)
async def ask(
    request: Request,
    prompt: str = Form(...),
    debate: bool = Form(False),
    sources: str = Form(""),
    files: list[UploadFile] | None = File(None, description="PDFs and images for the council to read"),
):
    clean_prompt, parsed_sources = _validate_submission(prompt, sources)
    uploads = await _read_uploads(files)
    try:
        return await _run_and_save(clean_prompt, debate, parsed_sources, uploads=uploads)
    except CouncilUnavailableError as error:
        logger.warning("Council unavailable: %s", error)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        logger.exception("Council run failed")
        raise HTTPException(status_code=502, detail=_public_error_detail(error)) from error


@app.post("/v1/ask/stream", tags=["council"], dependencies=[Depends(require_api_key)])
@limiter.limit(RATE_LIMIT)
async def ask_stream(
    request: Request,
    prompt: str = Form(...),
    debate: bool = Form(False),
    sources: str = Form(""),
    files: list[UploadFile] | None = File(None, description="PDFs and images for the council to read"),
):
    """Stream lifecycle events as SSE so clients can show deliberation progress.

    Events, in order of appearance: ``evidence_started`` / ``evidence_ready`` (per upload),
    ``charter_ready``, ``member_started`` / ``member_done`` (per member, per round), ``consensus_update``
    (after each round), ``debate_skipped``
    or ``debate_started``, ``synthesis_started``, ``cache_hit``, then a terminal ``complete`` or ``error``.
    Comment lines (``: keep-alive``) are sent periodically so proxies keep the connection open.
    """
    clean_prompt, parsed_sources = _validate_submission(prompt, sources)
    uploads = await _read_uploads(files)

    async def event_stream() -> AsyncIterator[str]:
        queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()

        async def on_event(event: str, data: dict) -> None:
            if event != "final":  # the full result is sent once, as the terminal "complete" event
                await queue.put((event, data))

        task = asyncio.create_task(_run_and_save(clean_prompt, debate, parsed_sources, on_event, uploads))
        last_sent = time.monotonic()
        try:
            yield ": stream-open\n\n"
            while not task.done() or not queue.empty():
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=0.25)
                except TimeoutError:
                    if time.monotonic() - last_sent >= cfg.stream_heartbeat_seconds:
                        last_sent = time.monotonic()
                        yield ": keep-alive\n\n"
                    continue
                last_sent = time.monotonic()
                yield _sse(event, json.dumps(data))
            result = await task
            yield _sse("complete", result.model_dump_json())
        except Exception as error:
            logger.exception("Council stream failed")
            yield _sse("error", json.dumps({"detail": _public_error_detail(error)}))
        finally:
            if not task.done():
                task.cancel()
                # The client disconnected or the stream failed; the task's outcome no longer matters.
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error.", "request_id": REQUEST_ID.get()},
    )


# The web interface is mounted last so every /v1 route above takes precedence.
_frontend_dir = Path(cfg.frontend_dir)
if (_frontend_dir / "index.html").is_file():
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        # Browsers request /favicon.ico regardless of the <link rel="icon"> tag.
        return RedirectResponse("/assets/favicon.svg", status_code=status.HTTP_301_MOVED_PERMANENTLY)

    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="ui")
else:
    logger.warning("Web interface not found at %s; serving the API only.", _frontend_dir)
