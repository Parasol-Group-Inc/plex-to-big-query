# Customer List by Sales Rep

> **Status:** ✅ Deployed 2026-08-21, decided best-criteria · **Category:** Sales · **Runs:** rides the Sales Orders pipeline, 7:00 PM / 7:10 PM Mountain (prod/test)

## What this tells you

One row per sales-rep-and-customer pair — which customers each sales rep covers. This is the Plex-native answer to NetSuite's "Customer List by Sales Rep" saved search, so Sales can see rep coverage without checking NetSuite.

## Where it fits

Built as part of the 2026-08-14 sweep to find Plex equivalents for every NetSuite-sourced row in [`reports-list/sales.md`](../../reports-list/sales.md) (row: "Customer List by Sales Rep"). The confirmation history for the underlying decision is in [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../../docs/NETSUITE_REPORT_BUILD_PLAN.md) and [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../../docs/NETSUITE_PARITY_OPEN_ITEMS.md).

## How it's built (high level)

Plex has no standing "this customer's assigned rep" field anywhere on the customer record — rep assignment only exists at the order level (who was assigned to a given sales order). So this report builds the customer list a different way: it looks at every order a rep has ever been assigned to, and lists that order's customer as one this rep "covers." If a rep worked at least one order for a customer, that customer shows up under that rep.

- **Pipeline:** `reports/sales_orders.yaml` → `sales_customers_by_rep_report`
- **SQL:** `reports/sql/sales_customers_by_rep_view.sql`

## Flags and open questions

- **This is a best-criteria proxy, not NetSuite-confirmed.** Because Plex has no standing customer→rep assignment record, "which customers does this rep cover" is derived from order history instead — nobody has verified this matches how NetSuite (or Vox's own definition) actually assigns customers to reps. A data-scientist review should confirm whether per-order rep history is an acceptable stand-in, or whether a different source should be used (a customer "region/type" record exists in Plex with its own salesperson field, but it hasn't been confirmed as live/populated data).
- **A customer can appear under more than one rep.** If different orders for the same customer were placed under different reps (e.g. a rep change, or a fill-in), that customer shows up once per rep it's been assigned to — this list does not pick one "current" rep per customer.
- **Report is untested against real production order volume.** It was confirmed to deploy and query correctly, but has only been checked against the small number of live orders on the test tenant so far.

## More detail

[`reports-list/sales.md`](../../reports-list/sales.md) and [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../../docs/NETSUITE_REPORT_BUILD_PLAN.md) have the full live-confirmation history behind this decision, including the alternate customer→rep source that was considered and not yet confirmed.
