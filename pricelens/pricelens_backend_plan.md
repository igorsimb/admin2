# Pricelens Backend Implementation Plan (TDD Approach)

**Goal:** To incrementally build and test the backend logic for the Pricelens feature, ensuring each component is robust before integrating it into the larger, distributed pipeline.

---

### Phase 1: The Database Foundation (Models & Migrations)

*   **Objective:** Create the necessary database tables in the `admin2` Postgres database. This is the foundational layer for all other logic.
*   **TDD Steps:**
    1.  **Create Test File:** Create `tests/pricelens/test_models.py`.
    2.  **Write Failing Test:** The test will attempt to create an instance of the `Investigation` model and save it. It will fail because the model doesn't exist yet.
    3.  **Write Code:** Create the `Investigation`, `CadenceDaily`, and `CadenceProfile` models in `pricelens/models.py` as defined in the blueprint.
    4.  **Run Migrations:** Run `makemigrations` and `migrate` to create the tables in the test database.
    5.  **Run Test & Refactor:** The test should now pass.
*   **Testable Outcome:** The `pricelens_*` tables exist in the database, and a basic unit test confirms that model instances can be created and saved successfully.

---

### Phase 2: The Core Logic (The `log_investigation_event` Hook)

*   **Objective:** Create and thoroughly test the utility function that will be the primary entry point for logging errors from external services.
*   **TDD Steps:**
    1.  **Create Test File:** Create `tests/pricelens/test_utils.py`.
    2.  **Write Failing Tests:** Write tests that:
        *   Check if calling the function creates a new `Investigation` record.
        *   Check if calling the function a second time with the *exact same arguments* does **not** create a duplicate record (testing for idempotency).
        *   These will fail as the function doesn't exist.
    3.  **Write Code:** Create the `log_investigation_event` function in a new `pricelens/utils.py` file.
    4.  **Run Test & Refactor:** The tests should now pass, proving the function is correct and safe to call multiple times.
*   **Testable Outcome:** A robust, unit-tested utility function `log_investigation_event` is ready for integration.

---

### Phase 3: Cross-Service Integration (Instructions for You)

*   **Objective:** Provide you with the exact code and instructions to hook the `log_investigation_event` function into your external services.
*   **Steps (I will provide the code, you will apply it):**
    1.  **For `load_mail`:** I will provide a Python snippet showing how to import and call `log_investigation_event` from within the error handling blocks of your `load_mail` service (e.g., in the `except` block for a `FILE_READ_ERROR`).
    2.  **For `load_ftp`:** Similar to `load_mail`, I will provide the snippet for its error handling.
    3.  **For `consolidate`:** I will provide the snippet for its validation and error handling sections.
*   **Testable Outcome (Manual):** After you apply the changes, you can manually trigger an error in one of the services (e.g., send a corrupted file to the email inbox). You can then verify that a new record appears in the `pricelens_investigation` table in the `admin2` database.
* Edit:
* From load_mail, here's an example of where we send a message to the chat. So we should probably ingest log_investigation_event into every instance of send_message_to_chat use (do I understand it correctly?):
```python
def exel_reader(dateupd: datetime.date, supid: int, brand: int, articles: int, price: int, quantity: int, name: int,
                file_path: str, skip: int = 0) -> pd.DataFrame | None:
    logger.info(f"Начинаем чтение Excel файла: {file_path}")
    logger.debug(f"Параметры чтения: supid={supid}, пропуск строк={skip}")
    logger.debug(
        f"Индексы колонок: бренд={brand}, артикул={articles}, наименование={name}, цена={price}, количество={quantity}")
    
    if Path(file_path).stat().st_size == 0:
        reason = FailReasons.FILE_READ_ERROR
        logger.error(f"[{reason.value}] Файл пуст: {file_path}")
        message = f"[{reason.value}] Файл {Path(file_path).name} поставщика {get_sup_name(supid)} ({supid}) пуст"
        send_message_to_chat(f"{message} #LoadMail.")
        save_failed_file(supid, file_path, reason)
        return None
```
---

### Phase 4: Backend Automation (Celery Tasks)

*   **Objective:** Implement the scheduled Celery tasks that will perform daily data analysis and backfilling from ClickHouse.
*   **TDD Steps:**
    1.  **Create Test File:** Create `tests/pricelens/test_tasks.py`.
    2.  **Write Failing Tests:** For each task (`refresh_cadence_profiles`, `backfill_investigations`), write a test that calls the task function directly. These tests will use `mock.patch` to simulate the `get_clickhouse_client` and provide fake return data. The tests will assert that the correct Django models are created or updated.
    3.  **Write Code:** Implement the tasks in `pricelens/tasks.py` and add their schedules to `config/third_party_config/celery.py`.
    4.  **Run Test & Refactor:** The tests should pass, proving the tasks' logic is correct without needing a live ClickHouse connection.
*   **Testable Outcome:** The Celery tasks are implemented and have unit tests verifying their logic and database interactions.

---

### Phase 5: Connecting the Dots (Live Views)

*   **Objective:** Replace the dummy data in the `pricelens` views with live queries to the Postgres database.
*   **TDD Steps:**
    1.  **Update View Tests:** Modify the tests in `tests/pricelens/test_views.py`.
    2.  **Write Failing Tests:** The tests will now create dummy `Investigation` and `CadenceProfile` objects in the test database. They will then assert that the view's context contains the specific data from those objects (e.g., `assert response.context['summary']['failures'] == 5`).
    3.  **Write Code:** Update the `get_context_data` and `get_queryset` methods in `pricelens/views.py` to perform real database queries using the Django ORM.
    4.  **Run Test & Refactor:** The view tests will pass, confirming the frontend is now correctly displaying data from the database.
*   **Testable Outcome:** The Pricelens UI is fully powered by the backend database, and the test suite verifies this from end to end.
