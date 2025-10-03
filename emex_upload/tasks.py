from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from loguru import logger

from config.third_party_config.celery import app
from emex_upload.services import get_validation_summary


@app.task(bind=True)
def validate_emex_file_task(self, file_path: str):
    """
    Celery task to validate an uploaded Emex file by calling the validation service.

    This task orchestrates the validation process and reports progress back to the user.
    """
    logger.info(f"Starting validation for file: {file_path}")
    self.update_state(state="PROGRESS", meta={"step": "File Received", "status": "IN_PROGRESS"})

    try:
        file_path_obj = Path(file_path)
        with open(file_path_obj, "rb") as f:
            # Wrap the file in a Django-compatible object for the service layer
            uploaded_file = SimpleUploadedFile(name=file_path_obj.name, content=f.read())

        self.update_state(state="PROGRESS", meta={"step": "File Received", "status": "SUCCESS"})

        errors, original_count, problematic_count, _ = get_validation_summary(
            file_obj=uploaded_file, task=self
        )

        result = {
            "status": "COMPLETE",
            "original_row_count": original_count,
            "problematic_row_count": problematic_count,
            "error_summary": {k: v for k, v in errors.items() if v},
        }
        logger.info(f"Finished validation for file: {file_path}. Result: {result}")
        return result

    except Exception as e:
        logger.error(f"Validation task failed for file {file_path}: {e}")
        self.update_state(
            state="FAILURE",
            meta={
                "step": "Task Execution",
                "status": "FAILURE",
                "details": f"An unexpected error occurred: {e}",
            },
        )
        # Re-raise the exception to mark the task as failed in Celery
        raise
