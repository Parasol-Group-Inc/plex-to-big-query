-- ─────────────────────────────────────────────────────────────────────────────
-- label_design_push_latency — how long a Label Design line took to reach Monday
--
-- One row per item the push service tried to create (label_design_push_log),
-- with the Plex times that explain the wait. Added 2026-10-20.
--
-- WHAT THE TIMES MEAN
--   line_added_at       the order line was entered in Plex (Sales_v_PO_Line.Add_Date)
--   release_added_at    its first release was entered (MIN Sales_v_Release.Add_Date)
--   order_added_at      the order header was entered (Sales_v_PO.Add_Date)
--   order_updated_at    the order header's LAST edit (Sales_v_PO.Update_Date).
--                       Plex keeps no status history, so this is the closest we
--                       get to "approved to Pending Fulfillment". It is today's
--                       value: an edit after the push replaces it, which
--                       order_updated_after_push flags (then it means nothing).
--   pushed_at           the item was created on the board (push log, UTC)
--
-- PLEX CLOCK: Plex dates are naive Mountain wall-clock times. Checked
-- 2026-10-20: SELECT GETDATE() in Plex SQL Developer returned 19:39 when it
-- was 19:40 MDT (01:40 UTC). America/Denver handles the DST change.
--
-- ODBC LAG: the prod ODBC source runs about an hour behind Plex. Order 373 was
-- last edited (approved) at 12:16 MT, yet the 13:03 MT full run still read it
-- as Deposit Review; releases stamped 11:58 and 15:51 MT first showed up at
-- 13:03 and 17:04. So hours_update_to_board includes that hour (OPEN_ITEMS L14).
--
-- Raw date columns land as INT64 nanoseconds (see label_design_view.sql,
-- "Dates"). SAFE_CAST on both sides of every join (CLAUDE.md).
-- ─────────────────────────────────────────────────────────────────────────────
WITH push AS (
  SELECT
    run_id,
    pushed_at,
    outcome,
    order_number,
    customer_part_no,
    monday_item_id,
    dedupe_key,
    SAFE_CAST(REGEXP_EXTRACT(dedupe_key, r'\|L(\d+)$') AS INT64) AS po_line_key
  FROM `{gcp_project}.{dataset}.label_design_push_log` AS pl
  -- Not pushes: 'repaired' rows (the retired repair job, 2026-10-22 to 10-27)
  -- refilled an item already counted here; 'alert' rows (2026-10-27) record
  -- an email the push sent; 'filled' rows (2026-10-28) record a label field
  -- written into an item after it was created.
  WHERE pl.outcome NOT IN ('repaired', 'alert', 'filled')
),

release_added AS (
  SELECT
    SAFE_CAST(r.PO_Line_Key AS INT64) AS po_line_key,
    MIN(SAFE_CAST(CAST(r.Add_Date AS STRING) AS INT64)) AS add_ns
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Release` AS r
  GROUP BY 1
),

plex AS (
  SELECT
    push.*,
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(po.PO_Date     AS STRING) AS INT64), 0), 1000))) AS order_date,
    -- naive Plex wall-clock time, read as Mountain time
    TIMESTAMP(DATETIME(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(l.Add_Date     AS STRING) AS INT64), 0), 1000))), 'America/Denver') AS line_added_at,
    TIMESTAMP(DATETIME(TIMESTAMP_MICROS(DIV(NULLIF(ra.add_ns, 0), 1000))), 'America/Denver')                                           AS release_added_at,
    TIMESTAMP(DATETIME(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(po.Add_Date    AS STRING) AS INT64), 0), 1000))), 'America/Denver') AS order_added_at,
    TIMESTAMP(DATETIME(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(po.Update_Date AS STRING) AS INT64), 0), 1000))), 'America/Denver') AS order_updated_at
  FROM push
  LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` AS l
    ON SAFE_CAST(l.PO_Line_Key AS INT64) = push.po_line_key
  LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO` AS po
    ON SAFE_CAST(po.PO_Key AS INT64) = SAFE_CAST(l.PO_Key AS INT64)
  LEFT JOIN release_added AS ra
    ON ra.po_line_key = push.po_line_key
)

SELECT
  order_number,
  customer_part_no,
  po_line_key,
  monday_item_id,
  outcome,
  run_id,
  order_date,
  -- the 38 items of the 2026-10-19 cutover push predate the go-live floor;
  -- filter them out to measure normal operation
  order_date < DATE '2026-10-18'                                   AS before_go_live_floor,
  order_added_at,
  line_added_at,
  release_added_at,
  order_updated_at,
  order_updated_at > pushed_at                                     AS order_updated_after_push,
  pushed_at,
  DATETIME(pushed_at,        'America/Denver')                     AS pushed_at_mt,
  DATETIME(line_added_at,    'America/Denver')                     AS line_added_at_mt,
  DATETIME(order_updated_at, 'America/Denver')                     AS order_updated_at_mt,
  -- total wait: line entered in Plex -> item on the board
  ROUND(TIMESTAMP_DIFF(pushed_at, line_added_at, SECOND) / 3600, 2) AS hours_plex_to_board,
  -- our part of it: last order edit (~ approval) -> item on the board
  IF(order_updated_at > pushed_at, NULL,
     ROUND(TIMESTAMP_DIFF(pushed_at, order_updated_at, SECOND) / 3600, 2)) AS hours_update_to_board,
  -- the sales side: line entered -> last order edit (~ approval)
  IF(order_updated_at > pushed_at, NULL,
     ROUND(TIMESTAMP_DIFF(order_updated_at, line_added_at, SECOND) / 3600, 2)) AS hours_plex_to_update
FROM plex
