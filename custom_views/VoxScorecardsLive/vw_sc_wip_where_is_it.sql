-- VoxScorecardsLive.vw_sc_wip_where_is_it (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-11 15:52 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH l AS (SELECT * FROM `voxdatalake.VoxScorecardsLive.vw_sc_wip_status_lines`),
pk AS (SELECT Part_No, ANY_VALUE(Part_Key) AS part_key FROM `voxdatalake.PlexProd.raw_Part_v_Part` GROUP BY 1),
bom AS (
  SELECT SAFE_CAST(b.Part_Key AS INT64) AS parent_key, SAFE_CAST(b.Component_Part_Key AS INT64) AS comp_key,
         c.Part_No AS comp_no, c.Name AS comp_name, SUBSTR(c.Part_No, 1, 1) AS comp_pfx,
         SAFE_CAST(b.Quantity AS FLOAT64) AS per_unit
  FROM `voxdatalake.PlexProd.raw_Part_v_BOM` b
  JOIN `voxdatalake.PlexProd.raw_Part_v_Part` c ON c.Part_Key = SAFE_CAST(b.Component_Part_Key AS INT64)
  WHERE COALESCE(SAFE_CAST(b.Active AS INT64), 1) = 1 AND SUBSTR(c.Part_No, 1, 1) IN ('5', '3', '7')
),
bulk AS (
  SELECT * EXCEPT (rn) FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY parent_key ORDER BY IF(comp_pfx = '5', 0, 1), comp_no) rn
    FROM bom WHERE comp_pfx IN ('5', '3')) WHERE rn = 1
),
caps AS (
  SELECT * EXCEPT (rn) FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY parent_key ORDER BY comp_no) rn FROM bom WHERE comp_pfx = '3') WHERE rn = 1
),
label AS (
  SELECT * EXCEPT (rn) FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY parent_key ORDER BY comp_no) rn FROM bom WHERE comp_pfx = '7') WHERE rn = 1
),
onhand AS (SELECT part_key, SUM(on_hand_qty) AS qty FROM `voxdatalake.PlexProd.part_on_hand_inventory_report` GROUP BY 1),
open_jobs AS (
  SELECT SAFE_CAST(j.Part_Key AS INT64) AS part_key, SUM(SAFE_CAST(j.Quantity AS FLOAT64)) AS qty,
         STRING_AGG(j.Job_No, ', ' ORDER BY j.Job_No LIMIT 5) AS job_nos
  FROM `voxdatalake.PlexProd.raw_Part_v_Job` j
  JOIN `voxdatalake.PlexProd.raw_Part_v_Job_Status` js ON SAFE_CAST(js.Job_Status_Key AS INT64) = SAFE_CAST(j.Job_Status_Key AS INT64)
  WHERE COALESCE(SAFE_CAST(js.Completed_Status AS INT64), 0) = 0 AND COALESCE(SAFE_CAST(js.Cancelled_Status AS INT64), 0) = 0
    AND COALESCE(SAFE_CAST(js.Scrapped_Status AS INT64), 0) = 0 AND COALESCE(SAFE_CAST(js.Template_Status AS INT64), 0) = 0
  GROUP BY 1
),
x AS (
  SELECT l.*,
    b.comp_no AS bulk_part_no, b.comp_name AS bulk_part_name,
    (l.qty_pending - l.ready_qty) * b.per_unit AS bulk_needed,
    IFNULL(bo.qty, 0) AS bulk_on_hand, IFNULL(bj.qty, 0) AS bulk_open_job_qty, bj.job_nos AS bulk_job_nos,
    COUNTIF(b.comp_key IS NOT NULL) OVER (PARTITION BY b.comp_key) AS bulk_lines_needing,
    c.comp_no AS caps_part_no,
    (l.qty_pending - l.ready_qty) * b.per_unit * c.per_unit AS caps_needed,
    IFNULL(co.qty, 0) AS caps_on_hand, IFNULL(cj.qty, 0) AS caps_open_job_qty, cj.job_nos AS caps_job_nos,
    COUNTIF(c.comp_key IS NOT NULL) OVER (PARTITION BY c.comp_key) AS caps_lines_needing,
    lb.comp_no AS label_part_no, IFNULL(lo.qty, 0) AS label_on_hand, IFNULL(lj.qty, 0) AS label_open_job_qty, lj.job_nos AS label_job_nos,
    (l.qty_pending - l.ready_qty) * lb.per_unit AS label_needed
  FROM l
  LEFT JOIN pk ON pk.Part_No = l.part_no
  LEFT JOIN bulk b ON b.parent_key = pk.part_key
  LEFT JOIN onhand bo ON bo.part_key = b.comp_key
  LEFT JOIN open_jobs bj ON bj.part_key = b.comp_key
  LEFT JOIN caps c ON c.parent_key = b.comp_key AND b.comp_pfx = '5'
  LEFT JOIN onhand co ON co.part_key = c.comp_key
  LEFT JOIN open_jobs cj ON cj.part_key = c.comp_key
  LEFT JOIN label lb ON lb.parent_key = pk.part_key
  LEFT JOIN onhand lo ON lo.part_key = lb.comp_key
  LEFT JOIN open_jobs lj ON lj.part_key = lb.comp_key
),
s AS (
  SELECT x.*,
    CASE
      WHEN remaining_sort = 6 THEN '0 New product, part not created yet'
      WHEN remaining_sort = 7 THEN '0 Service / fee / credit'
      WHEN qty_pending > 0 AND ready_qty >= qty_pending THEN '7 Ready to ship'
      WHEN remaining_sort = 2 THEN '6 Finished-goods job open'
      WHEN remaining_sort = 3 THEN '5 Finished-goods job done, not in stock'
      WHEN remaining_sort = 4 THEN '1 Label design'
      WHEN bulk_part_no IS NULL THEN '1 No bulk component on BOM'
      WHEN bulk_on_hand >= bulk_needed THEN IF(bulk_part_no LIKE '5%', '4 Bottled, needs finished-goods job', '4 Capsules made, needs finished-goods job')
      WHEN bulk_open_job_qty > 0 THEN IF(bulk_part_no LIKE '5%', '3 Bottling job open', '3 Encapsulation job open')
      WHEN caps_part_no IS NOT NULL AND caps_on_hand >= caps_needed THEN '2 Capsules made, needs bottling job'
      WHEN caps_part_no IS NOT NULL AND caps_open_job_qty > 0 THEN '2 Encapsulation job open'
      WHEN bulk_on_hand > 0 OR caps_on_hand > 0 THEN '2 Partly made, not enough for this order'
      ELSE '1 Not started'
    END AS stage
  FROM x
)
SELECT
  order_no, document_so, customer_name, sales_rep, next_due_date, is_on_hold, release_status,
  part_no, part_name, qty_pending, ready_qty, wip_value, ready_value, remaining_value,
  remaining_status, job_nos AS fg_job_nos, stage,
  IF(ready_qty > 0 AND ready_qty < qty_pending, 'Partly in stock', NULL) AS partial_note,
  CASE
    WHEN STARTS_WITH(stage, '0') THEN NULL
    WHEN stage = '1 Label design' THEN 'Linked to order'
    WHEN STARTS_WITH(stage, '1') THEN NULL
    WHEN SUBSTR(stage, 1, 1) IN ('5', '6', '7') THEN 'Linked to order'
    WHEN SUBSTR(stage, 1, 1) IN ('3', '4') THEN IF(bulk_lines_needing = 1, 'Dedicated', 'Shared')
    WHEN stage IN ('2 Capsules made, needs bottling job', '2 Encapsulation job open') THEN IF(caps_lines_needing = 1, 'Dedicated', 'Shared')
    ELSE 'Shared' END AS confidence,
  bulk_part_no, bulk_part_name, bulk_needed, bulk_on_hand, bulk_open_job_qty, bulk_job_nos, bulk_lines_needing,
  caps_part_no, caps_needed, caps_on_hand, caps_open_job_qty, caps_job_nos, caps_lines_needing,
  label_part_no, label_needed, label_on_hand, label_open_job_qty, label_job_nos,
  CASE WHEN label_part_no IS NULL THEN NULL
       WHEN remaining_sort = 4 THEN 'Label design in progress'
       WHEN label_on_hand >= label_needed THEN 'Labels on hand (check artwork version)'
       WHEN label_open_job_qty > 0 THEN 'Label printing job open'
       WHEN label_on_hand > 0 THEN 'Some labels on hand'
       ELSE 'No labels yet' END AS label_status
FROM s
