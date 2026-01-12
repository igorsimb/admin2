# AGENTS.md (repo instructions for coding agents)

This repository is a Django 5.2 project targeting Python 3.12+.

**Sources of truth already in repo** (these rules are included/expanded here):
- `.cursorrules`
- `.cursor/rules/admin2.mdc`
- `docs/project_overview.md`

## Agent behavior (from Cursor rules)

- Be direct; don’t be sycophantic.
- Don’t make code changes the user didn’t explicitly request.
- Never apply superficial “patches” — identify and fix the root cause.
- After implementing a feature/fix, briefly suggest obvious refactors (DRY/readability).
- Assume humans may handle git; when asked, propose a Conventional Commit message.

## Quick start (local)

- Create venv: `uv venv`
- Install dependencies (incl. dev tools): `uv sync --all-groups`
- Run Django migrations: `uv run manage.py migrate`
- Run dev server: `uv run manage.py runserver`

Notes:
- For Python-related commands, prefer `uv run <command>`.
- Django settings selection:
  - `manage.py` uses `DJANGO_ENVIRONMENT` (`staging` default, `production` when set).
  - Tests use `DJANGO_SETTINGS_MODULE=config.django_config.test` (see `pytest.ini`).

## Build / run (Docker)

- Start staging/dev stack: `docker-compose -f docker-compose.dev.yml up --build -d`
- Start default stack: `docker-compose up --build -d`

Services include Postgres, Redis, Django, Celery worker, Celery beat, and Nginx.

## Lint / format

This repo uses Ruff for linting + formatting (see `ruff.toml`).

- Format everything: `uv run ruff format .`
- Check formatting (no changes): `uv run ruff format --check .`
- Lint: `uv run ruff check --config ruff.toml .`
- Lint + autofix: `uv run ruff check --fix --config ruff.toml .`

Pre-commit is configured (see `.pre-commit-config.yaml`):
- Install hooks: `uv run pre-commit install`
- Run all hooks: `uv run pre-commit run --all-files`

Hooks include Ruff formatting/linting, typo checks, and Prettier for YAML/JSON5.

## Tests

Pytest is the standard test runner.

- Run full test suite: `uv run pytest`

Important defaults (repo config):
- `pytest.ini` sets `addopts = "-n 4"` (xdist parallel runs).
- `tests/conftest.py` enables verbose output by default.

### Run a single test (recommended patterns)

- Single test function:
  - `uv run pytest -n 0 tests/path/test_file.py::test_name`
- Single test class:
  - `uv run pytest -n 0 tests/path/test_file.py::TestClass`
- Filter by name substring:
  - `uv run pytest -n 0 -k "some_substring"`

Why `-n 0`?
- Disables xdist when debugging (overrides `pytest.ini`).

Other useful flags:
- Disable the repo’s default verbosity: `uv run pytest --no-verbose`
- Stop on first failure: `uv run pytest -x`
- Show local variables in tracebacks: `uv run pytest -l`

## Django management commands

Use `uv run manage.py <command>` instead of calling Python directly:
- `uv run manage.py makemigrations`
- `uv run manage.py migrate`
- `uv run manage.py createsuperuser`
- `uv run manage.py shell`

Celery (local):
- Worker: `uv run celery -A config.third_party_config.celery worker -l info`
- Beat: `uv run celery -A config.third_party_config.celery beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler`

## Project architecture (high-level)

This codebase is a rewrite/strangler-style replacement for a legacy system.
Key principles (see `docs/project_overview.md`):
- Prefer modular Django apps (“pseudo-services”).
- Avoid hidden dependencies and tight coupling across apps.
- If one app needs work done by another, prefer explicit boundaries (e.g., Celery tasks/events)
  over deep import chains.
- Avoid cross-app imports at module import-time; keep app initialization in `AppConfig.ready()`.

## Code style (Python)

### Formatting
- Ruff is the formatter; do not hand-format.
- Line length: 120.
- Indentation: 4 spaces.
- Strings: use double quotes (Ruff `quote-style = "double"`).

### Imports
- Let Ruff/isort organize imports.
- Import grouping/order follows Ruff’s `section-order`:
  1) future
  2) standard-library
  3) third-party
  4) first-party (project apps)
  5) local-folder
- Keep imports explicit and readable; avoid star imports except in settings override modules
  (and then add `# noqa` as already used in `config/django_config/test.py`).

### Typing
- Python version is `>=3.12`.
- Prefer PEP 604 unions: `X | Y`, `X | None` (avoid `Optional[X]`).
- Annotate `-> None` explicitly for functions returning nothing.
- Use modern built-in generics: `list[str]`, `dict[str, Any]`.
- Avoid gratuitous typing on trivial code; optimize for clarity.

### Naming
- Modules/packages: `snake_case`.
- Functions/variables: `snake_case`.
- Classes/enums: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Tests: long, descriptive names are encouraged (see `.cursorrules`).
- Mocks: prefer `mock_...` prefix.

### Django conventions
- Settings modules live in `config/django_config/`.
- Keep Django views thin:
  - Parse/validate request
  - Call a service function
  - Return response
- Put heavy business logic in `services.py` (or similar) and keep it importable/testable.
- For Celery:
  - Keep tasks in `tasks.py` and delegate work to services.
  - Report progress via `core/reporting.py` where appropriate.

### Error handling & logging
- Don’t apply superficial patches: identify the root cause.
- Prefer catching specific exceptions at boundaries:
  - External HTTP calls
  - DB/network operations
  - File I/O
- Log with enough context (IDs, filenames, URLs) to debug production incidents.
- Use `logger.exception(...)` (or `exc_info=True`) when you need a traceback.
- Avoid swallowing exceptions silently; either re-raise or return a structured error.

Logging split in repo today:
- Django modules often use stdlib logging (`logging.getLogger(__name__)`).
- Some non-Django modules/scripts use Loguru (`from loguru import logger`).
Follow local patterns in the file you’re editing.

### Concurrency / performance
- For performance-critical async code, default to a concurrency limiter (e.g., `asyncio.Semaphore`)
  to avoid resource exhaustion (per `.cursor/rules/admin2.mdc`).

## Testing guidelines (Pytest)

- Use pytest for unit/integration tests.
- Follow AAA in structure (Arrange/Act/Assert), but **do not** literally write
  “Arrange/Act/Assert” as comments.
- Keep tests independent (order does not matter).
- Use fixtures for shared setup; prefer local mocking (`monkeypatch`, `patch`) over
  massive all-encompassing fixtures.
- Mirror the app structure under `tests/`.
- Prefer parametrization (`@pytest.mark.parametrize`) for scenario matrices.

## Commit message convention

- Use Conventional Commits style (e.g., `feat(scope): ...`, `fix(scope): ...`, `refactor(scope): ...`).
- If asked to propose a commit message, focus on the “why”, not just “what” in the commit body.

## Safety / scope

- Don’t commit secrets (e.g., `.env.*`, credentials) and avoid hardcoding credentials.
- Don’t change code unless the user request requires it; stay tightly scoped.
