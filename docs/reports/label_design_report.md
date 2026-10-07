# Label Design Queue

> **Status:** ✅ Built and verified — `label_design_report` exists and is queryable on `PlexTest` · **Category:** Sales · **Runs:** hourly, 5 AM - 5 PM Mountain, Monday to Friday (only does real work when something changed)

## What this tells you

Which sales orders are sitting in **Label Design** right now and need artwork
before they can move — with the customer, the label SKU, the job note, and the
name of the sales rep to ask if something is unclear.

It exists to replace a twice-daily manual loop: download a report from
NetSuite, paste it into a Google Sheet, check it for duplicates by hand, upload
the new rows to Monday. The sales and design teams work the queue itself; this
just keeps it filled and de-duplicated.

## Where it fits

Replaces Jennilyn's Plex stored procedure "Label Design Report"
(`sproc338756_18319605_1407579`) and the manual NetSuite → Sheet → Monday loop
around it, agreed on the 2026-09-11 call.

This is **not** a scorecard tile. It is an operational queue, which is why it
runs through the working day rather than riding the overnight `sales_orders`
pipeline.

**It runs every hour, 5 AM - 5 PM Mountain, Monday to Friday**, so an order that
reaches Label Design at 10:20 is on the board by 10:35 instead of waiting for
the afternoon run. The 5 AM start is the team's own: they are working the queue
before most of the office. The last board update of the day is 5:35 PM.

**Nothing runs at weekends** (since 2026-10-02). Orders entered on Saturday or
Sunday reach the board on Monday at 5 AM, ahead of the team arriving — so the
queue is current when anyone looks at it, even though it sat still for two
days. If the team ever starts working weekends, this needs changing back.
Most of those hourly runs do almost nothing: the job first asks Plex which
order lines are sitting on the Label Design status, and if that list is exactly
what it was last time, it stops there — no extraction, no board update, no
email. The same is true of the push: it checks in BigQuery whether anything is
new before it opens Monday at all. A quiet hour costs seconds; an hour with a
new order does the full job.

## How it's built (high level)

Takes every sales-order release whose status is **Label Design**, keeps only
those on an order that is **Pending Fulfillment** (approved), and limits it to
orders placed in the **last 14 days**. Each row is joined to the customer, the
customer part number and description, the job note, and the sales reps on the
order.

Since 2026-09-29 it also carries the Plex part number and revision, the
**Reason Code** and **Memo** split out of the job note (see below), and three
links that open the record straight in Plex: `part_url`, `customer_po_url` and
`sales_order_url`. They point at `vox.test.on.plex.com` on PlexTest and
`vox.on.plex.com` on PlexProd. The status filters ignore stray spaces and
capitals, so a status typed as " label design" still counts.

Nine of its fourteen source tables are already extracted by `sales_orders`.
They are extracted again here on purpose: this runs through the working day,
hours after that pipeline ran overnight, and a label-design queue built on a
14-hour-old order
list would miss exactly the new orders it exists to surface.

- **Pipeline:** `reports/label_design.yaml` → `label_design_report`
- **SQL:** `reports/sql/label_design_view.sql`
- **Downstream (from 2026-09-24):** `label_design_service/push.py`, a Cloud Run
  job (`plex-etl-label-design-push-test`) that runs 30 minutes after the ETL and
  creates one Monday item per new order **line**, straight from this view. No
  sheet in between. It is test-only for now (PlexTest → the "Plex Import" board).
- **Retired:** `deploy/archive/label_design_sync/`, the Apps Script that used to decide
  which rows were new, write them to a sheet, and push them to Monday.

## What lands on Monday

Each new row becomes an item in the **New from Plex** group, named after the
label SKU. The job fills: Customer Name, Date (order date), Description, Sales
Order ("Sales Order #…"), Email, Phone Number, **Item** (the Plex part number,
in the text column next to Design File), **Sales Rep** (the BDM, see below),
**Priority** (the line's Priority dropdown from Plex, see below) and LCR. The Job Note is split in two, in the view itself (`reason_code`,
`reason_code_label`, `memo`): if its **first character is a digit 1–6**, that
digit sets Reason Code and the rest becomes Memo; otherwise the whole note goes
to Memo and **nothing is written to Reason Code**. A note that only *starts
with a number* is not read as a code: "12ct bottle" and "3.5 oz jar" go to
Memo whole.

**Description** is the part line from the Plex order: part number, revision
and the Plex part name, e.g. `93001-00KAYAN-0 Rev 00 | FG | Max Detox 60ct 175cc
White Bottle/White Lid +Standard Label (s3832)`. **Bottle Material** (HDPE /
PET / Glass) comes from the finished good's bottle component in the bill of
materials, e.g. `BOTTLE | 175cc White HDPE Packer Bottle`. When a bottle's name
doesn't say its material, the column is left blank rather than guessed.

