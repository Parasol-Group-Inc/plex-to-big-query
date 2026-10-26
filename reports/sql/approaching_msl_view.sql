-- approaching_msl_report — rebuild of Jennilyn's "Approaching MSL" Google Sheet (2026-10-26)
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime. Do NOT hardcode them.
--
-- GRAIN: one row per part that has a reorder point (Part.Minimum_Inventory_Quantity > 0)
-- or any measured usage.
--
-- COLUMNS, in the sheet's order:
--   reorder_point        Part_v_Part.Minimum_Inventory_Quantity
--   on_hand_qty          Part_v_Container (via inventory_available_to_sell_report)
--   quantity_available   on hand MINUS sold demand MINUS BOM-exploded demand (the
--                        sheet's "Current QTY Available"). It goes NEGATIVE on purpose:
--                        finished goods on open orders will consume more of the part than
--                        is in stock. Same number as inventory_out_of_stock_report.
--   at_reorder_point     quantity_available <= reorder_point
--   avg_daily_usage      DERIVED, see usage CTE. Plex stores no average.
--   days_on_hand         on_hand_qty / avg_daily_usage
--   days_to_reorder      (quantity_available - reorder_point) / avg_daily_usage; negative
--                        = already past the reorder point by that many days of usage
--   on_order_qty         open purchase orders for the part (purchasing_open_orders_report)
--   open_job_qty         quantity on open jobs making the part
--   in_mfg_or_ordered    on_order_qty > 0 OR open_job_qty > 0
--
-- AVG DAILY USAGE: component quantity consumed by recorded production
--   = SUM(Part_v_Production.Quantity x Part_v_BOM.Quantity) joined on Part_Operation_Key,
--   rejected production excluded, over the last 90 days or since Plex's first recorded
--   production if that is shorter (usage_days). Plex production history starts 2026-10-18,
--   so early figures rest on very few days: check usage_days before trusting a number.
--
-- NETSUITE FALLBACK (added 2026-10-26): Plex has under two weeks of production history,
--   so most parts have no usable average. The manual-data app's "MSL inputs" tab holds
--   NetSuite's average daily usage and reorder point per part (msl_item_inputs), and its
--   "MSL rules" tab holds the thresholds below (msl_rules). Rules and defaults:
--     usage_min_days  30    Plex usage is trusted once it rests on this many days; until
--                           then NetSuite's figure is used if there is one.
--     reorder_source  ns    'ns' or 'plex': whose reorder point wins when both exist.
--                           A NetSuite 0 counts as "none".
--     disagree_pct    25    flag when trusted Plex usage and NetSuite usage differ by more.
--     stale_days      45    flag NetSuite figures older than this.
--   usage_source says where avg_daily_usage came from; data_flag lists every reason a row
--   deserves a second look (negative availability, NetSuite-only usage, disagreement,
--   stale NetSuite figures), '; '-separated, NULL when there is nothing to say.
--
-- DEPENDS ON inventory_available_to_sell_report (same pipeline, listed before this view)
-- and on msl_item_inputs / msl_rules, which the manual-data app creates on its first push.
-- THE VIEW FAILS TO CREATE IF EITHER TABLE IS MISSING: create them empty first (DDL in
-- docs/reports/approaching_msl_report.md).

WITH

prod AS (
  SELECT
    SAFE_CAST(Part_Operation_Key AS INT64) AS op_key,
    SAFE_CAST(Quantity AS FLOAT64)         AS q,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(Report_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(Report_Date AS STRING) AS DATE), DATE '1970-01-01')
    )                                      AS d
  FROM `{gcp_project}.{dataset}.raw_Part_v_Production`
  WHERE COALESCE(SAFE_CAST(Rejected AS INT64), 0) = 0
),

span AS (
  SELECT
    MAX(d) AS last_d,
    GREATEST(DATE_SUB(MAX(d), INTERVAL 89 DAY), MIN(d)) AS first_d
  FROM prod
),

