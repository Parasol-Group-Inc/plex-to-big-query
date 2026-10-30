-- inventory_lot_detail_report — stock by part, lot and container status, with
-- the lot's Best By date and value (added 2026-10-30 for Jennilyn: drill into
-- Lot Hold / Expired / Quarantine, and find lots that reach Best By within
-- X days).
--
-- GRAIN: one row per (part, lot, container status) over ACTIVE containers.
-- A lot's quantity is the SUM over its status rows; filter on status first
-- when you want one kind of stock only.
--
-- SAME STOCK AND COST AS THE TOTAL. Containers are every active one, and
-- in_valuation_total marks the rows inventory_valuation_total_report counts
-- (every status except Receiving — see inventory_valuation_summary_view.sql,
-- CONTAINER SCOPE). SUM(inventory_value) WHERE in_valuation_total equals its
-- total_inventory_value; WHERE is_available equals available_inventory_value.
-- Unit cost is the summary's primary-model cost on the current snapshot, so a
-- part with no cost there has a NULL unit_cost and $0 value, as in Plex.
-- MUST stay listed after inventory_valuation_summary_report in
-- reports/inventory_snapshot.yaml.
--
-- BEST BY: Part_v_Lot_Shelf_Life holds one date per lot per shelf-life type.
-- The type is picked by Part_v_Shelf_Life_Type.Best_By = 1 (key 327 on this
-- tenant; 329 Use By, 333 Sell By and 364 Retest are the others), not by key.
-- Lot_Shelf_Life is DATETIME (see mfg_job_schedule_view.sql). Some lots carry
-- a 2300-xx-xx date, Plex's "does not expire"; best_by_is_placeholder flags
-- them. Containers with no lot have no Best By.
--
-- EXPIRED: Plex sets the container status itself; is_expired_status is
-- simply Container_Status = 'EXPIRED'. A lot past its Best By date whose
-- containers are not yet marked Expired shows days_to_best_by < 0 with
-- is_expired_status FALSE.
--
-- AVAILABLE: is_available repeats part_on_hand_inventory_view.sql's status
-- list (it is per part there, so it cannot be joined at status grain). If
-- that list changes, change this one; SUM(inventory_value) WHERE is_available
-- must keep equalling the total's available_inventory_value.
--
-- Raw tables from other pipelines (not re-extracted here): raw_Part_v_Container
-- (part_on_hand_inventory), raw_Part_v_Lot and raw_Part_v_Lot_Shelf_Life
-- (work_orders), raw_Part_v_Shelf_Life_Type (part_routing), raw_Part_v_Part
-- and raw_Part_v_Part_Product_Type (sales_orders).
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.

WITH

containers AS (
  SELECT
    SAFE_CAST(c.Part_Key AS INT64)                      AS part_key,
    SAFE_CAST(c.Lot_Key AS INT64)                       AS lot_key,
    UPPER(TRIM(CAST(c.Container_Status AS STRING)))     AS container_status,
    SAFE_CAST(c.Quantity AS FLOAT64)                    AS quantity
  FROM `{gcp_project}.{dataset}.raw_Part_v_Container` c
  WHERE SAFE_CAST(c.Active AS INT64) = 1
),

by_lot_status AS (
  SELECT
    part_key,
    lot_key,
    container_status,
    COUNT(*)                                            AS container_count,
    SUM(quantity)                                       AS quantity
  FROM containers
  GROUP BY part_key, lot_key, container_status
),

best_by AS (
  SELECT
    SAFE_CAST(sl.Lot_Key AS INT64)                      AS lot_key,
    MIN(DATE(SAFE_CAST(sl.Lot_Shelf_Life AS TIMESTAMP))) AS best_by_date
  FROM `{gcp_project}.{dataset}.raw_Part_v_Lot_Shelf_Life` sl
  JOIN `{gcp_project}.{dataset}.raw_Part_v_Shelf_Life_Type` t
    ON SAFE_CAST(t.Shelf_Life_Type_Key AS INT64) = SAFE_CAST(sl.Shelf_Life_Type_Key AS INT64)
  WHERE SAFE_CAST(t.Best_By AS INT64) = 1
  GROUP BY lot_key
),

-- One row per part: the summary's primary-model cost on the current snapshot.
unit_cost AS (
  SELECT
    SAFE_CAST(s.part_key AS INT64)                      AS part_key,
    ANY_VALUE(s.unit_cost)                              AS unit_cost
  FROM `{gcp_project}.{dataset}.inventory_valuation_summary_report` s
  WHERE s.is_current_snapshot AND s.is_primary_cost_model
  GROUP BY part_key
)

SELECT
  p.Part_No                                             AS part_no,
  p.Revision                                            AS revision,
  p.Name                                                AS part_name,
  pt.Product_Type                                       AS part_product_type,
  l.Lot_No                                              AS lot_no,
  b.container_status                                    AS container_status,
  b.container_count                                     AS container_count,
  b.quantity                                            AS quantity,
  uc.unit_cost                                          AS unit_cost,
  b.quantity * COALESCE(uc.unit_cost, 0)                AS inventory_value,

  bb.best_by_date                                       AS best_by_date,
  DATE_DIFF(bb.best_by_date, CURRENT_DATE('America/Denver'), DAY)
                                                        AS days_to_best_by,
  COALESCE(EXTRACT(YEAR FROM bb.best_by_date) >= 2200, FALSE)
                                                        AS best_by_is_placeholder,

  b.container_status = 'EXPIRED'                        AS is_expired_status,
  b.container_status IN ('OK', 'HOLD', 'INSPECTION REQUIRED', 'HOLD FOR DESIGN ORDER')
                                                        AS is_available,
  b.container_status != 'RECEIVING'                     AS in_valuation_total,

  b.part_key                                            AS part_key,
  b.lot_key                                             AS lot_key

FROM by_lot_status b

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(p.Part_Key AS INT64) = b.part_key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Product_Type` pt
  ON SAFE_CAST(p.Product_Type_Key AS FLOAT64) = SAFE_CAST(pt.Product_Type_Key AS FLOAT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Lot` l
  ON SAFE_CAST(l.Lot_Key AS INT64) = b.lot_key

LEFT JOIN best_by bb
  ON bb.lot_key = b.lot_key

LEFT JOIN unit_cost uc
  ON uc.part_key = b.part_key
