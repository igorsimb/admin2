from django.contrib.auth import get_user_model
from django.views.generic import TemplateView

User = get_user_model()


class IndexView(TemplateView):
    template_name = "core/index.html"
