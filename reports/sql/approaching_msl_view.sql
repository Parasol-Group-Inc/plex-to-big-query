-- approaching_msl_report — rebuild of Jennilyn's "Approaching MSL" Google Sheet (2026-10-26)
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime. Do NOT hardcode them.
--
-- GRAIN: one row per part NUMBER (Part_Keys rolled up, see WRAPPER KEYS below) that has a
-- reorder point (Part.Minimum_Inventory_Quantity > 0) or any measured usage. Driven from
-- Part_v_Part, not from inventory_available_to_sell_report: that view only lists parts with
-- stock or open demand, so a part with a reorder point, nothing in stock and nothing on order
-- (the most urgent case) used to be missing (419 parts on 2026-10-28).
--
-- COLUMNS, in the sheet's order:
--   reorder_point        Part_v_Part.Minimum_Inventory_Quantity, Plex only (Jennilyn,
--                        2026-10-28); 0 when Plex has none. ns_reorder_point stays
--                        as a reference column.
--   on_hand_qty          Part_v_Container (via inventory_available_to_sell_report)
--   quantity_available   on hand MINUS sold demand MINUS BOM-exploded demand (the
--                        sheet's "Current QTY Available"). It goes NEGATIVE on purpose:
--                        finished goods on open orders will consume more of the part than
--                        is in stock. Same number as inventory_out_of_stock_report.
--   at_reorder_point     quantity_available <= reorder_point when the part has one (at or
--                        below, the usual reorder rule; the sheet used <, which differs on 4
--                        parts); with no reorder point, only when available is negative
--                        (2026-10-28: 0 <= 0 flagged 23 parts with nothing set and nothing due).
--   avg_daily_usage      DERIVED, see usage CTE. Plex stores no average.
--   days_on_hand         on_hand_qty / avg_daily_usage
--   days_to_reorder      (quantity_available - reorder_point) / avg_daily_usage; negative
--                        = already past the reorder point by that many days of usage
--   on_order_qty         open purchase order releases for the part (see on_order CTE)
--   open_job_qty         quantity on open jobs making the part
--   in_mfg_or_ordered    on_order_qty > 0 OR open_job_qty > 0
--   demand_qty           the demand quantity_available subtracts: sold demand plus
--                        BOM-exploded demand from open orders and jobs of PARENT items
--                        (stocked key only, see WRAPPER KEYS). on_hand_qty - demand_qty =
--                        quantity_available. NOT open_job_qty, which is jobs making the
--                        part itself (added 2026-10-28).
--                        NETTED since 2026-10-30: a parent passes down only what its own
--                        stock does not cover, level by level (inventory_available_to_sell_
--                        view.sql, "Netted component demand"). Jennilyn's capsule 33312-00NUT46-0
--                        read 12.05M (50,000 bottles x 241) against 2,182,496 netted.
--   gross_demand_qty     the same demand WITHOUT netting: every open order exploded through
--                        the whole BOM. Kept beside demand_qty because Jennilyn wants both
--                        (total demand on a component, and that reduced by stock above it).
--   Every quantity is in the unit of the part's stocked key (unit column; blank in Plex
--   for most raw materials, which are kg).
--   part_type / part_group_key / part_group / part_source_key   filter attributes of the
--                        stocked key (added 2026-10-28 from Jennilyn's v2 view, which this
--                        replaces).
--
-- WRAPPER KEYS (fixed 2026-10-28): Plex holds up to four Part_Keys per part number. One is
--   the stocked key; each other one is a "wrapper" whose own BOM is a single line pointing at
--   the stocked key, with the conversion factor as its quantity (1, 0.001 for a gram key,
--   0.000001 for a milligram key). Flat_BOM explodes demand through the wrapper, so the
--   stocked key's demand ALREADY includes the wrapper's, converted (checked on all 383
--   stocked keys). The roll-up therefore takes demand from the stocked key only, and
--   converts everything else on a wrapper (stock, minimum, usage, jobs, orders) by its
--   factor. Until 2026-10-28 it summed every key: demand counted twice, in mixed units for
--   gram keys, which put 39 parts at their reorder point wrongly.
--
-- AVG DAILY USAGE: component quantity consumed by recorded production
--   = SUM(Part_v_Production.Quantity x Part_v_BOM.Quantity) joined on Part_Operation_Key,
--   rejected production excluded, over the last 90 days or since Plex's first recorded
--   production if that is shorter (usage_days). Plex production history starts 2026-10-18,
--   so early figures rest on very few days: check usage_days before trusting a number.
--   Production IS recorded on wrapper operations (stocked key into wrapper); those BOM lines
--   are skipped, and the wrapper's own downstream consumption is counted instead, converted,
--   so each kilo is counted once.
--
-- NETSUITE FALLBACK (added 2026-10-26): Plex has under two weeks of production history,
--   so most parts have no usable average. The manual-data app's "MSL inputs" tab holds
--   NetSuite's average daily usage and reorder point per part (msl_item_inputs), and its
--   "MSL rules" tab holds the thresholds below (msl_rules). Rules and defaults:
--     usage_min_days  30    Plex usage is trusted once it rests on this many days; until
--                           then NetSuite's figure is used if there is one.
--     reorder_source        NO LONGER READ (2026-10-28): the reorder point is Plex's.
--     disagree_pct    25    flag when trusted Plex usage and NetSuite usage differ by more.
--     stale_days      45    flag NetSuite figures older than this.
--   usage_source says where avg_daily_usage came from; data_flag lists every reason a row
--   deserves a second look (negative availability, NetSuite-only usage, disagreement,
--   stale NetSuite figures, partly received PO lines), '; '-separated, NULL when there is
--   nothing to say.
--
-- DEPENDS ON inventory_available_to_sell_report (same pipeline, listed before this view),
-- the purchasing pipeline's raw Purchasing_v_* tables, and msl_item_inputs / msl_rules,
-- which the manual-data app creates on its first push. THE VIEW FAILS TO CREATE IF EITHER
-- APP TABLE IS MISSING: create them empty first (DDL in docs/reports/approaching_msl_report.md).

