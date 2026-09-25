-- inventory_valuation_summary_report — Vox | Inventory Valuation Summary (NetSuite parity)
--
-- Wired into reports/inventory_snapshot.yaml as the second entry in that
-- report's bq_view list (main.py's bq_view now accepts a list — added
-- specifically to support this, see main.py's bq_view_configs/
-- validate_bq_view). Reads the SAME raw tables that report extracts
-- (Part_v_Snapshot, Part_v_Snapshot_Cost_Sub_Type_Breakdown,
-- Part_v_Cost_Sub_Type_Breakdown_History, Part_v_Part) plus the on-hand
-- quantity from part_on_hand_inventory_report (see ON-HAND below). See
-- docs/NETSUITE_REPORT_BUILD_PLAN.md (#73) for the original confirmation log.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime (or by
-- whatever runs this manually) using the GCP_PROJECT and BQ_DATASET values.
--
-- GRAIN: one row per (snapshot, cost model, part).
--
-- ⚠ REWRITTEN 2026-09-24 (found by the scorecard sandbox, finding 4 in
-- docs/SCORECARD_SANDBOX_FINDINGS.md). The old view was
-- `SUM(h.Cost) GROUP BY snapshot, snapshot.Cost_Model_Key, part`, which was
-- wrong three ways at once:
--   1. Plex's Cost is PER UNIT (real rows: $0.0014/capsule, $0.039/label,
--      $0.22/finished bottle). Summing it with no quantity gave "total
--      inventory value" ≈ $77 for the whole building.
--   2. It added every OPERATION's cost for a part. Plex costs each part
--      operation CUMULATIVELY — the real blend 23127-01VOXNU-1 costs $1.25 at
--      op 65259260 (which carries its whole BOM) and $1.354 at op 65259261
--      (which has NO BOM rows — it only adds conversion). Op 2's cost already
--      contains op 1's. Summing the blend's 4 operation rows gave $4.85/unit
--      for a $1.25-1.35 part.
--   3. It grouped by Part_v_Snapshot.Cost_Model_Key, which is NULL on the
--      real snapshot. The cost model lives on the history rows (1892).
--   It also summed every history row the snapshot pointed at, and did not
--   pick the cost in force per key — harmless while Plex's pointer rows are
--   one-per-key, wrong the moment they are not.
--
-- THE RULE NOW
--   Per-unit cost of a part at a snapshot:
--     a. The cost rows in force: Plex's own pointer rows
--        (Part_v_Snapshot_Cost_Sub_Type_Breakdown) when that snapshot has any;
--        otherwise every history row changed on or before the snapshot date.
--        The pointer table is EMPTY in real Plex (both PlexTest and PlexProd,
--        checked 2026-09-24), so without the fallback this view is empty on
--        real data forever. Either way only the LATEST row per (cost model,
--        part, operation, cost sub-type) counts.
--     b. Operation cost = SUM over cost sub-types (13688 + 13690 on this
--        tenant). They are components of one cost, not alternatives: each
--        rolls up independently through the BOM (finished bottle 13688
--        $0.0876 = bright bottle $0.0566 + label $0.0156 + conversion) and
--        the sum reproduces the real per-unit costs above.
--     c. The part's cost = the HIGHEST operation cost among the operations
--        costed on the part's most recent cost-change date. Highest, because
--        operation costs are cumulative, so the final operation (the finished
--        part) carries the most. Most-recent-date, because a routing rebuild
--        creates NEW Part_Operation_Keys and leaves the retired operations'
--        cost rows in history: the real blend was re-routed 2026-09-04 onto
--        ops 66227453/66227454 at $1.25, while retired op 65259261 still
--        reads $1.354. Without that filter a later snapshot would value the
--        blend on a routing that no longer exists.
--        This is a PROXY for "the final active operation": the routing
--        itself (Part_v_Part_Operation — operation sequence and Active) is
--        not extracted anywhere in this repo. Extracting it would replace
--        rule c with an exact one.
--
--   ON-HAND (quantity): Part_v_Snapshot carries NO quantity — its columns are
--   keys, dates, Cost_Model_Key and delta bookkeeping only. It is a COST
--   snapshot, not a stock snapshot. The only on-hand this repo has is TODAY's,
--   from Part_v_Container via part_on_hand_inventory_report (Vox's status
--   rule — OK / Hold / Inspection Required / Hold for Design Order — lives
--   there, deliberately not copied a fourth time). So:
--     inventory_value = on_hand_qty × unit_cost  on the CURRENT (latest)
--                       snapshot only;
--     NULL on every earlier snapshot, because the quantity on hand at that
--     month-end was never captured. Valuing today's stock at January's cost
--     would draw a trend that is really just the cost roll. A month-end
--     trend needs historical on-hand, which is not extracted — see
--     docs/reports/inventory_valuation_total_report.md.
--   Containers are valued at the part's final-operation cost, not at the
--   operation each container sits at (WIP between operations would read
--   slightly high — for the blend, $1.25 vs $1.354).
--
-- Downstream: inventory_valuation_total_report (same config) sums
-- inventory_value. total_cost keeps its name but is now the part's per-unit
-- standard cost (what the column was always described as), not a sum across
-- operations.

WITH

