"""Verify shared dictionary normalization without multiplying or losing uploaded rows."""

from types import SimpleNamespace
from unittest import mock

import pytest
from clickhouse_connect.driver.httpclient import HttpClient

from cross_dock.services.normalization import normalize_brand_sku_pairs


@pytest.fixture
def mock_client():
    client = mock.create_autospec(HttpClient, instance=True, spec_set=True)
    with mock.patch("cross_dock.services.normalization.get_clickhouse_client") as get:
        get.return_value.__enter__.return_value = client
        yield client


def test_aliases_share_canonical_brand_and_preserve_duplicate_pairs(mock_client):
    mock_client.query.side_effect = [
        SimpleNamespace(result_rows=[("HYUNDAI/KIA", 1), ("HYUNDAI/KIA", 1), ("HYUNDAI/KIA/MOBIS", 1)]),
        SimpleNamespace(result_rows=[(1, "HYUNDAI/KIA/MOBIS")]),
    ]

    result = normalize_brand_sku_pairs(
        [
            (" hyundai/kia ", " 001abc "),
            ("Hyundai/Kia/Mobis", "001ABC"),
            ("hyundai/kia", "001abc"),
        ]
    )

    assert result == [("HYUNDAI/KIA/MOBIS", "001ABC")] * 3
    assert mock_client.query.call_count == 2
    assert mock_client.query.call_args.kwargs["parameters"] == {"parent_ids": (1,)}


def test_unknown_cyrillic_brand_and_sku_fall_back_to_unicode_uppercase(mock_client):
    mock_client.query.return_value = SimpleNamespace(result_rows=[])

    assert normalize_brand_sku_pairs([(" ямз ", "236д1003009")]) == [("ЯМЗ", "236Д1003009")]
    assert mock_client.query.call_count == 1


def test_space_insensitive_alias_matching_prefers_exact_match(mock_client):
    mock_client.query.side_effect = [
        SimpleNamespace(result_rows=[("A B", 1), ("AB", 2), ("LAND ROVER", 3)]),
        SimpleNamespace(result_rows=[(1, "FIRST"), (2, "SECOND"), (3, "LAND ROVER")]),
    ]

    assert normalize_brand_sku_pairs([("A B", "1"), ("AB", "2"), ("landrover", "3")]) == [
        ("FIRST", "1"),
        ("SECOND", "2"),
        ("LAND ROVER", "3"),
    ]


@pytest.mark.parametrize(
    ("mapping", "canonical", "message"),
    [
        ([("ALIAS", 1), ("ALIAS", 2)], [(1, "ONE"), (2, "TWO")], "Conflicting brand normalization"),
        ([("ALIAS", 1)], [(1, "ONE"), (1, "TWO")], "Conflicting or empty canonical brand"),
        ([("ALIAS", 1)], [], "Missing canonical brand"),
        ([("ALIAS", 1)], [(1, "")], "Conflicting or empty canonical brand"),
    ],
)
def test_ambiguous_or_broken_dictionary_fails_instead_of_choosing_arbitrarily(mock_client, mapping, canonical, message):
    mock_client.query.side_effect = [SimpleNamespace(result_rows=mapping), SimpleNamespace(result_rows=canonical)]

    with pytest.raises(ValueError, match=message):
        normalize_brand_sku_pairs([("alias", "123")])


@pytest.mark.parametrize("stage", [0, 1])
def test_dictionary_query_failure_is_not_treated_as_an_unknown_brand(mock_client, stage):
    mock_client.query.side_effect = [SimpleNamespace(result_rows=[("ALIAS", 1)])] * stage + [RuntimeError("Offline")]

    with pytest.raises(RuntimeError, match="Offline"):
        normalize_brand_sku_pairs([("alias", "123")])


def test_empty_input_avoids_dictionary_queries(mock_client):
    assert normalize_brand_sku_pairs([]) == []
    assert normalize_brand_sku_pairs([(" ", "1"), ("A", "")]) == [("", "1"), ("A", "")]
    mock_client.query.assert_not_called()
