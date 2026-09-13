-- label_design_report — the Label Design queue, for the Monday holding board
-- ============================================================================
-- ORIGIN: Jennilyn's Plex stored procedure "Label Design Report"
-- (`sproc338756_18319605_1407579`), rewritten here against the extracted raw
-- tables. This replaces a daily manual loop: the sales team downloads a
-- NetSuite report, pastes it into a Google Sheet, checks it for duplicates by
-- hand, and uploads the new rows to Monday.
--
-- The Job Note was the hard part of the original query to find, and the join
-- is kept identical to hers (`Note_Type = 'Job_Note'`) rather than
-- reinterpreted.
--
-- ── THE THREE ADDITIONS SHE ASKED FOR (2026-09-11) ──────────────────────────
--  1. The outside sales rep / BDM name, for reference — so a designer with a
--     question knows who to ask. Deliberately NOT matched against Monday's own
--     rep names ("just pull it from here"); the Monday board maps it to its
--     status column on its side.
--  2. Order status must be Pending Fulfillment. The stored procedure filtered
--     only on the RELEASE status being Label Design, which also returned lines
--     whose order had not been approved yet.
--  3. A rolling date window on the order date, so the queue is current work
--     rather than everything ever in Label Design.
--
-- Deduplication against what is already on the sheet happens in the Apps
-- Script, not here, on ORDER NUMBER + CUSTOMER PART NUMBER — her rule, chosen
-- because dates can change and an order can be cancelled and reopened, while
-- the same customer part on a *different* order legitimately repeats.
--
-- ── ONE DELIBERATE DIFFERENCE FROM THE STORED PROCEDURE ─────────────────────
-- Hers joins `Common_v_Customer` on `Customer_No`. That is kept, but note the
-- rep columns come from `Sales_v_Order_Salesperson`, which is per ORDER, not
-- per line — so every line of an order carries the same rep, which is what
-- "so they know which rep to ask" wants.
--
-- BDM vs primary rep is NOT guessed at: both are exposed. `Sort_Order = 1` is
-- the primary and `2` the secondary, and which of those Vox calls the BDM has
-- never been stated. The consumer picks; nothing here silently decides.
--
-- Every join uses SAFE_CAST on both sides — the repo rule, earned by an empty
-- raw table being autodetected as all-STRING and breaking view creation.

WITH rep_primary AS (
  SELECT
    SAFE_CAST(sp.PO_Key AS INT64)         AS PO_Key,
    SAFE_CAST(sp.Plexus_User_No AS INT64) AS Plexus_User_No
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Order_Salesperson` AS sp
  WHERE SAFE_CAST(sp.Sort_Order AS INT64) = 1
),

rep_secondary AS (
  SELECT
    SAFE_CAST(sp.PO_Key AS INT64)         AS PO_Key,
    SAFE_CAST(sp.Plexus_User_No AS INT64) AS Plexus_User_No
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Order_Salesperson` AS sp
  WHERE SAFE_CAST(sp.Sort_Order AS INT64) = 2
),

-- `Plexus_Control_v_Plexus_User` has NO `Name` column — it holds `First_Name`,
-- `Last_Name` and `Middle_Name`. This read `u.Name` from the 2026-09-11 build
-- and failed view creation outright ("Name not found inside u") on the very
-- first run the view was ever asked to build, 2026-09-12. It had been invisible
-- until then for the reason this repo keeps warning about: no job existed, so
-- the view had never been created, and nothing else in the pipeline touches it.
--
-- CONCAT(First_Name, ' ', Last_Name) is the convention every other rep-name
-- view here already uses (sales_orders_open, sales_orders_aging,
-- sales_customers_by_rep, pipeline_plex_value, sales_mtd_by_status_change), and
-- it happens to produce exactly the "Tyler Hall" / "Kami Butcher" shape the
-- Label Design sheet's own Sales Rep column has always carried — so the new
-- rows match the 5,000 already on the archive rather than introducing a second
-- spelling of the same person.
--
-- Deliberately NOT null-guarded, matching those five: CONCAT returns NULL if
-- either part is NULL, so a half-populated user yields no name rather than a
-- trailing-space fragment like "Tyler ".
users AS (
  SELECT
    SAFE_CAST(u.Plexus_User_No AS INT64)   AS Plexus_User_No,
    CONCAT(u.First_Name, ' ', u.Last_Name) AS user_name
  FROM `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` AS u
),

-- One note per line. The source can hold more than one row per line, and a
-- duplicated line would land in Monday twice, so the newest is taken rather
-- than letting the join fan out.
job_notes AS (
  SELECT
    PO_Line_Key,
    ANY_VALUE(Note HAVING MAX Note_Key) AS Job_Note
  FROM (
    SELECT
      -- The key column is PO_Line_Note_Key, not Note_Key. Same class of error
      -- as the users CTE above, found by the same 2026-09-12 dry run.
      SAFE_CAST(n.PO_Line_Key AS INT64)      AS PO_Line_Key,
      SAFE_CAST(n.PO_Line_Note_Key AS INT64) AS Note_Key,
      n.Note                                 AS Note
    FROM `{gcp_project}.{dataset}.raw_Sales_v_PO_Line_Note` AS n
    WHERE n.Note_Type = 'Job_Note'
  )
  GROUP BY PO_Line_Key
),

