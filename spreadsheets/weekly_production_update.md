# Weekly Production Update

- **Type:** Google Sheet
- **Category:** Weekly/Monthly Production Attainment
- **Departments:** Production, Planning (Users: Mark, Nick, Chris — per `reports-list/production.md`)
- **Status:** 🔍 Mapped — real content received 2026-08-26 (2 tabs: "Capacity" and "Goals"). Partially buildable; several open questions below before the rest can be built.

## What it is

Two tabs tracking weekly/monthly production attainment against manually set targets, for 4 departments: Encap, Bottling, Labeling, Printing (a different department set than the 4 Daily Reports' Encap/Blending/Labeling/Packaging — no Blending here, and this tab calls the Bottling-mapped one "Bottling" directly rather than "Packaging").

**"Goals" tab** — two side-by-side tables (Weekly, Monthly), each with Department / Actual (WTD or MTD) / Goal / % of Goal, plus a small "Weekly Loss (Encap)" side table (Product / Caps Lost / Time (hours)) and a "% of Month Complete" figure.

**"Capacity" tab** — Department / Weekly Capacity Avg % / Monthly Capacity Avg %. Only Encap has real values filled in (66.69%/59.53%); Bottling/Labeling/Printing are blank.

## Findings — column-by-column

**Buildable from Plex (confirmed live sources, reusing the 4 Daily Reports' pattern):**

| Column | Plex source |
|---|---|
| Actual WTD/MTD quantity by department | `Part_v_Production` (`Quantity`, `Rejected`) joined through `Part_v_Job_Op` to `Part_v_Workcenter.Workcenter_Group`, non-rejected quantity summed over the relevant date range — exact same source and Plex-boolean convention (`Rejected = -1`) already confirmed and used by `encap_daily_report`/`blending_daily_report`/`labeling_daily_report`/`packaging_daily_report`. Only difference from those reports: summed over week-to-date/month-to-date instead of grouped by single day. |
| Printing department coverage | **New** — no existing Daily Report covers Printing. `Workcenter_Group = 'Printing'` is already confirmed live (`reports-list/production.md`'s 2026-08-21 confirmed-workcenter-roster note), so this is the same pattern as the other 4, just not built yet. |
| "Caps Lost" (Weekly Loss - Encap) | Same `Rejected` flag already used as `scrap_qty` on `encap_daily_report` — buildable, not a new gap. |
| "% of Month Complete" | Pure date arithmetic (`EXTRACT(DAY FROM CURRENT_DATE()) / days in current month`) — no Plex dependency at all, doesn't need any of this pipeline's extracted data. |

**Manual-only / needs a decision before buildable — not a data gap, a "where does this live" question:**

| Column | Why it's not a straightforward Plex pull |
|---|---|
| Goal (weekly and monthly, per department) | No Plex source at all — these are business-set targets a person types in, not something any ERP tracks. To compute "% of Goal" in BigQuery, the goal numbers need to live *somewhere* this pipeline can read them — see Open Questions below. |
| Weekly Capacity Avg % / Monthly Capacity Avg % | Formula unconfirmed. "Capacity" isn't defined anywhere in this pipeline's existing work — it's presumably `Actual ÷ some theoretical maximum throughput`, but that theoretical-max input (a rate per workcenter, e.g. units/hour × scheduled hours) has no established Plex source yet, unlike Yield's "planned qty" (which is a real Plex column, `Part_v_Job.Quantity`). Only Encap has real values filled in on the tab itself — worth confirming whether this metric is even fully defined yet on the business side before guessing a formula. |
| "Time (hours)" — Weekly Loss (Encap) | `Caps Lost` has a confirmed Plex source (see above), but lost *time* doesn't — no downtime/stoppage-reason table has been identified for this pipeline. Possibly `Part_v_Workcenter_Log` (already extracted for `work_orders_report`, actual hours logged) could bound this, but that's a lead, not a confirmed source. |
| "WTD (M-T)" — exact week window | The header literally says "M-T," which could mean "Monday-through-Thursday" (a partial-week snapshot, not a full calendar week) or something else entirely. Assumed to mean "Monday of the current week through today" for the build below — **not confirmed**, see Open Questions. |

## Open Questions for Emilio

1. **Where should the Goal numbers live?** Options: (a) a small manually-maintained BigQuery reference table this pipeline reads at query time (someone updates it when targets change), (b) this report only outputs Actual/the department breakdown, and "% of Goal" stays a manual formula in the Google Sheet itself (the Sheet already does this today), (c) something else. Without an answer, "% of Goal" can't be automated — Actual can still be built either way.
2. **What is "Capacity Avg %", exactly?** Is it `Actual ÷ theoretical max throughput`? If so, where does the theoretical max come from per workcenter/department — a rate Plex tracks somewhere, or a number that only exists in this sheet/someone's head? Also worth confirming this metric is actually in active use given only Encap has real values.
3. **Does "WTD (M-T)" mean Monday-through-today, or something else?** Confirms which date range the Actual/WTD build below should use.
4. **Is there a Plex source for "Time (hours)" lost**, or is that hand-logged (e.g. from a paper downtime log)?

## Built 2026-08-26 — the unblocked half

Built `weekly_production_update_report`: department-level Actual WTD/MTD quantity (Encap/Bottling/Labeling/Printing, reusing the confirmed non-rejected-`Part_v_Production` pattern, extended to cover Printing for the first time) plus `pct_of_month_complete` (pure date math). Goal/`% of Goal`/both Capacity Avg columns/the Weekly Loss "Time (hours)" column are deliberately **not** built — see Open Questions above; building a Goal-comparison or Capacity number without knowing where the input lives or what the formula is would be guessing, not a best-criteria decision like the ones made elsewhere in this project.

See `docs/reports/weekly_production_update_report.md` and `reports/sql/weekly_production_update_view.sql`.
