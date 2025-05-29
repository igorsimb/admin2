# syntax=docker/dockerfile:1.4

FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy dependency files first for cache efficiency
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --locked --no-editable

# Copy the rest of the project
COPY . .

# Collect static files (if needed)
# RUN uv run manage.py collectstatic --noinput

# Final image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    DJANGO_SETTINGS_MODULE=config.django_config.production

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /bin/uv /app/.venv/bin/uv
COPY --from=builder /app /app

# Set PATH
ENV PATH="/app/.venv/bin:$PATH"

# Create logs directory
RUN mkdir -p /app/logs

# Set the command to run when the container starts
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
