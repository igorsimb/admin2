"""
Lightweight progress reporting primitives for Celery tasks.

How to use
----------
1) Instantiate a reporter in your Celery task (tasks.py) and pass it to services:

    from core.reporting import ProgressReporter, ReportStatus

    @app.task(bind=True)
    def my_task(self):
        reporter = ProgressReporter(task=self, delay_between_report_steps_sec=1.0)
        result = run_service(reporter=reporter)
        return {"status": "COMPLETE", **result}

2) Emit step, sub-step and percentage updates from services using the reporter:

    from core.reporting import ProgressReporter, ReportStatus

    def run_service(*, reporter: ProgressReporter) -> dict:
        reporter.report_step(step="Reading File", status=ReportStatus.IN_PROGRESS)
        # ... do work ...
        reporter.report_step(step="Reading File", status=ReportStatus.SUCCESS)

        reporter.report_step(step="Business Rule Validation", status=ReportStatus.IN_PROGRESS)

        # named sub-step with index for compatibility with current UI
        reporter.report_step(
            step="Business Rule Validation",
            sub_step_name="Проверка формата 'склад'",
            sub_step_index=0,
            status=ReportStatus.FAILURE,
            message="Строк с ошибками: 15",
        )

        # percentage progress example
        for pct in (10, 40, 70, 100):
            reporter.report_percentage(step="INSERTING", progress=pct)

        # Return the final payload; the task will wrap it as {"status":"COMPLETE", "result": ...}
        return {
            "original_row_count": 5000,
            "problematic_row_count": 15,
            "error_summary": {"Проверка формата 'склад'": 15},
            "clean_file_path": "/path/to/clean.pkl",
        }
"""

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
    def __init__(self, *, task: Any, state_name: str = "PROGRESS",
                 delay_between_report_steps_sec: float | None = None) -> None:
        self._task = task
        self._state_name = state_name
        self._delay = delay_between_report_steps_sec

    def _sleep_if_needed(self) -> None:
        if self._delay:
            time.sleep(self._delay)

    def report_step(self, *, step: str, status: ReportStatus, sub_step_name: str | None = None,
                    sub_step_index: int | None = None, details: dict[str, Any] | None = None,
                    message: str | None = None) -> None:
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
