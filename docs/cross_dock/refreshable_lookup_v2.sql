-- Cross-dock lookup proposal for ClickHouse 24.10.1.2812 (single server, Atomic database).
-- Run each numbered stage separately and inspect its result before continuing.
-- This creates a parallel lookup. The current application still reads mv_cross_dock.
-- Do not drop the old objects until a matching FAST reader has been deployed and verified.

-- 1. Confirm the server/database and preserve the old definitions outside this session.
SELECT version();
SELECT name, engine FROM system.databases WHERE name = 'sup_stat';
SHOW CREATE TABLE sup_stat.mv_cross_dock_view;
SHOW CREATE TABLE sup_stat.mv_cross_dock;

-- 2. Create an empty, separately named destination. Plain MergeTree is intentional:
-- each refresh replaces the complete contents; it does not append/reconcile versions.
-- Keep raw identity and zero-stock rows. Normalize brands and select offers in the reader.
CREATE TABLE sup_stat.cross_dock_lookup_v2
(
    supid Int32,
    brand_raw String,
    sku_raw String,
    brand_lower String,
    sku_lower String,
    price Float64,
    quantity Int32,
    update_date Date,
    refreshed_at DateTime
)
ENGINE = MergeTree
ORDER BY (brand_lower, sku_lower, supid, update_date, brand_raw, sku_raw);

-- 3. Populate automatically on creation, then replace the snapshot after each refresh.
-- No APPEND, supplier join, positive-stock filter, or independently merging target.
-- FINAL resolves same-day replacements BEFORE the reader filters quantity > 0.
-- Date filtering is safe here because dateupd is part of the source replacement key.
-- Five days are retained; the reader must still enforce its two-day eligibility cutoff.
-- AFTER 1 DAY is a fallback. Trigger REFRESH + WAIT after each completed supplier load.
CREATE MATERIALIZED VIEW sup_stat.cross_dock_lookup_refresh_v2
REFRESH AFTER 1 DAY
TO sup_stat.cross_dock_lookup_v2
AS
SELECT
    supid,
    b AS brand_raw,
    a AS sku_raw,
    lower(b) AS brand_lower,
    lower(a) AS sku_lower,
    p AS price,
    q AS quantity,
    dateupd AS update_date,
    now() AS refreshed_at
FROM sup_stat.dif_step_1 FINAL
WHERE dateupd >= today() - INTERVAL 5 DAY;

-- 4. Wait for initial population and inspect refresh state (columns available in 24.10).
SYSTEM WAIT VIEW sup_stat.cross_dock_lookup_refresh_v2;
SELECT
    database, view, status, last_success_time, last_success_duration_ms,
    last_refresh_time, next_refresh_time, exception
FROM system.view_refreshes
WHERE database = 'sup_stat' AND view = 'cross_dock_lookup_refresh_v2';

SELECT count() AS rows, min(update_date), max(update_date), max(refreshed_at)
FROM sup_stat.cross_dock_lookup_v2;

-- 5. Compare both directions during a quiet interval without source inserts/mutations.
-- Each result must be zero. Source changes after the refresh can legitimately differ.
SELECT 'source_minus_snapshot' AS comparison, count() AS differences
FROM
(
    SELECT supid, b, a, p, q, dateupd
    FROM sup_stat.dif_step_1 FINAL
    WHERE dateupd >= today() - INTERVAL 5 DAY
    EXCEPT ALL
    SELECT supid, brand_raw, sku_raw, price, quantity, update_date
    FROM sup_stat.cross_dock_lookup_v2
);

SELECT 'snapshot_minus_source' AS comparison, count() AS differences
FROM
(
    SELECT supid, brand_raw, sku_raw, price, quantity, update_date
    FROM sup_stat.cross_dock_lookup_v2
    EXCEPT ALL
    SELECT supid, b, a, p, q, dateupd
    FROM sup_stat.dif_step_1 FINAL
    WHERE dateupd >= today() - INTERVAL 5 DAY
);

-- 6. Commands for the Airflow task downstream of write_to_dif_v3.
-- Use a writable ClickHouse account, and fail/alert if REFRESH or WAIT fails.
-- Do not refresh after each supplier or each report upload.
-- SYSTEM REFRESH VIEW sup_stat.cross_dock_lookup_refresh_v2;
-- SYSTEM WAIT VIEW sup_stat.cross_dock_lookup_refresh_v2;

-- 7. Application cutover is a SEPARATE REQUIRED change before cleanup:
-- - Read cross_dock_lookup_v2 and join sup_list FINAL on supid = dif_id at query time.
-- - Apply current list membership, shared brand normalization, cutoff and ranking rules.
-- - Agree on FINAL and deterministic tie-breaking for SLOW/parser as well.
-- - Check refresh freshness and benchmark representative files before switching readers.
-- - Compare SLOW/FAST on an unchanged source; retain the old objects during validation.

-- 8. ONLY AFTER the new reader is deployed and validated, remove the old trigger first.
-- These commands are intentionally commented out; the current reader needs the old table.
-- DROP TABLE sup_stat.mv_cross_dock_view;
-- DROP TABLE sup_stat.mv_cross_dock;
