# NetSuite Reports → Plex Module/Category Mapping (First Pass)

Working doc mapping the NetSuite saved-search/report list against the Plex
(vox.test.on.plex.com) module → category taxonomy in
[available-reports.md](available-reports.md) / [enabled-reports.md](enabled-reports.md).

**Method:** name and keyword matching only — no NetSuite report definitions
were inspected, so this is a *conceptual* first pass, not a verified
functional equivalence. Confirmed by direct search: none of these NetSuite
names exist verbatim in the Plex catalog (no "Tax Exemption", "Quarantine",
"Fraud", "Prop 65", "UAT", "Turn Around", or "RUSH" anywhere in the 1,153-row
catalog). A few DO have exact or near-exact name twins in Plex — those are
flagged **High** confidence below and are the best starting points for the
one-by-one pass.

**Confidence key:**
- **High** — exact or near-literal name match exists in Plex
- **Med** — same business concept, clear module/category, no name match
- **Low** — ambiguous, cross-module, or likely no real Plex analog (custom/internal-process items)

| # | NetSuite Report | Plex Module | Plex Category | Nearest Plex Report(s) / Note | Confidence |
|---|---|---|---|---|---|
| 1 | Accounting \| Pending Approval Bills | Accounting / Platform | Accounts Payable | *Documents Pending Approval* (Platform, generic approval queue) | Low |
| 2 | Accounting \| Tax Exemption Expiration 1 month | Accounting | Accounts Receivable | none found | Low |
| 3 | Accounting \| Tax Exemption Expiration 2 months | Accounting | Accounts Receivable | none found | Low |
| 4 | Applying CM to SO Review | Accounting + Sales and CRM | Accounts Receivable (Credit Memos) / Customer Orders and Releases | *Credit Memos*, *Credit Memos by Reason* exist separately; no combined CM-to-SO report | Med |
| 5 | ATL \| RUSH Open SOs w/ Item Promise Dates | Sales and CRM | Customer Orders and Releases | *Open Releases*, *Release Confirmed Ship Date* | Med |
| 6 | Base Formula - Inventory Profitability | Costing | Actual Costing | *Gross Profits* | Med |
| 7 | Base Formula - Inventory Valuation Detail | Costing | Actual Costing / Inventory Valuation - Standard Cost | *Inventory Valuation Actual PiT Cost Type Summary*, *Inventory Valuation by Building* — naming convention matches Plex's own | Med-High |
| 8 | Base Formula - Inventory Valuation Summary | Costing | Actual Costing / Inventory Valuation - Standard Cost | same family as #7 | Med-High |
| 9 | Base Formula - Sales by Item Detail | Sales and CRM | (no exact category) | no "by Item" sales category in Plex | Low-Med |
| 10 | Base Formula - Sales by Item Summary | Sales and CRM | (no exact category) | same as #9 | Low-Med |
| 11 | Capsule/Powder Inventory On Hand + Stock Levels | Inventory | Inventory Tracking | *Inventory Status Summary*, *Inventory by Type*, *On Hand Inventory Valuation* (Costing) | Med |
| 12 | Containers - Purchased Detail | Purchasing / Inventory | Receiving / Container Types | *Containers By Supplier* | Med |
| 13 | Containers - Purchased Summary | Purchasing / Inventory | Receiving / Container Types | same as #12 | Med |
| 14 | Credit Card Approval - Email Schedule | Platform / Communication | Automatic Email Notification | *Auto Emails* (delivery mechanism only; no CC-approval subject match) | Low |
| 15 | Current Inventory Snapshot | Costing | Advanced Standard Costing | **Inventory Snapshots** — exact match | **High** |
| 16 | Custom Purchase Order History with Dates | Purchasing | Purchase Orders | *Purchase Order Details*, *Purchase Order Line Release History* | Med-High |
| 17 | Custom Sales by Customer Summary | Accounting / Sales and CRM | Accounts Receivable / Revenue Reporting | *Customer Revenue by Period*, *Customer Revenue by Account* | Med |
| 18 | Cycle Count Tool - Average Cost | Inventory | Cycle Count | *Cycle Inventory Summary*, *Cycle Count Item Detail* (no cost variant) | Med |
| 19 | Data Migration Tracker (Regular Email Summary) | Management / Platform | Workflow | none — looks like an internal IT/migration tracker, not a business report | Low |
| 20 | Design \| SO's Revenue from Design Department MTD | Sales and CRM | Revenue Reporting | *Revenue by Account*, *Revenue Analysis by Period and State* | Med |
| 21 | ERP \| Revenue | Accounting / Sales and CRM | Revenue Reporting / Financial Statements | too generic to pin to one report | Low |
| 22 | ERP \| SO's Approved YTD | Sales and CRM | Customer Orders and Releases | *Sales Orders*, *Order Summary* | Med |
| 23 | Formula - Inventory Profitability | Costing | Actual Costing | same family as #6 (non-prefixed variant) | Med |
| 24 | Formula - Inventory Valuation Detail | Costing | Actual Costing / Inventory Valuation - Standard Cost | same family as #7 | Med-High |
| 25 | Formula - Inventory Valuation Summary | Costing | Actual Costing / Inventory Valuation - Standard Cost | same family as #7 | Med-High |
| 26 | Formula - Sales by Item Detail | Sales and CRM | (no exact category) | same as #9 | Low-Med |
| 27 | Formula - Sales by Item Summary | Sales and CRM | (no exact category) | same as #9 | Low-Med |
| 28 | High Risk Report [EMAIL] | Accounting | Credit Checking | *Customer Credit Watch* | Med |
| 29 | Inventory Activity Detail Usage Per Month *(listed twice)* | Inventory | Inventory Tracking | **Inventory Activity** — exact base-name match, and already **enabled** in Plex | **High** |
| 30 | Inventory Profitability by Item | Costing | Actual Costing | *Gross Profits*, *Order Profit Analysis* | Med |
| 31 | Inventory Risk Analysis - Custom Formula | Inventory | Inventory Tracking | *Slow Moving Stock*, *Aged Inventory* | Med |
| 32 | Inventory Risk Analysis - Item Stock Type | Inventory | Inventory Tracking | *Inventory by Type*, *Inventory by Part Type Summary* | Med |
| 33 | Inventory Value | Costing | Inventory Valuation - Standard Cost / Actual Costing | *On Hand Inventory Valuation*, *Inventory Valuation by Building* | Med-High |
| 34 | Invoice and Credit Memo Review | Accounting | Accounts Receivable | *Customer Invoices Needing Attention*, *Credit Memos* | Med |
| 35 | Items Pending Fulfillment | Sales and CRM / Shipping | Customer Orders and Releases / Customer Shipping | *Open Releases*, *Shipping Backlog* | Med |
| 36 | NetSuite Alert: Weekly Email of Open UAT Items to Assigned Party | Management / Platform | Workflow | none — IT/QA process tracker, not a manufacturing report | Low |
| 37 | NetSuite Alert: Weekly Email of UAT Items to NetSuite Employees | Management / Platform | Workflow | same as #36 | Low |
| 38 | Open Requisitions [by approver with email] | Purchasing | Requisitions | category exists but only holds *Purchase Expense Summary*; no approver/email routing analog | Med |
| 39 | Operations \| YTD Bottle Production | Production Tracking | Production Tracking | *Production Summary By Part*, *Production History Summaries* | Med-High |
| 40 | Operations \| YTD Labeled Bottles Produced | Production Tracking | Production Tracking | same family as #39 | Med |
| 41 | Packaged Formula - Inventory Profitability | Costing | Actual Costing | same family as #6 | Med |
| 42 | Packaged Formula - Inventory Val Detail | Costing | Actual Costing / Inventory Valuation - Standard Cost | same family as #7 | Med-High |
| 43 | Packaged Formula - Inventory Valuation Summary | Costing | Actual Costing / Inventory Valuation - Standard Cost | same family as #7 | Med-High |
| 44 | Packaged Formula - Sales by Item Detail | Sales and CRM | (no exact category) | same as #9 | Low-Med |
| 45 | Packaged Formula - Sales by Item Summary | Sales and CRM | (no exact category) | same as #9 | Low-Med |
| 46 | Pending Bill Approval - Email Schedule | Accounting / Platform | Accounts Payable / Document Control System | *Documents Pending Approval* (Platform, currently enabled) | Med |
| 47 | Pending CC Charge Approval - Email Schedule | Accounting / Platform | Accounts Payable / Document Control System | same pattern as #46 | Med |
| 48 | Possible Fraud Customer [Email] | Accounting / Security | Credit Checking | *Customer Credit Watch* | Low-Med |
| 49 | Prop 65 Items | Quality / Engineering | Part Specifications / Part List | none — compliance-labeling concept not in Plex catalog | Low |
| 50 | Quality \| Bottling Production Search | Production Tracking | Production Tracking | *Production Summary*, *Production History* (module is Production Tracking despite "Quality \|" prefix) | Med |
| 51 | Quality \| Encapsulation Production Search | Production Tracking | Production Tracking | same as #50 | Med |
| 52 | Quality \| Label Production Search | Production Tracking / Shipping | Production Tracking / Shipping Labels | | Med |
| 53 | Quality \| Labeling Production Search | Production Tracking / Shipping | Production Tracking / Shipping Labels | same as #52 | Med |
| 54 | Revenue | Accounting / Sales and CRM | Revenue Reporting | too generic to pin to one report | Low |
| 55 | Revenue Practice Update | — | — | may not be a report at all (reads like a policy/process update) — flag for clarification | Low |
| 56 | Sales & Quotes Data | Sales and CRM | Sales Quote Management | *Quote History*, *Quote Activity* | Med |
| 57 | Sales \| Prop 65 Monthly Mailings | Sales and CRM / Quality | (no exact category) | none | Low |
| 58 | Sales \| SO's Approved MTD (TEST) | Sales and CRM | Customer Orders and Releases | note "(TEST)" suffix — may be a dev/test artifact, not a production report | Med |
| 59 | Sales \| SO's Revenue from Design Department YTD | Sales and CRM | Revenue Reporting | same family as #20 | Med |
| 60 | Sales \| WO's partially buildable (Labeling) | Scheduling / Engineering | Material Requirements Planning (MRP) / Bill of Materials | *BOM Component Availability*, *MRP Shortages* | Med |
| 61 | Sales \| WOs w/ buildable percentage (released day before) | Scheduling / Engineering | Material Requirements Planning (MRP) / Bill of Materials | same family as #60 | Med |
| 62 | Sales by Item Summary | Sales and CRM | (no exact category) | same as #9 | Low-Med |
| 63 | Sales Order by Sales Rep (SO Status) | Sales and CRM | Customer Master Data Management / Order Entry and Tracking | *Customers By Salesperson* | Med-High |
| 64 | Sales Revenue by Domestic vs. Foreign | Sales and CRM / Accounting | Revenue Reporting | *Revenue Geographics* (AR) | Med |
| 65 | Sample Room Invoices for sales tax-Scheduled | Accounting | Accounts Receivable | none close | Low |
| 66 | Shipping \| Aging Report Email List | Shipping | Customer Shipping | *Shipping Backlog*, *Late Shipments* — or Accounting *Accounts Receivable Aging* if this is really an AR aging report | Med |
| 67 | Shipping \| Revenue Waiting to be Shipped | Shipping | Customer Shipping | *Revenue Forecasts*, *Future Monthly Revenue by Customer* | Med-High |
| 68 | Total Revenue by Finished good (Inventory Revenue Summary) | Costing / Accounting | Actual Costing / Revenue Reporting | | Med |
| 69 | Turn Around Time Report - Last Month | Quality / Production Tracking | Problem Control / Production Tracking | *Average Days to Problem Resolution* | Low-Med |
| 70 | Turn Around Time Report - Rolling | Quality / Production Tracking | Problem Control / Production Tracking | same as #69 | Low-Med |
| 71 | Vox \| A/R Register | Accounting | Accounts Receivable | *Sales Register* — near-literal match | Med-High |
| 72 | Vox \| EPSON Printer WOs (Released) | Production Tracking | Job Tracking System | very Vox/hardware-specific, no Plex analog | Low-Med |
| 73 | Vox \| Inventory Valuation Summary | Costing | Actual Costing / Inventory Valuation - Standard Cost | Plex has several "Inventory Valuation ... Summary" reports — same naming pattern | **High** |
| 74 | Vox \| Inventory Valuation Summary Transaction | Costing | Actual Costing / Inventory Valuation - Standard Cost | same as #73 | **High** |
| 75 | Vox \| Open Purchase Orders | Purchasing | Purchase Orders | **Open Purchase Orders** — exact match | **High** |
| 76 | Vox \| Open Sales Orders | Sales and CRM | Customer Orders and Releases | *Sales Orders*, *Open Releases* — exact/near match | **High** |
| 77 | VOX \| Products to be discontinued *(listed twice, one with trailing period)* | Engineering | Part List | **Part Obsolescence** / *Part Obsolescence - Quick* — exact match | **High** |
| 78 | Vox \| Quarantine Inventory | Inventory / Quality | Inventory Tracking / Problem Control | no "quarantine hold" concept in Plex catalog | Low-Med |
| 79 | Vox \| RUSH Open Sos | Sales and CRM | Customer Orders and Releases | *Open Releases* (no urgency/rush flag concept) | Med |
| 80 | WIP Revenue with Promise Dates | Costing / Inventory | Actual Costing / Inventory Tracking | *Work In Progress Inventory*, *WIP/FG Inventory Transactions* | Med |

