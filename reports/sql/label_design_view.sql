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
-- The BDM (Outside Salesperson) lands in `Sales_v_Order_Salesperson`, one or
-- more rows per ORDER — NOT in `Sales_v_PO.Outside_Sales`, which replicates as
-- 0 even when the Plex UI shows a BDM (order 16 / PO_Key 5021015 has BDM Janet
-- Pacheco on screen, Outside_Sales = 0 in BigQuery, and her user_no lands here
-- instead). This is the same "the field the picker writes isn't the field that
-- replicates" trap `Sales_v_Priority` already sprang.
--
-- `Sort_Order` is 0 on EVERY row across PlexTest, so it cannot rank anything —
-- an earlier build filtered `= 1` / `= 2` and matched nothing, which is why the
-- BDM read NULL. Some orders carry more than one outside rep (orders 4, 5, 12
-- each have two); the lowest Plexus_User_No is taken so one deterministic BDM
-- lands per order. The Order_Salesperson rep is never the order's Inside_Sales
-- AM — confirmed across every populated order — so it is unambiguously the BDM.
--
-- Every join uses SAFE_CAST on both sides — the repo rule, earned by an empty
-- raw table being autodetected as all-STRING and breaking view creation.

WITH rep_outside AS (
  SELECT
    SAFE_CAST(sp.PO_Key AS INT64) AS PO_Key,
    MIN(SAFE_CAST(sp.Plexus_User_No AS INT64)) AS Plexus_User_No
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Order_Salesperson` AS sp
  GROUP BY 1
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
-- REAL ATTRIBUTE NAMES, read from `raw_Part_v_Attribute` rather than guessed.
-- The original build here guessed 'Bottle Material' and 'Regulatory' and BOTH
-- were wrong, so this pivot deliberately exposes every attribute Plex actually
-- defines instead of pre-selecting the ones that look relevant.
--
-- UPDATED 2026-09-21: Jennilyn added five more attributes since 2026-09-16,
-- and they are in BOTH PlexProd and PlexTest (identical catalogs), so this is
-- real production configuration, not test-tenant scratch work. Full catalog:
--
--   Key  | Name                    | Assignments as of 2026-09-21
--   2383 | Size                    | 0
--   6537 | Allergen                | 14
--   6538 | Hazardous               | 14
--   6770 | Certifications          | 0
--   7427 | California PDP          | 0   (new)
--   7428 | Prop 65 Requirement     | 0   (new)
--   7429 | Trademark               | 0   (new)
--   7431 | Bottle Material         | 0   (new)
--   7432 | Printing Material       | 0
--   7435 | Material Classification | 0   (new)
--
-- NOTE the key churn: 'Printing Material' MOVED from Attribute_Key 7427 to
-- 7432, and 7427 is now 'California PDP'. That is exactly why this pivot joins
-- on Attribute_Name and never on Attribute_Key -- a key-based pivot would have
-- silently started reporting California PDP as the printing material. Keep it
-- name-based.
--
-- All ten have `Use_Value_Table = 1` except Size, i.e. they are controlled
-- dropdowns, which is what the pass-through-untouched design above assumes.
--
-- Which of these (if any) maps to which *Monday* column is still open and is
-- NOT decided by exposing them here. Two data points that narrow it: Ashley
-- confirmed 2026-09-16 that Monday's "Bottle Material" (container material:
-- HDPE/PET/Glass) and Plex's "Printing Material" (label stock) are different
-- concepts -- and Plex now has its own separate 'Bottle Material' attribute,
-- so that mapping finally has a real source. The rest is pending Jennilyn's
-- internal team meeting.
--
-- ── These hang off the LABEL part, not the finished good (2026-10-02) ──────
-- Until today this CTE was joined to the order line's part -- the finished
-- good, 93001-00KAYAN-0 -- and every one of these columns read NULL. QA does
-- not put attributes there. They put them on the LABEL part, 73001-00KAYAN-0,
-- which reaches the order line only through the bill of materials. Hence the
-- `labels` CTE below, and the join on lb.l.part_key rather than pol.Part_Key.
--
-- 40 assignments across 10 label parts, IDENTICAL in PlexTest and PlexProd
-- (verified 2026-10-02), so this is verifiable on test. Four attributes carry
-- values -- Label Size, Printing Material, Allergen, Trademark -- and the
-- other four in the catalog are assigned to nothing yet.
--
-- The NULLIF(TRIM(...), '') on every branch stays regardless: Plex writes an
-- EMPTY STRING, not NULL, for an assigned-but-unfilled attribute, and without
-- this these columns emit '' rather than NULL. Downstream that reads as
-- "filled in, but blank" and would let the Monday push overwrite a
-- hand-entered value with an empty one.
--
-- THREE NAMES BELOW NO LONGER EXIST IN PLEX. The catalog on 2026-10-02 holds
-- exactly eight attributes: Allergen, Certifications, Hazardous, Label Size,
-- Material Classification, Printing Material, Size, Trademark. 'Bottle
-- Material', 'California PDP' and 'Prop 65 Requirement' were all there on
-- 2026-09-21 and are gone. Their columns are KEPT, emitting NULL, until
-- Jennilyn says whether they were removed or renamed -- dropping a column
-- that turns out to have been renamed loses the mapping work twice over.
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
    -- 'Label Size' (key 7436) is where the values are: "2.4 x 6.8 in",
    -- "Custom". Plain 'Size' (key 2383) still exists and is assigned to
    -- nothing -- this CTE asked only for that one until 2026-10-02, so
    -- part_size read NULL even for parts that had a size filled in.
    MAX(CASE WHEN pt.Attribute_Name = 'Label Size'              THEN NULLIF(TRIM(pa.Value), '') END) AS part_label_size,
    MAX(CASE WHEN pt.Attribute_Name = 'Size'                    THEN NULLIF(TRIM(pa.Value), '') END) AS part_size,
    MAX(CASE WHEN pt.Attribute_Name = 'Allergen'                THEN NULLIF(TRIM(pa.Value), '') END) AS part_allergen,
    MAX(CASE WHEN pt.Attribute_Name = 'Hazardous'               THEN NULLIF(TRIM(pa.Value), '') END) AS part_hazardous,
    MAX(CASE WHEN pt.Attribute_Name = 'Certifications'          THEN NULLIF(TRIM(pa.Value), '') END) AS part_certifications,
    MAX(CASE WHEN pt.Attribute_Name = 'Printing Material'       THEN NULLIF(TRIM(pa.Value), '') END) AS part_printing_material,
    MAX(CASE WHEN pt.Attribute_Name = 'Bottle Material'         THEN NULLIF(TRIM(pa.Value), '') END) AS part_bottle_material,
    MAX(CASE WHEN pt.Attribute_Name = 'California PDP'          THEN NULLIF(TRIM(pa.Value), '') END) AS part_california_pdp,
    MAX(CASE WHEN pt.Attribute_Name = 'Prop 65 Requirement'     THEN NULLIF(TRIM(pa.Value), '') END) AS part_prop_65_requirement,
    MAX(CASE WHEN pt.Attribute_Name = 'Trademark'               THEN NULLIF(TRIM(pa.Value), '') END) AS part_trademark,
    MAX(CASE WHEN pt.Attribute_Name = 'Material Classification' THEN NULLIF(TRIM(pa.Value), '') END) AS part_material_classification
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Attribute` AS pa
  JOIN part_attribute_types AS pt
    ON pt.Attribute_Key = SAFE_CAST(pa.Attribute_Key AS INT64)
  GROUP BY SAFE_CAST(pa.Part_Key AS INT64)
),

