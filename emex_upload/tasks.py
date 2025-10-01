from pathlib import Path
import pandas as pd
from loguru import logger

from config.third_party_config.celery import app
from emex_upload.services import validate_file_and_animate_progress, insert_data_to_clickhouse


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
        with open(file_path_obj, "rb") as f:
            # The service function is now a generator that yields progress
            progress_generator = validate_file_and_animate_progress(f, self)
            for progress_update in progress_generator:
                # The final yield will have a 'COMPLETE' status
                if progress_update.get("status") == "COMPLETE":
                    final_result = progress_update["result"]
                    break

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
    self.update_state(state='PROGRESS', meta={'step': 'INSERTING', 'status': 'IN_PROGRESS'})
    try:
        if not clean_file_path:
            raise ValueError("No clean file path provided for insertion.")

        df = pd.read_pickle(clean_file_path)
        
        success, message = insert_data_to_clickhouse(df, task=self)

        if not success:
            raise RuntimeError(f"ClickHouse insertion failed: {message}")

        logger.info(f"Successfully inserted data from file: {clean_file_path}")
        return {"status": "SUCCESS", "message": message}

    except Exception as e:
        logger.error(f"Data insertion task for {clean_file_path} failed: {e}", exc_info=True)
        self.update_state(state='FAILURE', meta={'step': 'INSERTING', 'status': 'FAILURE', 'details': str(e)})
        # Re-raise the exception so the task fails in Celery
        raise