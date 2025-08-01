# Pricelens Backend Implementation Plan (TDD Approach)

**Goal:** To incrementally build and test the backend logic for the Pricelens feature, ensuring each component is robust before integrating it into the larger, distributed pipeline.

---

### Phase 1: The Database Foundation (Models & Migrations)

*   **Status:** ✅ **Complete**
*   **Objective:** Create the necessary database tables in the `admin2` Postgres database.
*   **Outcome:** The `pricelens_*` tables exist in the database, and unit tests confirm that model instances can be created and saved successfully.

---

### Phase 2: The Core Logic (The `log_investigation_event` Hook)

*   **Status:** ✅ **Complete**
*   **Objective:** Create and thoroughly test the utility function that will be the primary entry point for logging errors.
*   **Outcome:** A robust, unit-tested utility function `log_investigation_event` is ready for use by the API.

---

### Phase 2.5: The API Endpoint (Django Rest Framework)

*   **Status:** ⏳ **In Progress**
*   **Objective:** Expose the `log_investigation_event` functionality via a secure, versioned REST API endpoint.
*   **TDD Steps:**
    1.  Add `djangorestframework` to `requirements.txt`.
    2.  Create `tests/pricelens/test_api.py`.
    3.  Write failing tests to ensure the endpoint requires authentication and validates incoming data correctly.
    4.  Create `pricelens/serializers.py` to define the data shape for an investigation event.
    5.  Create `pricelens/api.py` with a DRF `APIView` or `ViewSet`.
    6.  Add the URL `/api/v1/pricelens/log_event/` to the project's root `urls.py`.
    7.  Run tests and refactor until they pass.
*   **Testable Outcome:** A new API endpoint is available at `http://87.242.110.159:8061/api/v1/pricelens/log_event/` that accepts authenticated `POST` requests.

---

### Phase 3: Cross-Service Integration (Instructions for You)

*   **Status:** 📋 **To Do**
*   **Objective:** Provide you with the exact code and instructions to call the new API endpoint from your external services.
*   **Steps (I will provide the code, you will apply it):**
    1.  **For `load_mail`, `load_ftp`, `consolidate`:** I will provide Python snippets using the `requests` library to make a `POST` call to the new API endpoint in the event of an error.
*   **Testable Outcome (Manual):** After you apply the changes, a manually triggered error in an external service will create a new `Investigation` record in the `admin2` database via the API.

---

### Phase 4: Backend Automation (Celery Tasks)

*   **Status:** 📋 **To Do**
*   **Objective:** Implement the scheduled Celery tasks that will perform daily data analysis and backfilling from ClickHouse.
*   **Outcome:** The Celery tasks will be implemented and have unit tests verifying their logic and database interactions.

---

### Phase 5: Connecting the Dots (Live Views)

*   **Status:** 📋 **To Do**
*   **Objective:** Replace the dummy data in the `pricelens` views with live queries to the Postgres database.
*   **Outcome:** The Pricelens UI will be fully powered by the backend database, and the test suite will verify this from end to end.