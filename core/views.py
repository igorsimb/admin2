from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_not_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

User = get_user_model()


@login_not_required
@require_GET
def health(_request):
    return JsonResponse({"status": "ok"})


class IndexView(TemplateView):
    template_name = "core/index.html"
