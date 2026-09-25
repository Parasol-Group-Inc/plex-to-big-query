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

-- ⚠ FIXED 2026-09-22 — THIS VIEW WAS UNQUERYABLE, not empty.
-- It read `DATE(SAFE_CAST(Cycle_Inventory_Date AS TIMESTAMP))`. That column
-- arrives as INT64 nanoseconds, and BigQuery rejects an INT64→TIMESTAMP cast
-- outright — SAFE_CAST does not rescue an illegal cast, it only rescues a
-- failed parse — so the view failed to PARSE and every query against it
-- errored. It was written when the raw table was still all-STRING (0 rows
-- autodetected), and broke silently the moment real typed rows landed.
--
-- Now uses the repo's standard date-conversion COALESCE, which handles all
-- three shapes a raw date column takes here. See reports/sql/work_orders_view.sql.

-- ⚠ FIXED 2026-09-24 — ACCURACY WAS WEIGHTED PER COUNT, NOT PER LOCATION.
-- accuracy_pct used to AVG over every count row, so a location counted twice
-- in a month weighed double — and the location that gets recounted is usually
-- the one that missed, so misses were over-weighted. (PlexTest's Sep 2026
-- "82.1%" was injected test rows, not real counts — do not cite it.) The
-- definition above is a per-location
-- hit rate, so now each location is judged ONCE per month, on its LATEST count
-- that month (latest Cycle_Inventory_Date, ties broken by the higher
-- Cycle_Inventory_Key). Every per-location figure — accuracy_pct,
-- locations_with_a_miss, the quantity sums and accuracy_pct_qty_weighted,
-- avg_plex_accuracy — reads that one count per location. items_counted,
-- counters and last_counted_date still cover every count, so the effort is
-- still visible; recounted_locations says how many locations were counted
-- more than once. locations_counted is exactly the accuracy_pct denominator.
-- A count with no Location (none dated on this tenant today) is treated as
-- its own location rather than all such counts collapsing into one.

WITH counts AS (
  SELECT
    ci.Location                                           AS location,
    -- The identity a location is judged under. An unlocated count stands
    -- alone rather than every NULL location merging into one.
    COALESCE(CAST(ci.Location AS STRING),
             CONCAT('unlocated:', CAST(ci.Cycle_Inventory_Key AS STRING)))
                                                          AS location_id,
    SAFE_CAST(ci.Cycle_Inventory_Key AS INT64)            AS cycle_inventory_key,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(ci.Cycle_Inventory_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(ci.Cycle_Inventory_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(ci.Cycle_Inventory_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    )  AS count_date,
    DATE_TRUNC(
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(ci.Cycle_Inventory_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(ci.Cycle_Inventory_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(ci.Cycle_Inventory_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    ), MONTH)  AS count_month,
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
),

ranked AS (
  SELECT
    c.*,
    ROW_NUMBER() OVER (
      PARTITION BY c.count_month, c.location_id
      ORDER BY c.count_date DESC, c.cycle_inventory_key DESC
    ) = 1                                                 AS is_latest_in_month,
    COUNT(*) OVER (PARTITION BY c.count_month, c.location_id) AS counts_this_month
  FROM counts AS c
)

SELECT
  r.count_month,

  -- The three the warehouse tracks.
  COUNTIF(r.is_latest_in_month)                   AS locations_counted,
  COUNT(*)                                        AS items_counted,
  AVG(IF(r.is_latest_in_month, IF(r.is_accurate, 1.0, 0.0), NULL)) * 100
                                                  AS accuracy_pct,

  -- Supporting detail.
  COUNT(DISTINCT r.counted_by)                    AS counters,
  MAX(r.count_date)                               AS last_counted_date,
  COUNTIF(r.is_latest_in_month AND NOT r.is_accurate)
                                                  AS locations_with_a_miss,
  SUM(IF(r.is_latest_in_month, r.accounted_for, NULL))   AS accounted_for_qty,
  SUM(IF(r.is_latest_in_month, r.unaccounted_for, NULL)) AS unaccounted_for_qty,
  SUM(IF(r.is_latest_in_month, r.moved, NULL))           AS moved_qty,

  -- Not the tile. Kept because a gap between this and accuracy_pct means the
  -- misses are concentrated in the locations holding the most stock, which the
  -- hit rate alone cannot show. Same one-count-per-location basis.
  SAFE_DIVIDE(
    SUM(IF(r.is_latest_in_month, r.accounted_for, NULL)),
    SUM(IF(r.is_latest_in_month, r.accounted_for, NULL))
      + SUM(IF(r.is_latest_in_month, r.unaccounted_for, NULL))
  ) * 100                                         AS accuracy_pct_qty_weighted,

  -- Plex's own per-count figure, averaged over the same latest-per-location
  -- counts, purely as a cross-check on the reading of its Accuracy column.
  AVG(IF(r.is_latest_in_month, r.plex_accuracy, NULL))   AS avg_plex_accuracy,

  -- New 2026-09-24: locations counted more than once this month (only their
  -- latest count is judged).
  COUNTIF(r.is_latest_in_month AND r.counts_this_month > 1)
                                                  AS recounted_locations

FROM ranked AS r
GROUP BY r.count_month
ORDER BY r.count_month DESC
