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
-- DEPENDS ON inventory_available_to_sell_report (same pipeline, listed before this view).

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

base AS (
  SELECT
    a.part_key,
    a.part_no,
    a.part_name,
    a.minimum_inventory_quantity AS reorder_point,
    a.on_hand_qty,
    a.available_vs_total_demand  AS quantity_available,
    u.qty_used / NULLIF(DATE_DIFF(s.last_d, s.first_d, DAY) + 1, 0) AS avg_daily_usage,
    DATE_DIFF(s.last_d, s.first_d, DAY) + 1                          AS usage_days,
    COALESCE(oo.on_order_qty, 0) AS on_order_qty,
    COALESCE(oj.open_job_qty, 0) AS open_job_qty
  FROM `{gcp_project}.{dataset}.inventory_available_to_sell_report` a
  CROSS JOIN span s
  LEFT JOIN usage u      ON u.part_key = SAFE_CAST(a.part_key AS INT64)
  LEFT JOIN on_order oo  ON oo.part_number = a.part_no
  LEFT JOIN open_jobs oj ON oj.part_key = SAFE_CAST(a.part_key AS INT64)
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
  (on_order_qty > 0 OR open_job_qty > 0)     AS in_mfg_or_ordered
FROM base
WHERE reorder_point > 0 OR avg_daily_usage > 0
