## Ground rules

* **Wire format** must remain exactly as today:

  * Generic step payload: `{"step", "status", "sub_step_name"?, "sub_step_index"?, "details"?}`.
  * Percentage progress: `{"step": "INSERTING", "status": "IN_PROGRESS", "progress": <0–100>}`.
  * Final task result: `{"status": "COMPLETE", "result": {...}}`.
* **SSE** contract / views remain unchanged.
* **UI** timelines & radial progress keep working as-is. Sub-steps are rendered as static `<li>` lists and currently updated by **index** lookup (`parentUl.children[sub_step_index]`).

---

## Phase 1 — Introduce `core/reporting.py` (no call sites changed)

**Purpose**
Add reusable reporter with exact payload shapes. No other files touched.

**Deliverable** `core/reporting.py`

```python
import time
from enum import Enum
from typing import Any


class ReportStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    # Optional for future clarity with sub-steps. Not emitted by default.
    PENDING = "PENDING"


class ProgressReporter:
    def __init__(
        self,
        *,
        task: Any,
        state_name: str = "PROGRESS",
        delay_between_report_steps_sec: float | None = None,
    ) -> None:
        self._task = task
        self._state_name = state_name
        self._delay = delay_between_report_steps_sec

    def _sleep_if_needed(self) -> None:
        if self._delay:
            time.sleep(self._delay)

    def report_step(
        self,
        *,
        step: str,
        status: ReportStatus,
        sub_step_name: str | None = None,
        sub_step_index: int | None = None,
        details: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "step": step,
            "status": status.value,
            "sub_step_name": sub_step_name,
            "sub_step_index": sub_step_index,
        }
        if details is not None:
            payload["details"] = details
        if message is not None:
            payload.setdefault("details", {})
            payload["details"]["message"] = message

        self._task.update_state(state=self._state_name, meta=payload)
        self._sleep_if_needed()

    def report_percentage(self, *, step: str, progress: int) -> None:
        payload = {
            "step": step,
            "status": ReportStatus.IN_PROGRESS.value,
            "progress": int(progress),
        }
        self._task.update_state(state=self._state_name, meta=payload)
        self._sleep_if_needed()

    def report_failure(self, *, step: str, details: dict[str, Any] | None = None) -> None:
        self.report_step(step=step, status=ReportStatus.FAILURE, details=details)

    def finalize(self, *, result: dict[str, Any]) -> dict[str, Any]:
        return {"status": "COMPLETE", "result": result}
```

**Notes**

* Added `PENDING` to `ReportStatus` for potential future explicit “queued/not started” events; **we will not emit it** until you explicitly approve. Current UI already renders a pending icon locally before messages arrive.

**Acceptance**

* File exists, API matches.
* No other files changed.
* Local unit tests for payload shapes pass.

**STOP. Await your approval before Phase 2.**

---

## Phase 2 — Refactor services to use reporter (no task logic change)

**Purpose**
Replace direct progress emissions in services with `ProgressReporter`. Keep result dicts the same.

**Changes**

* In validation services: replace emits with `reporter.report_step(...)` (include both `sub_step_index` and **now** `sub_step_name`).
* In insertion: use `reporter.report_percentage(step="INSERTING", progress=p)`.

**Compatibility**

* Keep `sub_step_index` because the current JS updates sub-steps by index.
* Keep step names exactly as the UI maps them to DOM IDs.
* Final result dict unchanged.

**Acceptance**

* Services emit via reporter only.
* Payload shapes identical; added `sub_step_name` is additive.
* Manual run: timeline & error texts still behave as before.

**STOP. Await your approval before Phase 2.5.**

---

## Phase 2.5 — Frontend: prefer `sub_step_name`, fallback to index (tiny, safe)

**Purpose**
Teach the UI to look up sub-steps by **name** first, falling back to **index**. This enables backend to add/rename/reorder sub-steps without breaking the UI list mapping.

**Change (only in `upload_status.html`)**
Patch `handleProgressUpdate` where it handles sub-steps:

