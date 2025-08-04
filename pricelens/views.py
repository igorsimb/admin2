import datetime

from django.db.models import Count, F
from django.shortcuts import redirect
from django.utils import timezone
from django.views import generic

from .models import BucketChoices, CadenceProfile, Investigation, InvestigationStatus


class DashboardView(generic.TemplateView):
    template_name = "pricelens/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        yesterday_open = Investigation.objects.filter(
            status=InvestigationStatus.OPEN,
            event_dt__date=timezone.now().date() - datetime.timedelta(days=1),
        )
        top = yesterday_open.values("error_text").annotate(cnt=Count("id")).order_by("-cnt")[:5]

        # Get counts for each status
        status_counts = Investigation.objects.values("status").annotate(cnt=Count("id")).order_by("status")
        status_counts_dict = {s["status"]: s["cnt"] for s in status_counts}

        investigation_stats = []
        for value, label in InvestigationStatus.choices:
            investigation_stats.append(
                {
                    "label": label.capitalize(),
                    "value": value,
                    "count": status_counts_dict.get(value, 0),
                }
            )

        # Get counts for each bucket
        bucket_counts = CadenceProfile.objects.values("bucket").annotate(cnt=Count("supplier"))
        bucket_counts_dict = {b["bucket"]: b["cnt"] for b in bucket_counts}

        # Enforce static order and use Russian labels
        ordered_buckets = []
        tooltips = {
            BucketChoices.CONSISTENT: "Поставщик, у которого стандартное отклонение меньше или равно половине медианного интервала",  # noqa: RUF001
            BucketChoices.INCONSISTENT: "Поставщик, у которого стандартное отклонение больше половины медианного интервала",  # noqa: RUF001
            BucketChoices.DEAD: "Поставщик, от которого не было успешных поставок 28 дней или более",
        }
        for value, label in BucketChoices.choices:
            ordered_buckets.append(
                {
                    "label": label,
                    "count": bucket_counts_dict.get(value, 0),
                    "tooltip": tooltips.get(value, ""),
                }
            )

        ctx.update(
            {
                "summary": {
                    "failures": yesterday_open.count(),
                    "suppliers": yesterday_open.values("supplier").distinct().count(),
                },
                "top_reasons": list(top),
                "investigation_stats": investigation_stats,
                "buckets": ordered_buckets,
                "anomalies": CadenceProfile.objects.exclude(bucket=BucketChoices.DEAD)
                .filter(days_since_last__gt=F("median_gap_days") * 2)
                .order_by("-days_since_last")[:50],
            }
        )
        return ctx


class QueueView(generic.ListView):
    model = Investigation
    template_name = "pricelens/queue.html"
    paginate_by = 50
    context_object_name = "investigations"

    def get_queryset(self):
        queryset = Investigation.objects.select_related("supplier").all()

        # Filter by status from URL query param. Default to OPEN if no param.
        status_filter = self.request.GET.get("status")

        if status_filter and status_filter.isdigit():
            queryset = queryset.filter(status=int(status_filter))
        elif status_filter is None:
            queryset = queryset.filter(status=InvestigationStatus.OPEN)
        # If status is 'all' or something else, we show all records.

        return queryset.order_by("-event_dt")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass the status choices and the current filter to the template
        context["status_choices"] = InvestigationStatus.choices
        # Default to '0' (OPEN) for the active button state if not specified
        context["current_status"] = self.request.GET.get("status", str(InvestigationStatus.OPEN))
        # Pass query parameters to the template for pagination
        context["query_params"] = self.request.GET.urlencode()
        return context


class InvestigationDetailView(generic.UpdateView):
    model = Investigation
    fields = ["note"]  # note editable
    template_name = "pricelens/investigate.html"
    context_object_name = "investigation"

    def form_valid(self, form):
        obj = self.get_object()
        obj.note = form.cleaned_data["note"]

        action = self.request.POST.get("action")
        if action == "resolve":
            obj.status = InvestigationStatus.RESOLVED
        else:
            obj.status = InvestigationStatus.UNRESOLVED

        obj.investigated_at = timezone.now()
        obj.investigator = self.request.user
        obj.save()
        return redirect("pricelens:queue")
