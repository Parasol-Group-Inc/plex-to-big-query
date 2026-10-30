-- Daily history of component demand, gross vs netted (see docs/BOM_DEMAND_NETTING.md).
-- Run by the `msl_demand_daily` scheduled query (terraform/main.tf), every day 13:00 UTC,
-- after the 4 AM MT full prod run. Jennilyn asked to track both numbers over time
-- (2026-10-30): the views only ever show today.
--
-- GRAIN: one row per (snapshot_date, part_key), stocked keys only (wrapper keys carry no
-- demand of their own), for every part with stock or open demand. A re-run on the same
-- day replaces that day's rows, so it is safe to run by hand.
-- snapshot_date is the America/Denver date. BigQuery-only data: also in
-- terraform/backup_snapshots.sql.

CREATE TABLE IF NOT EXISTS `voxdatalake.PlexProd.msl_demand_daily` (
  snapshot_date               DATE      NOT NULL,
  part_key                    INT64,
  part_no                     STRING,
  revision                    STRING,
  part_name                   STRING,
  part_product_type           STRING,
  unit                        STRING,
  bom_low_level_code          INT64,
  stock_qty                   FLOAT64   OPTIONS (description = "available on-hand, plus stock on wrapper keys converted"),
  order_demand_qty            FLOAT64   OPTIONS (description = "the part's own open sales-order demand"),
  gross_component_demand_qty  FLOAT64   OPTIONS (description = "parents' orders exploded through the whole BOM, ignoring stock in between"),
  netted_component_demand_qty FLOAT64   OPTIONS (description = "what parents pass down after their own stock (component_demand_qty)"),
  covered_by_stock_qty        FLOAT64   OPTIONS (description = "gross - netted: component demand already covered by stock higher up"),
  available_qty               FLOAT64   OPTIONS (description = "stock - order demand - netted component demand"),
  reorder_point               FLOAT64   OPTIONS (description = "from approaching_msl_report; NULL when the part is not in MSL"),
  at_reorder_point            BOOL      OPTIONS (description = "from approaching_msl_report; NULL when the part is not in MSL"),
  captured_at                 TIMESTAMP NOT NULL
)
PARTITION BY snapshot_date
OPTIONS (description = "Daily gross vs netted component demand per part. Filled by the msl_demand_daily scheduled query; see docs/BOM_DEMAND_NETTING.md.");

DELETE FROM `voxdatalake.PlexProd.msl_demand_daily`
WHERE snapshot_date = CURRENT_DATE('America/Denver');

INSERT INTO `voxdatalake.PlexProd.msl_demand_daily`
SELECT
  CURRENT_DATE('America/Denver')                        AS snapshot_date,
  a.part_key,
  a.part_no,
  a.revision,
  a.part_name,
  a.part_product_type,
  a.unit,
  a.bom_low_level_code,
  a.on_hand_qty + a.wrapper_on_hand_qty                 AS stock_qty,
  a.order_demand_qty,
  a.gross_component_demand_qty,
  a.component_demand_qty                                AS netted_component_demand_qty,
  a.gross_component_demand_qty - a.component_demand_qty AS covered_by_stock_qty,
  a.available_vs_total_demand                           AS available_qty,
  m.reorder_point,
  m.at_reorder_point,
  CURRENT_TIMESTAMP()                                   AS captured_at
FROM `voxdatalake.PlexProd.inventory_available_to_sell_report` a
LEFT JOIN `voxdatalake.PlexProd.approaching_msl_report` m
  ON m.part_no = a.part_no
WHERE NOT a.is_unit_wrapper;
