-- part_usage_for_month(target_month DATE): usage per part for one calendar month, with the
-- daily average. The ONE definition behind both
--   * PlexProd.part_usage_monthly (scheduled query part_usage_monthly, terraform/part_usage_monthly.sql,
--     records the previous month on the 1st) and
--   * PlexProd.part_usage_month_to_date (view: the current month so far, through yesterday),
-- so the two can never be measured differently. Method, grain and caveats: the header of
-- terraform/part_usage_monthly.sql and docs/reports/part_usage_monthly.md.
-- Days are counted through yesterday (Mountain) at most: today's production is still coming in.
-- A table function (google_bigquery_routine.part_usage_for_month in terraform/main.tf);
-- its column order is the table's, so the scheduled query can INSERT ... SELECT *.
WITH

part AS (
  SELECT
    SAFE_CAST(Part_Key AS INT64)                         AS part_key,
    Part_No                                              AS part_no,
    Revision                                             AS revision,
    Name                                                 AS part_name,
    NULLIF(TRIM(Unit), '')                               AS unit,
    SAFE_CAST(Product_Type_Key AS FLOAT64)               AS product_type_key,
    Part_Type                                            AS part_type,
    SAFE_CAST(Part_Group_Key AS INT64)                   AS part_group_key
  FROM `voxdatalake.PlexProd.raw_Part_v_Part`
),

wrap AS (
  SELECT
    SAFE_CAST(b.Part_Key AS INT64)            AS wrapper_key,
    SAFE_CAST(b.Component_Part_Key AS INT64)  AS root_key,
    MAX(SAFE_CAST(b.Quantity AS FLOAT64))     AS factor
  FROM `voxdatalake.PlexProd.raw_Part_v_BOM` b
  JOIN part pw ON pw.part_key = SAFE_CAST(b.Part_Key AS INT64)
  JOIN part pc ON pc.part_key = SAFE_CAST(b.Component_Part_Key AS INT64)
  WHERE pw.part_no = pc.part_no
    AND pw.part_key != pc.part_key
    AND COALESCE(SAFE_CAST(b.Active AS INT64), 1) != 0
    AND SAFE_CAST(b.Quantity AS FLOAT64) > 0
  GROUP BY wrapper_key, root_key
),

prod AS (
  SELECT
    SAFE_CAST(Part_Operation_Key AS INT64) AS op_key,
    SAFE_CAST(Quantity AS FLOAT64)         AS q,
    COALESCE(
      DATE(TIMESTAMP_ADD(
        TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(Report_Date AS STRING) AS INT64), 0), 1000)),
        INTERVAL 2 HOUR)),
      NULLIF(SAFE_CAST(CAST(Report_Date AS STRING) AS DATE), DATE '1970-01-01')
    )                                      AS d
  FROM `voxdatalake.PlexProd.part_production_current`
  WHERE COALESCE(SAFE_CAST(Rejected AS INT64), 0) = 0
),

span AS (
  SELECT
    GREATEST(target_month, MIN(d)) AS first_d,
    LEAST(LAST_DAY(target_month), DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 1 DAY)) AS last_d
  FROM prod
),

usage AS (
  SELECT
    SAFE_CAST(b.Component_Part_Key AS INT64)            AS part_key,
    pr.d,
    SUM(pr.q * SAFE_CAST(b.Quantity AS FLOAT64))        AS qty_used
  FROM prod pr
  CROSS JOIN span s
  JOIN `voxdatalake.PlexProd.raw_Part_v_BOM` b
    ON SAFE_CAST(b.Part_Operation_Key AS INT64) = pr.op_key
  LEFT JOIN wrap w
    ON w.wrapper_key = SAFE_CAST(b.Part_Key AS INT64)
   AND w.root_key    = SAFE_CAST(b.Component_Part_Key AS INT64)
  WHERE pr.d BETWEEN s.first_d AND s.last_d
    AND COALESCE(SAFE_CAST(b.Active AS INT64), 1) != 0
    AND w.wrapper_key IS NULL
  GROUP BY part_key, pr.d
),

attrs AS (
  SELECT
    p.part_no,
    COALESCE(MAX(IF(w.wrapper_key IS NULL, p.part_name, NULL)), MAX(p.part_name)) AS part_name,
    MAX(IF(w.wrapper_key IS NULL, p.unit, NULL))                            AS unit,
    COALESCE(MAX(IF(w.wrapper_key IS NULL, p.product_type_key, NULL)),
             MAX(p.product_type_key))                                       AS product_type_key,
    ARRAY_AGG(STRUCT(p.part_key, p.revision, p.part_type, p.part_group_key)
              ORDER BY IF(w.wrapper_key IS NULL, 0, 1), p.part_key LIMIT 1)[OFFSET(0)] AS stk
  FROM part p
  LEFT JOIN wrap w ON w.wrapper_key = p.part_key
  WHERE p.part_no IS NOT NULL
  GROUP BY p.part_no
),

used AS (
  SELECT
    p.part_no,
    SUM(u.qty_used * COALESCE(w.factor, 1)) AS qty_used,
    COUNT(DISTINCT u.d)                     AS days_with_usage
  FROM part p
  LEFT JOIN wrap w ON w.wrapper_key = p.part_key
  JOIN usage u     ON u.part_key    = p.part_key
  WHERE p.part_no IS NOT NULL
  GROUP BY p.part_no
),

loaded AS (
  SELECT TIMESTAMP_MILLIS(MIN(last_modified_time)) AS loaded_at
  FROM `voxdatalake.PlexProd.__TABLES__`
  WHERE table_id IN ('raw_Part_v_Production', 'raw_Part_v_BOM', 'raw_Part_v_Part')
)

SELECT
  target_month                                              AS usage_month,
  a.stk.part_key                                            AS part_key,
  a.part_no,
  a.stk.revision                                            AS revision,
  a.part_name,
  pt.Product_Type                                           AS part_product_type,
  a.stk.part_type                                           AS part_type,
  pg.Part_Group                                             AS part_group,
  a.unit,
  u.qty_used,
  u.days_with_usage,
  EXTRACT(DAY FROM LAST_DAY(target_month))                               AS days_in_month,
  DATE_DIFF(s.last_d, s.first_d, DAY) + 1                   AS days_covered,
  DATE_DIFF(s.last_d, s.first_d, DAY) + 1 < EXTRACT(DAY FROM LAST_DAY(target_month)) AS is_partial_month,
  SAFE_DIVIDE(u.qty_used, DATE_DIFF(s.last_d, s.first_d, DAY) + 1)      AS avg_daily_usage,
  l.loaded_at                                               AS source_tables_loaded_at,
  CURRENT_TIMESTAMP()                                       AS recorded_at
FROM used u
JOIN attrs a ON a.part_no = u.part_no
CROSS JOIN span s
CROSS JOIN loaded l
LEFT JOIN `voxdatalake.PlexProd.raw_Part_v_Part_Product_Type` pt
  ON SAFE_CAST(pt.Product_Type_Key AS FLOAT64) = a.product_type_key
LEFT JOIN `voxdatalake.PlexProd.raw_Part_v_Part_Group` pg
  ON SAFE_CAST(pg.Part_Group_Key AS INT64) = a.stk.part_group_key

