# Open Quotes

> **Status:** ✅ Built, deployed, and verified 2026-08-23 · **Category:** Sales · **Runs:** own Cloud Run job, 10:00 PM / 10:10 PM Mountain (prod/test)

## What this tells you

One row per open sales quote — quote number, title, the date it was created, its due date, current status, and which customer it's for. This is the Plex-native replacement for the NetSuite "Open Quotes" saved search, so Sales can see which quotes are still active without logging into NetSuite.

## Where it fits

Fulfills NetSuite's **"Sales | Open Quotes"** saved search, tracked as the "Open Quotes" row in [`reports-list/sales.md`](../../reports-list/sales.md). Full research and decision history is in [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../../docs/NETSUITE_REPORT_BUILD_PLAN.md) and [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../../docs/NETSUITE_PARITY_OPEN_ITEMS.md).

## How it's built (high level)

Pulls every quote from Plex, attaches its status name and the customer's name, and keeps only the quotes considered "open." A quote counts as open if it's still New, in Estimating, or Quoted — once it's Approved, Won, Lost, Cancelled, or marked No Quote, it drops off this list.

- **Pipeline:** `reports/sales_quotes.yaml` -> `sales_quotes_open_report`
- **SQL:** `reports/sql/sales_quotes_open_view.sql`

## Flags and open questions

- **The first real run failed to build the view.** `raw_Sales_v_Quote` had 0 rows, so BigQuery auto-typed it all-`STRING`, while `raw_Sales_v_Quote_Status` and `raw_Common_v_Customer` both have real data and are properly typed (`INT64`); joining without a cast fails outright. Fixed same day with `SAFE_CAST` on both sides of every join and the status-exclusion filter. Re-verified by directly querying the view (a Cloud Run job can exit successfully even when the view itself failed to build — the note below about a "clean" test run predates this fix).
- **"Open" is a workaround, not a direct match.** Plex's quote status table has a literal Open_Quote yes/no flag that looked like the obvious answer, but when checked against the live system it turned out to be "No" on every single status Vox uses — it can't tell open from closed at all. This report instead defines "open" as "not yet Won, Lost, Cancelled, or No Quote," the same approach used elsewhere in this pipeline for other "open" reports.
- **Whether Approved quotes count as open is a judgment call, not a confirmed NetSuite match.** The decision (made 2026-08-21) is that an Approved quote is closed — the customer has already decided and it's on its way to becoming an order, not still awaiting action. If Vox's team actually still tracks Approved quotes as open and needing follow-up, this should be revisited.
- **Untested against real quotes.** There were zero quote records on the test system at the time this was built, so the logic above is confirmed against Plex's schema and status list, but not yet checked against an actual live quote. The view now builds and queries cleanly (see the SAFE_CAST fix above), but the test tenant still has no quote records to verify row-level correctness against.

## More detail

[`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../../docs/NETSUITE_REPORT_BUILD_PLAN.md) and [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../../docs/NETSUITE_PARITY_OPEN_ITEMS.md) have the full research trail, including how the dead Open_Quote flag was discovered and the reasoning behind the Approved-is-closed decision.
