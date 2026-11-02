ARG PYTHON_VERSION=3.14.8
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.24 /uv /uvx /bin/

WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1

COPY pyproject.toml uv.lock .python-version ./
ARG INSTALL_DEV=false
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$INSTALL_DEV" = "true" ]; then \
        uv sync --locked --all-groups; \
    else \
        uv sync --locked --no-dev; \
    fi

FROM python:${PYTHON_VERSION}-slim-bookworm

RUN useradd -m -r appuser && \
    mkdir -p /app/media && \
    chown -R appuser /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY --chown=appuser:appuser . .

EXPOSE 8000
RUN python -c "from pathlib import Path; p = Path('/app/entrypoint.prod.sh'); p.write_bytes(p.read_bytes().replace(b'\r\n', b'\n'))" \
    && chmod +x /app/entrypoint.prod.sh

CMD ["/app/entrypoint.prod.sh"]
