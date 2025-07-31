import contextlib
import logging
import os
import uuid

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import ListView

from cross_dock.models import CrossDockTask, TaskComment
from cross_dock.tasks import process_file_task

logger = logging.getLogger(__name__)


def index(request):
    supplier_lists = ["Группа для проценки ТРЕШКА", "ОПТ-2"]

    context = {
        "supplier_lists": supplier_lists,
    }

    return render(request, "cross_dock/index.html", context)


class CrossDockTaskListView(ListView):
    model = CrossDockTask
    template_name = "cross_dock/task_list.html"
    context_object_name = "tasks"
    paginate_by = 10
    ordering = ["-created_at"]


def task_detail(request, task_id):
    """
    Display details for a specific task and handle comments.

    This view shows task details and allows users to add comments.
    """
    task = get_object_or_404(CrossDockTask, id=task_id)
    comments = task.comments.all().select_related("user", "user__profile")

    # Handle new comment submission
    if request.method == "POST" and request.user.is_authenticated:
        comment_text = request.POST.get("comment_text")
        if comment_text:
            TaskComment.objects.create(task=task, user=request.user, text=comment_text)
            # Redirect to avoid form resubmission
            return redirect("cross_dock:task_detail", task_id=task_id)

    return render(request, "cross_dock/task_detail.html", {"task": task, "comments": comments})


def process_file(request):
    """
    Process the uploaded Excel file and selected supplier list.

    This view handles file upload validation, creates a task record,
    and submits a Celery task for asynchronous processing.
    """
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

        # Read use_mv flag from POST (treat '1' or 'true' as True)
        use_mv_raw = request.POST.get("use_mv", "0").lower()
        use_mv = use_mv_raw in ("1", "true")

        filename = f"cross_dock_{uuid.uuid4().hex}.xlsx"

        upload_dir = os.path.join(settings.MEDIA_ROOT, "uploads")
        export_dir = os.path.join(settings.MEDIA_ROOT, "exports")

        try:
            os.makedirs(upload_dir, exist_ok=True)
            os.makedirs(export_dir, exist_ok=True)
            logger.info(f"Created directories: {upload_dir}, {export_dir}")
        except Exception as e:
            logger.error(f"Error creating directories: {e}")
            return redirect(reverse("cross_dock:task_list"))

        file_path = os.path.join(upload_dir, filename)

        with open(file_path, "wb+") as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        try:
            from common.utils.clickhouse import get_clickhouse_client

            try:
                with get_clickhouse_client() as client:
                    # Verify database connectivity before starting the task
                    test_result = client.execute("SELECT 1")
                    logger.info(f"ClickHouse connection test successful: {test_result}")
            except Exception as db_error:
                logger.error(f"ClickHouse connection error: {db_error}")
                # Clean up the uploaded file
                with contextlib.suppress(Exception):
                    os.remove(file_path)
                return redirect(reverse("cross_dock:task_list"))

            # Create task record with PENDING status
            with transaction.atomic():
                task = CrossDockTask.objects.create(
                    status="PENDING",
                    filename=uploaded_file.name,
                    supplier_group=supplier_list,
                    user=request.user if request.user.is_authenticated else None,
                )

            # Submit Celery task (add use_mv argument)
            celery_task = process_file_task.delay(
                file_path=file_path, supplier_list=supplier_list, task_id=str(task.id), use_mv=use_mv
            )

            logger.info(f"Submitted Celery task {celery_task.id} for CrossDockTask {task.id} (use_mv={use_mv})")

            # Redirect to task list
            return redirect(reverse("cross_dock:task_list"))

        except Exception as e:
            logger.exception(f"Error submitting task: {e}")

            # Try to mark the task as failed if it was created
            task_id = getattr(locals().get("task", None), "id", None)
            if task_id:
                try:
                    with transaction.atomic():
                        task = CrossDockTask.objects.get(id=task_id)
                        task.mark_as_failed(str(e))
                except Exception as task_error:
                    logger.exception(f"Error updating task status: {task_error}")

            # Clean up the uploaded file
            try:
                os.remove(file_path)
            except Exception:
                pass

            return redirect(reverse("cross_dock:task_list"))

    except Exception as e:
        logger.exception(f"Error processing file: {e}")
        return redirect(reverse("cross_dock:task_list"))