snap AS (
  SELECT
    SAFE_CAST(s.Snapshot_Key AS INT64)                  AS snapshot_key,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(s.Snapshot_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(s.Snapshot_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(s.Snapshot_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    )                                                   AS snapshot_date,
    -- NULL on the real snapshot; used only as a filter when Plex does set it.
    SAFE_CAST(s.Cost_Model_Key AS INT64)                AS snapshot_cost_model_key
  FROM `{gcp_project}.{dataset}.raw_Part_v_Snapshot` s
),

-- NOTE: source column is "Change_key" (lowercase k) on this view — confirmed live.
hist AS (
  SELECT
    SAFE_CAST(h.Change_key AS INT64)                    AS change_key,
    SAFE_CAST(h.Cost_Model_Key AS INT64)                AS cost_model_key,
    SAFE_CAST(h.Part_Key AS INT64)                      AS part_key,
    SAFE_CAST(h.Part_Operation_Key AS INT64)            AS part_operation_key,
    SAFE_CAST(h.Cost_Sub_Type_Key AS INT64)             AS cost_sub_type_key,
    SAFE_CAST(h.Cost AS FLOAT64)                        AS cost,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(h.Change_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(h.Change_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(h.Change_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    )                                                   AS change_date,
    -- Timestamp only to order two changes on the same day.
    COALESCE(
      TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(h.Change_Date AS STRING) AS INT64), 0), 1000)),
      SAFE_CAST(CAST(h.Change_Date AS STRING) AS TIMESTAMP)
    )                                                   AS change_ts
  FROM `{gcp_project}.{dataset}.raw_Part_v_Cost_Sub_Type_Breakdown_History` h
),

ptr AS (
  SELECT
    SAFE_CAST(p.Snapshot_Key AS INT64)                  AS snapshot_key,
    SAFE_CAST(p.Change_Key AS INT64)                    AS change_key
  FROM `{gcp_project}.{dataset}.raw_Part_v_Snapshot_Cost_Sub_Type_Breakdown` p
),

-- (a) the cost rows each snapshot sees
candidate AS (
  -- Plex's own membership, for snapshots that have pointer rows
  SELECT s.snapshot_key, s.snapshot_date, 'snapshot pointer' AS cost_source, h.*
  FROM snap s
  JOIN ptr
    ON SAFE_CAST(ptr.snapshot_key AS INT64) = SAFE_CAST(s.snapshot_key AS INT64)
  JOIN hist h
    ON SAFE_CAST(h.change_key AS INT64) = SAFE_CAST(ptr.change_key AS INT64)
  WHERE s.snapshot_cost_model_key IS NULL OR h.cost_model_key = s.snapshot_cost_model_key

  UNION ALL

  -- as-of fallback, for snapshots with none (every real snapshot today)
  SELECT s.snapshot_key, s.snapshot_date, 'cost history as of snapshot date' AS cost_source, h.*
  FROM snap s
  JOIN hist h
    ON h.change_date <= s.snapshot_date
  WHERE s.snapshot_key NOT IN (SELECT snapshot_key FROM ptr WHERE snapshot_key IS NOT NULL)
    AND (s.snapshot_cost_model_key IS NULL OR h.cost_model_key = s.snapshot_cost_model_key)
),

in_force AS (
  SELECT *
  FROM candidate
  WHERE TRUE
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY snapshot_key, cost_model_key, part_key, part_operation_key, cost_sub_type_key
    ORDER BY change_ts DESC, change_key DESC) = 1
),

-- (b) one cost per operation = sum of its cost sub-types
op_cost AS (
  SELECT
    snapshot_key, snapshot_date, cost_source, cost_model_key, part_key, part_operation_key,
    SUM(cost)                                           AS op_unit_cost,
    COUNT(*)                                            AS cost_sub_type_count,
    MAX(change_date)                                    AS op_change_date
  FROM in_force
  GROUP BY snapshot_key, snapshot_date, cost_source, cost_model_key, part_key, part_operation_key
),

-- (c) the part's cost = highest operation cost on its latest cost-change date
part_cost AS (
  SELECT
    *,
    COUNT(*) OVER w                                     AS operation_count
  FROM op_cost
  WHERE TRUE
  QUALIFY op_change_date = MAX(op_change_date) OVER w
      AND ROW_NUMBER() OVER (
            PARTITION BY snapshot_key, cost_model_key, part_key
            ORDER BY op_unit_cost DESC, part_operation_key DESC) = 1
  WINDOW w AS (PARTITION BY snapshot_key, cost_model_key, part_key)
),

latest_snapshot AS (
  SELECT MAX(snapshot_key) AS snapshot_key
  FROM snap
  WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM snap)
)

SELECT
  pc.snapshot_key                                       AS snapshot_key,
  pc.snapshot_date                                      AS snapshot_date,
  pc.cost_model_key                                     AS cost_model_key,

  p.Part_No                                             AS part_number,
  p.Name                                                AS part_name,

  -- Per-unit standard cost of the finished part (sum of cost sub-types at the
  -- costed operation). Name kept for downstream compatibility.
  pc.op_unit_cost                                       AS total_cost,
  pc.cost_sub_type_count                                AS cost_sub_type_count,

  -- Added 2026-09-24
  pc.part_key                                           AS part_key,
  pc.op_unit_cost                                       AS unit_cost,
  pc.part_operation_key                                 AS costed_operation_key,
  pc.operation_count                                    AS operation_count,
  pc.op_change_date                                     AS cost_change_date,
  pc.cost_source                                        AS cost_source,
  (pc.snapshot_key = ls.snapshot_key)                   AS is_current_snapshot,
  -- Quantity is today's on-hand, so it is only attached to the current snapshot.
  IF(pc.snapshot_key = ls.snapshot_key, COALESCE(oh.on_hand_qty, 0), NULL)
                                                        AS on_hand_qty,
  IF(pc.snapshot_key = ls.snapshot_key, COALESCE(oh.on_hand_qty, 0) * pc.op_unit_cost, NULL)
                                                        AS inventory_value

FROM part_cost pc

CROSS JOIN latest_snapshot ls

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(pc.part_key AS INT64) = SAFE_CAST(p.Part_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.part_on_hand_inventory_report` oh
  ON SAFE_CAST(oh.part_key AS INT64) = SAFE_CAST(pc.part_key AS INT64)
