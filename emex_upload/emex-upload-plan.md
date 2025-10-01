# Emex Data Upload and Processing Plan (v2)

## 1. Project Overview

The goal is to create a feature within the `emex_upload` Django app that allows users to upload a TSV file containing sales data. This data will be cleaned, validated, and inserted into the `sup_stat.emex_dif` ClickHouse table.

This plan incorporates a user-in-the-loop validation workflow, robust data cleaning with `pyjanitor`, and a final phase for asynchronous processing of large files using Celery.

**Key Considerations:**
- **Database Schema:** We will add a new `uploaded_at` column (`Date`) to the `sup_stat.emex_dif` table.
- **UI/UX:** The interface will use **Tailwind/DaisyUI** to match the existing project style.
- **Data Cleaning:** We will map Russian column names to clean English names for processing, use `pyjanitor.currency_column_to_numeric` for currency fields, and handle data type conversions.
- **Data Validation:** The process will check for missing columns and data integrity (`Количество * Цена == Сумма`).
- **User-in-the-Loop Feedback:** For a low number of errors, rows will be dropped automatically. For a high number, the user will be prompted for confirmation before proceeding.
- **Asynchronous Processing:** A final phase will introduce Celery to handle large file uploads in the background, providing progress feedback to the user.

---

## Phased Implementation

### Phase 1: Frontend UI and Basic Django Setup

**Purpose**: To create the user-facing file upload interface using DaisyUI components and the necessary Django wiring.

**Tasks**:
1.  **Create HTML Template**:
    -   Develop `emex_upload/templates/emex_upload/upload.html`.
    -   The template will use **DaisyUI components** (e.g., `file-input`, `card`, `btn`) to create a form that is visually consistent with `core/index.html`.
2.  **Create Django Form**:
    -   Create `emex_upload/forms.py` with a `FileUploadForm`.
3.  **Create View**:
    -   In `emex_upload/views.py`, create `upload_file_view` to render the form. The POST handler will be a placeholder.
4.  **Configure URLs**:
    -   **Update** the existing `emex_upload/urls.py` to define a path for the `upload_file_view`.
    -   Include the `emex_upload` URLs in `config/urls.py` at `/emex-upload/`.

**Deliverables**:
-   `emex_upload/templates/emex_upload/upload.html`
-   `emex_upload/forms.py`
-   `emex_upload/views.py` (updated)
-   `emex_upload/urls.py` (updated)
-   `config/urls.py` (updated)

**Acceptance Criteria**:
-   A user can navigate to `/emex-upload/`.
-   The page displays a DaisyUI-styled form for file uploads.

---

### Phase 2: Data Cleaning and Validation Service

**Purpose**: To build the core data processing logic with a clear, maintainable mapping for column names.

**Tasks**:
1.  **Create Service Module**:
    -   Create `emex_upload/services.py`.
2.  **Develop Processing Function**:
    -   Implement `process_emex_file(file_obj)` that performs the following:
        1.  **Column Name Mapping**:
            -   Define a dictionary to map Russian column names to clean **English** names (e.g., `{'Дата': 'date', 'Арт': 'article', 'Количество': 'quantity'}`).
            -   Read the TSV and immediately rename columns using the map.
        2.  **Initial Validation**:
            -   Check if all expected columns are present after renaming. If not, raise a validation error.
        3.  **Type Conversion**:
            -   Convert the `date` column to datetime objects, then extract the date part (`YYYY-MM-DD`).
            -   Use `pyjanitor.currency_column_to_numeric` on the `purchase_price`, `purchase_total`, `sale_price`, and `sale_total` columns to handle decimal commas and convert to numeric types.
        4.  **Data Integrity Validation**:
            -   Check for mismatches: `(quantity * purchase_price) != purchase_total` and `(quantity * sale_price) != sale_total`. Flag invalid rows.
        5.  **Add Upload Timestamp**:
            -   Add the `uploaded_at` column, populating it with the current UTC date (`YYYY-MM-DD`).
        6.  **Final Transformation**:
            -   Before returning, rename the columns **back to Russian** to match the ClickHouse schema.
            -   Return the DataFrame and a summary of validation errors (e.g., count of invalid rows, types of errors).
3.  **Write Unit Tests**:
    -   Create `tests/emex_upload/test_services.py` to test the service, including the column mapping, validation, and type conversions.

**Deliverables**:
-   `emex_upload/services.py`
-   `tests/emex_upload/test_services.py`

**Acceptance Criteria**:
-   The service correctly processes a file using English column names internally.
-   The service identifies rows with missing columns or calculation errors.
-   Unit tests pass.

---

### Phase 3: ClickHouse Integration

**Purpose**: To handle the database schema migration and create the data insertion logic.

**Tasks**:
1.  **Update ClickHouse Schema**:
    -   The following non-destructive SQL command needs to be executed on ClickHouse:
      ```sql
      ALTER TABLE sup_stat.emex_dif ADD COLUMN uploaded_at Date;
      ```
    -   **Note**: This is a metadata-only operation in ClickHouse and will not modify or corrupt existing data. Existing rows will have a default empty/null value for this new column.
2.  **Create Insertion Service**:
    -   In `emex_upload/services.py`, create `insert_data_to_clickhouse(df)`.
    -   This function will use the `get_clickhouse_client` from `common.utils.clickhouse` (`readonly=0`) to insert the DataFrame data.
3.  **Write Mocked Tests**:
    -   In `tests/emex_upload/test_services.py`, add mocked tests for the insertion logic to verify the correct query and data are passed to the client.

