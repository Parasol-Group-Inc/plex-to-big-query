# MFG Job Schedule — "FG Testing Pending" tab

- **Parent spreadsheet:** [MFG Job Schedule](mfg_job_schedule.md) (see its
  "Tabs in this spreadsheet" tracker)
- **Status:** 🔍 Mapped — real data analyzed (11 rows), same job-level grain
  as the "Open" tab, mostly buildable

## What it is

Same row grain as the "Open" tab (one row per blend/encap job), filtered to
jobs whose **FG (finished goods) testing hasn't been released yet** — i.e.
still in the QC release pipeline after production. Real data (not a
template) — 11 in-flight jobs, mostly custom capsule runs for
`Nutricost Manufacturing, LLC` and stock runs routed to an internal
`Warehouse` bucket.

**Architectural note:** this is very likely a **filtered view of the same
underlying job data** as the Open tab / `mfg_job_schedule_report`, not a
distinct data source — once `FG_Testing_Released` is buildable, this tab
is that same report `WHERE FG_Testing_Released_date IS NULL`, not a new
report.

## Findings — column-by-column

**Buildable from Plex (same confirmed sources as the Open tab):**

| Column | Plex source |
|---|---|
| SKU, Description | `Part_v_Part.Part_No`/`.Name` |
| Capsule Count (= Qty Ordered) | `Part_v_Job.Quantity` |
| Blending Started/complete, Encap Started, FG Complete | `Part_v_Job_Op.Start_Date`/`Complete_Date` filtered by confirmed workcenter roster (`Blend 2-5` / `Encapsulation 1-10`) |
| Operator | `Job_Op.Started_By`/`Completed_By` → `Personnel_v_Employee.Common_Name` |
| Lot #, exp: (expiration) | `Part_v_Job.Lot_Key` → `Part_v_Lot`, `Part_v_Lot_Shelf_Life` |
| NC # | `Quality_v_Problem` (same NC-to-job correlation gap as always — see below) |
| Room # | `Part_v_Job.Building_Key` → `Common_v_Building` |
| Asset # | `Job_Op.Workcenter_Key` → `Maintenance_v_Equipment` |
| All Raws Sampled & Shipped, Raws Released, FG Testing Released | `Quality_v_Checksheet`/`_Status` |
| Available Inventory | `Part_v_Container` (`part_on_hand_inventory_report`) — **see caveat below**, the raw on-hand number is buildable but this tab pairs it with a derived metric that isn't |
| POs Received | `purchasing_open_orders_report` — **see caveat below**, the exact semantics of this column are ambiguous in the export |

**New finding — "Custom or Stock" is confirmed manual, not a Plex gap:**
This tab has an explicit `Custom or Stock` column with hand-typed values
(`custom`/`stock`) — direct proof this classification is **not** currently
pulled from Plex by whoever maintains the sheet. That doesn't mean Plex
has no way to derive it, though: see the corrected finding in
`catalog/plex_part_views_catalog.md` and
`mfg_job_schedule_ytd_gate_stats.md` — `Part_v_Job.Job_Type_Key` →
`Part_v_Job_Type` (`Stock`/`Service`/`Pre-Production`/`Rework`) and
`Part_v_Job_Distribution.Release_Key` (populated = tied to a customer
order) are both real leads, added to `mfg_job_schedule_view.sql` as
`job_type`/`job_distribution_count`/`job_distribution_sample_release_key`
(committed `6c3b1c7`, **deployed 2026-08-11** — verified live against
`PlexTest.mfg_job_schedule_report`). Local BigQuery test already
partially validated the first lead: 2 leftover job records resolved
`job_type = 'Stock'` through the new join. `Job_Distribution` is still
empty on the test tenant, so the second lead remains untested. This
hand-typed column is a real replacement candidate once more job data
exists, not a permanent gap.

**New finding — "Customer" column is a plausible new lead:** values are
either a real customer name (`Nutricost Manufacturing, LLC`) for custom
jobs, or the literal placeholder `Warehouse` for stock jobs — i.e. this
column and `Custom or Stock` look like they encode the same underlying
fact. `Part_v_Job_Distribution.Release_Key` (see above) is the most
plausible Plex-side source for both at once, unconfirmed against data.

