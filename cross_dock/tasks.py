"""
Celery tasks for cross-dock functionality.

This module contains Celery tasks for processing cross-dock data asynchronously.
"""

import logging
import os

from celery import shared_task
from django.conf import settings

from cross_dock.models import CrossDockTask
from cross_dock.services.excel_service import process_cross_dock_data_from_file

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def process_file_task(self, file_path, supplier_list, task_id):
    """
    Process the uploaded file in the background.

    Args:
        file_path: Path to the uploaded file
        supplier_list: Selected supplier list
        task_id: UUID of the CrossDockTask record
    """
    try:
        # Get the task record
        task = CrossDockTask.objects.get(id=task_id)

        # Mark as running
        task.mark_as_running()

        # Process the file
        output_file_path = process_cross_dock_data_from_file(file_path, supplier_list)
        output_filename = os.path.basename(output_file_path)
        output_url = f"{settings.MEDIA_URL}exports/{output_filename}"

        # Mark as success
        task.mark_as_success(output_url)

        # Clean up the input file
        try:
            os.remove(file_path)
            logger.info(f"Removed temporary upload file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to remove temporary upload file {file_path}: {e}")

        return {
            "status": "success",
            "task_id": task_id,
            "output_url": output_url
        }
    except Exception as e:
        logger.exception(f"Error processing file: {e}")
        
        # Try to mark the task as failed
        try:
            task = CrossDockTask.objects.get(id=task_id)
            task.mark_as_failed(str(e))
        except Exception as task_error:
            logger.exception(f"Error updating task status: {task_error}")
        
        # Clean up the input file
        try:
            os.remove(file_path)
            logger.info(f"Removed temporary upload file after error: {file_path}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to remove temporary upload file {file_path}: {cleanup_error}")
        
        # Re-raise the exception to mark the task as failed in Celery
        raise
