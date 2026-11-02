-- Refreshable cross-dock MV for ClickHouse 24.10.1.2812 (single server, Atomic database).
-- Permanent names: rmv_cross_dock (data table), rmv_cross_dock_view (refreshable MV).
-- The rmv prefix distinguishes these objects from the existing incremental mv objects.
-- Run each numbered stage separately and inspect its result before continuing.
-- Create this lookup before deploying the FAST reader that uses rmv_cross_dock.
-- Do not drop the old objects until that reader has been deployed and verified.

-- 1. Confirm the server/database and preserve the old definitions outside this session.
SELECT version();
SELECT name, engine FROM system.databases WHERE name = 'sup_stat';
SHOW CREATE TABLE sup_stat.mv_cross_dock_view;
SHOW CREATE TABLE sup_stat.mv_cross_dock;

-- 2. Create an empty, separately named destination. Plain MergeTree is intentional:
-- each refresh replaces the complete contents; it does not append/reconcile versions.
-- Source brands/SKUs are already normalized uppercase strings. Preserve them unchanged.
-- Keep zero-stock rows; normalize uploaded brands to the same canonical names in the reader.
CREATE TABLE sup_stat.rmv_cross_dock
(
    supid Int32,
    brand String,
    sku String,
    price Float64,
    quantity Int32,
    update_date Date,
    refreshed_at DateTime
)
ENGINE = MergeTree
ORDER BY (brand, sku, supid, update_date);

-- 3. Populate automatically on creation, then replace the snapshot after each refresh.
-- No APPEND, supplier join, positive-stock filter, or independently merging target.
-- FINAL resolves same-day replacements BEFORE the reader filters quantity > 0.
-- Date filtering is safe here because dateupd is part of the source replacement key.
-- Five days are retained; the reader must still enforce its two-day eligibility cutoff.
-- AFTER 1 DAY is a fallback. Trigger REFRESH + WAIT after each completed supplier load.
CREATE MATERIALIZED VIEW sup_stat.rmv_cross_dock_view
REFRESH AFTER 1 DAY
TO sup_stat.rmv_cross_dock
AS
SELECT
    supid,
    b AS brand,
    a AS sku,
    p AS price,
    q AS quantity,
    dateupd AS update_date,
    now() AS refreshed_at
FROM sup_stat.dif_step_1 FINAL
WHERE dateupd >= today() - INTERVAL 5 DAY;

-- 4. Wait for initial population and inspect refresh state (columns available in 24.10).
SYSTEM WAIT VIEW sup_stat.rmv_cross_dock_view;
SELECT
    database, view, status, last_success_time, last_success_duration_ms,
    last_refresh_time, next_refresh_time, exception
FROM system.view_refreshes
WHERE database = 'sup_stat' AND view = 'rmv_cross_dock_view';

SELECT count() AS rows, min(update_date), max(update_date), max(refreshed_at)
FROM sup_stat.rmv_cross_dock;

-- 5. Compare both directions during a quiet interval without source inserts/mutations.
-- Each result must be zero. Source changes after the refresh can legitimately differ.
SELECT 'source_minus_snapshot' AS comparison, count() AS differences
FROM
(
    SELECT supid, b, a, p, q, dateupd
    FROM sup_stat.dif_step_1 FINAL
    WHERE dateupd >= today() - INTERVAL 5 DAY
    EXCEPT ALL
    SELECT supid, brand, sku, price, quantity, update_date
    FROM sup_stat.rmv_cross_dock
);

SELECT 'snapshot_minus_source' AS comparison, count() AS differences
FROM
(
    SELECT supid, brand, sku, price, quantity, update_date
    FROM sup_stat.rmv_cross_dock
    EXCEPT ALL
    SELECT supid, b, a, p, q, dateupd
    FROM sup_stat.dif_step_1 FINAL
    WHERE dateupd >= today() - INTERVAL 5 DAY
);

-- 6. Commands for the Airflow task downstream of write_to_dif_v3.
-- Use a writable ClickHouse account, and fail/alert if REFRESH or WAIT fails.
-- Do not refresh after each supplier or each report upload.
-- Run after the complete ingestion task finishes: ingestion -> REFRESH -> WAIT.
-- Implemented by refresh_cross_dock in airflow/dags/write_to_dif.py.
-- SYSTEM REFRESH VIEW sup_stat.rmv_cross_dock_view;
-- SYSTEM WAIT VIEW sup_stat.rmv_cross_dock_view;

-- 7. Application deployment and validation are REQUIRED before cleanup:
-- - Read rmv_cross_dock and join sup_list FINAL on supid = dif_id at query time.
-- - Apply current list membership, shared brand normalization, cutoff and ranking rules.
-- - Use FINAL in admin2 and parser SLOW reads, including supplier metadata.
-- - Choose latest date, then lowest price, then highest quantity within a supplier.
--   Order the top three by price and supplier name (then supplier ID in admin2).
-- - Preserve positive-stock filtering BEFORE selecting the newest qualifying day.
--   Yesterday's positive offer remains eligible when today's separate daily row is zero.
-- - Normalize uploaded brands/SKUs to the same uppercase convention as dif_step_1.
--   Match directly against the source b/a or snapshot brand/sku fields without case conversion.
-- - Check refresh freshness and benchmark representative files after deploying the reader.
-- - Compare SLOW/FAST on an unchanged source; retain the old objects during validation.

-- 8. ONLY AFTER the new reader is deployed and validated, remove the old trigger first.
-- These commands stay commented out until the deployment and comparisons pass.
-- DROP TABLE sup_stat.mv_cross_dock_view;
-- DROP TABLE sup_stat.mv_cross_dock;
