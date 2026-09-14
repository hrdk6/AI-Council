# syntax=docker/dockerfile:1
# Build from the repository root: docker build -f backend/Dockerfile .
# One image serves the API (/v1) and the web interface (/).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATABASE_PATH=/app/data/ai_council.db \
    FRONTEND_DIR=/app/web

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /home/app app

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/app ./app
COPY frontend/public ./web
RUN mkdir -p /app/data && chown app:app /app/data

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/v1/health' % os.environ.get('PORT', '8000'), timeout=4)"]

# A single worker keeps the in-memory cache, rate limiter, and SQLite history consistent.
# PORT is set by hosts such as Render; it defaults to 8000 for docker compose.
# Behind a reverse proxy, set FORWARDED_ALLOW_IPS to the proxy address so client IPs are rate-limited correctly.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --timeout-graceful-shutdown 30"]
