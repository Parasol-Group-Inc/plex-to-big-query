-- plex_api_label_design_report — Label Design queue built from the REST API
-- ============================================================================
-- Same report shape as label_design_report (from the ODBC ETL), but sourced
-- from the live Plex REST API tables (plex_api_*_latest views). Only the
-- columns the API can provide are populated; see the column mapping in
-- label-design/STATUS.md for what's missing.
--
-- Created/refreshed by deploy/plex_api_function/push.py on each run.

CREATE OR REPLACE VIEW `{p}.{d}.plex_api_label_design_report` AS
WITH
-- ── Label Design releases ───────────────────────────────────────────────────
ld_releases AS (
  SELECT
    r.record_id          AS release_id,
    r.orderLineId        AS order_line_id,
    r.status             AS line_status,
    r.partNumber         AS release_part_no,
    r.dueDate            AS due_date,
    r.quantity           AS quantity,
    r.note               AS release_note
  FROM `{p}.{d}.plex_api_releases_latest` AS r
  WHERE r.status = 'Label Design'
),

-- ── Order lines for those releases ──────────────────────────────────────────
lines AS (
  SELECT
    l.record_id          AS line_id,
    l.orderId            AS order_id,
    l.partId             AS part_id,
    l.customerPartId     AS customer_part_id,
    l.note               AS line_note
  FROM `{p}.{d}.plex_api_order_lines_latest` AS l
),

-- ── Orders ──────────────────────────────────────────────────────────────────
orders AS (
  SELECT
    o.record_id          AS order_id,
    o.orderNumber        AS order_number,
    o.poNumber           AS customer_po,
    o.status             AS order_status,
    o.orderDate          AS order_date,
    o.customerId         AS customer_id,
    o.insideSalesId      AS inside_sales_id,
    o.note               AS order_note,
    -- outsideSalesIds is a JSON array; extract first element
    JSON_VALUE(o.payload, '$.outsideSalesIds[0]') AS outside_sales_id
  FROM `{p}.{d}.plex_api_orders_latest` AS o
),

-- ── Customers ───────────────────────────────────────────────────────────────
customers AS (
  SELECT
    c.record_id          AS customer_id,
    c.name               AS customer_name,
    c.code               AS customer_code,
    c.email              AS customer_email,
    c.phone              AS customer_phone
  FROM `{p}.{d}.plex_api_customers_latest` AS c
),

-- ── Parts (finished goods) ──────────────────────────────────────────────────
parts AS (
  SELECT
    p.record_id          AS part_id,
    JSON_VALUE(p.payload, '$.number')      AS part_no,
    JSON_VALUE(p.payload, '$.revision')    AS part_revision,
    JSON_VALUE(p.payload, '$.name')        AS part_name,
    JSON_VALUE(p.payload, '$.description') AS part_description,
    JSON_VALUE(p.payload, '$.group')       AS part_group,
    JSON_VALUE(p.payload, '$.productType') AS product_type
  FROM `{p}.{d}.plex_api_parts_latest` AS p
),

-- ── BOM: label parts (73*) and bottle parts (53*) ───────────────────────────
label_parts AS (
  SELECT
    b.parent_id          AS fg_part_id,
    JSON_VALUE(b.payload, '$.componentPartId')     AS label_part_id,
    JSON_VALUE(b.payload, '$.componentPartNumber')  AS label_part_no
  FROM `{p}.{d}.plex_api_boms_latest` AS b
  WHERE JSON_VALUE(b.payload, '$.componentPartNumber') LIKE '73%'
),

bottle_parts AS (
  SELECT
    b.parent_id          AS fg_part_id,
    JSON_VALUE(b.payload, '$.componentPartId')     AS bottle_part_id,
    JSON_VALUE(b.payload, '$.componentPartNumber')  AS bottle_part_no
  FROM `{p}.{d}.plex_api_boms_latest` AS b
  WHERE JSON_VALUE(b.payload, '$.componentPartNumber') LIKE '53%'
),

-- ── Release count per order line ────────────────────────────────────────────
release_counts AS (
  SELECT orderLineId, COUNT(*) AS release_count
  FROM `{p}.{d}.plex_api_releases_latest`
  GROUP BY 1
)

-- ── Final join ──────────────────────────────────────────────────────────────
SELECT
  o.order_number,
  o.customer_po,
  c.customer_name,
  rl.line_status,
  rl.due_date,
  o.order_date,
  o.order_status,
  -- Part info (finished good)
  p.part_no,
  p.part_revision,
  p.part_name,
  p.part_description   AS line_description,
  -- Label part (from BOM)
  lp.label_part_no,
  lp_detail.part_name  AS label_part_name,
  -- Bottle part (from BOM)
  bp.bottle_part_no,
  bp_detail.part_name  AS bottle_part_name,
  -- Bottle material: parse from FG part name (e.g. "White Bottle", "Amber Bottle")
  CASE
    WHEN UPPER(p.part_name) LIKE '%WHITE HDPE%' THEN 'HDPE'
    WHEN UPPER(p.part_name) LIKE '%AMBER BOTTLE%' THEN 'Amber'
    WHEN UPPER(p.part_name) LIKE '%WHITE BOTTLE%' THEN 'White'
    WHEN UPPER(p.part_name) LIKE '%PET BOTTLE%' THEN 'PET'
    WHEN UPPER(p.part_name) LIKE '%GLASS%' THEN 'Glass'
    ELSE NULL
  END AS bottle_material,
  -- Customer
  c.customer_email,
  c.customer_phone,
  -- Releases
  rc.release_count,
  rl.quantity,
  -- Notes
  o.order_note,
  rl.release_note,
  -- Sales reps (IAM user UUIDs — names not resolvable via API)
  o.outside_sales_id   AS bdm_id,
  o.inside_sales_id    AS am_id,
  -- Dedupe key: order number + line id (same pattern as the ODBC push)
  CONCAT(o.order_number, '|L', l.line_id) AS dedupe_key
FROM ld_releases AS rl
  INNER JOIN lines   AS l  ON l.line_id    = rl.order_line_id
  INNER JOIN orders  AS o  ON o.order_id   = l.order_id
  LEFT JOIN customers AS c ON c.customer_id = o.customer_id
  LEFT JOIN parts     AS p ON p.part_id     = l.part_id
  LEFT JOIN label_parts  AS lp ON lp.fg_part_id = l.part_id
  LEFT JOIN parts AS lp_detail ON lp_detail.part_id = lp.label_part_id
  LEFT JOIN bottle_parts AS bp ON bp.fg_part_id = l.part_id
  LEFT JOIN parts AS bp_detail ON bp_detail.part_id = bp.bottle_part_id
  LEFT JOIN release_counts AS rc ON rc.orderLineId = rl.order_line_id
