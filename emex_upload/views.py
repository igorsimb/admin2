import json
import time

from celery.result import AsyncResult
from django.conf import settings
from django.contrib.auth.decorators import login_required, login_not_required
from django.core.files.storage import FileSystemStorage
from django.http import StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .forms import FileUploadForm
from .tasks import validate_emex_file_task

ACCEPTABLE_ERROR_THRESHOLD = 100


@login_required
def upload_file_view(request):
    """
    Handle the file upload by dispatching a Celery task for validation
    and rendering a progress-monitoring page.
    """
    if request.method == "POST":
        form = FileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES["file"]

            # Define the temporary directory and ensure it exists
            temp_dir = settings.MEDIA_ROOT / "temp_uploads"
            temp_dir.mkdir(parents=True, exist_ok=True)

            # Save the file temporarily
            fs = FileSystemStorage(location=temp_dir)
            filename = fs.save(uploaded_file.name, uploaded_file)
            file_path = fs.path(filename)

            # Start the validation task
            task = validate_emex_file_task.delay(file_path)

            # Render the status page
            return render(
                request,
                "emex_upload/upload_status.html",
                {"task_id": task.id},
            )
    else:
        form = FileUploadForm()

    return render(
        request,
        "emex_upload/emex_upload.html",
        {"form": form},
    )

@login_not_required
@require_GET
def task_status_view(request, task_id: str):
    """
    Streams the status of a Celery task using Server-Sent Events (SSE).
    """

    def sse_stream():
        while True:
            task_result = AsyncResult(task_id)
            if task_result.ready():
                # Send final event and close connection
                data = {"status": task_result.state, "result": task_result.result}
                yield f"data: {json.dumps(data)}\n\n"
                break
            else:
                # Send progress update
                if task_result.info:
                    data = {"status": task_result.state, "meta": task_result.info}
                    yield f"data: {json.dumps(data)}\n\n"

            # Send a heartbeat to keep the connection alive
            yield ": ping\n\n"
            time.sleep(1)
    response = StreamingHttpResponse(sse_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    return response