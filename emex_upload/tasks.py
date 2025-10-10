from pathlib import Path
import pandas as pd
from loguru import logger

from config.third_party_config.celery import app
from emex_upload.services import validate_file_and_animate_progress, insert_data_to_clickhouse
from core.reporting import ProgressReporter, ReportStatus


def convert_sets_to_lists(obj):
    """Recursively convert sets to lists in a dictionary for JSON serialization."""
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, dict):
        return {k: convert_sets_to_lists(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_sets_to_lists(i) for i in obj]
    return obj


@app.task(bind=True)
def validate_emex_file_task(self, file_path: str):
    """
    Celery task to validate an uploaded Emex file by calling the validation service.
    This task orchestrates the validation process and reports progress back to the user.
    """
    logger.info(f"Starting validation for file: {file_path}")

    try:
        file_path_obj = Path(file_path)
        final_result = None
        reporter = ProgressReporter(task=self, delay_between_report_steps_sec=1.0)
        with open(file_path_obj, "rb") as f:
            final_result = validate_file_and_animate_progress(f, reporter)

        if not final_result:
            raise ValueError("Validation did not produce a final result.")

        # The result from the validation task now includes the path to the clean file
        result = {
            "status": "COMPLETE",
            "original_row_count": final_result["original_row_count"],
            "problematic_row_count": final_result["problematic_row_count"],
            "error_summary": convert_sets_to_lists(final_result["error_summary"]),
            "clean_file_path": final_result.get("clean_file_path"),
        }
        logger.info(f"Finished validation for file: {file_path}. Result: {result}")
        return result

    except Exception:
        logger.error(f"Validation task for {file_path} failed catastrophically.", exc_info=True)
        raise

@app.task(bind=True)
def insert_emex_data_task(self, clean_file_path: str):
    """
    Celery task to insert a clean Emex data file into ClickHouse.
    """
    logger.info(f"Starting data insertion for file: {clean_file_path}")
    reporter = ProgressReporter(task=self, delay_between_report_steps_sec=1.0)
    reporter.report_step(step="INSERTING", status=ReportStatus.IN_PROGRESS)
    try:
        if not clean_file_path:
            raise ValueError("No clean file path provided for insertion.")

        df = pd.read_pickle(clean_file_path)
        
        success, message = insert_data_to_clickhouse(df, reporter=reporter)

        if not success:
            raise RuntimeError(f"ClickHouse insertion failed: {message}")

        logger.info(f"Successfully inserted data from file: {clean_file_path}")
        return {"status": "SUCCESS", "message": message}

    except Exception as e:
        logger.error(f"Data insertion task for {clean_file_path} failed: {e}", exc_info=True)
        reporter.report_failure(step="INSERTING", details={"error": str(e)})
        # Re-raise the exception so the task fails in Celery
        raise