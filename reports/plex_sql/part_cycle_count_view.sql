-- part_cycle_count_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/part_cycle_count_view.sql
-- confidence: high
-- plex_views: Part_v_Cycle_Inventory
-- notes: Mechanical translation (COUNTIF/IF -> SUM/CASE, SAFE_DIVIDE -> NULLIF); booleans become 1/0 internally. Location is cast to varchar for the location_id identity.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per month.
-- RULE: each location is judged ONCE per month on its latest count (latest date, then higher key);
--       accurate = Unaccounted_For is 0/NULL. accuracy_pct = per-location hit rate, not quantity-weighted.
-- RULE: a count with no Location stands alone as its own location.
WITH counts AS (
  SELECT
    ci.Location                                           AS location,
    COALESCE(CAST(ci.Location AS varchar(200)),
             CONCAT('unlocated:', CAST(ci.Cycle_Inventory_Key AS varchar(30))))
                                                          AS location_id,
    ci.Cycle_Inventory_Key                                AS cycle_inventory_key,
    CAST(ci.Cycle_Inventory_Date AS date)                 AS count_date,
    DATEFROMPARTS(YEAR(ci.Cycle_Inventory_Date), MONTH(ci.Cycle_Inventory_Date), 1) AS count_month,
    ci.Cycle_Inventory_By                                 AS counted_by,
    ci.Accuracy                                           AS plex_accuracy,
    ci.Accounted_For                                      AS accounted_for,
    ci.Unaccounted_For                                    AS unaccounted_for,
    ci.Moved                                              AS moved,
    CASE WHEN ISNULL(ci.Unaccounted_For, 0) = 0 THEN 1 ELSE 0 END AS is_accurate
  FROM Part_v_Cycle_Inventory AS ci
  WHERE ci.Cycle_Inventory_Date IS NOT NULL
),

ranked AS (
  SELECT
    c.*,
    CASE WHEN ROW_NUMBER() OVER (
           PARTITION BY c.count_month, c.location_id
           ORDER BY c.count_date DESC, c.cycle_inventory_key DESC) = 1 THEN 1 ELSE 0 END AS is_latest_in_month,
    COUNT(*) OVER (PARTITION BY c.count_month, c.location_id) AS counts_this_month
  FROM counts AS c
)

SELECT
  r.count_month,

  -- the three the warehouse tracks
  SUM(r.is_latest_in_month)                       AS locations_counted,
  COUNT(*)                                        AS items_counted,
  AVG(CASE WHEN r.is_latest_in_month = 1 THEN CAST(r.is_accurate AS float) END) * 100
                                                  AS accuracy_pct,

  -- supporting detail
  COUNT(DISTINCT r.counted_by)                    AS counters,
  MAX(r.count_date)                               AS last_counted_date,
  SUM(CASE WHEN r.is_latest_in_month = 1 AND r.is_accurate = 0 THEN 1 ELSE 0 END)
                                                  AS locations_with_a_miss,
  SUM(CASE WHEN r.is_latest_in_month = 1 THEN r.accounted_for END)   AS accounted_for_qty,
  SUM(CASE WHEN r.is_latest_in_month = 1 THEN r.unaccounted_for END) AS unaccounted_for_qty,
  SUM(CASE WHEN r.is_latest_in_month = 1 THEN r.moved END)           AS moved_qty,

  -- quantity-weighted accuracy, not the tile; a gap vs accuracy_pct means misses sit in big locations
  SUM(CASE WHEN r.is_latest_in_month = 1 THEN r.accounted_for END)
    / NULLIF(SUM(CASE WHEN r.is_latest_in_month = 1 THEN r.accounted_for END)
           + SUM(CASE WHEN r.is_latest_in_month = 1 THEN r.unaccounted_for END), 0) * 100
                                                  AS accuracy_pct_qty_weighted,

  -- Plex's own per-count Accuracy column on the same latest-per-location counts (cross-check)
  AVG(CASE WHEN r.is_latest_in_month = 1 THEN r.plex_accuracy END)   AS avg_plex_accuracy,

  -- locations counted more than once this month (only their latest count is judged)
  SUM(CASE WHEN r.is_latest_in_month = 1 AND r.counts_this_month > 1 THEN 1 ELSE 0 END)
                                                  AS recounted_locations
FROM ranked AS r
GROUP BY r.count_month
ORDER BY r.count_month DESC;