WITH

part AS (
  SELECT
    SAFE_CAST(Part_Key AS INT64)                         AS part_key,
    Part_No                                              AS part_no,
    Name                                                 AS part_name,
    NULLIF(TRIM(Unit), '')                               AS unit,
    SAFE_CAST(Product_Type_Key AS FLOAT64)               AS product_type_key,
    Part_Type                                            AS part_type,
    SAFE_CAST(Part_Group_Key AS INT64)                   AS part_group_key,
    SAFE_CAST(Part_Source_Key AS INT64)                  AS part_source_key,
    SAFE_CAST(Minimum_Inventory_Quantity AS FLOAT64)     AS minimum_inventory_quantity
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part`
),

-- A wrapper key's BOM line pointing at another key of the same part number. factor converts
-- one unit of the wrapper into units of the stocked key.
wrap AS (
  SELECT
    SAFE_CAST(b.Part_Key AS INT64)            AS wrapper_key,
    SAFE_CAST(b.Component_Part_Key AS INT64)  AS root_key,
    MAX(SAFE_CAST(b.Quantity AS FLOAT64))     AS factor
  FROM `{gcp_project}.{dataset}.raw_Part_v_BOM` b
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
  LEFT JOIN wrap w
    ON w.wrapper_key = SAFE_CAST(b.Part_Key AS INT64)
   AND w.root_key    = SAFE_CAST(b.Component_Part_Key AS INT64)
  WHERE pr.d BETWEEN s.first_d AND s.last_d
    AND COALESCE(SAFE_CAST(b.Active AS INT64), 1) != 0
    AND w.wrapper_key IS NULL
  GROUP BY part_key
),

-- Open purchase order releases. Read from the raw tables rather than
-- purchasing_open_orders_report so a release already marked Received on a PO that is still
-- open is left out. Plex records no received quantity per release, so a Partial release
-- counts in full and is flagged.
on_order AS (
  SELECT
    SAFE_CAST(li.Part_Key AS INT64)                      AS part_key,
    SUM(SAFE_CAST(rel.Quantity AS FLOAT64))              AS on_order_qty,
    COUNTIF(rel.Release_Status = 'Partial')              AS partial_releases
  FROM `{gcp_project}.{dataset}.raw_Purchasing_v_PO` po
  LEFT JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_PO_Status` sts
    ON SAFE_CAST(po.PO_Status_Key AS INT64) = SAFE_CAST(sts.PO_Status_Key AS INT64)
  JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_Line_Item` li
    ON SAFE_CAST(po.PO_Key AS INT64) = SAFE_CAST(li.PO_Key AS INT64)
  JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_Release` rel
    ON SAFE_CAST(li.Line_Item_Key AS INT64) = SAFE_CAST(rel.Line_Item_Key AS INT64)
  WHERE COALESCE(SAFE_CAST(sts.Cancelled_Status AS INT64), 0) = 0
    AND COALESCE(SAFE_CAST(sts.Received AS INT64), 0) = 0
    AND IFNULL(rel.Release_Status, '') != 'Received'
  GROUP BY part_key
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
    COALESCE(MAX(IF(rule = 'disagree_pct',   SAFE_CAST(value AS FLOAT64), NULL)), 25) AS disagree_pct,
    COALESCE(MAX(IF(rule = 'stale_days',     SAFE_CAST(value AS FLOAT64), NULL)), 45) AS stale_days
  FROM rules
),

