# AI Council

> For setup problems, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

Put a hard decision to a council of AI specialists and watch them debate it. Each member reads your
question and any PDFs or images you attach, gives an opening statement, then challenges the others'
claims. A Chairman weighs the debate and issues **one directive**: a recommendation, why it wins, an
execution plan, guardrails, and a calibrated confidence level.

## What you see

The interface is a dark council chamber. Members sit around a glowing table, and everything on screen
is driven by what the council is actually doing:

- **Thinking**: an orbiting ring and halo while a member prepares a statement or challenge.
- **Speaking**: the seat lights up, a speech bubble shows the member's position, and the full
  statement types into the debate transcript.
- **Challenging**: during cross-examination, a beam is drawn from the challenger to the member being
  challenged, and the bubble quotes the specific point.
- **Consensus index**: the table shows how aligned the members' recommendations are, updated after each round.
- **Live argument stream**: the side panel lists the latest positions and challenges as they're made.
- **Progress**: a progress bar tracks the real steps (evidence, framing, each statement, the directive),
  and **Halt session** stops a run in progress.
- **Roster**: a card per member shows their status (thinking, has the floor, challenged, not seated)
  and their current position.
- **Directive**: the Chairman takes the floor and the directive is laid out below the roster.
  **Export brief** downloads it as Markdown.

The animation is driven by live server events. Members work in parallel, and the interface gives each
statement the floor in the order it finished, so several answers arriving at once still read as a debate.
Past decisions can be reopened and replayed.

## Evidence uploads

Attach up to 5 files by choosing, dragging, or pasting them.

| File | How the council reads it |
|------|--------------------------|
| PDF with text | Text is extracted from up to 40 pages with `pypdf`. |
| Scanned PDF (no text layer) | The first 3 pages are rendered with `pypdfium2` and read by a vision model. |
| PNG, JPEG, WebP, GIF | Validated and re-encoded with Pillow (stripping metadata), then transcribed and described by a vision model. |

Files are identified by their content rather than their extension, size-limited (PDF 15 MB, image 8 MB),
and never stored. Only a summary (name, pages, how it was read) is saved with the decision. Extracted text
is labelled as untrusted reference material in every model prompt. If one file can't be read, for example
because it's password-protected, the council continues with the rest and tells you why.

## Architecture

```
Browser ──► FastAPI (one process, port 8000)
            ├── /            web interface (static HTML, CSS, and JavaScript; no build step)
            ├── /v1/ask/stream   Server-Sent Events: evidence → charter → statements → challenges → directive
            ├── attachments.py   PDF/image extraction and the vision model
            ├── council.py       orchestration, retries, model fallback, consensus scoring
            └── history.py       SQLite decision history
```

- **Models:** Groq by default (`openai/gpt-oss-20b` and `-120b` for the council, `qwen/qwen3.8-27b` for
  vision). Every role's provider and model is configurable. NVIDIA NIM, Gemini, and OpenRouter are supported too.
- **Resilience:** transient failures (429, 5xx, timeouts, empty answers) are retried with backoff that follows
  the provider's `Retry-After`, and Groq roles fall back along `GROQ_FALLBACK_CHAIN`. `gpt-oss` models run with
  low reasoning effort so their hidden reasoning can't consume the whole token budget. A directive cut off by the
  token limit is retried once with more room. Partial results are flagged and never cached.

## Quick start

