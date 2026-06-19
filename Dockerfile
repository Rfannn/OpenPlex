# ── Stage 1: Build dependencies ──────────────────────────────────────────────
FROM python:3.10-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
        libxml2-dev \
        libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime (minimal image) ─────────────────────────────────────────
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Runtime deps only (no gcc, no dev headers)
RUN apt-get update && apt-get install -y --no-install-recommends \
        aria2 \
        ffmpeg \
        libxml2 \
        libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application code
COPY app/       ./app/
COPY static/    ./static/
COPY templates/ ./templates/
COPY alembic/   ./alembic/
COPY alembic.ini .

# Create runtime directories (overlaid by volumes in production)
RUN mkdir -p data thumbnails

EXPOSE 8185

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:${PORT:-8185}/api/health'); assert r.status_code == 200"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8185} --workers ${WORKERS:-1}"]
