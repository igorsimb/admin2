"""
Factory classes for cross-dock tests.

This module contains factory classes for creating test data for cross-dock tests.
"""

import factory


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
