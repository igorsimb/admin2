# Pricelens Frontend Implementation Plan

**Goal:** Develop a high-fidelity, interactive frontend prototype for the Pricelens feature using Django templates. All backend data will be simulated in the views to allow for rapid UI development and testing.

**Technology & Styling:**
*   Django Templates & HTML
*   **DaisyUI**: All components should be styled using DaisyUI classes to ensure visual consistency with the existing project. The UI should be clean, modern, and professional.

---

### Phase 1: Dashboard Foundation & "Yesterday's Failures" Widget

*   **Objective:** Establish the main dashboard page and display the top-level summary of daily failures.
*   **Steps:**
    1.  **Verify** the existing `pricelens` app structure, URL routing (`/pricelens/`), and the placeholder `DashboardView` and `dashboard.html` files.
    2.  **Modify** the `dashboard.html` template, ensuring it correctly extends the project's base layout (e.g., `core/_base.html`).
    3.  In `DashboardView`, generate static, dummy context data for:
        *   A summary dictionary (e.g., `{'failures': 127, 'suppliers': 15}`).
        *   A list of top failure reasons (e.g., `[{'error_text': 'File not found', 'cnt': 58}, ...]`).
    4.  Render this data in the template using DaisyUI components (e.g., `stats` and `card` components for the summary, and a styled list for the reasons).
    5. Current official fail reasons class:
    ```python

    class FailReasons(Enum):
       FILE_FORMAT_UNRECOGNIZED = "FILE_FORMAT_UNRECOGNIZED"  # неподдерживаемый формат файла (if file_format is None)
       FILE_READ_ERROR = "FILE_READ_ERROR"  # Ошибка чтения файла (файл поврежден или не читается)
    
       COLUMN_MISSING_VALUES = "COLUMN_MISSING_VALUES"  # Слишком много пропущенных значений (NaN/None > 50%)
       COLUMN_UNEXPECTED_NUMERIC = "COLUMN_UNEXPECTED_NUMERIC"  # В текстовом столбце слишком много числовых значений (>30%)
    
       BRAND_CROSS_MISMATCH = "BRAND_CROSS_MISMATCH"  # Данные не соответствуют таблице brand_cross
       SKU_FORMAT_INVALID = "SKU_FORMAT_INVALID"  # Артикулы не соответствуют требуемому формату (<70% совпадений)
    
       PRICE_TOO_LOW = "PRICE_TOO_LOW"  # Более 30% цен в файле ниже 9 рублей
       PRICE_DEVIATION_HIGH = "PRICE_DEVIATION_HIGH"  # Цены отклоняются от средней за неделю более чем на 30%
    
       VALUE_NEGATIVE = "VALUE_NEGATIVE"  # Количество содержит отрицательные значения или неверные числа
       UNEXPECTED_PROCESSING_ERROR = "UNEXPECTED_PROCESSING_ERROR"  # Любая другая неожиданная ошибка обработки
    
       DIF_STEP1_WRITE_ERROR = "DIF_STEP1_WRITE_ERROR" # Ошибка при записи в dif.dif_step_1
       NAME_PRICE_WRITE_ERROR = "NAME_PRICE_WRITE_ERROR" # Ошибка при записи в dif.name_price
       ROW_COUNT_THRESHOLD_EXCEEDED = "ROW_COUNT_THRESHOLD_EXCEEDED"  # Значительная разница в количестве строк между файлами


* **Testable Outcome:** You will be able to navigate to `/pricelens/`, see the main page layout, and view the "Yesterday's Failures" and "Top 5 Reasons" widgets populated with realistic dummy data and styled with DaisyUI.

---

### Phase 2: Dashboard Cadence & Anomaly Widgets

*   **Objective:** Complete the dashboard by adding the supplier consistency and anomaly widgets.
*   **Steps:**
    1.  Expand the dummy data in `DashboardView` to include:
        *   Consistency buckets (e.g., `[{'bucket': 'consistent', 'cnt': 85}, ...]`).
        *   A list of supplier anomalies (e.g., `[{'supid': 1234, 'days_since_last': 10}, ...]`).
    2.  Render the consistency buckets using a DaisyUI `stats` or `card` component.
    3.  Render the anomalies in a clean, sortable DaisyUI `table`.
*   **Testable Outcome:** The dashboard at `/pricelens/` will be visually complete, displaying all four data widgets populated with dummy data and styled with DaisyUI.

---

### Phase 3: The Investigation Queue Page

*   **Objective:** Build the main work queue where users can see all open investigations.
*   **Steps:**
    1.  Create the `QueueView` and the corresponding `pricelens/queue.html` template.
    2.  In `QueueView`, generate a list of 50-100 dummy "investigation" objects. Each will have a unique ID, `event_dt`, `supid`, `error_text`, and `stage`.
    3.  Implement Django's built-in `ListView` pagination and style it with DaisyUI's `join` component for the pagination controls.
    4.  Render the data in a well-structured DaisyUI `table`. Each row will have a link to the (not-yet-functional) investigation detail page.
*   **Testable Outcome:** You will be able to navigate to `/pricelens/queue/`, see a paginated list of investigations, and click through the pages.

---

### Phase 4: The Investigation Detail & Interaction

*   **Objective:** Build the page where a user can analyze and resolve a single investigation.
*   **Steps:**
    1.  Create the `InvestigationDetailView` and the `pricelens/investigate.html` template.
    2.  The view will accept a (dummy) ID from the URL and pass a single, hardcoded investigation object to the template.
    3.  The template will display all the details of the investigation inside a DaisyUI `card`.
    4.  Add a "Download source file" link styled as a `btn`.
    5.  Create a simple `<form>` with a "Notes" `textarea` and two `btn` elements: "Mark as Resolved" and "Mark as Unresolved".
    6.  Submitting the form will simply redirect back to the queue page, simulating the workflow.
*   **Testable Outcome:** You can click an item in the queue, see its detail page, type in the notes field, and click the action buttons to be redirected back to the queue.
