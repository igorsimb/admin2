# Containerization Strategy for admin2

## Overview

This document describes how to containerize the `admin2` Django project for both development and production/staging environments, leveraging Docker, Docker Compose, and the `uv` dependency manager. It covers:

- Service architecture and environment separation
- Developer experience optimizations (hot reload, dependency caching, etc.)
- Secure and reproducible builds
- Environment variable and secret management
- Deployment and operational best practices

---

## 1. Service Architecture

### Services to Containerize

- **Django** (admin2 web app)
- **Celery** (background task worker)
- **Redis** (Celery broker/result backend)
- **PostgreSQL** (production DB; SQLite for MVP/dev)
- **nginx** (reverse proxy/static/media serving)

### Volumes

- Static files (`/app/static`)
- Media files (`/app/media`)
- Database data (for PostgreSQL, Redis)
- (Optional) uv cache for faster dependency installs

---

## 2. Environment Separation: Staging vs Production

- Use **separate `.env.staging` and `.env.production`** files (already present).
- Each environment gets its own Docker Compose file:
  - `docker-compose.staging.yml`
  - `docker-compose.production.yml`
- Each Compose file references the appropriate `.env` file and can override ports, secrets, and service configs as needed.
- **Redis:** Use different ports for staging and production to avoid accidental cross-talk if both run on the same host. (e.g., 6377 for staging, 6378 for production)
- **nginx:** Expose different external ports (e.g., 8071 for staging, 8061 for production) to avoid conflicts with the legacy system and to match your new deployment URLs.

---

## 3. Developer Experience

- **Hot reload:** Mount source code as a volume in the Django container for instant code changes (dev only).
- **Dependency caching:** Use Docker build cache and uv's cache directory to avoid reinstalling dependencies on every build.
- **No local .venv in container:** Always build the virtual environment inside the container for platform consistency.
- **Watch mode:** Use Docker Compose's `develop`/`watch` features for live reload (see [uv Docker docs](https://docs.astral.sh/uv/guides/integration/docker/#developing-in-a-container)).
- **.dockerignore:** Exclude `.venv`, `__pycache__`, and other local artifacts.

---

## 4. Dockerfile: Best Practices with uv

- Use a multi-stage build for clean, small images.
- Install dependencies with `uv sync --locked --no-editable` for reproducible, non-editable installs.
- Copy only `pyproject.toml` and `uv.lock` first to leverage Docker cache for dependencies.
- Only copy the rest of the source after dependencies are installed.
- Set up the entrypoint to use `uv run` for all Django/Celery commands.

**Example Dockerfile:**

```dockerfile
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
RUN uv run manage.py collectstatic --noinput

# Final image
FROM python:3.12-slim

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"

# Entrypoint is set in docker-compose
```

---

## 5. Docker Compose: Service Definitions

- **Django:** Uses `uv run manage.py runserver 0.0.0.0:8000` (or `gunicorn` for production).
- **Celery:** Uses `uv run celery -A core worker -l info`.
- **Redis:** Use official image, expose different ports for staging/production (e.g., 6377 for staging, 6378 for production).
- **nginx:** Use a templated config, pass in environment variables for port mapping (e.g., 8071 for staging, 8061 for production).
- **PostgreSQL:** Use official image, mount a volume for data persistence.

**Example Compose Service (Django):**

```yaml
services:
  django:
    build: .
    command: uv run manage.py runserver 0.0.0.0:8000
    volumes:
      - .:/app
      - static_volume:/app/static
      - media_volume:/app/media
    env_file:
      - .env.staging  # or .env.production
    depends_on:
      - redis
      - db
    ports:
      - "8000:8000"
```

---

## 6. Environment Variables and Secrets

- Use `env_file` in Compose to load `.env.staging` or `.env.production`.
- Never hardcode secrets in Dockerfiles or Compose files.
- For production, consider using Docker secrets or a secrets manager.

---

## 7. Nginx Reverse Proxy

