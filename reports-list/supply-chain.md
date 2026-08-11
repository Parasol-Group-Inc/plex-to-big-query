# Reports List — Supply Chain

Source file: `Reports List - Supply Chain.csv`. Columns: Report Name,
Source, Function, Users, Link, Priority.

| Report | Source | Status | Notes |
|---|---|---|---|
| Inventory Activity Detail Usage Per Month | NetSuite | ✅ Already built | This is the exact NetSuite report this project built parity for as `inventory_activity_report` (#29 in `docs/NETSUITE_REPORT_BUILD_PLAN.md`) |
| Inventory Risk Analysis - Custom Formula | NetSuite | ❌ Out of scope | Native NetSuite search |
| Inventory Risk Analysis - Item Stock Type | NetSuite | ❌ Out of scope | Native NetSuite search |
| Open Purchase Orders Report V1 | NetSuite | ✅ Already built | Parity report `purchasing_open_orders_report` (#75) covers this concept |
| **Approaching MSL** | Google Sheet | 🔍 Candidate — Google Sheet, critical priority, existing overlap | Described as providing "the daily average and current available inventory to the MFG Job Schedule and other sources." This may be the **current manual source** of the exact number `part_on_hand_inventory_report` (built from `Part_v_Container`) now automates — high-value to get real content for and compare directly. Priority: Critical (daily use) |
| MFG Job Schedule | Google Sheet | ✅ Already built | See `spreadsheets/mfg_job_schedule.md` |
| Bottling Job Schedule | Google Sheet | 🔍 Mapped | See `spreadsheets/bottling_job_schedule.md` |
| NEW COA Library | Google Sheet | 🔍 Candidate — Google Sheet, existing overlap | "Tracks the testing of raw materials, finished goods and extensions" — overlaps with `Quality_v_Checksheet`/`Sample_Plan`, already extracted for `mfg_job_schedule_report` |
| Expiration Status Of Inventory 15 Months | Data Ninja | ❌ Out of scope | Different BI tool (same underlying concept as the Quality tab's expiration-tracking rows) |
| Manufacture Order Tracking Log | Excel / network share (`V:\...`) | ❌ Out of scope | Local file share, not analyzable by this pipeline directly — conceptually overlaps with `mfg_job_schedule_report`'s PO-tracking-per-job intent |
| Reorder Multiple Search | NetSuite | ❌ Out of scope | Native NetSuite search |
| Purchase Orders to Approve: Results | NetSuite | ❌ Out of scope | Native NetSuite search |
| Purchasing \| Pending Order Requisitions: Results | NetSuite | ❌ Out of scope | Native NetSuite search |
| Approve Vendor Return Authorizations | NetSuite | ❌ Out of scope | Native NetSuite transaction screen |

## Priority read

**Approaching MSL** is the standout — critical priority, described as
already feeding the exact "current available inventory" concept this
project just automated in `part_on_hand_inventory_report`. Getting its real
content would let us either validate that report against the team's
existing manual number, or discover we're missing something Container-based
on-hand-quantity doesn't capture (e.g. MSL = Minimum Stock Level, which
implies a reorder-point/threshold concept `Part_v_Container` alone doesn't
have).
