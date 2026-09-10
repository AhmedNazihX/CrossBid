# Crossbid API. Built with uv; runs as a non-root user.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, so a source-only change does not re-resolve the lock file.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY crossbid/ ./crossbid/
COPY settings.default.yaml ./


FROM python:3.12-slim-bookworm AS runtime

# Non-root: the container never needs to write to its own filesystem.
RUN groupadd --system --gid 1001 crossbid \
 && useradd --system --uid 1001 --gid crossbid crossbid

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder --chown=crossbid:crossbid /app /app

USER crossbid
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "crossbid.main:app", "--host", "0.0.0.0", "--port", "8000"]
