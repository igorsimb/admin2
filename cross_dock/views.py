import logging
import os
import uuid

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.generic import ListView

from cross_dock.models import CrossDockTask
from cross_dock.services.excel_service import process_cross_dock_data_from_file

logger = logging.getLogger(__name__)


def index(request):
    supplier_lists = ["Группа для проценки ТРЕШКА", "ОПТ-2"]

    context = {
        "supplier_lists": supplier_lists,
    }

    return render(request, "cross_dock/index.html", context)


def process_file(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        uploaded_file = request.FILES.get("file_upload")
        if not uploaded_file:
            return JsonResponse({"error": "No file uploaded"}, status=400)

        if not uploaded_file.name.lower().endswith((".xlsx", ".xls")):
            return JsonResponse({"error": "Invalid file format. Only Excel files are allowed."}, status=400)

        supplier_list = request.POST.get("supplier_list")
        if not supplier_list:
            return JsonResponse({"error": "No supplier list selected"}, status=400)

        filename = f"cross_dock_{uuid.uuid4().hex}.xlsx"

        # Set up directories for file storage
        upload_dir = os.path.join(settings.MEDIA_ROOT, "uploads")
        export_dir = os.path.join(settings.MEDIA_ROOT, "exports")

        try:
            os.makedirs(upload_dir, exist_ok=True)
            os.makedirs(export_dir, exist_ok=True)
            logger.info(f"Created directories: {upload_dir}, {export_dir}")
        except Exception as e:
            logger.error(f"Error creating directories: {e}")
            return JsonResponse({"error": f"Error creating directories: {e}"}, status=500)

        file_path = os.path.join(upload_dir, filename)

        with open(file_path, "wb+") as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        try:
            from cross_dock.services.clickhouse_service import get_clickhouse_client

            try:
                with get_clickhouse_client() as client:
                    # Verify database connectivity before processing
                    test_result = client.execute("SELECT 1")
                    logger.info(f"ClickHouse connection test successful: {test_result}")
            except Exception as db_error:
                logger.error(f"ClickHouse connection error: {db_error}")
                return JsonResponse(
                    {
                        "error": f"Could not connect to the database. Please check your connection settings or try again later. Error: {db_error!s}"
                    },
                    status=500,
                )

            try:
                # First transaction: Create the task with RUNNING status
                with transaction.atomic():
                    task = CrossDockTask.objects.create(
                        status="RUNNING",
                        filename=uploaded_file.name,
                        supplier_group=supplier_list,
                        user=request.user if request.user.is_authenticated else None,
                    )
                    # Get the task ID for later reference
                    task_id = task.id

                # Process the file outside of any transaction to avoid long db locks
                output_file_path = process_cross_dock_data_from_file(file_path, supplier_list)
                output_filename = os.path.basename(output_file_path)
                output_url = f"{settings.MEDIA_URL}exports/{output_filename}"

                # Second transaction: Update the task with SUCCESS status
                with transaction.atomic():
                    # Fetch the task again to ensure we have the latest state
                    task = CrossDockTask.objects.get(id=task_id)
                    task.mark_as_success(output_url)

            finally:
                try:
                    os.remove(file_path)
                    logger.info(f"Removed temporary upload file: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to remove temporary upload file {file_path}: {e}")

            return JsonResponse(
                {
                    "status": "success",
                    "message": "File processed successfully",
                    "filename": filename,
                    "supplier_list": supplier_list,
                    "output_url": output_url,
                }
            )
        except Exception as e:
            logger.exception(f"Error processing file: {e}")

            # If a task was created, mark it as failed in a separate transaction
            task_id = getattr(locals().get("task", None), "id", None)
            if task_id:
                try:
                    with transaction.atomic():
                        task = CrossDockTask.objects.get(id=task_id)
                        task.mark_as_failed(str(e))
                except Exception as task_error:
                    logger.exception(f"Error updating task status: {task_error}")

            return JsonResponse({"error": str(e)}, status=500)

    except Exception as e:
        logger.exception(f"Error processing file: {e}")

        # If a task was created, mark it as failed in a separate transaction
        task_id = getattr(locals().get("task", None), "id", None)
        if task_id:
            try:
                with transaction.atomic():
                    task = CrossDockTask.objects.get(id=task_id)
                    task.mark_as_failed(str(e))
            except Exception as task_error:
                logger.exception(f"Error updating task status: {task_error}")

        return JsonResponse({"error": str(e)}, status=500)


class CrossDockTaskListView(ListView):
    model = CrossDockTask
    template_name = "cross_dock/task_list.html"
    context_object_name = "tasks"
    paginate_by = 10
    ordering = ["-created_at"]