## Patterns worth noting for the one-by-one pass

- **Product-line prefixes** ("Base Formula -", "Formula -", "Packaged Formula -") are Vox-specific SKU segmentation, not Plex module names — the 15 reports in these three families collapse into really just 5 underlying report shapes (Inventory Profitability, Inventory Valuation Detail, Inventory Valuation Summary, Sales by Item Detail, Sales by Item Summary) run per product line.
- **"Vox |" and department prefixes** (ATL, Design, ERP, Operations, Quality, Sales, Shipping) look like a naming convention for saved-search folders/dashboards rather than module identifiers — several land in different Plex modules despite sharing a prefix (e.g., "Quality | Bottling Production Search" → Production Tracking, not Quality).
- **Email/alert-schedule reports** (#14, 19, 36, 37, 46, 47, 66) are delivery-mechanism reports, not content reports — their Plex analog (if any) is a subscription/notification feature, not a report category. Worth clarifying whether we're mapping the underlying data or the alerting behavior.
- **6 exact/near-exact name matches** (#15, 29, 73, 74, 75, 76, 77) are the highest-confidence starting points — good candidates to validate first since Plex already has a same-named report.
- **No Plex analog at all**: Tax Exemption Expiration (#2, 3), Prop 65 (#49, 57), Fraud (#48), UAT alerts (#36, 37), Data Migration Tracker (#19), Quarantine (#78) — these look like genuinely NetSuite/business-process-specific reports with nothing structurally similar in the Plex catalog.

## Round 2 — deeper study against the data-sources catalog

`mapping/data-sources.json`/`.csv` (14,350 `CustomerDataSourceManager` stored
procedures — see [docs/PLEX_REPORTS_CATALOG.md](../docs/PLEX_REPORTS_CATALOG.md)
for what this catalog is) became available after the Round 1 pass above,
which only checked report *titles*. Cross-checking the underlying stored-proc
layer either confirms a concept genuinely doesn't exist in Plex, or surfaces
a Plex-native term for the same concept under a different name. Findings:

- **#78 Vox | Quarantine Inventory — revise Low-Med → Med.** No "Quarantine"
  data source exists, but `Lot_Hold_Status_Get` and
  `Lots_On_Hold_Container_Status_Get` (Part / Inventory / Lot Management) do.
  Plex's native term for this concept is **Lot Hold**, not Quarantine — worth
  checking whether a "Lots on Hold" style report/view exists before writing
  this off as no-analog.
- **#9/10/26/27/44/45/62 "Sales by Item" family — confidence unchanged
  (Low-Med), now confirmed rather than assumed.** No stored procedure
  anywhere in the 1,831 Sales-database data sources matches "by item" /
  "item sales". This reinforces that Plex has no packaged concept here — a
  "Sales by Item" report would need to be assembled from
  `Sales_v_PO_Line` + `Part_v_Part`, same as the existing sales orders
  pipeline does today, rather than mapped to an existing report.
- **#2/3 Tax Exemption Expiration, #49/57 Prop 65, #48 Fraud/Risk, #19/36/37
  UAT & migration-tracker items — confidence unchanged (Low), now confirmed
  at the data-source layer too.** No matching stored procedures in
  Accounting, Sales, or Personnel. These remain genuinely NetSuite/
  process-specific with no structural Plex equivalent at either the report
  or stored-procedure layer.
- **#28/48 Credit/Fraud items** — `Customer Credit Watch` is a real,
  *available* Plex report (Accounting), but it is **not currently enabled**
  for this tenant (absent from `enabled-reports.md`). If Vox wants either
  NetSuite report replaced, enabling this UI report is a separate,
  lower-effort ask than building a new BigQuery pipeline for it.

No changes to the confidence ratings of the **High** matches (#15, 29, 73,
74, 75, 76, 77) from this pass — see
[docs/NETSUITE_REPORT_BUILD_PLAN.md](../docs/NETSUITE_REPORT_BUILD_PLAN.md)
for a correction to two of those (73/74) found while scoping the actual
build, and the concrete view-level plan for all seven.
