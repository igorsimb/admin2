# syntax=docker/dockerfile:1.4

FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy dependency files first for cache efficiency
COPY pyproject.toml uv.lock ./

# Install dependencies (no source code yet)
RUN uv sync --locked --no-editable

# Copy the rest of the project
COPY . .

# Collect static files (if needed)
# RUN uv run manage.py collectstatic --noinput

# Final image
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /bin/uv /app/.venv/bin/uv
COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"

# Entrypoint is set in docker-compose 