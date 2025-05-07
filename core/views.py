from django.conf import settings
from django.contrib.auth import get_user_model
from django.views.generic import TemplateView

User = get_user_model()


class IndexView(TemplateView):
    template_name = "core/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["environment"] = settings.DJANGO_ENVIRONMENT
        context["CLICKHOUSE_HOST"] = settings.CLICKHOUSE_HOST

        return context
