# ── Build stage (install deps) ────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build
COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

LABEL org.opencontainers.image.title="stock-ledger-api"
LABEL org.opencontainers.image.description="SQLite-backed portfolio ledger REST API"

# Copy installed packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Source code
COPY ledger/    ./ledger/
COPY domain/    ./domain/
COPY analysis/  ./analysis/
COPY apps/api/  ./apps/api/
COPY apps/__init__.py ./apps/__init__.py
COPY scripts/   ./scripts/

# Persistent data directory (mount a volume here)
RUN mkdir -p /data

ENV PYTHONPATH=/app
ENV DB_PATH=/data/ledger.db
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"]
