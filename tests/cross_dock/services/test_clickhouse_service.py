"""Protect canonical pair queries and error propagation through the real client API."""

import json
from types import SimpleNamespace
from unittest import mock

import pytest
from clickhouse_connect.driver.httpclient import HttpClient

from cross_dock.services.clickhouse_service import query_supplier_data, query_supplier_data_mv, supplier_query_session


@pytest.fixture
def mock_client():
    client = mock.create_autospec(HttpClient, instance=True, spec_set=True)
    with mock.patch("cross_dock.services.clickhouse_service.get_clickhouse_client") as mock_get:
        mock_get.return_value.__enter__.return_value = client
        yield client


@pytest.mark.parametrize("use_mv", [False, True])
def test_query_uses_canonical_pairs_and_current_supplier_metadata(mock_client, use_mv):
    offers = [(90.25, 3, "Supplier C", "ЯМЗ", "236Д1003009"), (100.50, 5, "Supplier A", "ЯМЗ", "236Д1003009")]
    mock_client.query.side_effect = [
        SimpleNamespace(result_rows=[(1001,), (1002,)]),
        SimpleNamespace(result_rows=offers),
    ]

    result = (
        query_supplier_data_mv([(" ямз ", "236д1003009"), ("ЯМЗ", "236Д1003009")], "ОПТ-2")
        if use_mv
        else query_supplier_data(" ямз ", "236д1003009", "ОПТ-2")
    )

    assert list(result.itertuples(index=False, name=None)) == (offers if use_mv else [row[:3] for row in offers])
    assert "sup_list FINAL" in mock_client.query.call_args_list[0].args[0]
    assert mock_client.query.call_args.kwargs["parameters"] == {
        "supplier_ids": (1001, 1002),
        "days_lookback": 2,
    }
    external = mock_client.query.call_args.kwargs["external_data"]
    assert external.files[0].name == "uploaded_pairs"
    assert [json.loads(row) for row in external.files[0].data.splitlines()] == [["ЯМЗ", "236Д1003009"]]
    query = mock_client.query.call_args.args[0]
    assert "sup_stat.sup_list FINAL" in query
    assert ("sup_stat.rmv_cross_dock" if use_mv else "sup_stat.dif_step_1 FINAL") in query
    assert "sup_stat.mv_cross_dock" not in query
    assert "lower(" not in query


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


@pytest.mark.parametrize("use_mv", [False, True])
def test_no_suppliers_returns_empty_offers_without_price_query(mock_client, use_mv):
    mock_client.query.return_value = SimpleNamespace(result_rows=[])

    result = (
        query_supplier_data_mv([("BRAND", "ARTICLE")], "empty")
        if use_mv
        else query_supplier_data("BRAND", "ARTICLE", "empty")
    )

    assert result.empty
    assert list(result.columns) == ["price", "quantity", "supplier_name"] + (["brand", "sku"] if use_mv else [])
    assert mock_client.query.call_count == 1


@pytest.mark.parametrize("use_mv", [False, True])
@pytest.mark.parametrize("failure_stage", ["suppliers", "offers"])
def test_query_failures_propagate_instead_of_becoming_empty_offers(mock_client, failure_stage, use_mv):
    error = RuntimeError("ClickHouse unavailable")
    mock_client.query.side_effect = (
        [error] if failure_stage == "suppliers" else [SimpleNamespace(result_rows=[(1,)]), error]
    )

    with pytest.raises(RuntimeError, match="ClickHouse unavailable"):
        if use_mv:
            query_supplier_data_mv([("BRAND", "ARTICLE")], "ОПТ-2")
        else:
            query_supplier_data("BRAND", "ARTICLE", "ОПТ-2")


def test_empty_fast_input_does_not_open_connection(mock_client):
    assert query_supplier_data_mv([], "ОПТ-2").empty
    mock_client.query.assert_not_called()


def test_large_pair_list_is_sent_as_data_instead_of_expanding_sql(mock_client):
    mock_client.query.side_effect = [SimpleNamespace(result_rows=[(1,)]), SimpleNamespace(result_rows=[])]
    pairs = [("BOSCH", f"{i:08d}") for i in range(40_000)]
    pairs += [("O'БРЕНД", '00"A\\B\tC\nD'), pairs[0]]

    query_supplier_data_mv(pairs, "Group")

    query = mock_client.query.call_args.args[0]
    kwargs = mock_client.query.call_args.kwargs
    assert len(query.encode("utf-8")) < 4096
    assert "brand_sku_pairs" not in kwargs["parameters"]
    payload = kwargs["external_data"].files[0]
    assert payload.fmt == "JSONCompactEachRow"
    assert payload.structure == "brand String,sku String"
    assert len(payload.data) > 262144
    assert [tuple(json.loads(row)) for row in payload.data.splitlines()] == sorted(set(pairs))