usage AS (
  SELECT
    SAFE_CAST(b.Component_Part_Key AS INT64)            AS part_key,
    SUM(pr.q * SAFE_CAST(b.Quantity AS FLOAT64))        AS qty_used
  FROM prod pr
  CROSS JOIN span s
  JOIN `{gcp_project}.{dataset}.raw_Part_v_BOM` b
    ON SAFE_CAST(b.Part_Operation_Key AS INT64) = pr.op_key
  WHERE pr.d BETWEEN s.first_d AND s.last_d
    AND COALESCE(SAFE_CAST(b.Active AS INT64), 1) != 0
  GROUP BY part_key
),

on_order AS (
  SELECT
    part_number,
    SUM(SAFE_CAST(qty_ordered AS FLOAT64)) AS on_order_qty
  FROM `{gcp_project}.{dataset}.purchasing_open_orders_report`
  GROUP BY part_number
),

open_jobs AS (
  SELECT
    SAFE_CAST(j.Part_Key AS INT64)         AS part_key,
    SUM(SAFE_CAST(j.Quantity AS FLOAT64))  AS open_job_qty
  FROM `{gcp_project}.{dataset}.raw_Part_v_Job` j
  JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Status` js
    ON SAFE_CAST(j.Job_Status_Key AS INT64) = SAFE_CAST(js.Job_Status_Key AS INT64)
  WHERE COALESCE(SAFE_CAST(js.Completed_Status AS INT64), 0) = 0
    AND COALESCE(SAFE_CAST(js.Cancelled_Status AS INT64), 0) = 0
    AND COALESCE(SAFE_CAST(js.Hold_Status AS INT64), 0) = 0
  GROUP BY part_key
),

-- Rules: newest row per rule, a tombstone removes it. Defaults apply to anything unset.
rules AS (
  SELECT rule, value
  FROM (
    SELECT rule, value, is_deleted,
           ROW_NUMBER() OVER (PARTITION BY rule ORDER BY updated_at DESC) AS rn
    FROM `{gcp_project}.{dataset}.msl_rules`
  )
  WHERE rn = 1 AND NOT IFNULL(is_deleted, FALSE)
),
cfg AS (
  SELECT
    COALESCE(MAX(IF(rule = 'usage_min_days', SAFE_CAST(value AS FLOAT64), NULL)), 30) AS usage_min_days,
    COALESCE(MAX(IF(rule = 'reorder_source', LOWER(TRIM(value)), NULL)), 'ns')        AS reorder_source,
    COALESCE(MAX(IF(rule = 'disagree_pct',   SAFE_CAST(value AS FLOAT64), NULL)), 25) AS disagree_pct,
    COALESCE(MAX(IF(rule = 'stale_days',     SAFE_CAST(value AS FLOAT64), NULL)), 45) AS stale_days
  FROM rules
),

-- NetSuite figures: newest row per NetSuite item, then newest per Plex part so two
-- NetSuite items pointing at one part never double the join.
ns AS (
  SELECT part_no, ns_avg_daily_usage, ns_reorder_point, as_of_date
  FROM (
    SELECT part_no, ns_avg_daily_usage, ns_reorder_point, as_of_date,
           ROW_NUMBER() OVER (PARTITION BY part_no ORDER BY updated_at DESC) AS rn
    FROM (
      SELECT *, ROW_NUMBER() OVER (PARTITION BY ns_item_id ORDER BY updated_at DESC) AS k
      FROM `{gcp_project}.{dataset}.msl_item_inputs`
    )
    WHERE k = 1 AND NOT IFNULL(is_deleted, FALSE) AND IFNULL(part_no, '') != ''
  )
  WHERE rn = 1
),

base AS (
  SELECT
    a.part_key,
    a.part_no,
    a.part_name,
    a.minimum_inventory_quantity AS plex_reorder_point,
    NULLIF(ns.ns_reorder_point, 0) AS ns_reorder_point,
    a.on_hand_qty,
    a.available_vs_total_demand  AS quantity_available,
    u.qty_used / NULLIF(DATE_DIFF(s.last_d, s.first_d, DAY) + 1, 0) AS plex_usage,
    ns.ns_avg_daily_usage        AS ns_usage,
    ns.as_of_date                AS ns_as_of,
    DATE_DIFF(s.last_d, s.first_d, DAY) + 1                          AS usage_days,
    COALESCE(oo.on_order_qty, 0) AS on_order_qty,
    COALESCE(oj.open_job_qty, 0) AS open_job_qty,
    c.usage_min_days, c.reorder_source, c.disagree_pct, c.stale_days
  FROM `{gcp_project}.{dataset}.inventory_available_to_sell_report` a
  CROSS JOIN span s
  CROSS JOIN cfg c
  LEFT JOIN usage u      ON u.part_key = SAFE_CAST(a.part_key AS INT64)
  LEFT JOIN ns           ON ns.part_no = a.part_no
  LEFT JOIN on_order oo  ON oo.part_number = a.part_no
  LEFT JOIN open_jobs oj ON oj.part_key = SAFE_CAST(a.part_key AS INT64)
),

chosen AS (
  SELECT
    *,
    (usage_days >= usage_min_days AND plex_usage > 0) AS plex_trusted,
    IF(reorder_source = 'plex',
       COALESCE(NULLIF(plex_reorder_point, 0), ns_reorder_point),
       COALESCE(ns_reorder_point, plex_reorder_point)) AS reorder_point
  FROM base
),

final AS (
  SELECT
    *,
    IF(plex_trusted, plex_usage, COALESCE(ns_usage, plex_usage)) AS avg_daily_usage,
    CASE
      WHEN plex_trusted           THEN 'Plex'
      WHEN ns_usage IS NOT NULL   THEN 'NetSuite'
      WHEN plex_usage IS NOT NULL THEN 'Plex (short history)'
    END AS usage_source
  FROM chosen
)

SELECT
  part_no,
  part_name                                  AS description,
  reorder_point,
  on_hand_qty,
  quantity_available,
  (quantity_available <= reorder_point)      AS at_reorder_point,
  avg_daily_usage,
  usage_days,
  SAFE_DIVIDE(on_hand_qty, avg_daily_usage)  AS days_on_hand,
  SAFE_DIVIDE(quantity_available - reorder_point, avg_daily_usage) AS days_to_reorder,
  on_order_qty,
  open_job_qty,
  (on_order_qty > 0 OR open_job_qty > 0)     AS in_mfg_or_ordered,
  usage_source,
  plex_usage                                 AS plex_avg_daily_usage,
  ns_usage                                   AS ns_avg_daily_usage,
  plex_reorder_point,
  ns_reorder_point,
  ns_as_of,
  NULLIF(ARRAY_TO_STRING([
    IF(quantity_available < 0,
       'Negative availability: open demand exceeds stock', NULL),
    IF(usage_source = 'NetSuite',
       CONCAT('Usage from NetSuite: Plex has ', CAST(usage_days AS STRING), ' days of history, needs ',
              CAST(CAST(usage_min_days AS INT64) AS STRING)), NULL),
    IF(usage_source = 'Plex (short history)',
       CONCAT('Usage from Plex on only ', CAST(usage_days AS STRING), ' days, no NetSuite figure'), NULL),
    IF(plex_trusted AND ns_usage > 0
         AND ABS(plex_usage - ns_usage) / ns_usage * 100 > disagree_pct,
       CONCAT('Plex and NetSuite usage differ by more than ',
              CAST(CAST(disagree_pct AS INT64) AS STRING), '%'), NULL),
    IF(ns_as_of IS NOT NULL AND DATE_DIFF(CURRENT_DATE(), ns_as_of, DAY) > stale_days,
       CONCAT('NetSuite figures older than ', CAST(CAST(stale_days AS INT64) AS STRING), ' days'), NULL)
  ], '; '), '') AS data_flag
FROM final
WHERE reorder_point > 0 OR avg_daily_usage > 0
