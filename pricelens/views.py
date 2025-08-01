import datetime
import random
import uuid

from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import ListView, TemplateView


class DashboardView(TemplateView):
    template_name = "pricelens/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Phase 1: Dummy data for the dashboard widgets
        context["summary"] = {
            "failures": 284,
            "suppliers": 23,
        }
        context["top_reasons"] = [
            {"error_text": "SKU_FORMAT_INVALID", "cnt": 112},
            {"error_text": "FILE_READ_ERROR", "cnt": 75},
            {"error_text": "PRICE_DEVIATION_HIGH", "cnt": 43},
            {"error_text": "COLUMN_MISSING_VALUES", "cnt": 28},
            {"error_text": "DIF_STEP1_WRITE_ERROR", "cnt": 11},
        ]
        # End of Phase 1 data

        # Phase 2: Dummy data for cadence and anomaly widgets
        context["buckets"] = [
            {"bucket": "Стабильные", "cnt": 85},
            {"bucket": "Нестабильные", "cnt": 22},
            {"bucket": "Мертвые", "cnt": 7},
        ]
        context["anomalies"] = [
            {"supid": 1234, "days_since_last": 10, "median_gap_days": 3},
            {"supid": 5678, "days_since_last": 7, "median_gap_days": 2},
            {"supid": 9012, "days_since_last": 14, "median_gap_days": 5},
            {"supid": 3456, "days_since_last": 5, "median_gap_days": 1},
            {"supid": 7890, "days_since_last": 21, "median_gap_days": 7},
        ]
        # End of Phase 2 data

        return context


class QueueView(ListView):
    template_name = "pricelens/queue.html"
    context_object_name = "investigations"
    paginate_by = 15

    def get_queryset(self):
        # Phase 3: Generate dummy investigation data
        reasons = [
            "SKU_FORMAT_INVALID",
            "FILE_READ_ERROR",
            "PRICE_DEVIATION_HIGH",
            "COLUMN_MISSING_VALUES",
            "DIF_STEP1_WRITE_ERROR",
        ]
        stages = ["load_mail", "consolidate", "airflow"]

        queryset = []
        for i in range(78):  # Create 78 dummy items for pagination
            event_time = timezone.now() - datetime.timedelta(hours=i, minutes=random.randint(0, 59))
            queryset.append(
                {
                    "id": uuid.uuid4(),
                    "event_dt": event_time,
                    "supid": random.randint(1000, 9999),
                    "error_text": random.choice(reasons),
                    "stage": random.choice(stages),
                }
            )
        return queryset


class InvestigationDetailView(TemplateView):
    template_name = "pricelens/investigate.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Phase 4: Generate a single dummy object for the detail view
        context["investigation"] = {
            "id": kwargs.get("pk"),
            "event_dt": timezone.now() - datetime.timedelta(hours=random.randint(1, 24)),
            "supid": random.randint(1000, 9999),
            "error_text": random.choice(["SKU_FORMAT_INVALID", "FILE_READ_ERROR", "PRICE_DEVIATION_HIGH"]),
            "stage": random.choice(["load_mail", "consolidate", "airflow"]),
            "file_path": f"/daily_consolidation/2025-07-30/sup_{random.randint(1000, 9999)}.csv",
        }
        return context

    def post(self, request, *args, **kwargs):
        # Simulate form submission
        return redirect("pricelens:queue")
