📄 Execution Plan for parser App (LLM Agent Playbook)
Scope: The agent follows these steps sequentially and pauses after each phase awaiting your approval in this chat.
What: Add parser of https://stparts.ru/ website (extensible to emex/autopiter/partkom later)
---
Tech Stack (as executed by the agent)
Django app: parser (monolith)
Celery: use existing app from config.third_party_config.celery import app
Scheduling: django-celery-beat
Async HTTP client: httpx.AsyncClient (per-proxy sessions)
HTML parser: selectolax
Validation: pydantic
Dataframe/Excel: pandas + xlsxwriter
DB: ClickHouse (TTL 6 months)
Concurrency control: asyncio.Semaphore
Realtime updates: SSE for parsing jobs only, via core/reporting.py::ProgressReporter
Typing: PEP 604 unions; use "double quotes" in Python
---
# P1 — App Scaffolding (Lean Structure)

### Purpose

Establish a **minimal, clean Django app structure** for the `parser` module — optimized for maintainability and quick growth.
Avoid redundant one-file folders; start flat and only introduce subpackages once multiple sources or large files justify them.

---

### Directory Structure (lean variant)

```
parser/
  __init__.py
  urls.py                 # routes
  views.py                # job endpoints (HTTP + SSE)
  tasks.py                # Celery orchestrator (ProgressReporter)
  types.py                # Pydantic schemas (OfferRow)

  http.py                 # HTTP sessions, fetch_html, ProxyPool
  stparts.py              # pure HTML → OfferRow parser
  stparts_pipeline.py     # fetch → parse → top10 shaping
  clickhouse_repo.py      # CH DDL + batch insert
  excel_export.py         # wide top-10 Excel writer
  cleanup.py              # old-export deletion logic
  utils.py                # small helpers (sorting, URLs, misc)
```

This keeps related logic discoverable, import paths short, and avoids “folder sprawl” like `parser/http/session.py` for a single module.
When new parsers (e.g., `emex.py`, `autopiter.py`) arrive, they’ll slot in next to `stparts.py` naturally.

---

### Tasks

1. **Create app** `parser/` (if not already).

2. Add stubs for each module:

   * `views.py`: define `health_view(request)` → `JsonResponse({"ok": True})`
   * `urls.py`:

     ```python
     from django.urls import path
     from .views import health_view

     urlpatterns = [
         path("health", health_view),
     ]
     ```
   * `tasks.py`: import existing Celery app:

     ```python
     from config.third_party_config.celery import app

     @app.task
     def placeholder_task():
         return "ok"
     ```
   * `types.py`: skeleton model:

     ```python
     from pydantic import BaseModel

     class OfferRow(BaseModel):
         source: str
         brand: str | None
         article: str
         name: str | None
         price: float | None
         quantity: int | None
         supplier: str | None
         rating: int | None
         deadline_days: int | None
         is_analog: bool
     ```
   * Other files: empty placeholders with short docstrings describing their future role.

3. **Wire routes**: include `parser.urls` in the project’s main `urls.py` under `/parser/`.

4. **Verify imports**: ensure `python -c "import parser; print('ok')"` runs cleanly.

---

### Deliverables

* The lean `parser/` directory as above.
* All files importable with no `ImportError`.
* `/parser/health` endpoint returns `{"ok": true}`.

---

### Acceptance Criteria

* ✅ `python -c "import parser; print('ok')"` prints `ok`
* ✅ `GET /parser/health` → 200, body `{"ok": true}`
* ✅ Directory tree matches the lean layout
* ✅ `ruff` / `flake8` / `mypy` (if used) pass cleanly
* ✅ No unnecessary folders like `/http/`, `/pipeline/`, `/tasks/`, `/housekeeping/`

---

**Pause Gate:**
After scaffolding and a successful health check, the agent pauses and waits for your explicit approval:

