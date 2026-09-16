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

-- ── Part Attributes ──────────────────────────────────────────────────────────
-- Added 2026-09-16, per Jennilyn: a part-level "spec sheet" of dropdown
-- answers, meant to be read from Plex instead of a person typing them into
-- Monday by hand. Confirmed with her (2026-09-14 meeting, and again
-- 2026-09-16): only ONE value per attribute per part — a need for more than
-- one flag at once (e.g. several regulatory concerns together) is handled by
-- Plex's own dropdown having pre-defined COMBINED entries as a single value
-- ("Prop 65 + Organic"), not by multiple rows here. Every value below is
-- passed through exactly as-is — deliberately NOT parsed/split on " + ",
-- since a new combination she adds tomorrow is a new string we've never
-- seen, not a new format to parse.
--
-- `Part_Key` (not `Customer_Part_Key`/`Customer_Part_No`) is the join key —
-- Plex's own internal part identifier, present directly on `Sales_v_PO_Line`,
-- independent of which customer-facing part-number format is in play (the
-- "seven part number vs. nine" distinction Jennilyn herself was unsure about
-- in the meeting doesn't apply here — this is Plex's stable internal key
-- either way).
--
-- REAL ATTRIBUTE NAMES, confirmed 2026-09-16 by querying Jennilyn's own test
-- upload (`raw_Part_v_Attribute`) rather than guessed: Size, Allergen,
-- Hazardous, Certifications, Printing Material. The original build here
-- guessed 'Bottle Material' and 'Regulatory' — NEITHER exists — so all five
-- real ones are exposed below instead of re-guessing which two matter.
-- Which of these (if any) maps to which *Monday* column (e.g. does
-- "Printing Material" feed the existing Bottle Material dropdown? does
-- Prop 65 information live under "Hazardous" or "Certifications"?) is a
-- separate, later decision — not yet answered, and not needed to expose the
-- data itself.
--
-- Most of her 28 test assignments still carry a blank Value (structure
-- created, values mostly not yet filled in) — the one populated example as
-- of this writing is Allergen = "Yes" on Part_Key 11003458.
part_attribute_types AS (
  SELECT
    SAFE_CAST(a.Attribute_Key AS INT64) AS Attribute_Key,
    a.Attribute_Name                     AS Attribute_Name
  FROM `{gcp_project}.{dataset}.raw_Part_v_Attribute` AS a
),

