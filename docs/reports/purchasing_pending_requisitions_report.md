# Purchasing Pending Requisitions

> **Status:** ✅ Built and deployed 2026-08-22, business rule confirmed but not yet checked against a real requisition · **Category:** Supply Chain · **Runs:** own daily job, 9:40 PM / 9:50 PM Mountain (prod/test)

## What this tells you

Which material requisitions are approved and ready to become a purchase order, but haven't been turned into one yet — the "what should Purchasing be buying right now" list. Marked Critical priority (daily use) by whoever requested it.

## Where it fits

Plex-native replacement for the NetSuite saved search **"Purchasing | Pending Order Requisitions"** — see [`reports-list/supply-chain.md`](../../reports-list/supply-chain.md) and [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md).

## How it's built (high level)

Plex doesn't have a requisition status literally called "Pending Order," so this report defines it as: the requisition has been approved AND is allowed to become a purchase order, AND no purchase order has been created from it yet. That business rule was confirmed directly with whoever requested the report, not guessed.

- **Pipeline:** `reports/purchasing_pending_requisitions.yaml` → `purchasing_pending_requisitions_report`
- **SQL:** `reports/sql/purchasing_pending_requisitions_view.sql`

## Flags and open questions

- **Not yet checked against a real requisition.** The test environment has zero real requisitions on it, so while the report's logic and the business rule are both confirmed correct in principle, nobody has been able to look at one real row and check it's showing the right thing. Worth a spot-check once real requisitions exist, either in production or on a test environment that has some.

## More detail

[`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md) (§ Purchasing | Pending Order Requisitions) has the full confirmation log and business-rule reasoning.