```js
function handleProgressUpdate(payload) {
    const { step, status, details, sub_step_index, sub_step_name } = payload;

    if (sub_step_index !== undefined || sub_step_name !== undefined) {
        const parentIdMap = {
            "row integrity & type coercion": "sub-steps-row-integrity",
            "business rule validation": "sub-steps-business-rules"
        };
        const parentUlId = parentIdMap[(step || "").toLowerCase()];
        if (parentUlId) {
            const parentUl = document.getElementById(parentUlId);

            let subStepElement = null;

            // Prefer name lookup when available
            if (sub_step_name) {
                const children = Array.from(parentUl.children);
                subStepElement = children.find(li => {
                    const text = li.textContent || "";
                    return text.toLowerCase().includes(sub_step_name.toLowerCase());
                }) || null;
            }

            // Fallback to index when needed
            if (!subStepElement && sub_step_index !== undefined) {
                subStepElement = parentUl.children[sub_step_index] || null;
            }

            updateSubStepItem(subStepElement, status, details);
        }
        return;
    }

    // (parent-step handling stays unchanged)
}
```

* Current JS initializes all icons to “pending” and updates them per message; this remains unchanged.
* Parent-step mapping (e.g., “Reading File”, “Header Validation”, etc.) remains unchanged.

**OPTIONAL (even safer selector)**
Add `data-substep="...exact name..."` attributes to each `<li>` and switch to a precise selector:

```js
subStepElement = parentUl.querySelector(`[data-substep="${CSS.escape(sub_step_name)}"]`);
```

(No visual change; just a more robust lookup.)

**Acceptance**

* When backend sends both `sub_step_name` and `sub_step_index`, UI uses **name** if it matches; otherwise index.
* Existing flows behave the same when names aren’t provided (index path unchanged).

**STOP. Await your approval before Phase 3.**

---

## Phase 3 — Tasks: pass reporter (no orchestration change)

**Purpose**
Instantiate and pass `ProgressReporter` to services in Celery tasks; keep generator orchestration and returns intact.

**Acceptance**

* Task returns still `{"status":"COMPLETE","result":...}`.
* SSE contract unchanged; radial progress still updates by percentage. (Insertion progress logic in UI remains the same.)

**STOP. Await your approval before Phase 4.**

---

## Phase 4 — (Optional) Convert validation generator → plain function

**Purpose**
Simplify control flow internally; keep external behavior.

**Acceptance**

* No UI/contract changes; payloads identical.
* Tests/snapshots show no drift.

**STOP. Await your approval before Phase 5.**

---

## Phase 5 — (Optional) Tiny DX sugar (no behavior change)

**Purpose**
Add a helper alias without altering payloads:

```python
def report_substep(self, *, step: str, index: int, **kwargs) -> None:
    self.report_step(step=step, sub_step_index=index, **kwargs)
```

**Acceptance**

* Purely ergonomic; payloads identical.

---

## DX example (updated to include names + indices)

```python
from core.reporting import ProgressReporter, ReportStatus

def full_process_example(task):
    reporter = ProgressReporter(task=task, delay_between_report_steps_sec=0.5)

    reporter.report_step(step="Reading File", status=ReportStatus.IN_PROGRESS)
    # ... read file ...
    reporter.report_step(step="Reading File", status=ReportStatus.SUCCESS)

    reporter.report_step(step="Business Rule Validation", status=ReportStatus.IN_PROGRESS)

    all_passed = True

    # sub-step 0 (also named)
    errors = 15
    st = ReportStatus.SUCCESS if errors == 0 else ReportStatus.FAILURE
    if st is ReportStatus.FAILURE:
        all_passed = False
    reporter.report_step(
        step="Business Rule Validation",
        sub_step_name="Проверка формата 'склад'",
        sub_step_index=0,
        status=st,
        message=f"Строк с ошибками: {errors}",
    )

    # sub-step 1 (also named)
    errors = 0
    st = ReportStatus.SUCCESS if errors == 0 else ReportStatus.FAILURE
    if st is ReportStatus.FAILURE:
        all_passed = False
    reporter.report_step(
        step="Business Rule Validation",
        sub_step_name="Проверка, что кол-во * цена = общая сумма",
        sub_step_index=1,
        status=st,
        message="OK",
    )

    final_status = ReportStatus.SUCCESS if all_passed else ReportStatus.FAILURE
    reporter.report_step(step="Business Rule Validation", status=final_status)

    total_rows = 1000
    for i in range(0, total_rows, 100):
        # ... insert 100 rows ...
        pct = int(((i + 100) / total_rows) * 100)
        reporter.report_percentage(step="INSERTING", progress=pct)

    final_payload = {
        "original_row_count": 5000,
        "problematic_row_count": 15,
        "error_summary": {"Проверка формата 'склад'": 15},
        "clean_file_path": "/path/to/clean.pkl",
    }
    return reporter.finalize(result=final_payload)
```