- Use a templated `nginx.conf` that can be filled with environment variables at container startup.
- Serve static and media files from volumes.
- Proxy pass to Django app (gunicorn) on the internal network.
- Expose ports 8071 (staging) and 8061 (production) externally.

---

## 8. Workflow: Local Development

- Use `docker-compose.staging.yml` for local dev.
- Mount code as a volume for hot reload.
- Use SQLite for MVP, switch to PostgreSQL for full dev/prod parity.
- Use `uv` for all Python commands inside the container.

---

## 9. Workflow: Staging/Production Deployment

- Build images with `docker-compose -f docker-compose.production.yml build`
- Push to server, run with `docker-compose -f docker-compose.production.yml up -d`
- Use `.env.production` for secrets and production settings.
- Expose the correct ports for your boss to access (e.g., 8061 for prod, 8071 for staging).

---

## 10. Example Directory Structure

```
admin2/
  Dockerfile
  docker-compose.staging.yml
  docker-compose.production.yml
  .dockerignore
  .env.staging
  .env.production
  nginx/
    nginx.conf.template
  ...
```

---

## 11. Example .dockerignore

```
.venv
__pycache__
*.pyc
*.pyo
*.pyd
db.sqlite3
.env
.env.*
*.log
```

---

## 12. References

- [uv Docker Integration Guide](https://docs.astral.sh/uv/guides/integration/docker/)
- [Docker Compose Watch/Develop](https://docs.docker.com/compose/watch/)
- [Django Deployment Checklist](https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/)

---

## 13. FAQ

**Q: Do I need two separate Compose files?**  
A: Yes, for clean separation and to avoid accidental config leaks between staging and production.

**Q: How do I avoid rebuilding on every code change?**  
A: Mount your code as a volume in dev/staging, and use Docker Compose's `develop`/`watch` features.

**Q: How do I keep dependencies cached?**  
A: Copy only `pyproject.toml` and `uv.lock` first in the Dockerfile, then install dependencies, then copy the rest of the code.

**Q: How do I switch environments?**  
A: Use the appropriate Compose file and `.env` file. The `setdjangoenv` function is not needed inside the container; just set the correct env file.

---

## 14. Next Steps

- Draft and test your Dockerfile and Compose files using the above patterns.
- Add this guide to `docs/containerization_plan.md`.
- Update as you iterate and learn from real deployments.

---

If you have any specific questions about the Compose file, Dockerfile, or want a full working example, let me know!

---

## 15. Health Checks and Service Startup Order

To ensure reliable startup and avoid race conditions, Docker Compose health checks should be used for critical dependencies like the database and Redis. This ensures that services like Django and Celery only start after their dependencies are actually ready to accept connections—not just running.

### Why Use Health Checks?
- **Prevents race conditions:** Ensures Django/Celery don't start before the database or Redis are ready.
- **Cleaner logs:** Reduces connection errors and retries on startup.
- **Production-grade reliability:** Follows best practices for orchestrated environments.

### How to Implement

1. **Add health checks** to your `db` and `redis` services in your Compose files:

```yaml
db:
  image: postgres:15-alpine
  environment:
    POSTGRES_DB: admin2
    POSTGRES_USER: admin2
    POSTGRES_PASSWORD: admin2password
  healthcheck:
    test: ["CMD", "pg_isready", "-U", "admin2"]
    interval: 5s
    timeout: 5s
    retries: 5
    start_period: 10s

redis:
  image: redis:alpine
  command: redis-server --port 6378  # or 6377 for staging
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 5s
    timeout: 3s
    retries: 3
```

2. **Update Django and Celery services to wait for healthy dependencies:**

```yaml
django:
  # ...
  depends_on:
    db:
      condition: service_healthy
    redis:
      condition: service_healthy

celery:
  # ...
  depends_on:
    db:
      condition: service_healthy
    redis:
      condition: service_healthy
```

This pattern ensures that Django and Celery will only start after both the database and Redis are healthy and ready.

For more details and best practices, see [Docker Compose Health Checks: An Easy-to-follow Guide (last9.io)](https://last9.io/blog/docker-compose-health-checks/).
