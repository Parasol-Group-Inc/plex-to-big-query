# Turnaround standards — the one Quality table nothing here creates

> **Status:** ✅ Table created in **both** `PlexTest` and `PlexProd` 2026-09-22 · **empty in production — waiting on the real figures** · **Category:** Quality · **Maintained by:** Jennilyn, by hand, directly in BigQuery

## What it is

The Performance and Bonus day counts a nonconformance is supposed to be closed
within, one row per stock type. [Turn Around Time](quality_turnaround_time_report.md)
reads it to say whether each record met its standard — without it, that report
can only tell you how long something took, never whether that was good.

## Why it is a table you edit rather than a form

It was going to be a tab on the manual-data web app. Jennilyn asked to drop it
on 2026-09-21: *"I don't think we need it… they don't change those standards
very much."* A form earns its keep on numbers that change often enough that
chasing someone to edit a table is worse than building one. These change about
never — and they are bonus-bearing, so the fewer people who can reach them the
better.

So it is an ordinary BigQuery table, edited in the console by the person who
owns the numbers. Same shape as `scorecard_goals`, and for the same reason.

## ⚠ It must exist, or the report fails to create

Exactly like `scorecard_goals` and the three vs-goal views: a **missing** table
fails view creation outright, and it fails looking like a broken report rather
than a missing dependency. An **empty** table is completely fine — every
standard column reads NULL and `standard_source` says `none set`.

Do not drop it. If it is ever lost, recreate it with the DDL below before the
next pipeline run.

## Rebuild DDL

```sql
CREATE TABLE IF NOT EXISTS `voxdatalake.PlexProd.turnaround_standards` (
  stock_type       STRING,     -- Plex Part_Type, exact string. Blank or 'ALL' = catch-all
  effective_month  DATE,       -- always the 1st; newest row on or before the NC's month wins
  performance_days INT64,
  bonus_days       INT64,
  note             STRING,
  updated_by       STRING,
  updated_at       TIMESTAMP
);
```

Same statement for `PlexTest`. Column descriptions are set on the live tables —
`bq show --schema voxdatalake.PlexProd.turnaround_standards` prints them.

## How to add or change a standard

**Add a row; never edit history.** The report picks the newest row effective on
or before the month each problem happened, so a standard that starts in
December is correctly not applied to a September problem. Editing an old row
silently rewrites the past.

```sql
INSERT INTO `voxdatalake.PlexProd.turnaround_standards`
  (stock_type, effective_month, performance_days, bonus_days, note, updated_by, updated_at)
VALUES
  ('Finished Goods', DATE '2026-10-01', 21, 10, 'Agreed with Quality', 'jennilyn', CURRENT_TIMESTAMP()),
  ('',               DATE '2026-10-01', 30, 15, 'Catch-all',           'jennilyn', CURRENT_TIMESTAMP());
```

### The two things to get right

**`stock_type` is an exact string match** against Plex's `Part_Type`. The valid
values, read from production: `Components`, `Raw Materials`,
`Semi-Finished Goods`, `Finished Goods`, `WIP`, `Supply`, `Inspection`. A typo
produces **no error** — just a standard that silently never applies, the same
failure mode as a goal whose scope says "Encapsulation" where Plex says
"Encapsulating". `standard_source` on the report is there to catch it.

**Always keep one catch-all row** (blank `stock_type`, or `ALL`). More than half
of real nonconformance records have no part attached at all, and therefore no
stock type — 12 of 22 on the test tenant. Without a catch-all those records get
no standard whatsoever.

## ⚠ One assumption, not yet confirmed

The Monthly TAT Analysis sheet keys its standards by **"Item Stock Type"**.
This table assumes that means Plex's **`Part_Type`** — the closest thing on the
part master, since there is no column called `Stock_Type`. Nobody has checked
that against the sheet. If it turns out to mean something else, only the join
column in the report's SQL and the values in this table change; the shape
doesn't.

## Test data

`PlexTest` holds **three placeholder rows** seeded on 2026-09-22 to prove the
wiring — a catch-all at 30/15, `Finished Goods` at 21/10 and `Raw Materials` at
7/3. Every one says PLACEHOLDER in its note. **They are not Vox's standards and
should be deleted** when the real figures arrive. `PlexProd` was deliberately
left empty.

## Who may edit it

Open. These are bonus-bearing numbers, and the "who can change this" question
raised on 2026-09-11 was originally about exactly them. Moving them out of the
web app narrowed that question rather than answering it: BigQuery table
permissions are now what controls this, and nobody has said who should hold
them.