-- One row per (Part_Key, Attribute_Key) is expected — confirmed with
-- Jennilyn, not just assumed (Plex only allows one value per attribute per
-- part). If that ever stops holding, MAX() below silently picks one value
-- rather than erroring — worth a one-off check once real data lands:
--   SELECT Part_Key, Attribute_Key, COUNT(*)
--   FROM raw_Part_v_Part_Attribute GROUP BY 1, 2 HAVING COUNT(*) > 1
part_attributes_pivoted AS (
  SELECT
    SAFE_CAST(pa.Part_Key AS INT64) AS Part_Key,
    MAX(CASE WHEN pt.Attribute_Name = 'Size'               THEN pa.Value END) AS part_size,
    MAX(CASE WHEN pt.Attribute_Name = 'Allergen'           THEN pa.Value END) AS part_allergen,
    MAX(CASE WHEN pt.Attribute_Name = 'Hazardous'          THEN pa.Value END) AS part_hazardous,
    MAX(CASE WHEN pt.Attribute_Name = 'Certifications'     THEN pa.Value END) AS part_certifications,
    MAX(CASE WHEN pt.Attribute_Name = 'Printing Material'  THEN pa.Value END) AS part_printing_material
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Attribute` AS pa
  JOIN part_attribute_types AS pt
    ON pt.Attribute_Key = SAFE_CAST(pa.Attribute_Key AS INT64)
  GROUP BY SAFE_CAST(pa.Part_Key AS INT64)
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
),

-- ── One row per PO Line + Release ───────────────────────────────────────────
-- A single PO_Line can legitimately have MORE THAN ONE Sales_v_Release record
-- — a split shipment, each release carrying its own Due_Date. That is what a
-- 2026-09-14 test pull turned out to be: order 11 / part 93081-00CHAR2-1 came
-- back twice, identical in every column except Due_Date (9/24 vs 9/25).
--
-- Traced by elimination, not assumed: every other join here is either a
-- single-row lookup by key (cp, cust, rp/rq/up/us) or already pre-aggregated
-- to one row per line (job_notes). Sales_v_Release is the only table that can
-- fan a line out into more than one row — and it is SUPPOSED to, because it is
-- one row per scheduled release, not one row per line.
--
-- The design queue doesn't track shipment-level scheduling, only whether a
-- part needs artwork, so this is collapsed below to one row per
-- order + customer part rather than left as two near-identical rows for a
-- person to puzzle over, or arbitrarily thinned by whichever release the
-- Apps Script's own in-batch dedupe happens to keep first.
release_lines AS (
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
    )                                             AS due_date_resolved,
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

    -- Added 2026-09-16 — see the "Part Attributes" CTEs above. A property of
    -- the PART, not the release, so it is identical across every row this
    -- collapses together; no aggregation needed beyond the plain passthrough.
    pap.part_size                                  AS part_size,
    pap.part_allergen                              AS part_allergen,
    pap.part_hazardous                             AS part_hazardous,
    pap.part_certifications                        AS part_certifications,
    pap.part_printing_material                     AS part_printing_material,

    -- Tie-breaker only — never surfaced. Keeps the QUALIFY below deterministic
    -- on the rare case where two releases for the same part share a Due_Date.
    rel.PO_Line_Key                               AS _tiebreak_line_key

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

  LEFT JOIN part_attributes_pivoted AS pap
    ON pap.Part_Key = SAFE_CAST(pol.Part_Key AS INT64)

  WHERE rs.Release_Status = 'Label Design'
    AND ps.PO_Status = 'Pending Fulfillment'
    -- Addition 3: a rolling window. 14 days per "keep this like within the last
    -- two weeks or something"; widen here rather than in the Apps Script, since
    -- the sheet's own dedupe stops a widened window re-adding old rows.
    AND po.order_date_resolved >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
)

-- ── Collapse to one row per order + customer part ───────────────────────────
-- This is the unit `dedupe_key` (and the Apps Script's own dedupe) has always
-- treated as "one thing to review" — the view now agrees with that instead of
-- leaving the collapse to chance downstream.
--
--   due_date       the EARLIEST due date across a part's releases: the
--                   soonest real deadline the label has to be ready for, not
--                   whichever release happened to sort first.
--   release_count   > 1 flags a part with more than one scheduled release, so
--                   the team can go check Plex if the shipment-level detail
--                   ever matters for a specific row. Costs nothing to carry.
SELECT
  order_number,
  customer_po,
  customer_name,
  customer_part_no,
  line_status,
  MIN(due_date_resolved) OVER (PARTITION BY order_number, customer_part_no) AS due_date,
  order_date,
  job_note,
  sales_rep_primary,
  sales_rep_secondary,
  customer_email,
  customer_phone,
  customer_part_description,
  order_status,
  part_size,
  part_allergen,
  part_hazardous,
  part_certifications,
  part_printing_material,
  COUNT(*) OVER (PARTITION BY order_number, customer_part_no)               AS release_count,
  CONCAT(CAST(order_number AS STRING), '|', IFNULL(customer_part_no, ''))   AS dedupe_key

FROM release_lines

-- One row survives per order + part: the one with the earliest due date.
-- _tiebreak_line_key only matters when two releases share that exact date.
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY order_number, customer_part_no
  ORDER BY due_date_resolved ASC, _tiebreak_line_key
) = 1

ORDER BY order_date DESC, order_number, customer_part_no
