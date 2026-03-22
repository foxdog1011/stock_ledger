# ── Build stage (install deps) ────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build
COPY apps/mcp/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

LABEL org.opencontainers.image.title="stock-ledger-mcp"
LABEL org.opencontainers.image.description="MCP server exposing stock ledger tools to Claude"

# Copy installed packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Source code — shared packages and the MCP app
COPY ledger/    ./ledger/
COPY domain/    ./domain/
COPY analysis/  ./analysis/
COPY apps/mcp/  ./apps/mcp/
COPY apps/__init__.py ./apps/__init__.py

# Persistent data directory (mount a volume here)
RUN mkdir -p /data

ENV PYTHONPATH=/app
ENV DB_PATH=/data/ledger.db
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

CMD ["python", "apps/mcp/server.py"]
