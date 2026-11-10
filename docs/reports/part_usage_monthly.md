# Part usage by month (`PlexProd.part_usage_monthly`)

> **Status:** ✅ Live 2026-11-10. October 2026 backfilled (partial: 13 of 31 days, from go-live). Each later month is recorded on the 1st of the next month, 06:30 MT, by the scheduled query `part_usage_monthly`. · **Category:** Supply Chain · **Asked for by:** Jennilyn (2026-11-10)

**What it answers:** how much of each part did production use in a month, and what was the daily average? A table of usage by item by month, for purchasing and production planning reports.

## How usage is measured

The same way the Approaching MSL report measures Plex usage: every production record (rejected ones excluded) times the quantity of each component on that part's bill of materials. So a part gets a row when production **consumed** it as a component: raw materials, capsules, blends, bottles, labels and so on. Making a part is not using it, so finished goods get no row unless they are themselves a component of something else.

Checked on 2026-11-10: summed over the same days, this table equals the MSL report's Plex usage on all 506 parts.

## Columns

| Column | Meaning |
|---|---|
| `usage_month` | first day of the month |
| `part_no`, `part_key`, `revision`, `part_name` | the part (its stocked key) |
| `part_product_type`, `part_type`, `part_group` | Plex's classification |
| `unit` | the stocked unit (blank in Plex for most raw materials, which are kilos) |
| `qty_used` | quantity consumed in the month |
| `days_with_usage` | production days that consumed it |
| `days_in_month` | calendar days in the month |
| `days_covered` | days of the month Plex has history for (October 2026: 13, from 10-19) |
| `is_partial_month` | true when `days_covered` < `days_in_month` |
| `avg_daily_usage` | `qty_used / days_covered`; for a full month that is per calendar day |
| `source_tables_loaded_at` | when the ETL last refreshed the production, BOM and part tables it read |
| `recorded_at` | when the row was written |

## Things to know

- **The production day is the Mountain record date.** Plex stamps a day's production at 22:00 the evening before; this table corrects for that, so production on the 1st counts in its own month.
- **The bill of materials is read when the month is recorded**, not as it was during the month. A BOM changed later does not rewrite history; re-running a month (SQL below) would.
- **Usage outside recorded production is not counted** (material issued by hand, scrap).
- **If Plex's database feed was behind on the 1st**, the month is short: check `source_tables_loaded_at`, then re-run that month.

## Re-running or backfilling a month

`terraform/part_usage_monthly.sql` with the first line changed to that month, e.g. `DECLARE target_month DATE DEFAULT DATE '2026-10-01';`. It deletes the month's rows and writes them again.

```sql
SELECT usage_month, part_no, part_name, qty_used, days_covered, avg_daily_usage
FROM `voxdatalake.PlexProd.part_usage_monthly`
ORDER BY usage_month DESC, qty_used DESC;
```

Backed up weekly with the other BigQuery-only tables (`terraform/backup_snapshots.sql`).
