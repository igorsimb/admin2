"""Protect parser-compatible supplier selection and the real ClickHouse client API."""

import re
from types import SimpleNamespace
from unittest import mock

import pytest
from clickhouse_connect.driver.httpclient import HttpClient

from cross_dock.services.clickhouse_service import query_supplier_data, query_supplier_data_mv, supplier_query_session

# Reference: parser/src/flask_api/tasks.py, process_data(), captured 2026-11-02.
PARSER_PRICE_QUERY = """
WITH recent_prices AS (
    SELECT DISTINCT df.p, df.q, sl.name, df.dateupd,
        ROW_NUMBER() OVER (PARTITION BY sl.name ORDER BY df.dateupd DESC) AS rn
    FROM sup_stat.dif_step_1 AS df
    INNER JOIN sup_stat.sup_list AS sl ON df.supid = sl.dif_id
    WHERE lower(df.a) = %(sku_lower)s
      AND lower(df.b) IN %(brand_values)s
      AND df.dateupd >= now() - interval %(days_lookback)s day
      AND df.supid IN %(supplier_ids)s
      AND df.q > 0
), ranked_suppliers AS (
    SELECT DISTINCT p, q, name,
        ROW_NUMBER() OVER (PARTITION BY name ORDER BY p ASC) AS rank
    FROM recent_prices WHERE rn = 1
)
SELECT p, q, name FROM ranked_suppliers WHERE rank = 1 ORDER BY p ASC LIMIT 3;
"""


@pytest.fixture
def mock_client():
    client = mock.create_autospec(HttpClient, instance=True, spec_set=True)
    with mock.patch("cross_dock.services.clickhouse_service.get_clickhouse_client") as mock_get:
        mock_get.return_value.__enter__.return_value = client
        yield client


@pytest.mark.parametrize(
    ("brand", "expected_brands"),
    [
        ("BOSCH", ("bosch",)),
        ("HYUNDAI/KIA", ("hyundai/kia", "hyundai/kia/mobis")),
        ("Hyundai/Kia/Mobis", ("hyundai/kia", "hyundai/kia/mobis")),
    ],
)
def test_slow_query_preserves_parser_selection(mock_client, brand, expected_brands):
    offers = [(90.25, 3, "Supplier C"), (100.50, 5, "Supplier A"), (120.75, 10, "Supplier B")]
    mock_client.query.side_effect = [
        SimpleNamespace(result_rows=[(1001,), (1002,)]),
        SimpleNamespace(result_rows=offers),
    ]

    result = query_supplier_data(brand, "Ab123", "ОПТ-2")

    assert list(result.itertuples(index=False, name=None)) == offers
    query = mock_client.query.call_args.args[0]
    query = re.sub(r"\bas\s+(price|quantity|supplier_name)\b", "", query, flags=re.IGNORECASE)
    for alias, original in [("price", "p"), ("quantity", "q"), ("supplier_name", "name")]:
        query = re.sub(r"\b" + alias + r"\b", original, query)
    assert re.sub(r"\s+", "", query).lower() == re.sub(r"\s+", "", PARSER_PRICE_QUERY).lower()
    assert mock_client.query.call_args.kwargs["parameters"] == {
        "sku_lower": "ab123",
        "brand_values": expected_brands,
        "supplier_ids": (1001, 1002),
        "days_lookback": 2,
    }


def test_report_resolves_supplier_ids_once(mock_client):
    mock_client.query.side_effect = [
        SimpleNamespace(result_rows=[(1001,)]),
        SimpleNamespace(result_rows=[]),
        SimpleNamespace(result_rows=[]),
    ]

    with supplier_query_session("ОПТ-2") as query:
        assert query("BOSCH", "123").empty
        assert query("VAG", "456").empty

    assert mock_client.query.call_count == 3
    for call in mock_client.query.call_args_list[1:]:
        assert call.kwargs["parameters"]["supplier_ids"] == (1001,)


def test_no_suppliers_returns_empty_offers_without_price_query(mock_client):
    mock_client.query.return_value = SimpleNamespace(result_rows=[])

    result = query_supplier_data("BRAND", "ARTICLE", "empty group")

    assert result.empty
    assert list(result.columns) == ["price", "quantity", "supplier_name"]
    assert mock_client.query.call_count == 1


@pytest.mark.parametrize("failure_stage", ["suppliers", "offers"])
def test_query_failures_propagate_instead_of_becoming_empty_offers(mock_client, failure_stage):
    error = RuntimeError("ClickHouse unavailable")
    mock_client.query.side_effect = (
        [error] if failure_stage == "suppliers" else [SimpleNamespace(result_rows=[(1,)]), error]
    )

    with pytest.raises(RuntimeError, match="ClickHouse unavailable"):
        query_supplier_data("BRAND", "ARTICLE", "ОПТ-2")


@pytest.mark.parametrize("offers", [[], [(100.0, 5, "Supplier A", "bosch", "123")]])
def test_fast_query_reads_rows_through_real_client_interface(mock_client, offers):
    mock_client.query.return_value = SimpleNamespace(result_rows=offers)

    result = query_supplier_data_mv([("bosch", "123")], "ОПТ-2")

    assert list(result.itertuples(index=False, name=None)) == offers
    assert list(result.columns) == ["price", "quantity", "supplier_name", "brand_lower", "sku_lower"]
    assert mock_client.query.call_args.kwargs["parameters"]["brand_sku_pairs"] == [("bosch", "123")]


def test_fast_query_failure_is_not_reported_as_no_offers(mock_client):
    mock_client.query.side_effect = RuntimeError("ClickHouse unavailable")

    with pytest.raises(RuntimeError, match="ClickHouse unavailable"):
        query_supplier_data_mv([("bosch", "123")], "ОПТ-2")
