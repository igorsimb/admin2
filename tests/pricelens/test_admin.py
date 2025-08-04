from importlib import import_module

import pytest
from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.utils import timezone

from pricelens.admin import InvestigationAdmin
from pricelens.models import Investigation, InvestigationStatus
from tests.factories import InvestigationFactory, UserFactory


@pytest.mark.django_db
class TestInvestigationAdmin:
    def setup_method(self):
        """Set up the test environment before each test method."""
        self.site = AdminSite()
        self.admin = InvestigationAdmin(Investigation, self.site)
        self.factory = RequestFactory()
        self.user = UserFactory()

        # Add session middleware to the request
        engine = import_module(settings.SESSION_ENGINE)
        session = engine.SessionStore()
        self.request = self.factory.get("/")
        self.request.session = session
        self.request.user = self.user
        self.request._messages = FallbackStorage(self.request)

    def test_mark_resolved_action_marks_investigations_as_resolved(self):
        """Verify that the mark_resolved action correctly updates the status and investigator."""
        investigations = InvestigationFactory.create_batch(3, status=InvestigationStatus.OPEN)
        queryset = Investigation.objects.filter(id__in=[i.id for i in investigations])

        self.admin.mark_resolved(self.request, queryset)

        for investigation in queryset:
            investigation.refresh_from_db()
            assert investigation.status == InvestigationStatus.RESOLVED
            assert investigation.investigator == self.user
            assert investigation.investigated_at is not None

    def test_mark_open_action_marks_investigations_as_open(self):
        """Verify that the mark_open action reverts investigations to the open state."""
        user = UserFactory()
        investigations = InvestigationFactory.create_batch(
            3, status=InvestigationStatus.RESOLVED, investigator=user, investigated_at=timezone.now()
        )
        queryset = Investigation.objects.filter(id__in=[i.id for i in investigations])

        self.admin.mark_open(self.request, queryset)

        for investigation in queryset:
            investigation.refresh_from_db()
            assert investigation.status == InvestigationStatus.OPEN
            assert investigation.investigator is None
            assert investigation.investigated_at is None
