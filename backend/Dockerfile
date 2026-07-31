# ── Stage 1: Builder ─────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim AS builder

WORKDIR /build

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# pyproject.toml/uv.lock first so dependency install is cached independently
# of source changes; the backend/ source itself is needed too since this
# project installs as an editable package (unlike ds, which sets
# [tool.uv] package = false).
COPY pyproject.toml uv.lock ./
COPY backend/ ./backend/

RUN uv sync --locked --no-dev


# ── Stage 2: Runtime ─────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/backend /app/backend
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Runs uvicorn directly (not `python -m backend.main`, which hardcodes
# reload=True — fine for local dev, wrong for a container).
CMD ["uvicorn", "backend.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