-- NetSuite figures: newest row per NetSuite item, then ONE row per Plex part. Two NetSuite
-- items can be the same material (e.g. two Inositol codes pointing at one Plex part): their
-- usage ADDS, the reorder point takes the larger, the figures date from the older of the two.
ns AS (
  SELECT
    part_no,
    SUM(ns_avg_daily_usage) AS ns_avg_daily_usage,
    MAX(ns_reorder_point)   AS ns_reorder_point,
    MIN(as_of_date)         AS as_of_date
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY ns_item_id ORDER BY updated_at DESC) AS k
    FROM `{gcp_project}.{dataset}.msl_item_inputs`
  )
  WHERE k = 1 AND NOT IFNULL(is_deleted, FALSE) AND IFNULL(part_no, '') != ''
  GROUP BY part_no
),

-- One row per PART NUMBER. Wrapper keys are converted into the stocked key's unit (factor)
-- and contribute no demand of their own: the stocked key's demand already holds theirs.
inv AS (
  SELECT
    p.part_no,
    COALESCE(MAX(IF(w.wrapper_key IS NULL, p.part_name, NULL)), MAX(p.part_name)) AS part_name,
    MAX(IF(w.wrapper_key IS NULL, p.unit, NULL))                            AS unit,
    COALESCE(MAX(IF(w.wrapper_key IS NULL, p.product_type_key, NULL)),
             MAX(p.product_type_key))                                       AS product_type_key,
    -- Filter attributes (Jennilyn's approaching_msl_report_v2, 2026-10-27) from the stocked
    -- key: wrapper keys are all Part_Type 'WIP' and disagree on all three.
    ARRAY_AGG(STRUCT(p.part_type, p.part_group_key, p.part_source_key)
              ORDER BY IF(w.wrapper_key IS NULL, 0, 1), p.part_key LIMIT 1)[OFFSET(0)] AS attr,
    MAX(p.minimum_inventory_quantity * COALESCE(w.factor, 1))               AS plex_reorder_point,
    SUM(COALESCE(a.on_hand_qty, 0) * COALESCE(w.factor, 1))                 AS on_hand_qty,
    SUM(COALESCE(a.on_hand_qty, 0) * COALESCE(w.factor, 1)
        - IF(w.wrapper_key IS NULL, COALESCE(a.total_demand_qty, 0), 0))   AS quantity_available,
    SUM(IF(w.wrapper_key IS NULL, COALESCE(a.total_demand_qty, 0), 0))    AS demand_qty,
    SUM(IF(w.wrapper_key IS NULL, COALESCE(a.order_demand_qty, 0)
           + COALESCE(a.gross_component_demand_qty, 0), 0))               AS gross_demand_qty,
    SUM(u.qty_used * COALESCE(w.factor, 1))                                 AS qty_used,
    SUM(COALESCE(oj.open_job_qty, 0) * COALESCE(w.factor, 1))               AS open_job_qty,
    SUM(COALESCE(oo.on_order_qty, 0) * COALESCE(w.factor, 1))               AS on_order_qty,
    SUM(COALESCE(oo.partial_releases, 0))                                   AS partial_releases
  FROM part p
  LEFT JOIN wrap w       ON w.wrapper_key = p.part_key
  LEFT JOIN `{gcp_project}.{dataset}.inventory_available_to_sell_report` a
    ON SAFE_CAST(a.part_key AS INT64) = p.part_key
  LEFT JOIN usage u      ON u.part_key  = p.part_key
  LEFT JOIN open_jobs oj ON oj.part_key = p.part_key
  LEFT JOIN on_order oo  ON oo.part_key = p.part_key
  WHERE p.part_no IS NOT NULL
  GROUP BY p.part_no
),

base AS (
  SELECT
    i.part_no,
    i.part_name,
    i.unit,
    pt.Product_Type              AS product_type,
    i.attr.part_type,
    i.attr.part_group_key,
    pg.Part_Group                AS part_group,
    i.attr.part_source_key,
    i.plex_reorder_point,
    NULLIF(ns.ns_reorder_point, 0) AS ns_reorder_point,
    i.on_hand_qty,
    i.quantity_available,
    i.demand_qty,
    i.gross_demand_qty,
    i.qty_used / NULLIF(DATE_DIFF(s.last_d, s.first_d, DAY) + 1, 0) AS plex_usage,
    ns.ns_avg_daily_usage        AS ns_usage,
    ns.as_of_date                AS ns_as_of,
    DATE_DIFF(s.last_d, s.first_d, DAY) + 1                          AS usage_days,
    i.on_order_qty,
    i.open_job_qty,
    i.partial_releases,
    c.usage_min_days, c.disagree_pct, c.stale_days
  FROM inv i
  CROSS JOIN span s
  CROSS JOIN cfg c
  LEFT JOIN ns ON ns.part_no = i.part_no
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Product_Type` pt
    ON SAFE_CAST(pt.Product_Type_Key AS FLOAT64) = i.product_type_key
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Group` pg
    ON SAFE_CAST(pg.Part_Group_Key AS INT64) = i.attr.part_group_key
),

chosen AS (
  SELECT
    *,
    (usage_days >= usage_min_days AND plex_usage > 0) AS plex_trusted,
    plex_reorder_point AS reorder_point
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
  (quantity_available < 0
   OR (reorder_point > 0 AND quantity_available <= reorder_point)) AS at_reorder_point,
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
       CONCAT('NetSuite figures older than ', CAST(CAST(stale_days AS INT64) AS STRING), ' days'), NULL),
    IF(partial_releases > 0,
       'On order includes a partly received PO line, counted in full', NULL)
  ], '; '), '') AS data_flag,
  unit,
  product_type,
  part_type,
  part_group_key,
  part_group,
  part_source_key,
  demand_qty,
  -- Appended 2026-10-30: demand before netting (see demand_qty above).
  gross_demand_qty
FROM final
WHERE reorder_point > 0 OR avg_daily_usage > 0
