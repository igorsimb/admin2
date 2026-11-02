"""Check real ClickHouse replacement and snapshot semantics in an opt-in local container.

Set CROSS_DOCK_TEST_CONTAINER to an isolated ClickHouse 24.10 container. Each test
creates and removes its own uniquely named database; no configured server is used.
"""

import json
import os
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from clickhouse_connect.driver.binding import bind_query
from openpyxl import load_workbook

from cross_dock.services import clickhouse_service, normalization
from cross_dock.services.excel_service import process_cross_dock_data


@pytest.fixture
def snapshot_client(monkeypatch):
    container = os.environ.get("CROSS_DOCK_TEST_CONTAINER")
    if not container:
        pytest.skip("Set CROSS_DOCK_TEST_CONTAINER to an isolated ClickHouse 24.10 container")
    database = "cross_dock_test_" + uuid.uuid4().hex

    class Client:
        def query(self, sql, parameters=None):
            sql = sql.replace("sup_stat.", database + ".").replace("dif.", database + ".")
            sql, _ = bind_query(sql, parameters)
            result = subprocess.run(
                ["docker", "exec", "-i", container, "clickhouse-client", "--format", "JSONCompact"],
                input=sql,
                encoding="utf-8",
                capture_output=True,
                check=True,
                timeout=60,
            )
            payload = json.loads(result.stdout) if result.stdout.strip() else {"data": []}
            return SimpleNamespace(result_rows=[tuple(row) for row in payload["data"]])

    client = Client()
    client.query(f"CREATE DATABASE {database}")
    try:
        client.query("""CREATE TABLE sup_stat.dif_step_1
            (dateupd Date, supid Int32, b String, a String, p Float64, q Int32)
            ENGINE = ReplacingMergeTree PARTITION BY toYYYYMMDD(dateupd) ORDER BY (dateupd, supid, b, a)""")
        client.query("""CREATE TABLE sup_stat.sup_list (dif_id Int32, name String, lists Array(String))
            ENGINE = ReplacingMergeTree ORDER BY dif_id""")
        client.query(
            "CREATE TABLE dif.zap_brand_cross (brand String, parent_id Int32) ENGINE = MergeTree ORDER BY brand"
        )
        client.query("CREATE TABLE dif.unique_brands (id Int32, brand String) ENGINE = MergeTree ORDER BY id")
        client.query("SYSTEM STOP MERGES sup_stat.dif_step_1")
        client.query("SYSTEM STOP MERGES sup_stat.sup_list")
        ddl = (Path(__file__).resolve().parents[3] / "docs/cross_dock/refreshable_cross_dock.sql").read_text("utf-8")
        for prefix in ("CREATE TABLE sup_stat.rmv_cross_dock", "CREATE MATERIALIZED VIEW sup_stat.rmv_cross_dock_view"):
            client.query(ddl[ddl.index(prefix) :].split(";", 1)[0])
        client.query("SYSTEM WAIT VIEW sup_stat.rmv_cross_dock_view")

        @contextmanager
        def connection():
            yield client

        monkeypatch.setattr(clickhouse_service, "get_clickhouse_client", connection)
        monkeypatch.setattr(normalization, "get_clickhouse_client", connection)
        yield client
    finally:
        client.query(f"DROP DATABASE {database} SYNC")


def refresh(client):
    client.query("SYSTEM REFRESH VIEW sup_stat.rmv_cross_dock_view")
    client.query("SYSTEM WAIT VIEW sup_stat.rmv_cross_dock_view")


def assert_offers(brand, sku, expected):
    slow = clickhouse_service.query_supplier_data(brand, sku, "Group")
    fast = clickhouse_service.query_supplier_data_mv([(brand, sku), (brand, sku)], "Group")
    assert list(slow.itertuples(index=False, name=None)) == expected
    assert list(fast[clickhouse_service.OFFER_COLUMNS].itertuples(index=False, name=None)) == expected