> “GO P2” or “REVISE P1: <instruction>”.
---
P2 — HTTP layer, proxy policy, proxy source
Purpose
Create a resilient fetcher with per-proxy AsyncClient, realistic headers/cookies, retries/backoff, and proxy retrieval from DB.
Tasks
parser/http/session.py:
  * class ProxySession: manages httpx.AsyncClient with:
    * http2=True, browser-like headers, initial cookies {"visited": "1", "visited_locale": "1"}
    * timeouts: connect 20s, read 30s, follow_redirects=True
  * async def fetch_html(self, url: str, params: dict[str, str] | None) -> str
    * Retry on {403, 429, 503} with exponential backoff + jitter.
    * Respect Retry-After on 429 if present.
  * def requested_article(url: str) -> str for /search?pcode=<CODE> and /search/<brand>/<CODE>?disableFiltering.
ProxyPool (round-robin):
  * Load proxies from DB via your ecosystem pattern (adapt to Django):
    * Rework our example into Django async utils to read (see the code from another project below):
  SELECT ip, port, username, password
  FROM proxy_list
  WHERE availability = TRUE
  * acquire() returns a ProxySession configured with one proxy; release() for cleanup; cool-off list after repeated failures.
Here's how it's done in another  (non-Django) project:
```python
@contextlib.asynccontextmanager
async def db_connection():
    """Создает и управляет соединением с базой данных PostgreSQL."""
    try:
        conn = await asyncpg.connect(
            host="postgres",
            database="parse",
            user="parse_user",
            password="password",
        )
        logger.debug("Соединение с базой данных установлено")
        try:
            yield conn
        finally:
            await conn.close()
            logger.debug("Соединение с базой данных закрыто")
    except Exception as e:
        logger.error(f"Ошибка при подключении к базе данных: {e}")
        raise
```
and then:
```python
@app.route('/get_proxies', methods=['GET'])
@require_app_key
@cached(ttl=cache_config['CACHE_TIMEOUT'], cache=Cache.MEMORY)
async def get_proxy():
    """
    Получает список всех доступных прокси-серверов из базы данных.

    Результаты кэшируются для уменьшения нагрузки на базу данных.
    Возвращает только прокси с флагом availability=TRUE.
    """
    client_ip = request.remote_addr

    try:
        logger.debug(f"Запрос списка прокси с IP {client_ip}")

        async with db_connection() as conn:
            query = """
            SELECT ip, port, username, password, availability
            FROM proxy_list
            WHERE availability = TRUE
            """
            proxies = await conn.fetch(query)

        if not proxies:
            logger.warning("В базе данных отсутствуют доступные прокси")
            return jsonify({"error": "No proxies available"}), 500

        proxy_count = len(proxies)
        logger.info(f"Получено {proxy_count} доступных прокси из базы данных")

        # Формируем список прокси для ответа
        proxy_list = [
            {
                "ip": proxy['ip'],
                "port": proxy['port'],
                "username": proxy['username'],
                "password": proxy['password'],
                "availability": proxy['availability']
            } for proxy in proxies
        ]

        return jsonify({"proxies": proxy_list}), 200
    except Exception as e:
        logger.error(f"Ошибка при получении списка прокси: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500
```

Deliverables   
ProxySession, ProxyPool, requested_article.  
Acceptance Criteria  
requested_article("https://stparts.ru/search?pcode=0PN1113H52") == "0PN1113H52".  
requested_article("https://stparts.ru/search/Hyundai-KIA/0PN1113H52?disableFiltering") == "0PN1113H52".  
Simulated 429 triggers backoff path.  
Pause Gate: Wait for GO P2  
---
P3 — HTML parsing (selectolax) for stparts
Purpose
Parse server-rendered results table. DOM obfuscation is ignored; article is stamped from URL.
Pydantic model (aligned to DB schema; warehouse → supplier)
```python
from pydantic import BaseModel
from decimal import Decimal

class OfferRow(BaseModel):
    source: str                   # "stparts" | "emex" | "autopiter" | "partkom"
    brand: str | None
    article: str                  # stamped from URL/request          
    name: str | None
    price: Decimal | None
    quantity: int | None
    supplier: str | None          # from td.resultWarehouse
    rating: int | None         # 0–100
    deadline_days: int | None     # latest day (max)
    is_analog: bool
```
Tasks
parser/parsers/stparts.py:
  * Table: table#searchResultsTable
  * Rows: tbody > tr.resultTr2
  * Row attrs:
    * data-brand, data-output-price, data-availability
    * data-deadline, data-deadline-max (hours)
    * data-is-analog, data-is-request-article (for filtering/QA)
  * Cells:
    * td.resultDescription → name
    * td.resultWarehouse → supplier
    * td.resultPrice (for currency detection; not stored)
  * Article: from URL (never DOM).
  * deadline_days:
    * if both: ceil(max(deadline, deadline_max)/24)
    * else if one present: ceil(value/24)
    * else: None
  * Analog toggle: default False (exclude rows where data-is-analog="1").
