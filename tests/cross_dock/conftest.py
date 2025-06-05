"""
Pytest fixtures for cross-dock tests.

This module contains pytest fixtures for cross-dock tests.
"""

import pandas as pd
import pytest


@pytest.fixture
def sample_supplier_data():
    """Fixture providing sample supplier data as a DataFrame."""
    return pd.DataFrame(
        {
            "price": [100.50, 120.75, 90.25],
            "quantity": [5, 10, 3],
            "supplier_name": ["Supplier A", "Supplier B", "Supplier C"],
        }
    )


@pytest.fixture
def sample_input_data():
    """Fixture providing sample input data."""
    return [{"Бренд": "HYUNDAI/KIA/MOBIS", "Артикул": "223112e100"}, {"Бренд": "VAG", "Артикул": "000915105cd"}]
