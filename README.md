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

## Live web research

Language models only know what was in their training data, so on their own they present stale facts
(last year's model, old prices) as current. The council handles this in two ways:

- **Every model is told today's date**, and that anything time-sensitive may have changed since it was trained.
- **For questions that depend on current facts** (releases, prices and plans, product comparisons, news, laws), the
  council researches the web before it deliberates:
  1. A planner decides whether the question needs current information and writes up to three searches. Questions
     that don't need it, such as personal or strategic decisions, skip this step.
  2. The first engine that works finds and reads the pages: **Tavily** when `TAVILY_API_KEY` is set, then **Groq's
     built-in browser search** (uses your Groq key), then **DuckDuckGo** (no key).
  3. A research analyst condenses the pages into a short brief with numbered citations. Every member and the
     Chairman receive it, with an instruction to prefer official, newer sources.

The chamber shows the searches and the pages being read as they happen. The directive lists every source under
"Checked on the web", and the exported brief includes them. If search is unavailable, the directive says so rather
than presenting remembered facts as current. Turn research off per question with the **Live web research** toggle,
or for the whole server with `WEB_RESEARCH=false`.

Pages are fetched only from public addresses (private, loopback, and cloud metadata addresses are refused, including
after redirects), limited in size and time, and labelled as untrusted content in every prompt.

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
            ├── /v1/ask/stream   Server-Sent Events: evidence → research → charter → statements → challenges → directive
            ├── attachments.py   PDF/image extraction and the vision model
            ├── research.py      live web research: plan, search, read pages, cited brief
            ├── council.py       orchestration, retries, model fallback, consensus scoring
            └── history.py       SQLite decision history
```

- **Models:** Groq by default (`openai/gpt-oss-20b` and `-120b` for the council, `qwen/qwen3.8-27b` for
  vision). Every role's provider and model is configurable. NVIDIA NIM, Gemini, and OpenRouter are supported too.
- **Automatic backup models:** when a model is rate-limited or fails, that council member switches to a backup
  and carries on. Every role tries its configured model, then every other model in `GROQ_FALLBACK_CHAIN`
  (`gpt-oss-20b`, `gpt-oss-120b`, `qwen3.8-27b`, `qwen3.6-27b` by default), then any cross-provider
  `BACKUP_MODELS` whose API key is set.
  - A rate-limited model is paused for everyone for as long as the provider asks, so members running in
    parallel skip it instead of each hitting the limit.
  - A rejected API key skips the whole provider; a retired model is benched for 10 minutes; flaky models are
    retried after the others have been tried. If every model is paused, a short wait (up to 15 seconds) is
    waited out; longer ones fail fast with a clear message.
  - The seat and roster show "Backup model" when a switch happens, the transcript names the model that
    answered, and `GET /v1/providers` lists each role's backups and any paused models.
- **Resilience:** `gpt-oss` models run with low reasoning effort (and Qwen with reasoning off) so hidden reasoning
  can't consume the whole token budget. A directive cut off by the token limit is retried once with more room.
  Partial results are flagged and never cached.

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

Environment variables: `GROQ_API_KEY`, optionally `TAVILY_API_KEY` (the most reliable web research engine; DuckDuckGo
often throttles cloud servers), `FORWARDED_ALLOW_IPS=*` (so rate limits apply per visitor rather
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
| `GROQ_FALLBACK_CHAIN` | Groq models every role can switch to, in order. |
| `BACKUP_MODELS` | Optional cross-provider backups as `provider:model`, e.g. `gemini:gemini-2.5-flash`. Used only when that provider's key is set. |
| `RATE_LIMIT_COOLDOWN_S` | How long a rate-limited model is skipped when the provider gives no retry time (default 30). |
| `REASONING_EFFORT` | Reasoning effort for `gpt-oss` models (default `low`). |
| `WEB_RESEARCH` | Live web research for time-sensitive questions (default `true`). |
| `SEARCH_ENGINES` / `TAVILY_API_KEY` | Research engines in order (`tavily,groq,duckduckgo`); Tavily is used only when its key is set. |
| `RESEARCH_MODEL`, `RESEARCH_BROWSER_MODELS`, `RESEARCH_MAX_SOURCES` | The planner and brief model, the Groq models that browse, and how many sources to cite. |
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
| POST | `/v1/ask` | ✓ | Multipart form: `prompt`, `debate` (bool), `research` (bool, default true), `files` (repeatable), `sources` (newline-separated URLs). Returns the full result, including `research` (brief and sources). |
| POST | `/v1/ask/stream` | ✓ | Same inputs, streamed as Server-Sent Events. |
| GET | `/v1/history?limit=30` | ✓ | Recent decisions. |
| GET | `/v1/history/{id}` | ✓ | One decision. |
| POST | `/v1/history/{id}/feedback` | ✓ | JSON `{"rating": 1-5, "outcome_note": "..."}`. |
| GET | `/v1/metrics` | ✓ | Request, cache, HTTP, and per-provider token metrics. |

**Stream events**, in order: `evidence_started` / `evidence_ready` per file, `research_started`, then either
`research_skipped` or `research_searching` / `research_reading` / `research_ready`, `charter_ready` (the seated
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