**Gaps — plausible source exists but unresolved, or genuinely absent:**

| Column | Gap |
|---|---|
| MG Per Cap, Cap Specs | Same BOM/unit-conversion gap already flagged on the Open tab — not built speculatively. |
| Blender (batch size, e.g. `2000L`/`1500L`) | Checked `Part_v_Job_Material` live (only `PCN`/`Job_Key`/`Part_Material_Key`/`Cuts` — not a batch-size field) — no confirmed source found yet. Likely a vessel/equipment attribute or a Job-level attribute, not yet located. |
| Days Left, Days on hand when completed | These look like a **derived days-of-supply metric** (`Available Inventory` ÷ an implied usage/demand rate), not a raw field — some rows have large negative values (e.g. `Available Inventory = -8,585,908`, `Days Left = -102.4`), consistent with a backorder condition in a live formula, not a static ERP column. The raw on-hand quantity is buildable (`part_on_hand_inventory_report`); the usage/demand-rate component that turns it into "days" has no confirmed Plex source — flagged, not built. |
| NC-to-job correlation | Same standing gap: `Quality_v_Problem` has no `Job_Key`/`Job_Op_Key`. |
| POs Received — exact semantics | The CSV export has **2 unlabeled columns** immediately before this one (holding a boolean-looking `FALSE` and a blank in the sample data) — the real sheet likely has hidden/helper columns that didn't carry a header name into the export. Recommend confirming the actual column headers directly in the Sheet UI before building, rather than trusting CSV column position. |

**Manual-only — never in any ERP, deliberately not built:**

Job # (multi-line free text embedding NetSuite WO numbers, e.g.
`NS Caps: WO0047525 (Rev 4)` — confirmed again here, same NetSuite
situation as every other tab), Date entered, Days in WIP, BR Ready for
MFG, Sign Off, and Notes (a rich, timestamped free-text commentary log —
e.g. multi-paragraph raw-material sourcing updates per job).

## Update 2026-08-23 — two new "Blender" candidates found

Re-swept the full schema catalog for "Blender"/"Batch_Size" beyond
`Part_v_Job_Material` (already ruled out). Two real, previously-unchecked
tables:

- **`Part_v_Job_Op_Batch`** — `Job_Op_Key` (direct FK to the already-
  extracted `Part_v_Job_Op`), `Batch_No`, `Batch_Size` (float), and
  `Resource_ID` (string). This is the stronger candidate: a per-job-
  operation *actual* batch record, and `Resource_ID` could plausibly BE
  the literal blender identifier, not just its size. Confirmed live to
  exist and be queryable — **0 rows** on the test tenant (no job has
  produced a batch yet, consistent with everything else on this tenant).
- **`Part_v_Approved_Workcenter`** — a part+operation+workcenter routing
  spec with a `Batch_Size` float column. **Confirmed LIVE with real data**
  (2,335 rows, 51 with non-zero `Batch_Size`: 348.75–1000.0 range). This
  is the *planned/approved* batch size for a routing, not a per-job
  actual — and the unit (count vs. liters) is unconfirmed; the sheet's
  own example (`2000L`) wasn't seen in this tenant's populated range, but
  that may just mean no Blending-workcenter row happens to be populated
  yet, not that the column is wrong.

**Ask Emilio to check, next time he's in Plex:** open the Job Routing (or
Approved Workcenter) screen for a part that runs on a Blending workcenter
— does it show a "Batch Size" field, and is it labeled in liters or a
count? If it matches one of the live `Part_v_Approved_Workcenter` values
above, that confirms the table; if not, `Part_v_Job_Op_Batch.Resource_ID`
is the next thing to check once a real job actually produces a batch.

## What's needed next

1. Confirm the real column headers for the 2 unlabeled columns before
   "POs Received" directly in the Google Sheet (not the CSV export).
2. Test the `Job_Type_Key`/`Job_Distribution.Release_Key` leads once real
   job data exists on either tenant — would resolve Stock/Custom AND
   Customer at once, for both this tab and YTD Gate Stats.
3. Confirm the two new "Blender" candidates above against a real Blending
   job/routing, either via live data or a Plex UI screenshot.