def test_replacements_stock_dates_current_metadata_and_price_ties(snapshot_client):
    client = snapshot_client
    client.query("""INSERT INTO sup_stat.sup_list VALUES
        (1,'Zeta',['Group']),(2,'Beta',['Group']),(3,'Alpha',['Group']),
        (4,'Omega',['Group']),(5,'Removed',['Group']),(6,'Old',['Group'])""")
    client.query("""INSERT INTO sup_stat.dif_step_1 VALUES
        (today(),1,'BOSCH','001A',10,9), (today()-1,2,'BOSCH','001A',80,8),
        (today(),2,'BOSCH','001A',90,9), (today(),3,'BOSCH','001A',100,3),
        (today(),4,'BOSCH','001A',100,4), (today(),5,'BOSCH','001A',2,5),
        (today()-3,6,'BOSCH','001A',1,6), (today(),1,'ЯМЗ','236Д1003009',50,2)""")
    client.query("""INSERT INTO sup_stat.dif_step_1 VALUES
        (today(),1,'BOSCH','001A',100,5), (today(),2,'BOSCH','001A',90,0)""")
    refresh(client)
    # Metadata changes after the snapshot must apply immediately without another refresh.
    client.query("INSERT INTO sup_stat.sup_list VALUES (1,'Aardvark',['Group']),(5,'Removed',['Other'])")

    assert_offers("BOSCH", "001A", [(80, 8, "Beta"), (100, 5, "Aardvark"), (100, 3, "Alpha")])
    assert_offers("ЯМЗ", "236Д1003009", [(50, 2, "Aardvark")])
    assert_offers("MISSING", "001A", [])


def test_fast_keeps_last_snapshot_until_refresh_then_reflects_replacements_and_deletes(snapshot_client):
    client = snapshot_client
    client.query("INSERT INTO sup_stat.sup_list VALUES (1,'Supplier',['Group'])")
    client.query("INSERT INTO sup_stat.dif_step_1 VALUES (today(),1,'BOSCH','A',100,5)")
    refresh(client)
    client.query("INSERT INTO sup_stat.dif_step_1 VALUES (today(),1,'BOSCH','A',120,8)")
    slow = clickhouse_service.query_supplier_data("BOSCH", "A", "Group")
    fast = clickhouse_service.query_supplier_data_mv([("BOSCH", "A")], "Group")
    assert slow.iloc[0]["price"] == 120
    assert fast.iloc[0]["price"] == 100
    refresh(client)
    assert_offers("BOSCH", "A", [(120, 8, "Supplier")])
    client.query("SYSTEM START MERGES sup_stat.dif_step_1")
    client.query("ALTER TABLE sup_stat.dif_step_1 DELETE WHERE a = 'A' SETTINGS mutations_sync = 2")
    refresh(client)
    assert_offers("BOSCH", "A", [])


def test_reports_match_for_aliases_duplicates_and_unicode(snapshot_client, settings, tmp_path):
    client = snapshot_client
    settings.MEDIA_ROOT = tmp_path
    client.query("INSERT INTO sup_stat.sup_list VALUES (1,'Supplier',['Group'])")
    client.query("""INSERT INTO dif.zap_brand_cross VALUES
        ('HYUNDAI/KIA',1),('Hyundai/Kia',1),('HYUNDAI/KIA/MOBIS',1),('Ямз',2)""")
    client.query("INSERT INTO dif.unique_brands VALUES (1,'HYUNDAI/KIA/MOBIS'),(2,'ЯМЗ')")
    client.query("""INSERT INTO sup_stat.dif_step_1 VALUES
        (today(),1,'HYUNDAI/KIA/MOBIS','001A',100,5), (today(),1,'ЯМЗ','236Д1003009',50,2)""")
    refresh(client)
    data = [
        {"Бренд": " hyundai/kia ", "Артикул": "001a"},
        {"Бренд": "Hyundai/Kia/Mobis", "Артикул": "001A"},
        {"Бренд": " hyundai/kia ", "Артикул": "001a"},
        {"Бренд": "ямз", "Артикул": "236д1003009"},
        {"Бренд": "unknown", "Артикул": "missing"},
    ]
    outputs = []
    for use_mv in (False, True):
        _, url = process_cross_dock_data(data, "Group", use_mv=use_mv)
        outputs.append(list(load_workbook(tmp_path / "exports" / url.rsplit("/", 1)[-1]).active.values))
    assert outputs[0] == outputs[1]
    assert len(outputs[0]) == 6
    assert [row[3:6] for row in outputs[0][1:]] == [
        (100, 5, "Supplier"),
        (100, 5, "Supplier"),
        (100, 5, "Supplier"),
        (50, 2, "Supplier"),
        (None, None, None),
    ]
