# Reports List — Quality

Source file: `Reports List - Quality.csv`. Columns: Report Name, Source,
Function, Users, Link, Priority.

**This tab is the highest-value list in the whole Reports List catalog.**
9 rows literally say `New W Plex` in both the Source and Link columns —
meaning Quality has already identified these as wanted, Plex-based reports
that don't exist yet. That's a ready-made roadmap, not a discovery task.

| Report | Source | Status | Notes |
|---|---|---|---|
| Quality \| Bottling Production Search | NS / Google Log for QA | ✅ Already built (mislabeled) | Link is actually the **Bottling Job Schedule** Google Sheet, not NetSuite. See `spreadsheets/bottling_job_schedule.md` |
| Quality \| Encapsulation Production Search | NS / Google Log for QA | ✅ Already built (mislabeled) | Link is actually a tab of the **MFG Job Schedule** Google Sheet (`gid=430198532`). See `spreadsheets/mfg_job_schedule.md` |
| Quality \| Label Production Search | Data Ninja by job | ❌ Out of scope | Different BI tool |
| Customer Label Cert / NSF / Organic Cert | Google Docs, marked "New W Plex" | 🎯 Candidate | Regulatory cert tracking — no columns/schema known yet |
| Discontinued Materials | "New W Plex" | 🎯 Candidate — likely already covered | Strong overlap with the already-built NetSuite parity report `part_obsolescence_report` (VOX \| Products to be discontinued) — check this first before treating as new work |
| Monthly CofA Report / Prop 65 | Google Docs | 🔍 Candidate — Google Sheet | No content provided yet |
| Deviation Open Closed Trending Area | Google Docs | 🔍 Candidate — Google Sheet | No content provided yet |
| CAPA open closed trending area | Excel Log | ❌ Out of scope | Local file, not a Google Sheet |
| Complaints | Google Docs | 🔍 Candidate — Google Sheet | No content provided yet |
| **NC** | Google Docs | 🔍 Candidate — Google Sheet, strong existing overlap | "Internally Generated Nonconformance Tracking." Very plausibly the human-maintained counterpart to the already-built `quality_nonconformance_report` (from `Quality_v_Problem`) — worth comparing directly once content is available, could validate or replace it |
| Material destruction open closed $$ Product | Google Docs | 🔍 Candidate — Google Sheet | No content provided yet |
| Risk Assessment Open Closed Product | Excel Log | ❌ Out of scope | Local file |
| RMA / Returns open closed product | Data Ninja by Location | ❌ Out of scope | Different BI tool |
| Rework Open Closed $$ Product | Google Docs | 🔍 Candidate — Google Sheet | No content provided yet |
| Expired or Expiring Materials | Google Docs | 🔍 Candidate — Google Sheet, existing overlap | Overlaps with `Part_v_Lot_Shelf_Life`/`Part_v_Container.Shelf_Date`, both already flagged (unconfirmed) in `spreadsheets/mfg_job_schedule.md` |
| SPC Check Sheets | "New W Plex" | 🎯 Candidate | Statistical process control — `Quality_v_Checksheet` (already extracted for `mfg_job_schedule_report`) is a plausible existing lead |
| Monthly Environmental | Google Docs | 🔍 Candidate — Google Sheet | Cleaning test results — no obvious Plex lead |
| Receiving Materials Report | Google Docs | 🔍 Candidate — Google Sheet, existing overlap | Overlaps with `Purchasing_v_Receipt` (tree-confirmed only, never live-verified — see `catalog/plex_purchasing_views_catalog.md`) |
| Supplier Surveys Monthly | Excel Spreadsheet | ❌ Out of scope | Local file |
| Turn Time Finished & Raw Testing | Google Docs | 🔍 Candidate — Google Sheet, existing overlap | Overlaps with `Quality_v_Checksheet`/`Sample_Plan`, already extracted |
| 15 Month Exp Report | Data Ninja | ❌ Out of scope | Different BI tool (though conceptually same expiration data as above) |
| Out of Specification Test Results | Excel Log | ❌ Out of scope | Local file |
| Equip Calibration | Google Docs | 🔍 Candidate — Google Sheet, existing overlap | Overlaps with `Maintenance_v_Equipment`, already extracted for `mfg_job_schedule_report` |
| Theory vrs Actual Yield | "New W Plex" | 🎯 Candidate | R&D use. Conceptually close to the Production Yield / Job_Op-quantity leads already being investigated for the Daily Reports — see `reports-list/production.md` |
| Where used Reports | "New W Plex" | 🎯 Candidate | R&D use — likely `Part_v_BOM` (component → finished-good lookup), same table already flagged as a gap-source for MFG Job Schedule's "MG Per Cap"/Bottling's "Fill Weight" |
| Ingredient Turn Times | "New W Plex" | 🎯 Candidate | R&D use — no obvious Plex lead identified yet |
| Ingredient Useage | "New W Plex" | 🎯 Candidate | R&D use — plausibly `Part_v_BOM` again |
| Cycle Time Blending Encap | "New W Plex" | 🎯 Candidate | Directly overlaps with the Blending/Encap workcenter-timing work already started in `mfg_job_schedule_report` (`Job_Op.Start_Date`/`Complete_Date`) |
| Certification Reports by Ingredient | "New W Plex" | 🎯 Candidate | R&D + Regulatory — no obvious Plex lead identified yet |
| Label Design / Label QA / Pending Customer Approval / Completion Approved Label | Monday.com | ❌ Out of scope | Different platform entirely (4 rows, same board) |
| Experation Status | Google Docs | 🔍 Candidate — Google Sheet, existing overlap | Same expiration-tracking overlap as above (<90 days variant) |
| Product Returns | Excel Logs | ❌ Out of scope | Local file/network share |
| R&D | Google Docs | 🔍 Candidate — Google Sheet | Sample/test log — no obvious Plex lead yet |

## Priority read

The 9 "New W Plex" rows are the clearest next targets — they're pre-approved
by Quality as wanted Plex-based reports. Two of them (**Discontinued
Materials**, **Cycle Time Blending Encap**) likely need little or no new
work since they overlap heavily with what's already built
(`part_obsolescence_report`, `mfg_job_schedule_report`'s Job_Op timing) —
worth confirming that overlap explicitly before scoping any of these as new
builds.