Deliverables
Pure function:
def parse_stparts(html: str, source_url: str, include_analogs: bool) -> list[OfferRow]:
Acceptance Criteria (with your local fixtures)
From tests/parser/page_with_disableFiltering.html, at least one row:
  * brand == "Hyundai-KIA"
  * article == "0PN1113H52" (from URL)
  * name == "КОЛЬЦО ФОРСУНКИ МЕТАЛЛИЧЕСКОЕ"
  * supplier == "UAE1893"
  * price == Decimal("38.07")
  * quantity == 243
  * deadline_days in {35, 36}
  * is_analog is False when include_analogs=False
With include_analogs=False, analog rows are excluded.
Pause Gate: Wait for GO P3
---
P4 — Pipeline (fetch → parse → lowest 10 per article) + SSE progress
Purpose
Run the fetch+parse loop in RAM (parse-while-scraping), cap to lowest 10 prices per article, and stream progress.
Tasks
parser/pipeline/stparts_run.py:
  * For each code:
    1. GET /search?pcode=<code>
    2. If “Показать все варианты” link present → follow absolute href
       * Else, if brand detected, attempt /search/<brand>/<code>?disableFiltering
       * Else, stick to initial page
    3. Parse rows with include_analogs
  * For each article, keep top-10 cheapest offers:
    * Filter out price is None
    * Sort by price ASC, quantity DESC, deadline days ASC
    * Take first 10
  * Return list[OfferRow] with source="stparts".
Progress: the pipeline reports to ProgressReporter (codes processed, rows found, warnings).
Deliverables
Working pipeline callable by Celery task.
Acceptance Criteria
For N codes, results have ≤10 offers per article.
Analog toggle respected.
Pause Gate: Wait for GO P4
---
P5 — ClickHouse persistence + Excel export + cleanup
Purpose
Persist results (TTL 4 months), export Excel in the wide “top-10 suppliers” layout your users expect, and delete exports older than 5 days.
---
ClickHouse DDL (final)
CREATE TABLE IF NOT EXISTS sup_stat.parser_offers
(
  run_id         UUID,
  fetched_at     DateTime DEFAULT now(),
  source         LowCardinality(String),
  brand          String,
  article        String,
  name           String,
  price          Decimal(12,2),
  quantity       UInt32,
  supplier       String,
  rating         Nullable(UInt8),      -- 0..100 where available
  deadline_days  UInt16,
  is_analog      UInt8
)
ENGINE = MergeTree
ORDER BY (article, source, supplier, price, deadline_days, fetched_at)
TTL fetched_at + INTERVAL 4 MONTH
SETTINGS index_granularity = 8192;

Notes
run_id groups a single job execution; fetched_at drives TTL.
source remains LowCardinality; rating is optional and nullable (0–100).
We insert top-10 cheapest per article upstream, but the table stays append-only for history.
---
Python model (aligned to DDL)
from pydantic import BaseModel
from decimal import Decimal

class OfferRow(BaseModel):
    source: str
    brand: str | None
    article: str
    name: str | None
    price: Decimal | None
    quantity: int | None
    supplier: str | None
    rating: int | None          # 0..100, None if not provided
    deadline_days: int | None
    is_analog: bool

---
Insert API
Module:parser/clickhouse_repo.py
insert_offers(run_id: UUID, rows: list[OfferRow]) -> None
 Batch insert rows. fetched_at defaults to now() server-side.
(Adapter: clickhouse-connect or your preferred client. Insert Decimal as string if you want exactness, otherwise float is acceptable.)
---
Excel export (wide “top-10 suppliers” layout)
Module:parser/excel_export.py
Layout per sheet (one sheet per source, e.g., "stparts"):
Row 1 (merged A1:…):source (e.g., stparts)
Row 2 (headers):
brand | article | price 1 | supplier 1 | quantity 1 | rating 1 | name 1 | price 2 | supplier 2 | quantity 2 | rating 2 | name 2 | ... | price 10 | supplier 10 | quantity 10 | rating 10 | name 10
Rows ≥3: one row per (brand, article) with up to 10 offers filled (sorted by price ASC, tie-breakers: quantity DESC, deadline_days ASC).
 Different suppliers may have different name i.