Four more columns since 2026-09-29: **Customer PO** (text), and three links
back into Plex: **Part URL** (shown as part number + revision, e.g.
`93001-00CGNUT-2 Rev 00`), **Customer PO URL** (`PO <customer PO>`) and
**Sales Order URL** (`SO <order #>`). The links are built in the view, so the
report carries them too. Each needs a column with exactly that title and type
on the board; a missing one is skipped with a warning, never a failure. They
replace the 2026-09-25 "Plex Part URL" and "PO URL" columns, deleted from
Plex Import on 2026-09-29.

**Four more since 2026-10-02, all about the label itself:** **Label Part #**
(the Plex label part number, e.g. `73001-00KAYAN-0`), **Label Size**,
**Printing Material** and **Allergen**. These are the attributes QA fills in
on the label part in Plex; until this change the report looked for them on the
product and found nothing, so they never reached the board. The item name is
unchanged — it is still the customer part number, and the label part number
has its own column rather than replacing it.

| First digit | Reason Code |
|---|---|
| 1 | Customer Initiated: Label Edit |
| 2 | Customer initiated: Label review |
| 3 | New label design (Vox design) |
| 4 | New label review (Customer design) |
| 5 | Vox Initiated: Label Edit/Review |
| 6 | 3D Rendering |

Everything else (Design Status, designer, files, dates further down the
process) is left for the team to fill in. **One Monday quirk:** a new item
with no Design Status set shows *Waiting on Customer*. That's the board's
default label, not something the job writes.

**No duplicates:** the LCR column holds a short code (e.g. `e0bd8c5e8e1b`)
made from the order number + the Plex order line (one item per line, so an order
with five lines gives five items, even when two lines carry the same part). A line whose code is already
on the board is never pushed again. Every push is also recorded in the
`label_design_push_log` table.

## Flags and open questions

- **Part-level columns**, pulled from Plex's generic Part Attribute system.
  Since 2026-10-02 they are keyed on the **label** part, not the product —
  QA fills these in against the label (`73001-00KAYAN-0`), which reaches the
  order line through the bill of materials, exactly like the bottle. Before
  that date they were looked up on the finished good and **every one read
  blank**, which is why the team's attributes never reached Monday.

  | Plex attribute | Column | Values populated? |
  |---|---|---|
  | Label Size | `part_label_size` | **yes** — "2.4 x 6.8 in", "Custom" |
  | Printing Material | `part_printing_material` | **yes** — "White BOPP", "White BOPP - Matte Lamination", "Outsourced" |
  | Allergen | `part_allergen` | **yes** — "Tree Nuts" |
  | Trademark | `part_trademark` | **yes** — "N/A" everywhere so far |
  | Size | `part_size` | no — a different, unassigned attribute from Label Size |
  | Hazardous | `part_hazardous` | no |
  | Certifications | `part_certifications` | no |
  | Material Classification | `part_material_classification` | no |
  | Bottle Material | `part_bottle_material` | **gone from Plex** — see below |
  | California PDP | `part_california_pdp` | **gone from Plex** — see below |
  | Prop 65 Requirement | `part_prop_65_requirement` | **gone from Plex** — see below |

  **Three of these attributes no longer exist in Plex.** The catalog on
  2026-10-02 holds eight: Allergen, Certifications, Hazardous, Label Size,
  Material Classification, Printing Material, Size, Trademark. Bottle
  Material, California PDP and Prop 65 Requirement were all there on
  2026-09-21. Their columns are kept, always blank, until Jennilyn says
  whether they were removed or renamed.

  **A product with no label component gets blanks**, not an error. 54 of the
  169 parts with a bill of materials in PlexTest have one; none has two.

  Confirmed with Jennilyn: one value per attribute per part — a need for
  several flags at once (e.g. Prop 65 *and* Organic) is handled by Plex's own
  dropdown having pre-defined combined entries ("Prop 65 + Organic") as a
  single value, passed through untouched rather than parsed.

  **The list grew from five to ten on 2026-09-21** — Jennilyn added California
  PDP, Prop 65 Requirement, Trademark, Bottle Material and Material
  Classification in Plex. They are present in **both** PlexProd and PlexTest
  with identical catalogs, so this is real production configuration, not
  test-tenant scratch work. All ten are exposed here rather than pre-selecting
  the ones that look relevant: the build originally *guessed* at two attribute
  names ('Bottle Material', 'Regulatory') before any real data existed and both
  were wrong, so names are now always read from Plex, never assumed.

  **40 assignments exist across 10 label parts, and PlexTest and PlexProd
  hold identical data** (verified 2026-10-02) — so a change here can be
  checked on test without waiting for a production run. An attribute that is
  assigned but not filled in comes back as an empty string from Plex, and the
  view turns it into a blank rather than letting it overwrite something a
  person typed on the board.

  **Partly settled 2026-10-02:** Label Size, Printing Material and Allergen
  now each feed a Monday column of the same name, and the label part number
  feeds `Label Part #`. What remains open is whether the item name should
  become the label code the team assigns (`s7187`, `CL3776`) instead of the
  customer part number — Ashley's call, since it changes how every row on the
  board reads. Ashley confirmed 2026-09-16 that Monday's "Bottle Material" (the container —
  HDPE/PET/Glass) and Plex's "Printing Material" (label stock — white BOPP,
  metallic, laminated) are genuinely different concepts; Plex now carries its
  own separate Bottle Material attribute, so that one mapping finally has a
  real source. The rest is pending Jennilyn's internal team meeting, and she
  has separately signalled that bottle/label size probably don't need a Monday
  column at all. Not wired to any Monday push yet either way.

