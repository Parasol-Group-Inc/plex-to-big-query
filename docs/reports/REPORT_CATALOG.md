# Report Catalog

Business-facing documentation for every deployed report in this pipeline — one file per `bq_view`. These are written for the team (product/ops/leadership on ClickUp), not engineers: the code already has comments, and the full technical trail (column-by-column mappings, live-data confirmations, decision history) lives in [`reports-list/`](../../reports-list/), [`spreadsheets/`](../../spreadsheets/), and `docs/*_BUILD_PLAN.md`. A doc here answers "what does this report do for the business, and what should I know before trusting it" — not "how does the SQL work."

**Convention: keep these in sync with the code.** Any change to a report's YAML/SQL gets a matching update to its doc here, in the same commit — same discipline as `CHANGELOG.md`.

## Template for a new report doc

```markdown
# {Display Name}

> **Status:** {✅ Built and verified / 🔬 Built, awaiting real-data confirmation / etc.} · **Category:** {Sales/Production/Supply Chain/Quality/Inventory} · **Runs:** {schedule}

## What this tells you

{2-4 plain-language sentences — what business question this answers, who'd look at it}

## Where it fits

{Which reports-list/<dept>.md row or spreadsheets/<name>.md this fulfills — "replaces the manual X sheet," "NetSuite parity for Y saved search," etc.}

## How it's built (high level)

{1 short paragraph, no SQL — what Plex data it pulls and roughly how it's combined/filtered/aggregated, in plain language}

- **Pipeline:** `reports/{yaml}.yaml` → `{bq_view_name}`
- **SQL:** `reports/sql/{file}.sql`

## Flags and open questions

{Bullet list — best-criteria decisions, 0-row caveats, unconfirmed leads, anything a non-engineer reader should be skeptical of. "None known" if genuinely none.}

## More detail

{Link to the full technical doc(s) for anyone who wants the complete history}
```

## Catalog

| Report | Category | Status | Doc |
|---|---|---|---|
| Sales Orders | Sales | ✅ Built | [sales_orders_report.md](sales_orders_report.md) |
| Open Sales Orders | Sales | ✅ Built | [sales_orders_open_report.md](sales_orders_open_report.md) |
| Pending Approval Orders | Sales | ✅ Built | [sales_orders_pending_approval_report.md](sales_orders_pending_approval_report.md) |
| Orders Pending Approval by Sales Rep | Sales | ✅ Built | [sales_orders_pending_approval_by_rep_report.md](sales_orders_pending_approval_by_rep_report.md) |
| Orders Pending Approval by Accounting | Sales | ✅ Built | [sales_orders_pending_accounting_approval_report.md](sales_orders_pending_accounting_approval_report.md) |
| Orders Past 14 Days Old | Sales | ✅ Built | [sales_orders_aging_report.md](sales_orders_aging_report.md) |
| Orders Over $10k | Sales | ✅ Built | [sales_orders_over_10k_report.md](sales_orders_over_10k_report.md) |
| Orders Over 10k Bottles | Sales | ✅ Built | [sales_orders_over_10k_bottles_report.md](sales_orders_over_10k_bottles_report.md) |
| Customer List by Sales Rep | Sales | ✅ Built | [sales_customers_by_rep_report.md](sales_customers_by_rep_report.md) |
| Revenue per Sales Rep | Sales | ✅ Built | [sales_revenue_by_rep_report.md](sales_revenue_by_rep_report.md) |
| RUSH Open Sales Orders | Sales | ✅ Built | [sales_orders_rush_open_report.md](sales_orders_rush_open_report.md) |
| Sales Order Allocation | Sales | ✅ Built | [sales_order_allocation_report.md](sales_order_allocation_report.md) |
| Open Quotes | Sales | ✅ Built | [sales_quotes_open_report.md](sales_quotes_open_report.md) |
| Open RMAs | Sales | ✅ Built | [sales_returns_open_report.md](sales_returns_open_report.md) |
| Work Orders | Production | ✅ Built | [work_orders_report.md](work_orders_report.md) |
| MFG Job Schedule | Production | ✅ Built | [mfg_job_schedule_report.md](mfg_job_schedule_report.md) |
| Labeling \| Open WO: Results | Production | ✅ Built | [labeling_open_work_orders_report.md](labeling_open_work_orders_report.md) |
| Printing Open Work Orders | Production | ✅ Built | [printing_open_work_orders_report.md](printing_open_work_orders_report.md) |
| Encap Daily Report | Production | ✅ Built | [encap_daily_report.md](encap_daily_report.md) |
| Blending Daily Report | Production | ✅ Built | [blending_daily_report.md](blending_daily_report.md) |
| Labeling Daily Report | Production | ✅ Built | [labeling_daily_report.md](labeling_daily_report.md) |
| Packaging Daily Report | Production | ✅ Built | [packaging_daily_report.md](packaging_daily_report.md) |
| Bottling Job Schedule | Production | ✅ Built | [bottling_job_schedule_report.md](bottling_job_schedule_report.md) |
| Purchasing Open Orders | Supply Chain | ✅ Built | [purchasing_open_orders_report.md](purchasing_open_orders_report.md) |
| Purchase Orders to Approve | Supply Chain | ✅ Built | [purchasing_po_pending_approval_report.md](purchasing_po_pending_approval_report.md) |
| Purchasing Pending Requisitions | Supply Chain | ✅ Built | [purchasing_pending_requisitions_report.md](purchasing_pending_requisitions_report.md) |
| Part Obsolescence | Supply Chain | ✅ Built | [part_obsolescence_report.md](part_obsolescence_report.md) |
| Inventory Activity | Inventory | ✅ Built | [inventory_activity_report.md](inventory_activity_report.md) |
| Inventory Snapshot | Inventory | ✅ Built | [inventory_snapshot_report.md](inventory_snapshot_report.md) |
| Inventory Valuation Summary | Inventory | ✅ Built | [inventory_valuation_summary_report.md](inventory_valuation_summary_report.md) |
| Part On-Hand Inventory | Inventory | ✅ Built | [part_on_hand_inventory_report.md](part_on_hand_inventory_report.md) |
| Inventory Risk Analysis | Inventory | ✅ Built | [inventory_risk_analysis_report.md](inventory_risk_analysis_report.md) |
| Quality Nonconformance | Quality | ✅ Built | [quality_nonconformance_report.md](quality_nonconformance_report.md) |
| Quality Turnaround Time | Quality | ✅ Built | [quality_turnaround_time_report.md](quality_turnaround_time_report.md) |
| Quality Deviation | Quality | ✅ Built | [quality_deviation_report.md](quality_deviation_report.md) |
| Quality Supplier Returns Pending | Quality | ✅ Built | [quality_supplier_returns_pending_report.md](quality_supplier_returns_pending_report.md) |

36 reports total. Two written so far as a format check (`bottling_job_schedule_report.md`, `purchasing_pending_requisitions_report.md`) — the rest follow once the format's confirmed.