Shaping helper:pivot_offers_for_export(offers: Iterable[OfferRow]) -> pandas.DataFrame
 Groups by (brand, article), picks top-10 cheapest offers, expands into the wide columns above.
Writer:
export_offers_xlsx(run_id: UUID, source: str, df_wide: pandas.DataFrame, export_dir: Path) -> Path
 Writes:
Merge row 1 across all columns with source
Headers at row 2
Data from row 3
Freeze panes at row 3
Two-decimal number format on all price i columns
---
Cleanup
Module:parser/cleanup.py
delete_old_exports(older_than_days: int = 5) -> int
 Deletes Excel files in EXPORT_DIR older than N days (configurable). Returns count deleted.
---
End-to-end flow in this phase
Pipeline returns list[OfferRow] (already filtered to top-10 per article).
clickhouse_repo.insert_offers(run_id, rows) → persist to parser.offers.
pivot_offers_for_export(rows) → df_wide.
export_offers_xlsx(run_id, "stparts", df_wide, EXPORT_DIR) → path to {run_id}.xlsx.
Schedule delete_old_exports() daily (or run after each job) to prune files > N days.
---
Acceptance Criteria
DB: Inserted rows visible in parser.offers with correct types; rating present when provided, NULL otherwise.
Excel:
Row 1 is a merged cell containing stparts.
Row 2 header exactly equals:
brand, article, price 1, supplier 1, quantity 1, rating 1, name 1, ..., price 10, supplier 10, quantity 10, rating 10, name 10
For each (brand, article), at most 10 supplier blocks are filled, ordered by price ASC (tie: quantity DESC, then deadline_days ASC).
If fewer than 10 offers, remaining blocks are blank.
Different supplier names appear in their respective name i cells.
Cleanup: Files older than 5 days in EXPORT_DIR are deleted; the function reports the number removed.
Pause Gate: Wait for GO P5
---
Of course, Igor. Here is the plan for phase P5.5.

# P5.5 Frontend UI for `stparts` Parser

### Purpose

Create a user interface for the `stparts` parser, allowing users to upload an Excel file with articles to parse, monitor the progress in real-time, and see a summary of the results. This phase will mirror the UX and technical implementation of the existing `emex_upload` feature.

---

### Tasks

1.  **Update Dashboard (`core/templates/core/index.html`)**:
    *   Add a new "Парсеры" (Parsers Section) card to the main dashboard.
    *   The card will contain a link to a new view for the `stparts` parser.

2.  **Create Parser Views and URLs (`parser/views.py`, `parser/urls.py`)**:
    *   Create a view to display the file upload page for the `stparts` parser.
    *   Create a view to handle the POST request from the upload form. This view will:
        *   Accept an `.xlsx` file.
        *   Save the file temporarily.
        *   Dispatch a Celery task to process the file.
        *   Redirect the user to a status page where they can monitor the progress.
    *   Create an SSE (Server-Sent Events) view to stream the progress of the Celery task to the frontend, similar to the `emex_upload` implementation.
    *   Wire up these views in `parser/urls.py`.

3.  **Create HTML Templates (`parser/templates/parser/`)**:
    *   Create `stparts_upload.html`: A template with a form for uploading the `.xlsx` file. The form will have a single file input field.
    *   Create `stparts_upload_status.html`: A template to display the real-time progress of the parsing task. It will connect to the SSE endpoint and update the UI with the current step (e.g., "Парсим stparts"), the progress percentage, and a final report on how many articles failed to parse.

4.  **Update Celery Task (`parser/tasks.py`)**:
    *   The `run_stparts_job` task will be modified to:
        *   Accept a file path to the uploaded Excel file instead of a list of articles.
        *   Read the `brand` and `article` columns from the file.
        *   Use the `ProgressReporter` to send updates on the parsing progress (percentage of rows processed).
        *   Keep track of articles that fail to parse and include this count in the final result.

---

### Deliverables

