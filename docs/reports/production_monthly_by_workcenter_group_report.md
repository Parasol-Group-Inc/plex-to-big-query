# Vox Scorecard | Production by Work Center Group & Month

> **Status:** ✅ Deployed and verified 2026-09-04 — 3,429 units across 2 groups, August 2026 · **Category:** Production · **Runs:** rides the Work Orders pipeline

## What this tells you

Actual production quantity, scrap quantity and scrap rate for **every work center group, by month** — Encapsulating, Bottling, Labeling, Blending and anything else Vox adds later, all in one place.

Asked for in exactly these terms by Jennilyn Tockstein: *"these are the production by work center group by month."*

## Where it fits

The **Actual** half of the scorecard's Production Actual-vs-Goal tiles. The Goal half comes from the table Jennilyn is building — once it exists, percent-to-goal is a simple division against this.

## How it's built (high level)

Reads `Part_v_Production` (the production log) joined to `Part_v_Workcenter` for the group name, grouped by month and group. Good quantity and scrap are split on the `Rejected` flag.

**Why this exists when the four Daily Reports already do:** `encap_daily_report` and its three siblings are per-*day*, per-*workcenter*, and each hardcodes a single work center group. The scorecard tile is per-*month*, per-*group*, and needs every group in one place to sit against one goal table. Rolling the daily views up in Looker Studio would silently miss any group without its own daily report and would need a new view every time Vox adds a line. This groups itself, so a new work center group appears automatically.

- **Pipeline:** `reports/work_orders.yaml` → `production_monthly_by_workcenter_group_report`
- **SQL:** `reports/sql/production_monthly_by_workcenter_group_view.sql`

## Flags and open questions

- **Bottling 9-parts are not counted (Jennilyn, 2026-10-22).** When Bottling completes a job for a part starting with **9** (the finished-good version), the same output was already counted on the job for its **5** part, so counting both is double credit. Bottling production records for 9-parts are left out, good and scrap alike. **Bottling only:** Labeling's output is all 9-parts and still counts. Live in prod 2026-10-22. October so far it removes **14,210** units from two parts: `93323-10REDRO-0` (Slim Complex FG, 14,055, one record on 10-22), a true double credit of the 14,055 already counted on its 5 part `53323-10REDRO-0` (10-19 to 10-20); and `93336-BKVOXNU-1` (Omega 3 bulk case, 155 cases on 10-21), which has **no 5-part job**. Whether bulk cases should stay dropped is with Jennilyn (`docs/OPEN_ITEMS.md` S18).
- **⚠ Reversed 2026-09-24: scrap is `Rejected != 0`.** The 2026-08-23 change moved the test from `1` to `-1`; the only real rejected record in PlexTest (Bottling Line 1, 500 units, 2026-09-24) has `Rejected = 1`, so scrap read **0** from 2026-08-23 until this fix. `!= 0` counts either value. Found by the scorecard sandbox — see [`docs/SCORECARD_SANDBOX_FINDINGS.md`](../SCORECARD_SANDBOX_FINDINGS.md).
- **Structurally immune to the join bug that bit the Daily Reports.** Those had to reach through `Part_v_Job_Op` to get Job/Part, and that join silently dropped every row whose operation had since closed (fixed 2026-09-01). This view needs no Job, so it doesn't make that join at all. Since 2026-10-22 it reads the part number from the production record's own `Part_Key` (for the 9-part rule), a join that can't drop a row.
- **Boolean convention — corrected 2026-09-24:** `Part_v_Production.Rejected` is **`1`** on a rejected record (the only real one in PlexTest, Bottling Line 1, 500 units). This bullet used to say `-1`, from a `Part_v_*` family "convention" the container flags had already disproved; the view counted no scrap at all. Scrap is now `Rejected != 0`, which holds either way. **Check real rows, never the family** ([`docs/CHEATSHEET.md`](../CHEATSHEET.md), Booleans).
- **Are these the same groups the scorecard means?** The scorecard names Encapsulation, Bottling and Labeling. Plex's group values include `Encapsulating` and others. Worth confirming with Jennilyn that the group names line up with the tiles, since this view no longer hardcodes a mapping.
- **Scrap rate should agree with FPY.** [`quality_fpy_by_area_month_report`](quality_fpy_by_area_month_report.md) is computed on the same table at the same grain — if the two disagree, one has a bug.
- **Limited real data so far** — only Bottling has logged production on this tenant (3,000 units, 2026-08-31).

## More detail

[`meetings-reference/Sep-1/`](../../meetings-reference/Sep-1/) has the full requirements conversation.
