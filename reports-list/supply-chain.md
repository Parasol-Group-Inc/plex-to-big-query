# Reports List — Supply Chain

Source file: `Reports List - Supply Chain.csv`. Columns: Report Name,
Source, Function, Users, Link, Priority.

| Report | Source | Status | Notes |
|---|---|---|---|
| Inventory Activity Detail Usage Per Month | NetSuite | ✅ Already built | This is the exact NetSuite report this project built parity for as `inventory_activity_report` (#29 in `docs/NETSUITE_REPORT_BUILD_PLAN.md`) |
| Inventory Risk Analysis - Custom Formula | NetSuite | ✅ Deployed, decided 2026-08-21 | No packaged "risk"/aging concept in Plex (confirmed at both the view and 14,350-row stored-procedure layer). Built as `inventory_risk_analysis_report` — on-hand qty + days-since-last-container-activity per part. **Decided: 90+ days since last activity (or none at all) = `is_at_risk`** — a general convention, not Vox-specific policy; `days_since_activity` stays exposed so the cutoff can change with zero recomputation if 90 turns out wrong. See docs/NETSUITE_PARITY_OPEN_ITEMS.md. |
| Inventory Risk Analysis - Item Stock Type | NetSuite | ✅ Deployed, decided 2026-08-21 | Same underlying view as the row above — both `Part_v_Part.Part_Type` and the real `part_product_type` classification (`Part_v_Part_Product_Type`, added 2026-08-19) are included per-part so it can be grouped/filtered by stock type from the same report. |
| Open Purchase Orders Report V1 | NetSuite | ✅ Already built | Parity report `purchasing_open_orders_report` (#75) covers this concept |
| **Approaching MSL** | Google Sheet | 🔍 Candidate — Google Sheet, critical priority, existing overlap | Described as providing "the daily average and current available inventory to the MFG Job Schedule and other sources." This may be the **current manual source** of the exact number `part_on_hand_inventory_report` (built from `Part_v_Container`) now automates — high-value to get real content for and compare directly. Priority: Critical (daily use) |
| MFG Job Schedule | Google Sheet | ✅ Already built | See `spreadsheets/mfg_job_schedule.md` |
| Bottling Job Schedule | Google Sheet | 🔍 Mapped | See `spreadsheets/bottling_job_schedule.md` |
| NEW COA Library | Google Sheet | 🔍 Candidate — Google Sheet, existing overlap | "Tracks the testing of raw materials, finished goods and extensions" — overlaps with `Quality_v_Checksheet`/`Sample_Plan`, already extracted for `mfg_job_schedule_report` |
| Expiration Status Of Inventory 15 Months | Data Ninja | ❌ Out of scope | Different BI tool (same underlying concept as the Quality tab's expiration-tracking rows) |
| Manufacture Order Tracking Log | Excel / network share (`V:\...`) | ❌ Out of scope | Local file share, not analyzable by this pipeline directly — conceptually overlaps with `mfg_job_schedule_report`'s PO-tracking-per-job intent |
| Reorder Multiple Search | NetSuite | ❌ Out of scope, confirmed no match | The only candidate name, `Material_v_Reorder_Point`, was tree-guessed only (❓ in `catalog/plex_material_views_catalog.md`) — confirmed live 2026-08-14 it does not actually exist ("Base table not found"). No other reorder-point view found anywhere in the schema. Get the actual NetSuite report definition, or ask the data scientist what Vox's real reorder-point source is. |
| Purchase Orders to Approve: Results | NetSuite | ✅ Built | `purchasing_po_pending_approval_report` — 2nd `bq_view` on the live `purchasing_open_orders.yaml`, filtered to the confirmed "Pending Approval-NS" status (key 5559). No business-rule guess needed. |
| Purchasing \| Pending Order Requisitions: Results | NetSuite | 🛠 Parity build scaffolded | Native NetSuite search, but a Plex equivalent exists — `Purchasing_v_Requisition` + `Requisition_Status` + `Req_PO_Release`. "Shows all pending requisitions waiting to be purchased." Priority: Critical (daily use). See `reports/purchasing_pending_requisitions.yaml` and `docs/NETSUITE_REPORT_BUILD_PLAN.md` § Purchasing \| Pending Order Requisitions — not yet deployed. |
| Approve Vendor Return Authorizations | NetSuite | 🛠 Parity build scaffolded, needs data-scientist input | `Quality_v_Supplier_Return` + `_Status` + `_Type` exist and are schema-confirmed, but the expected Approving/Approved status flags are confirmed live to be unused (0 on all 6 statuses) — see `reports/quality_supplier_returns.yaml`. Built with a status-exclusion proxy (not yet Shipped/Complete/Cancelled) pending a real definition. |

## Priority read

**Approaching MSL** is the standout — critical priority, described as
already feeding the exact "current available inventory" concept this
project just automated in `part_on_hand_inventory_report`. Getting its real
content would let us either validate that report against the team's
existing manual number, or discover we're missing something Container-based
on-hand-quantity doesn't capture (e.g. MSL = Minimum Stock Level, which
implies a reorder-point/threshold concept `Part_v_Container` alone doesn't
have).

**New lead, 2026-08-21:** a screenshot of the Plex UI's own "Scheduled Job
Requirements" report (Outlook-days filter, "Component" grain, columns Part/
Rev/Total Inventory/Avail Source/Job Count/Job Balance/Inv Balance/Total
Required) is structural evidence this exact concept — scheduled job
component requirements exploded through BOM, compared against on-hand
inventory — is buildable natively: `Part_v_BOM`/`Part_v_Flat_BOM`/
`Part_v_Job_Bom` are confirmed live, joined against `Part_v_Job`
(scheduled quantity) and `Part_v_Container` (on-hand). This may be the real
Plex-native answer "Approaching MSL" is manually approximating, and/or the
lead for `docs/NETSUITE_PARITY_OPEN_ITEMS.md`'s "Inventory consumption"
row. See `catalog/plex_catalog_index.md`'s 2026-08-21 confirmed-values
section for the full detail. Not yet built — needs a decision on scope
before writing SQL (MSL/reorder-point threshold logic hasn't been located
anywhere in the schema, so this covers the "requirements vs. available"
half, not a full MSL alert).