*   A new "Парсеры" section on the main dashboard.
*   A new page at `/parser/` for uploading Excel files.
*   A real-time progress monitoring page for parsing jobs.
*   Updated Celery task capable of processing an uploaded file and reporting progress.

---

### Acceptance Criteria

*   тЬЕ The main dashboard at `/` displays a new card for "Парсеры".
*   тЬЕ Navigating to the parser page allows a user to upload an `.xlsx` file.
*   тЬЕ Upon upload, a background job is started, and the user is redirected to a status page.
*   тЬЕ The status page shows a "Парсер stparts" step with a progress percentage that updates in real-time.
*   тЬЕ After the job is complete, the page displays the number of articles that failed to parse.

---
P6 — Celery orchestration (tasks.py) + endpoints (UI-facing, SSE)
Purpose
Use ProgressReporter for SSE, expose endpoints to start jobs, stream progress, and download results.
Tasks
parser/tasks/tasks.py (orchestrator only)
  * @app.task(bind=True)
def run_stparts_job(self, job_id: str, codes: list[str], include_analogs: bool) -> dict:
    # create run_id
    # init ProgressReporter(job_id)
    # report started
    # call pipeline
    # CH insert, Excel export
    # report finished with download URL
    # return metadata
parser/views.py
  * POST /parser/jobs → { "codes": [...], "includeAnalogs": false } → returns { "jobId": "<id>" } and enqueues task
  * GET /parser/jobs/<job_id> → status JSON (lightweight)
  * GET /parser/jobs/<job_id>/events → SSE stream from ProgressReporter
  * GET /parser/jobs/<job_id>/result.xlsx → serves recent file by run_id
Wire routes in parser/urls.py.
Deliverables
Celery task wired to existing app.
Endpoints live and reachable.
Acceptance Criteria
Local run with 2–3 codes (using saved HTML) streams started → progress → finished.
Excel is downloadable.
Old exports auto-deleted by cleanup.
Pause Gate: Wait for GO P6
---
P7 — Scheduling (django-celery-beat) + minimal UI
Purpose
Allow scheduled runs and a basic page to try the flow; Analogs checkbox OFF by default.
Tasks
django-celery-beat entry to call run_stparts_job daily/cron with configured codes and include_analogs flag (default False).
Minimal UI at /parser/:
  * upload Excel (.xlsx) with brand,article
  * Checkbox "Include analogs" (unchecked by default)
  * Start button (POST /parser/jobs)
  * Progress console (SSE)
  * Download link when finished
Deliverables
Beat task registered.
Simple page to drive the flow.
Acceptance Criteria
Scheduled job fires and produces DB + Excel output.
By default, analogs are excluded; enabling checkbox includes them (still top-10 per article).
Pause Gate: Wait for GO P7
---
Approval Protocol (chat-based)
Approve a phase: GO P<n>
Request changes: REVISE P<n>: <instruction>
Abort: ABORT
  The agent must not proceed to the next phase without your explicit GO.
---
Notes on Compliance & Performance
Parse-while-scraping: do not persist HTML; parse immediately, discard from memory.
html = await fetch_html(url)
rows = parse_stparts(html, url, include_analogs)
html = None
Rotate proxies; back off on 429; swap proxy or TLS client on repeated 403; only consider headless fallback if you instruct.
---
Quick Parsing Example (from our fixture)
Given the disableFiltering page for 0PN1113H52, the agent extracts:
Select: table#searchResultsTable tbody tr.resultTr2
Row attrs (examples):
  * data-brand="Hyundai-KIA"
  * data-output-price="38.07" → Decimal("38.07")
  * data-availability="243" → 243
  * data-deadline="840" and maybe data-deadline-max="864" → deadline_days = ceil(max/24) = 35 or 36
  * data-is-analog="0"
Cells:
  * td.resultDescription → "КОЛЬЦО ФОРСУНКИ МЕТАЛЛИЧЕСКОЕ"
  * td.resultWarehouse → "UAE1893" → supplier
Article is stamped from URL (.../search/Hyundai-KIA/0PN1113H52?disableFiltering → "0PN1113H52").
With Analogs OFF (default), rows with data-is-analog="1" are not included.
Post-parse, the pipeline keeps lowest 10 by price ASC, quantity DESC, deadline_days ASC.
