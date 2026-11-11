-- VoxScorecardsLive.vw_sc_rev_ready_to_ship (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-10-30 19:28 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH rel AS (
  SELECT po.PO_No, po.Order_No, SAFE_CAST(pl.Part_Key AS INT64) AS part_key, pl.PO_Line_Key,
    SAFE_CAST(r.Quantity AS FLOAT64) - COALESCE(SAFE_CAST(r.Quantity_Shipped AS FLOAT64), 0) AS rem_qty,
    COALESCE(SAFE_CAST(CAST(r.Due_Date AS STRING) AS DATE),
             DATE(TIMESTAMP_MICROS(DIV(SAFE_CAST(CAST(r.Due_Date AS STRING) AS INT64), 1000)))) AS due_date,
    COALESCE(SAFE_CAST(rs.Hold AS INT64),0) + COALESCE(SAFE_CAST(ps.Hold AS INT64),0)
      + COALESCE(SAFE_CAST(ps.Shipment_Hold AS INT64),0) > 0 AS on_hold
  FROM `voxdatalake.PlexProd.raw_Sales_v_Release` r
  JOIN `voxdatalake.PlexProd.raw_Sales_v_PO_Line` pl ON r.PO_Line_Key = pl.PO_Line_Key
  JOIN `voxdatalake.PlexProd.raw_Sales_v_PO` po ON pl.PO_Key = po.PO_Key
  LEFT JOIN `voxdatalake.PlexProd.raw_Sales_v_Release_Status` rs
    ON SAFE_CAST(r.Release_Status_Key AS INT64) = SAFE_CAST(rs.Release_Status_Key AS INT64)
  LEFT JOIN `voxdatalake.PlexProd.raw_Sales_v_PO_Status` ps
    ON SAFE_CAST(po.PO_Status_Key AS INT64) = SAFE_CAST(ps.PO_Status_Key AS INT64)
  WHERE COALESCE(SAFE_CAST(rs.Shipped_Status AS INT64),0) = 0
    AND COALESCE(SAFE_CAST(rs.Cancelled_Status AS INT64),0) = 0
    AND COALESCE(SAFE_CAST(rs.Closed_Status AS INT64),0) = 0
    AND COALESCE(SAFE_CAST(ps.Cancelled_Status AS INT64),0) = 0
    AND COALESCE(SAFE_CAST(ps.Completed_Status AS INT64),0) = 0
),
price AS (
  SELECT PO_Line_Key,
    ARRAY_AGG(SAFE_CAST(Price AS FLOAT64) ORDER BY SAFE_CAST(Breakpoint_Quantity AS FLOAT64) LIMIT 1)[OFFSET(0)] AS price_ea
  FROM `voxdatalake.PlexProd.raw_Sales_v_Price`
  WHERE COALESCE(SAFE_CAST(Active AS INT64),1) = 1
  GROUP BY 1
),
oh AS (
  SELECT part_key, ANY_VALUE(part_no) AS part_no, ANY_VALUE(part_name) AS part_name, SUM(on_hand_qty) AS on_hand_qty
  FROM `voxdatalake.PlexProd.part_on_hand_inventory_report` GROUP BY 1
),
alloc AS (
  SELECT rel.*, oh.part_no, oh.part_name, COALESCE(oh.on_hand_qty,0) AS on_hand_qty, p.price_ea,
    COALESCE(SUM(rem_qty) OVER (PARTITION BY rel.part_key ORDER BY due_date, PO_Line_Key
                                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS qty_ahead
  FROM rel LEFT JOIN oh USING (part_key) LEFT JOIN price p USING (PO_Line_Key)
  WHERE rem_qty > 0
)
SELECT Order_No, PO_No, part_no, part_name, due_date, on_hold, price_ea,
  rem_qty AS open_qty, on_hand_qty,
  LEAST(rem_qty, GREATEST(on_hand_qty - qty_ahead, 0)) AS ready_qty,
  LEAST(rem_qty, GREATEST(on_hand_qty - qty_ahead, 0)) * price_ea AS ready_value,
  rem_qty * price_ea AS open_value
FROM alloc
