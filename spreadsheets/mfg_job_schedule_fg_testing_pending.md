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
| Blender (batch size) | **Resolved 2026-08-23** — `Part_v_Approved_Workcenter.Batch_Size`, joined through `Part_v_Part_Operation`/`Part_v_Operation` for the unit (`kgs`/`kg`, confirmed live on all 6 real Blending parts). See the resolution below for the full query and reasoning. |

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

## Update 2026-08-23 (cont.) — live-confirmed, but unit is ambiguous, not settled

Ran the query above against `vox.test.odbc.plex.com` (SQL Development
Environment). `Part_v_Approved_Workcenter.Batch_Size` is confirmed real
and populated on actual Blending routings (`Blend 2`/`3`/`4`/`5`):

| Batch_Size | Unit | Workcenter | Part |
|---|---|---|---|
| 1000 | *(blank)* | Blend 2/3/5 | `BLEND \| Neuro Plus Brain and Focus` (`23111-01VOXNU-1`) |
| 750 | *(blank)* | Blend 4 | same part |
| 690 | *(blank)* | Blend 2/3/5 | `Powder \| L-Arginine Plus` |
| 645 | *(blank)* | Blend 2/3/5 | `Powder \| Beetroot` |
| 570 | *(blank)* | Blend 2/3/5 | `Powder \| BCAA Honeydew/Watermelon` |
| 500 | **eaches** | Blend 4 | `BLEND \| Myo D-Chiro Inositol Plus` |

`Part_v_Part.Unit` is a real column, populated (not NULL) but blank on
every row except one — and that one says **`eaches`** (a count), not
liters. This is the opposite of the sheet's `2000L` example, not a
confirmation of it. **Verdict at this point: right shape, wrong/unconfirmed
unit** — see resolution below, `Part_v_Part.Unit` was the wrong unit
column to check (it's the finished part's own stocking unit, not the
operation's production unit).

## RESOLVED 2026-08-23 — Blender batch size is in kilograms, not liters

`Part_v_Part.Unit` was the wrong place to look — it's the finished part's
stocking unit, not the unit an *operation* produces in. The right chain is
`Part_v_Approved_Workcenter.Part_Operation_Key` → `Part_v_Part_Operation.Part_Operation_Key`
→ `Part_v_Part_Operation.Operation_Key` → `Part_v_Operation.Operation_Key`,
which carries the operation-type's own unit columns
(`Unit`/`Production_Unit`/`Denominator_Unit`/`Cost_Unit`).

Live-confirmed (SQL Development Environment, `vox.test.odbc.plex.com`):
**every single Blending row** (`Operation_Code = 'Blending'`, all of
Blend 2/3/4/5, all 6 real parts) returns `Operation_Unit = 'kgs'`,
`Denominator_Unit = 'kg'` — no exceptions, no blanks. `Batch_Criteria`
(on `Part_v_Part_Operation`) came back blank on all rows — exists as a
real column, just not populated on this tenant.

```sql
SELECT TOP 20
  paw.Batch_Size,
  po.Unit AS Operation_Unit,
  po.Production_Unit,
  po.Denominator_Unit,
  po.Operation_Code,
  ppo.Batch_Criteria,
  wc.Name AS Workcenter_Name,
  p.Part_No,
  p.Name AS Part_Name
FROM Part_v_Approved_Workcenter AS paw
JOIN Part_v_Workcenter AS wc
  ON paw.Workcenter_Key = wc.Workcenter_Key
JOIN Part_v_Part AS p
  ON paw.Part_Key = p.Part_Key
JOIN Part_v_Part_Operation AS ppo
  ON paw.Part_Operation_Key = ppo.Part_Operation_Key
JOIN Part_v_Operation AS po
  ON ppo.Operation_Key = po.Operation_Key
WHERE wc.Workcenter_Group = 'Blending'
  AND paw.Batch_Size > 0
ORDER BY paw.Batch_Size DESC
```

**Verdict: `Part_v_Approved_Workcenter.Batch_Size` IS the "Blender" column
— measured in kilograms, not liters.** The sheet's `2000L` example was
either an approximation/rounding by whoever wrote the doc, a different
part not yet seen in this tenant's 51 populated rows, or a genuine
unit mismatch worth a quick confirmation with whoever fills in the sheet
— but the Plex-side mapping itself is settled: real numbers (500-1000 kg
range, live-confirmed on 6 real parts), real unit, no ambiguity left in
the schema. This is the **approved/planned** batch size (a routing spec),
not a per-job actual — `Part_v_Job_Op_Batch` (still 0 rows) remains the
place to check once a real job actually produces a batch, if a per-job
actual is ever needed instead of the routing spec.

## What's needed next

1. Confirm the real column headers for the 2 unlabeled columns before
   "POs Received" directly in the Google Sheet (not the CSV export).
2. Test the `Job_Type_Key`/`Job_Distribution.Release_Key` leads once real
   job data exists on either tenant — would resolve Stock/Custom AND
   Customer at once, for both this tab and YTD Gate Stats.
3. ✅ **Resolved 2026-08-23** — Blender/batch size mapping (see above).