-- ── Bottle, through the BOM (2026-09-29, Ashley) ─────────────────────────────
-- Monday's Bottle Material (HDPE / PET / Glass) is the CONTAINER, and Plex has
-- no attribute for it on the finished good. It is in the name of the bottle
-- component two levels down the bill of materials:
--
--   93001-00KAYAN-0  finished good (the order line's part)
--   └─ 53001-00VOXNU-0  BB | Max Detox 60ct 175cc White Bottle/White Lid
--      └─ 16115-01VOXNU-1  BOTTLE | 175cc White HDPE Packer Bottle 38-400
--
-- Flat_BOM lists every level against the top part, so no recursion is needed.
-- The bottle is the component whose Name starts "BOTTLE". All 13 real Label
-- Design lines on 2026-09-29 had exactly one. If a part ever has two, the
-- shallowest one (then the lowest part number) wins, picked HERE, before the
-- join, so a second bottle can never duplicate a queue row.
--
-- The material is read from that name and only ever one of the board's own
-- three labels: of 104 bottle parts in PlexTest, 93 name HDPE, PET or Glass.
-- The rest ("BOTTLE | 175cc Black") give NULL, not a guess, and the push then
-- writes nothing.
bottles AS (
  SELECT
    SAFE_CAST(fb.Part_Key AS INT64) AS Part_Key,
    ARRAY_AGG(STRUCT(c.Part_No AS part_no, c.Name AS name)
              ORDER BY SAFE_CAST(fb.BOM_Level AS INT64), c.Part_No LIMIT 1)[OFFSET(0)] AS b
  FROM `{gcp_project}.{dataset}.raw_Part_v_Flat_BOM` AS fb
  JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` AS c
    ON SAFE_CAST(c.Part_Key AS INT64) = SAFE_CAST(fb.Component_Part_Key AS INT64)
  WHERE STARTS_WITH(UPPER(TRIM(c.Name)), 'BOTTLE')
  GROUP BY 1
),

-- ── Label part, through the BOM (2026-10-02, Emilio) ────────────────────────
-- Monday only ever received the PRODUCT part number, but QA records the label
-- attributes against the LABEL part, which is a BOM component of it:
--
--   93001-00KAYAN-0  finished good (the order line's part)
--   └─ 73001-00KAYAN-0  LABEL | Kaya Naturals - Max Detox 60ct (X003F6U4BR)
--                       Standard Label        <- Label Size, Printing
--                                                Material, Allergen, Trademark
--
-- Identical mechanics to `bottles` above, prefix 'LABEL' instead of 'BOTTLE'.
-- Of the 169 parts with a BOM in PlexTest, 54 have a label component and NOT
-- ONE has two (checked 2026-10-02), so the ARRAY_AGG tie-break is insurance
-- rather than a real case. It still matters that the pick happens HERE,
-- before the join: a second label would otherwise duplicate a queue row, and
-- this view's whole contract is one row per order line.
--
-- A part with no label component gets NULLs. That is not a regression --
-- every attribute column was NULL for every row before this existed.
labels AS (
  SELECT
    SAFE_CAST(fb.Part_Key AS INT64) AS Part_Key,
    ARRAY_AGG(STRUCT(SAFE_CAST(c.Part_Key AS INT64) AS part_key,
                     c.Part_No AS part_no,
                     c.Name    AS name)
              ORDER BY SAFE_CAST(fb.BOM_Level AS INT64), c.Part_No LIMIT 1)[OFFSET(0)] AS l
  FROM `{gcp_project}.{dataset}.raw_Part_v_Flat_BOM` AS fb
  JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` AS c
    ON SAFE_CAST(c.Part_Key AS INT64) = SAFE_CAST(fb.Component_Part_Key AS INT64)
  WHERE STARTS_WITH(UPPER(TRIM(c.Name)), 'LABEL')
  GROUP BY 1
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

    -- The line's Priority (2026-10-07, Emilio). In the Plex sales-order screen
    -- each line/release row carries a Priority dropdown; it lives on the
    -- RELEASE (`Sales_v_Release.Priority_Key`), not the PO line, and resolves to
    -- its word through `Part_v_Priority` — NOT `Sales_v_Priority`, which
    -- replicates empty on this tenant (confirmed 2026-10-07). The label is that
    -- view's `Description` column (High/Medium/Low/RUSH/Blanket); its own
    -- `Priority` column is just a sort number (10/20/30/1/40). The value is
    -- carried from whichever release the QUALIFY below keeps (the earliest-due),
    -- so the surfaced priority matches the surfaced due date. Goes to Monday's
    -- Priority column.
    pr.Description                                AS priority,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(rel.Due_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(rel.Due_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(rel.Due_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    )                                             AS due_date_resolved,
    po.order_date_resolved                        AS order_date,
    jn.Job_Note                                   AS job_note,
    NULLIF(TRIM(jn.Job_Note), '')                 AS _note,

    -- ── Sales roles: AM and BDM are DIFFERENT people (2026-10-08, Emilio) ──────
    -- Plex (and Vox's glossary) split the sales rep in two, and they were being
    -- conflated: everything below used to feed one `bdm` column that was really
    -- the AM. The glossary origins pin each one down, but the FIELD each one
    -- actually replicates into had to be found by chasing order 16 (below):
    --   AM  (Account Manager / Inside Salesperson), terms "Assigned To /
    --        Inside Sales / Inside Salesperson":
    --        Sales_v_PO.Inside_Sales  -> Common_v_Customer.Assigned_To
    --   BDM (Business Dev. Manager / Outside Salesperson), terms "Outside Sales /
    --        Outside Salesperson / Assigned To 2", picker "Outside Sales Dialog":
    --        lands in Sales_v_Order_Salesperson (see rep_outside above);
    --        Sales_v_PO.Outside_Sales / Common_v_Customer.Assigned_To2 replicate
    --        empty, so they are only trailing fallbacks.
    -- Monday's "Sales Rep" is the BDM; the AM goes to a new "Inside Sales Rep".
    ui.user_name                                  AS sales_rep_inside,
    ua.user_name                                  AS customer_account_rep,
    -- AM: the order's Inside_Sales first, then the customer's Assigned_To.
    COALESCE(ui.user_name, ua.user_name)          AS am,
    -- BDM: the Order_Salesperson outside rep first (the only field populated in
    -- PlexTest), then Outside_Sales, then Assigned_To2 as last resorts.
    COALESCE(uo2.user_name, uo.user_name, ub.user_name) AS bdm,

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

    -- Keys and the internal part number (2026-09-29), per Emilio's hand-checked
    -- Plex version of this query. The keys are what a Plex deep link needs.
    SAFE_CAST(po.PO_Key AS INT64)                 AS po_key,
    SAFE_CAST(pol.Part_Key AS INT64)              AS part_key,
    part.Part_No                                  AS part_no,
    part.Revision                                 AS part_revision,
    part.Name                                     AS part_name,
    bt.b.part_no                                  AS bottle_part_no,
    bt.b.name                                     AS bottle_name,
    lb.l.part_key                                 AS label_part_key,
    lb.l.part_no                                  AS label_part_no,
    lb.l.name                                     AS label_part_name,

    -- Added 2026-09-16 — see the "Part Attributes" CTEs above. A property of
    -- the PART, not the release, so it is identical across every row this
    -- collapses together; no aggregation needed beyond the plain passthrough.
    pap.part_label_size                            AS part_label_size,
    pap.part_size                                  AS part_size,
    pap.part_allergen                              AS part_allergen,
    pap.part_hazardous                             AS part_hazardous,
    pap.part_certifications                        AS part_certifications,
    pap.part_printing_material                     AS part_printing_material,
    pap.part_bottle_material                       AS part_bottle_material,
    pap.part_california_pdp                        AS part_california_pdp,
    pap.part_prop_65_requirement                   AS part_prop_65_requirement,
    pap.part_trademark                             AS part_trademark,
    pap.part_material_classification               AS part_material_classification,

    -- Tie-breaker only — never surfaced. Keeps the QUALIFY below deterministic
    -- on the rare case where two releases for the same part share a Due_Date.
    -- The unit of the queue (2026-09-30, Ashley): ONE ITEM PER ORDER LINE.
    -- An order with five lines is five items, even if two lines carry the
    -- same part; a line split into several releases is still one item.
    SAFE_CAST(pol.PO_Line_Key AS INT64)           AS po_line_key,

    -- Tie-breaker only, never surfaced: keeps the QUALIFY below deterministic
    -- when two releases of one line share a Due_Date.
    SAFE_CAST(rel.Release_Key AS INT64)           AS _tiebreak_release_key

  FROM dates AS po

  JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` AS pol
    ON SAFE_CAST(pol.PO_Key AS INT64) = SAFE_CAST(po.PO_Key AS INT64)

  JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` AS rel
    ON SAFE_CAST(rel.PO_Line_Key AS INT64) = SAFE_CAST(pol.PO_Line_Key AS INT64)

  JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release_Status` AS rs
    ON SAFE_CAST(rs.Release_Status_Key AS INT64) = SAFE_CAST(rel.Release_Status_Key AS INT64)

  -- Priority lookup (2026-10-07). LEFT so a release with no/unknown priority
  -- key still produces its queue row rather than being dropped.
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Priority` AS pr
    ON SAFE_CAST(pr.Priority_Key AS INT64) = SAFE_CAST(rel.Priority_Key AS INT64)

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

  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` AS part
    ON SAFE_CAST(part.Part_Key AS INT64) = SAFE_CAST(pol.Part_Key AS INT64)

  LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` AS cust
    ON SAFE_CAST(cust.Customer_No AS INT64) = SAFE_CAST(po.Customer_No AS INT64)

  -- AM side: the order's Inside_Sales and the customer's Assigned_To.
  LEFT JOIN users         AS ui ON ui.Plexus_User_No = SAFE_CAST(po.Inside_Sales AS INT64)
  LEFT JOIN users         AS ua ON ua.Plexus_User_No = SAFE_CAST(cust.Assigned_To AS INT64)
  -- BDM side (2026-10-08): the real source is Order_Salesperson (rep_outside);
  -- Outside_Sales and Assigned_To2 replicate empty and are trailing fallbacks.
  LEFT JOIN rep_outside   AS ro  ON ro.PO_Key = SAFE_CAST(po.PO_Key AS INT64)
  LEFT JOIN users         AS uo2 ON uo2.Plexus_User_No = ro.Plexus_User_No
  LEFT JOIN users         AS uo  ON uo.Plexus_User_No = SAFE_CAST(po.Outside_Sales AS INT64)
  LEFT JOIN users         AS ub  ON ub.Plexus_User_No = SAFE_CAST(cust.Assigned_To2 AS INT64)

  LEFT JOIN bottles AS bt
    ON bt.Part_Key = SAFE_CAST(pol.Part_Key AS INT64)

  LEFT JOIN labels AS lb
    ON lb.Part_Key = SAFE_CAST(pol.Part_Key AS INT64)

  -- The LABEL part's attributes, not the finished good's (2026-10-02). See the
  -- `labels` CTE. Joining this to pol.Part_Key, as it did until today, matched
  -- nothing: all 40 populated assignments in Plex are on 73001-* label parts.
  LEFT JOIN part_attributes_pivoted AS pap
    ON pap.Part_Key = lb.l.part_key

  -- Trimmed and uppercased so stray whitespace or casing in Plex can't
  -- silently empty the queue (2026-09-29, matching the Plex version).
  WHERE UPPER(TRIM(rs.Release_Status)) = 'LABEL DESIGN'
    AND UPPER(TRIM(ps.PO_Status)) = 'PENDING FULFILLMENT'
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
  priority,
  MIN(due_date_resolved) OVER (PARTITION BY po_line_key) AS due_date,
  order_date,
  job_note,
  sales_rep_inside,
  customer_account_rep,
  am,
  bdm,
  customer_email,
  customer_phone,
  customer_part_description,
  order_status,
  po_key,
  po_line_key,
  part_key,
  part_no,
  part_revision,
  part_name,
  -- The "part line" Ashley asked for (2026-09-29): what the Plex order screen
  -- shows under the part, e.g. "93001-00KAYAN-0 Rev 00 | FG | Max Detox 60ct
  -- 175cc White Bottle/White Lid +Standard Label (s3832)". Goes to Monday's
  -- Description. ARRAY_TO_STRING skips a NULL half.
  NULLIF(ARRAY_TO_STRING([
    CONCAT(part_no, IF(NULLIF(TRIM(part_revision), '') IS NULL, '', CONCAT(' ', TRIM(part_revision)))),
    NULLIF(TRIM(part_name), '')], ' | '), '')                               AS line_description,
  bottle_part_no,
  bottle_name,
  label_part_key,
  label_part_no,
  label_part_name,
  CASE REGEXP_EXTRACT(UPPER(bottle_name), r'\b(HDPE|PET|GLASS)\b')
    WHEN 'HDPE'  THEN 'HDPE'
    WHEN 'PET'   THEN 'PET'
    WHEN 'GLASS' THEN 'Glass'
  END                                                                       AS bottle_material,
  part_label_size,
  part_size,
  part_allergen,
  part_hazardous,
  part_certifications,
  part_printing_material,
  part_bottle_material,
  part_california_pdp,
  part_prop_65_requirement,
  part_trademark,
  part_material_classification,
  COUNT(*) OVER (PARTITION BY po_line_key)               AS release_count,

  -- ── Reason Code + Memo, split out of the Job Note (2026-09-29) ─────────────
  -- Rule (Emilio): the note's FIRST character, if it is 1-6, is the Reason
  -- Code; the rest is the Memo. Anything else -> no code, the whole note is
  -- the Memo, and the push writes nothing to Monday's Reason Code.
  --
  -- Guarded so a note that merely STARTS WITH A NUMBER is not read as a code:
  -- "12ct bottle" and "3.5 oz label" start with a digit but are quantities.
  -- A code is a 1-6 followed by end-of-note, or by something that is not a
  -- digit and not a decimal point/comma leading into a digit.
  --
  -- One optional separator after the digit is dropped ("1 - text", "1: text",
  -- "1.text", "1text" all give Memo "text").
  --
  -- This is the ONLY place the rule lives. The push service reads these
  -- columns and no longer parses the note itself.
  CASE WHEN REGEXP_CONTAINS(_note, r'^[1-6]($|[^0-9.,]|[.,]($|[^0-9]))')
       THEN SAFE_CAST(SUBSTR(_note, 1, 1) AS INT64) END                     AS reason_code,
  CASE WHEN REGEXP_CONTAINS(_note, r'^[1-6]($|[^0-9.,]|[.,]($|[^0-9]))')
       THEN CASE SUBSTR(_note, 1, 1)
              -- Label text exactly as spelled on the Monday board, including
              -- the lower-case "initiated" in code 2.
              WHEN '1' THEN 'Customer Initiated: Label Edit'
              WHEN '2' THEN 'Customer initiated: Label review'
              WHEN '3' THEN 'New label design (Vox design)'
              WHEN '4' THEN 'New label review (Customer design)'
              WHEN '5' THEN 'Vox Initiated: Label Edit/Review'
              WHEN '6' THEN '3D Rendering'
            END END                                                         AS reason_code_label,
  CASE WHEN REGEXP_CONTAINS(_note, r'^[1-6]($|[^0-9.,]|[.,]($|[^0-9]))')
       THEN NULLIF(REGEXP_REPLACE(SUBSTR(_note, 2), r'^[\s\-:.]+', ''), '')
       ELSE _note END                                                       AS memo,

  -- ── Deep links into Plex (2026-09-29) ─────────────────────────────────────
  -- Host follows the dataset: PlexProd -> vox.on.plex.com, else the test
  -- tenant. `{dataset}` is replaced as plain text by main.py before this runs.
  -- PartNo and Revision are URL-encoded by hand (BigQuery has no function
  -- for it); '%' goes first so the escapes added after it aren't re-escaped.
  IF(part_key IS NULL, NULL, CONCAT(
    IF('{dataset}' = 'PlexProd', 'https://vox.on.plex.com', 'https://vox.test.on.plex.com'),
    '/Engineering/Part/ViewForm?__sk=5&__sak=2&FromPartMenu=True&PartKey=', CAST(part_key AS STRING),
    '&PartNo=', REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
      IFNULL(part_no, ''), '%', '%25'), ' ', '%20'), '&', '%26'), '#', '%23'),
      '+', '%2B'), '?', '%3F'), '/', '%2F'), '=', '%3D'),
    '&Revision=', REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
      IFNULL(part_revision, ''), '%', '%25'), ' ', '%20'), '&', '%26'), '#', '%23'),
      '+', '%2B'), '?', '%3F'), '/', '%2F'), '=', '%3D')))                AS part_url,
  IF(po_key IS NULL, NULL, CONCAT(
    IF('{dataset}' = 'PlexProd', 'https://vox.on.plex.com', 'https://vox.test.on.plex.com'),
    '/SalesAndCRM/SalesOrders/PoFormView?OriginLocation=SalesOrders&POKey=', CAST(po_key AS STRING)))
                                                                            AS customer_po_url,
  IF(po_key IS NULL, NULL, CONCAT(
    IF('{dataset}' = 'PlexProd', 'https://vox.on.plex.com', 'https://vox.test.on.plex.com'),
    '/SalesAndCRM/OrderEntry/ViewOrderForm?POKey=', CAST(po_key AS STRING))) AS sales_order_url,

  -- One key per order LINE (2026-09-30): "<order>|L<PO_Line_Key>". Plex's
  -- line key never changes when a line's part or quantity is edited, so an
  -- edited line is not pushed again as a new item. It replaced
  -- "<order>|<customer part>"; the items pushed under the old key had their
  -- LCR rewritten the same day (see CHANGELOG), so none is pushed twice.
  CONCAT(CAST(order_number AS STRING), '|L', CAST(po_line_key AS STRING))   AS dedupe_key

FROM release_lines

-- One row survives per order LINE: its earliest release. Until 2026-09-30
-- this was per order + customer part, which merged two lines carrying the same
-- part into one item; Ashley settled it as one item per line.
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY po_line_key
  ORDER BY due_date_resolved ASC, _tiebreak_release_key
) = 1

ORDER BY order_date DESC, order_number, customer_part_no
