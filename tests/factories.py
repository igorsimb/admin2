import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from accounts.models import User
from common.models import Supplier
from pricelens.models import Investigation, InvestigationStatus


class SupplierFactory(DjangoModelFactory):
    class Meta:
        model = Supplier

    supid = factory.Sequence(lambda n: n)
    name = factory.Faker("company")


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Faker("user_name")
    email = factory.Faker("email")


class InvestigationFactory(DjangoModelFactory):
    class Meta:
        model = Investigation

    supplier = factory.SubFactory(SupplierFactory)
    event_dt = factory.Faker("date_time", tzinfo=factory.LazyFunction(lambda: timezone.get_current_timezone()))
    error_id = factory.Faker("pyint", min_value=1, max_value=100)
    error_text = factory.Faker("sentence")
    stage = factory.Faker("random_element", elements=["load_mail", "consolidate"])
    status = InvestigationStatus.OPEN


class SupplierDataFactory(factory.Factory):
    """Factory for creating supplier data dictionaries."""

    class Meta:
        model = dict

    price = factory.Faker("pydecimal", left_digits=4, right_digits=2, positive=True)
    quantity = factory.Faker("pyint", min_value=1, max_value=100)
    supplier_name = factory.Faker("company")


class InputDataFactory(factory.Factory):
    """Factory for creating input data dictionaries."""

    class Meta:
        model = dict

    Бренд = factory.Faker("random_element", elements=["HYUNDAI/KIA/MOBIS", "VAG", "NISSAN", "SSANGYONG"])
    Артикул = factory.Faker("bothify", text="#######??")
