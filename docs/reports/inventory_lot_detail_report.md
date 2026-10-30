# Vox | Inventory by Lot with Best By

> **Status:** 🛠 In repo 2026-10-30, deploy pending · **Category:** Inventory · **Runs:** rides the Inventory Snapshot pipeline (prod 1 PM / 6 PM / 11 PM probe + 4 AM full, test nightly)

## What this tells you

All stock by **part, lot and container status**, with each lot's **Best By date**, the days left until it, and the stock's value at Go-Live cost. Use it to:

- **Total and drill into a status.** Group by `container_status` to get Lot Hold, Expired, Quarantine and the rest. Filter to one status, then drill to part and lot.
- **Find stock nearing Best By.** Filter `days_to_best_by` to between 0 and X (for example, 90) to list what reaches Best By in the next X days.
- **Find stock past Best By.** `days_to_best_by` below 0. `is_expired_status` tells you whether Plex has already marked those containers Expired.

Asked for by Jennilyn, 2026-10-30.

## Where it fits

It is the drill-down behind [Inventory Value Total](inventory_valuation_total_report.md), using the same stock and the same cost:

- **Valuation total:** summing `inventory_value` where `in_valuation_total` is true gives that report's `total_inventory_value`.
- **Available stock:** summing where `is_available` is true gives its `available_inventory_value`.

It also covers two Quality rows in `reports-list/quality.md`, the Google Sheets "Expired or Expiring Materials" and "Experation Status" (the under-90-days variant).

## How it's built (high level)

Every active container in Plex, grouped by part, lot and container status. Each group gets:
- the lot's Best By date, from Plex's lot shelf-life dates (the date type Plex flags as Best By);
- the part's unit cost from the Go-Live cost model, the model Plex's Inventory Valuation screen uses.

Value is quantity × unit cost.

- **Pipeline:** `reports/inventory_snapshot.yaml` → `inventory_lot_detail_report`
- **SQL:** `reports/sql/inventory_lot_detail_view.sql`

## What a row is

One row per part, per lot, per container status. A lot with some containers OK and some on Lot Hold has **two rows**. To get a lot's full quantity, add its rows up, or filter to the statuses you want first.

Columns:
- **Part:** `part_no`, `revision`, `part_name`, `part_product_type`.
- **Lot and stock:** `lot_no`, `container_status`, `container_count`, `quantity`.
- **Value:** `unit_cost`, `inventory_value`.
- **Best By:** `best_by_date`, `days_to_best_by`, `best_by_is_placeholder`.
- **Flags:** `is_expired_status`, `is_available`, `in_valuation_total`.
- **Keys:** `part_key`, `lot_key`.

PlexProd, 29 Oct load:

| Check | Value |
|---|---|
| Rows | 5,030 |
| Value, valuation scope | $15,180,711.53 (matches the total report) |
| Value, available stock | $11,900,013.15 |
| Value, Expired status | $1,035,247.19 |
| Rows reaching Best By within 90 days | 125 |
| Rows past Best By but not marked Expired | 25 |

## Flags and open questions

- **"Expired" is Plex's container status, not a date rule.** Plex marks containers Expired itself. On 29 Oct, 25 part/lot/status rows were already past their Best By date but not yet marked Expired. They are worth a look, and `days_to_best_by < 0` finds them.
- **Best By is Plex's lot date.** Plex keeps four shelf-life dates per lot: Best By, Use By, Sell By and Retest. This report uses the one Plex flags as Best By. Every lot in stock had one on 29 Oct.
- **Year-2300 dates mean "does not expire."** Plex uses a far-future date for those. `best_by_is_placeholder` marks them (2 rows on 29 Oct), and a "within X days" filter leaves them out anyway.
- **Containers with no lot have no Best By.** About 2,000 of 62,700 active containers have no lot.
- **Parts with no Go-Live cost show $0 value**, as in Plex. Their quantity is still correct.
- **Receiving is listed but not valued in the total.** `in_valuation_total` is false on Receiving rows, matching the total report.

## More detail

[`inventory_valuation_total_report.md`](inventory_valuation_total_report.md), [`inventory_valuation_summary_report.md`](inventory_valuation_summary_report.md), and [`part_shelf_life_report.md`](part_shelf_life_report.md) for how shelf life is set up per part.