- **Priority (2026-10-07).** The Priority dropdown (`PriorityKey`) shown on each
  sales-order line in Plex. It lives on the **release**
  (`Sales_v_Release.Priority_Key`), not the PO line, and is resolved to its word
  through the `Sales_v_Priority` lookup. The value carried is the one on the
  release the row collapses to (the earliest-due), so it matches the Due Date
  shown. The five Plex options are **RUSH / High / Medium / Low / Blanket**, and
  the word is pushed **verbatim** to Monday's **Priority** status column — the
  board's Priority column is set up to carry those same five labels. In PlexTest
  every release currently sits on one priority key, so only one of the five is
  exercised on test until production data varies. Because the push only ever
  *creates* items, a priority changed on an order already on the board is not
  re-pushed.

- **Sales Rep = the BDM (2026-09-24).** Plex's "BDM" fields are the order's
  **Inside Salesperson** (`Sales_v_PO.Inside_Sales`) and the customer's
  **Assigned To** (`Common_v_Customer.Assigned_To`). The `bdm` column takes
  the order's first, then the customer's. The older primary/secondary
  salesperson table is only a last fallback, because Plex barely uses it: one
  row in all of test. All three are still exposed separately.

- **Two sheet columns cannot be filled from Plex.** *WO Number* (the work order
  is raised *after* the label is approved, so an order still in Label Design
  usually has none) and *Item* (the NetSuite item name, which no Plex column
  reproduces). They are written blank and flagged in every run email so the
  team knows they stay that way rather than assuming the data was lost.

- **Four more are blank by design** — *Reason Code*, *Label*, *Bottle
  Material*, *LCR* are filled in by a person during review. That review is the
  reason rows land on a **holding** board rather than the live one.

- **Email and Phone are the customer's account-level details**, not a per-order
  contact. Plex holds a per-line contact as well; which one the label team
  actually wants to reach has never been asked.

- **The dedupe depends on order numbers matching across two spellings** — the
  sheet says "Sales Order #SO0110212" and Plex says "SO0110212". If that ever
  stops matching, *every* row looks new at once. The Apps Script watches for
  exactly that shape and holds the run back to a dated review tab instead of
  re-importing the queue onto the board.

- **The `historical` tab is read and never written.** Notes and reason codes are
  hand-edited there, and re-writing a row would destroy that work.

- **Superseded by the push job (2026-09-24):** the Sheet-era notes above
  (holding board, `historical` tab, "Sales Order #" matching, placeholder
  column IDs). The job finds columns by title and dedupes on LCR.
- **Orders with no customer part number (2026-09-29):** each part gets its own
  row and its own LCR, keyed on the Plex `Part_Key`. Before, two such parts on
  one order shared a key and only the first reached Monday.
- **Part attributes reach Monday from 2026-10-02:** `Label Part #`,
  `Label Size`, `Printing Material` and `Allergen` are written to columns of
  those exact titles. The other `part_*` columns are in the report but feed no
  Monday column — there is nothing in them yet.

## More detail

- [`deploy/archive/label_design_sync/README.md`](../../deploy/archive/label_design_sync/README.md)
  — the Apps Script half: dedupe rules, tabs, notifications, the Monday traps.
- [`CHANGELOG.md`](../../CHANGELOG.md) — 2026-09-11, 2026-09-12, 2026-09-24 and 2026-09-29 entries.
- Test cases: `python scripts/label_design_test_data.py --inject`, then
  `--check` grades the local SQL against 31 edge cases (PASS/FAIL each).
