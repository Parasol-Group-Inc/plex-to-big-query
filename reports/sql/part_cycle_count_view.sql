-- Vox Scorecard | Cycle Count Accuracy
-- ============================================================================
-- Cycle counting was recorded in this repo as "Plex probably can't do this"
-- because Warehouse_v_Cycle_Count / _Line genuinely do not exist on this
-- tenant (the ODBC driver returns "Base table ... not found"). It lives under
-- the PART module instead — the same trap as on-hand inventory, where
-- Warehouse_v_Part_Quantity was the intuitive guess and Part_v_Container was
-- the real carrier.
--
-- Grain: one row per month. Confirmed in scope 2026-09-11, along with the
-- three numbers the warehouse team actually tracks:
--
--     locations_counted · items_counted · accuracy_pct
--
-- ── HOW ACCURACY IS DEFINED, AND WHY IT IS NOT THE OBVIOUS ONE ──────────────
-- The first version of this view computed accuracy by weighting each count by
-- quantity, on the reasoning that a per-count percentage cannot be averaged
-- without weighting or a one-container location counts the same as a full
-- rack. That is defensible arithmetic and it is NOT what Vox means.
--
-- Their definition (2026-09-11): each assigned location is judged accurate or
-- not — it either held what it was supposed to or it didn't — and those
-- yes/nos are then averaged. It is a per-location hit rate, deliberately
-- blind to how much sat in each location.
--
-- So `accuracy_pct` is that hit rate, because matching the number the
-- warehouse already reports matters more than being cleverer than it.
-- `accuracy_pct_qty_weighted` is kept beside it, unused by the tile, because
-- the two diverging is a real signal: it means the misses are concentrated in
-- the big locations.
--
-- Counting periods are lumpy on purpose — "they go through periods where they
-- do a whole lot and where they don't do anything" — so a month with no counts
-- is normal and must not read as 0% accurate. `locations_counted = 0` is what
-- a consumer should check before showing a percentage at all.

WITH counts AS (
  SELECT
    ci.Location                                           AS location,
    DATE(SAFE_CAST(ci.Cycle_Inventory_Date AS TIMESTAMP)) AS count_date,
    DATE_TRUNC(DATE(SAFE_CAST(ci.Cycle_Inventory_Date AS TIMESTAMP)), MONTH)
                                                          AS count_month,
    ci.Cycle_Inventory_By                                 AS counted_by,
    SAFE_CAST(ci.Accuracy AS FLOAT64)                     AS plex_accuracy,
    SAFE_CAST(ci.Accounted_For AS FLOAT64)                AS accounted_for,
    SAFE_CAST(ci.Unaccounted_For AS FLOAT64)              AS unaccounted_for,
    SAFE_CAST(ci.Moved AS FLOAT64)                        AS moved,

    -- The per-location yes/no the average is built from: the location held
    -- what it was supposed to. Anything unaccounted for makes it a miss.
    IFNULL(SAFE_CAST(ci.Unaccounted_For AS FLOAT64), 0) = 0 AS is_accurate

  FROM `{gcp_project}.{dataset}.raw_Part_v_Cycle_Inventory` AS ci
  WHERE ci.Cycle_Inventory_Date IS NOT NULL
)

SELECT
  c.count_month,

  -- The three the warehouse tracks.
  COUNT(DISTINCT c.location)                      AS locations_counted,
  COUNT(*)                                        AS items_counted,
  AVG(IF(c.is_accurate, 1.0, 0.0)) * 100          AS accuracy_pct,

  -- Supporting detail.
  COUNT(DISTINCT c.counted_by)                    AS counters,
  MAX(c.count_date)                               AS last_counted_date,
  COUNTIF(NOT c.is_accurate)                      AS locations_with_a_miss,
  SUM(c.accounted_for)                            AS accounted_for_qty,
  SUM(c.unaccounted_for)                          AS unaccounted_for_qty,
  SUM(c.moved)                                    AS moved_qty,

  -- Not the tile. Kept because a gap between this and accuracy_pct means the
  -- misses are concentrated in the locations holding the most stock, which the
  -- hit rate alone cannot show.
  SAFE_DIVIDE(
    SUM(c.accounted_for),
    SUM(c.accounted_for) + SUM(c.unaccounted_for)
  ) * 100                                         AS accuracy_pct_qty_weighted,

  -- Plex's own per-count figure, averaged, purely as a cross-check on the
  -- reading of its Accuracy column.
  AVG(c.plex_accuracy)                            AS avg_plex_accuracy

FROM counts AS c
GROUP BY c.count_month
ORDER BY c.count_month DESC
