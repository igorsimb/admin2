"""Celery tasks for the parser app."""
from loguru import logger

from parser.services import run_stparts_parsing_service

try:
    from config.third_party_config.celery import app
    from core.reporting import ProgressReporter
except ImportError:
    # Fallback for environments where celery is not configured
    class DummyApp:
        def task(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

    app = DummyApp()

    class ProgressReporter:
        """
        Fallback implementation of the ProgressReporter interface for testing in isolation.
        """
        def __init__(self, task, **kwargs):
            self.task = task

        def report_percentage(self, step: str, progress: int):
            self.task.update_state(state="PROGRESS", meta={"step": step, "progress": progress})

        def report_step(self, step: str, status: str, **kwargs):
            self.task.update_state(state="PROGRESS", meta={"step": step, "status": status, **kwargs})

        def report_failure(self, step: str, details: dict):
            self.task.update_state(state="FAILURE", meta={"step": step, "details": details})


@app.task(bind=True)
def run_stparts_parser_task(self, file_path: str, include_analogs: bool):
    """
    Celery task that orchestrates the stparts parsing process by calling the main service function.
    """
    logger.info(f"Starting stparts parser task for file: {file_path}")
    try:
        reporter = ProgressReporter(task=self, delay_between_report_steps_sec=0.5)
        result = run_stparts_parsing_service(file_path=file_path, include_analogs=include_analogs, reporter=reporter)
        logger.info(f"Finished stparts parser task for file: {file_path}. Result: {result}")
        return result
    except Exception:
        logger.error(f"Stparts parser task for {file_path} failed catastrophically.", exc_info=True)
        # The service layer should have already reported the failure step via the reporter.
        # We re-raise to mark the task as FAILED in Celery.
        raise