**Deliverables**:
-   SQL statement for schema migration (documented here).
-   `emex_upload/services.py` (updated).
-   `tests/emex_upload/test_services.py` (updated).

**Acceptance Criteria**:
-   The `insert_data_to_clickhouse` function correctly calls the (mocked) database client.
-   The `uploaded_at` column in the prepared data is a `Date` type.

---

### Phase 4: Asynchronous Validation with Real-Time UI Feedback
**Purpose**: To offload file validation to a background Celery task and provide granular, real-time feedback to the user with a DaisyUI timeline, powered by HTMX and Server-Sent Events (SSE).

**Tasks**:
1.  **Create Celery Validation Task**:
    -   In `emex_upload/tasks.py`, create `validate_emex_file_task`.
    -   This task will be a thin wrapper that accepts a temporary file path and orchestrates calls to the validation logic.
    -   The core business logic for validation will remain in `emex_upload/services.py`. The task's purpose is to find and count errors, not to implement the logic itself.
2.  **Implement Granular Progress Updates**:
    -   The task will report its state after each major validation step is called from the service layer.
    -   It will use `self.update_state(state='PROGRESS', meta={'step': '...', 'status': '...', 'details': '...' })` to send structured updates.
    -   Example steps: `HEADER_VALIDATION`, `ROW_INTEGRITY`, `BUSINESS_RULES`, `CALCULATION_CHECKS`.
3.  **Create Status Template**:
    -   Create `emex_upload/templates/emex_upload/upload_status.html`.
    -   This template will contain the DaisyUI vertical timeline structure. Each `<li>` element will have an ID corresponding to a validation step (e.g., `id="timeline-step-headers"`).
    -   It will also include a target div for HTMX to render the final confirmation buttons.
4.  **Create SSE View**:
    -   In `emex_upload/views.py`, create a view that takes a `task_id`, reads the task's status from the Celery result backend, and streams it as an SSE event.
5.  **Update `upload_file_view`**:
    -   On POST, the view will save the uploaded file to a temporary location.
    -   It will trigger `validate_emex_file_task.delay(temp_file_path)`.
    -   It will render the `upload_status.html` template, passing the `task_id`.
6.  **Integrate HTMX for SSE**:
    -   The `upload_status.html` template will use `hx-ext="sse"` to connect to the SSE view.
    -   HTMX will listen for `sse:message` events and dynamically add success/error classes to the timeline items, making them change color as the backend task progresses.

**Deliverables**:
-   `emex_upload/tasks.py` with `validate_emex_file_task`.
-   `emex_upload/templates/emex_upload/upload_status.html`.
-   New SSE view and updated `upload_file_view` in `emex_upload/views.py`.

**Acceptance Criteria**:
-   Uploading a file redirects to a status page showing a DaisyUI timeline.
-   The timeline items turn green in real-time as validation steps are completed by the Celery worker.
-   The process is fully asynchronous.

---

### Phase 5: Conditional Data Insertion and Finalization
**Purpose**: To implement the final user confirmation step and trigger the database insertion based on the number of validation errors reported by the background task.

**Tasks**:
1.  **Define Configurable Threshold**:
    -   In a relevant location (e.g., `emex_upload/views.py` or a new `constants.py`), define `ACCEPTABLE_ERROR_THRESHOLD = 100`. This ensures the value is not hardcoded and is easily changed.
2.  **Create Insertion Celery Task**:
    -   In `emex_upload/tasks.py`, create `insert_emex_data_task`.
    -   This task will be a thin wrapper that accepts a file path, calls the service-layer functions to re-process the file (getting the clean DataFrame), and then calls `insert_data_to_clickhouse`.
3.  **Finalize SSE Event Stream**:
    -   The `validate_emex_file_task` will send a final event with `status: 'COMPLETE'` and `meta: {'problematic_rows': count}`.
4.  **Update Frontend for Confirmation**:
    -   The `upload_status.html` template will have a hidden `div` containing the "Confirm Upload" and "Cancel" buttons.
    -   An HTMX handler will listen for the `COMPLETE` SSE event.
    -   **If `problematic_rows <= ACCEPTABLE_ERROR_THRESHOLD`**: HTMX will automatically make a POST request to a new endpoint to trigger the insertion task.
    -   **If `problematic_rows > ACCEPTABLE_ERROR_THRESHOLD`**: HTMX will make the confirmation `div` visible, allowing the user to click "Confirm Upload".
5.  **Create Confirmation Endpoint**:
    -   Create a new view, `confirm_upload_view`, that the "Confirm Upload" button (or the automatic trigger) will POST to.
    -   This view will receive the temporary file path and trigger the `insert_emex_data_task.delay()`.
    -   It will return a response that redirects the user back to the main upload page with a success message.

**Deliverables**:
-   `emex_upload/tasks.py` updated with `insert_emex_data_task`.
-   `upload_status.html` updated with confirmation logic.
-   New `confirm_upload_view` in `emex_upload/views.py`.
-   Updated URL configuration.

**Acceptance Criteria**:
-   If validation finds more than `ACCEPTABLE_ERROR_THRESHOLD` errors, the user is presented with "Confirm Upload" and "Cancel" buttons.
-   If validation finds `ACCEPTABLE_ERROR_THRESHOLD` or fewer errors, the data is automatically sent for insertion into ClickHouse.
-   Clicking "Confirm Upload" successfully triggers the background insertion task.