-- ── Dates ──────────────────────────────────────────────────────────────────
-- `PO_Date` and `Due_Date` land in BigQuery as **INT64 nanoseconds** since the
-- epoch (1750118400000000000 = 2025-06-17), not as a TIMESTAMP: pandas holds
-- them as datetime64[ns] and the raw int64 is what gets written. The original
-- `DATE(SAFE_CAST(x AS TIMESTAMP))` was therefore not merely wrong at runtime
-- but a compile error — "Invalid cast from INT64 to TIMESTAMP" — which is the
-- fourth thing that blocked this view's first ever creation, 2026-09-12.
--
-- The COALESCE below is this repo's existing idiom for exactly this, copied
-- rather than reinvented (see sales_orders_aging_view.sql,
-- purchasing_open_orders_view.sql, pipeline_plex_value_view.sql). It reads the
-- value whichever of the three ways the column happens to have landed:
--
--   1. INT64 nanoseconds  -> DIV by 1000 gives microseconds for TIMESTAMP_MICROS
--   2. a DATE/date string -> cast straight across
--   3. a TIMESTAMP/string -> cast and take the date part
--
-- That matters because the landed TYPE is not stable: an extraction that
-- fetches 0 rows leaves the column typed from a previous run, so the same
-- column can be INT64 in test and STRING in prod. `1970-01-01` is treated as
-- absent — it is what an epoch-zero/empty date decodes to, not a real order.
dates AS (
  SELECT
    po.*,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(po.PO_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(po.PO_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(po.PO_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    ) AS order_date_resolved
  FROM `{gcp_project}.{dataset}.raw_Sales_v_PO` AS po
)

SELECT
  po.Order_No                                   AS order_number,
  po.PO_No                                      AS customer_po,
  cust.Name                                     AS customer_name,
  cp.Customer_Part_No                           AS customer_part_no,
  rs.Release_Status                             AS line_status,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(rel.Due_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(rel.Due_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(rel.Due_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                             AS due_date,
  po.order_date_resolved                        AS order_date,
  jn.Job_Note                                   AS job_note,

  -- Addition 1: who to ask. Both, because "BDM" has never been pinned to one.
  up.user_name                                  AS sales_rep_primary,
  us.user_name                                  AS sales_rep_secondary,

  -- Added 2026-09-12, to fill columns the Monday-tab layout already has and
  -- the sheet was otherwise leaving blank (Email, Phone Number, Description).
  -- No new extractions: `Common_v_Customer` and `Part_v_Customer_Part` are
  -- already joined above for the name and the part number.
  --
  -- NOTE these are the CUSTOMER-level contact details, not a per-order
  -- contact. Plex holds a per-line `Contact_No` as well; which one the label
  -- team actually wants to reach has never been stated, so the account-level
  -- one ships (it is always populated) and the choice stays visible here
  -- rather than being silently made in the Apps Script.
  cust.Email                                    AS customer_email,
  cust.Phone                                    AS customer_phone,
  cp.Customer_Part_Description                  AS customer_part_description,

  -- Carried so the Apps Script can dedupe and the sheet can show provenance
  -- without re-deriving anything.
  -- The column is PO_Status, not Status (third of the same class of error the
  -- 2026-09-12 dry run found). The OUTPUT name stays `order_status`, which is
  -- what the Apps Script reads.
  ps.PO_Status                                  AS order_status,
  CONCAT(CAST(po.Order_No AS STRING), '|',
         IFNULL(cp.Customer_Part_No, ''))       AS dedupe_key

FROM dates AS po

JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` AS pol
  ON SAFE_CAST(pol.PO_Key AS INT64) = SAFE_CAST(po.PO_Key AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` AS rel
  ON SAFE_CAST(rel.PO_Line_Key AS INT64) = SAFE_CAST(pol.PO_Line_Key AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release_Status` AS rs
  ON SAFE_CAST(rs.Release_Status_Key AS INT64) = SAFE_CAST(rel.Release_Status_Key AS INT64)

-- Addition 2: the ORDER must be approved, not just the release in Label
-- Design. Matched on the status NAME rather than the key on purpose — Vox cut
-- the status list from 10 to 7 in September and three keys vanished, which is
-- exactly how another report silently returned 0 rows for weeks.
JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Status` AS ps
  ON SAFE_CAST(ps.PO_Status_Key AS INT64) = SAFE_CAST(po.PO_Status_Key AS INT64)

LEFT JOIN job_notes AS jn
  ON jn.PO_Line_Key = SAFE_CAST(pol.PO_Line_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Customer_Part` AS cp
  ON SAFE_CAST(cp.Customer_Part_Key AS INT64) = SAFE_CAST(pol.Customer_Part_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` AS cust
  ON SAFE_CAST(cust.Customer_No AS INT64) = SAFE_CAST(po.Customer_No AS INT64)

LEFT JOIN rep_primary   AS rp ON rp.PO_Key = SAFE_CAST(po.PO_Key AS INT64)
LEFT JOIN rep_secondary AS rq ON rq.PO_Key = SAFE_CAST(po.PO_Key AS INT64)
LEFT JOIN users         AS up ON up.Plexus_User_No = rp.Plexus_User_No
LEFT JOIN users         AS us ON us.Plexus_User_No = rq.Plexus_User_No

WHERE rs.Release_Status = 'Label Design'
  AND ps.PO_Status = 'Pending Fulfillment'
  -- Addition 3: a rolling window. 14 days per "keep this like within the last
  -- two weeks or something"; widen here rather than in the Apps Script, since
  -- the sheet's own dedupe stops a widened window re-adding old rows.
  AND po.order_date_resolved >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)

-- Ordered by the RESOLVED date, not the raw column. Sorting on the raw int64
-- would happen to work while it stays nanoseconds and silently change meaning
-- the day the column lands as a string instead.
ORDER BY po.order_date_resolved DESC, po.Order_No, cp.Customer_Part_No