Requires **Python 3.11+** and a free [Groq API key](https://console.groq.com/keys).

**Windows:**
```powershell
Copy-Item .env.example .env   # then set GROQ_API_KEY
.\start_all.ps1               # installs dependencies, starts the server, opens the browser
```

**macOS/Linux:**
```bash
cp .env.example .env          # then set GROQ_API_KEY
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --port 8000
```

Open http://localhost:8000. API docs are at http://localhost:8000/docs (disabled in production).

### Docker

```bash
cp .env.example .env          # set GROQ_API_KEY and API_KEY
docker compose up --build
```

Open http://localhost:8000 and enter your `API_KEY` when asked for the access key. The container runs in
production mode as a non-root user, and history persists in the `council-data` volume.

### Render

One web service runs both the API and the interface.

| Setting | Docker runtime | Python runtime |
|---------|----------------|----------------|
| Dockerfile path / root directory | `backend/Dockerfile`, context `.` | Root directory `backend` |
| Build command | (from Dockerfile) | `pip install -r requirements.txt` |
| Start command | (from Dockerfile) | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers` |
| Health check path | `/v1/health` | `/v1/health` |

Environment variables: `GROQ_API_KEY`, `FORWARDED_ALLOW_IPS=*` (so rate limits apply per visitor rather
than to Render's proxy), and either `ENVIRONMENT=production` with an `API_KEY` for a private council, or
`ENVIRONMENT=staging` without one for an open demo. Render's free instances have no persistent disk, so
decision history resets on each deploy or restart unless you attach a disk and point `DATABASE_PATH` at it.

## Configuration

Every setting is an environment variable; see [.env.example](.env.example) for the full list with comments.

| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` (etc.) | Provider keys. Only providers used by a configured role are required. |
| `API_KEY` | Access key. The web interface asks for it once; API clients send `X-API-Key`. **Required in production.** |
| `ENVIRONMENT` | `development`, `staging`, `production`, or `test`. Production turns on JSON logs, hides error details, and disables `/docs`. |
| `<ROLE>_PROVIDER` / `<ROLE>_MODEL` / `<ROLE>_MAX_TOKENS` | Per role: `EXPERT_OPERATOR`, `EXPERT_ANALYST`, `EXPERT_RISK`, `EXPERT_RESEARCHER`, `ARCHITECT`, `CHAIRMAN`. |
| `REASONING_EFFORT` | Reasoning effort for `gpt-oss` models (default `low`). |
| `VISION_MODELS` | Vision models for images and scanned PDFs, tried in order. |
| `MAX_UPLOAD_FILES`, `MAX_PDF_MB`, `MAX_IMAGE_MB`, `MAX_PDF_PAGES`, `MAX_OCR_PAGES` | Upload limits. Set `MAX_UPLOAD_FILES=0` to turn uploads off. |
| `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW` | Per-IP limit on council runs (default 10 per 60 seconds). |
| `DATABASE_PATH` | SQLite history file. |

Invalid values stop startup with a message naming the setting.

> **Groq free tier:** the free tier allows about 8,000 tokens per minute per model. A council with
> cross-examination and evidence can reach that, and members then wait for the limit to reset. The seats
> keep showing "Preparing a statement" during the wait. Turn off cross-examination for quicker, cheaper answers.

## API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/v1/health` | – | Liveness (`degraded` if a provider in use has no key). |
| GET | `/v1/ready` | – | Readiness: 503 until provider keys and the database are usable. |
| GET | `/v1/config` | – | What the interface needs: members, upload limits, whether a key is required. |
| POST | `/v1/ask` | ✓ | Multipart form: `prompt`, `debate` (bool), `files` (repeatable), `sources` (newline-separated URLs). Returns the full result. |
| POST | `/v1/ask/stream` | ✓ | Same inputs, streamed as Server-Sent Events. |
| GET | `/v1/history?limit=30` | ✓ | Recent decisions. |
| GET | `/v1/history/{id}` | ✓ | One decision. |
| POST | `/v1/history/{id}/feedback` | ✓ | JSON `{"rating": 1-5, "outcome_note": "..."}`. |
| GET | `/v1/metrics` | ✓ | Request, cache, HTTP, and per-provider token metrics. |

**Stream events**, in order: `evidence_started` / `evidence_ready` per file, `charter_ready` (the seated
council), `member_started` / `member_done` per member and round (round-2 results include `challenges`),
`consensus_update` after each round, `debate_skipped` or `debate_started`, `synthesis_started`, and finally `complete` (the full result) or `error`.

```bash
curl -N http://localhost:8000/v1/ask/stream \
  -H "X-API-Key: $API_KEY" \
  -F "prompt=Should we renew our current CRM or switch vendors before Q4?" \
  -F "debate=true" \
  -F "files=@vendor-quotes.pdf" \
  -F "files=@usage-chart.png"
```

## Security

- The interface is served with a strict Content-Security-Policy (`script-src 'self'`, no inline scripts).
  Model output is rendered through a small markdown parser that builds DOM nodes with `textContent` only, never `innerHTML`.
- The access key is compared in constant time. The browser keeps it in session storage, or in local storage
  only if the user chooses "Remember on this device".
- Uploads are size-limited before parsing, sniffed by magic bytes, re-encoded (images), and never persisted.
  Password-protected, damaged, and decompression-bomb files are rejected with a clear message.
- Also included: per-IP rate limiting, prompt-injection screening, security headers, request IDs, non-root containers, and hidden error details in production.

## Development

```bash
pip install -r backend/requirements-dev.txt
ruff check . && mypy backend/app          # lint and type-check
(cd backend && pytest --cov=app)          # backend tests
(cd frontend && npm test)                 # interface logic tests (Node 20+, no dependencies)
```

CI runs all of the above, then builds the Docker image and smoke-tests the running container: the interface,
its CSP header, authentication, and upload type checks.

## Project structure

```
AI-Council/
├── backend/
│   ├── app/
│   │   ├── main.py          # routes, auth, uploads, SSE, serves the web interface
│   │   ├── council.py       # deliberation, challenges, retries, fallback
│   │   ├── attachments.py   # PDF and image evidence
│   │   ├── config.py        # validated settings and role prompts
│   │   ├── history.py       # SQLite history
│   │   └── ...
│   ├── tests/
│   └── Dockerfile           # single image: API + web interface
├── frontend/
│   ├── public/              # served at /
│   │   ├── index.html
│   │   └── assets/          # css/app.css, js/*.js (ES modules)
│   └── tests/               # node:test suites for the pure logic modules
├── docker-compose.yml
└── .env.example
```

## License

MIT
