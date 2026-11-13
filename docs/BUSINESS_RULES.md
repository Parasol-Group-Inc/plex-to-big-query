# Business rules

*Generated from `docs/hub/business_rules.json` by `python scripts/hub/rules_tab.py --md`. Do not edit by hand.* Collected 2026-11-13; 92 rules. The hub's Business rules tab shows the same rules with live numbers.

## Revenue and shipping

### REV-01 Revenue is what shipped: quantity x price

- **Rule:** Revenue is the quantity on each shipment line that has status Shipped, times the price on that shipment line. Sales orders and invoices are not the measure. Shipments not yet invoiced still count, and a partial shipment counts only the part that left.
- **Why:** Orders can be closed short or shipped in parts, and invoicing lags behind shipping, so the units that went out the door are the most reliable measure.
- **Decided:** Jennilyn, 2026-11-13 · D32 (closed) · status: in force
- **In her words:** "Our revenue should be based on shipment quantity and shipment value. Invoicing may lag behind. (11-13; first said 2026-09-01: "the shipping revenue should just be the units that went out the door, the summed value of the units that went out the door")"
- **Reports:** `shipping_revenue_report`, `sales_revenue_summary_report`, `sales_revenue_run_rate_report`, `revenue_vs_goal_report`, `shipping_daily_report`
- **Enforced in:** `reports/sql/shipping_revenue_report.sql` lines 153-154, `reports/sql/shipping_revenue_report.sql` lines 198, `reports/sql/sales_revenue_summary_view.sql` lines 38-47
- **Measured:** 1,271,123: Shipped revenue this month to date, dollars (quantity x shipment-line price) (2026-11-13 10:36 MT). Revenue is what shipped: $1,271,123 so far this month on 245 shipment lines, $1,157,799 in October from 10-19, $2.43M in all.

### REV-02 A revenue month is the ship month, not the invoice month

- **Rule:** Each shipment is counted in the month it shipped. The invoice date is shown on the detail rows for information only and does not move revenue between months. October is closed and was not restated.
- **Why:** Revenue is reported by shipment. An invoice linked a few days later (or dated in the previous month) must not change a month already reported.
- **Decided:** Jennilyn, 2026-11-13 · D40 (closed) · status: in force
- **In her words:** "We cannot change any financials for Oct because the reporting is done. In general, we report revenue based on shipments, not the invoices."
- **Reports:** `shipping_revenue_report`, `sales_revenue_summary_report`, `sales_revenue_run_rate_report`, `revenue_vs_goal_report`
- **Enforced in:** `reports/sql/sales_revenue_summary_view.sql` lines 39, `reports/sql/shipping_revenue_report.sql` lines 134-143
- **Measured:** 0: Shipment lines invoiced in a different month than they shipped (revenue stays in the ship month) (2026-11-13 10:36 MT). All 423 shipment lines were invoiced in their ship month, so this rule moves $0 today; it protects month-end shipments invoiced after midnight.

### REV-03 Revenue uses the shipment price, not the invoiced amount

- **Rule:** The price is the price on the shipment line. If the invoiced amount differs (for example SH00105, shipment price 2.53 invoiced at 1.265), revenue still follows the shipment line. A separate shipment-price override field is shown but not used.
- **Why:** Jennilyn decided shipment value is the measure; the invoiced amount is a different number that lags.
- **Decided:** Jennilyn, 2026-11-13 · D32 (closed) · status: in force
- **Reports:** `shipping_revenue_report`
- **Enforced in:** `reports/sql/shipping_revenue_report.sql` lines 150-154
- **Measured:** 2,088: Dollar gap between shipment-line revenue and what the invoice accounting (4xxxx accounts) booked, all months (2026-11-13 10:36 MT). Shipment-line revenue is $2,428,922 versus $2,426,834 booked on the 4xxxx invoice accounts, a $2,088 gap (0.09%).
- **Finding:** shipment_price_override (Shipment_Price) is 0 on all 423 lines, so the override path the rule describes (e.g. SH00105) does not show in the report; revenue always equals qty x price.

### REV-04 Revenue by part group uses Plex's part group

- **Rule:** Revenue is split by the part's Plex Part Group (Capsule, Softgel, Label and so on). A part with no group is shown as '(no group)'. Sum all groups for the company total.
- **Why:** Jennilyn wanted each group's percent of revenue. The lookup used before 2026-09-24 was empty and put everything in one bar.
- **Decided:** Jennilyn, 2026-09-01 · status: in force
- **In her words:** "it actually would be pretty nice to have by part group so that I can tell them their percent of revenue by part group."
- **Reports:** `shipping_revenue_report`, `sales_revenue_summary_report`
- **Enforced in:** `reports/sql/shipping_revenue_report.sql` lines 191-196, `reports/sql/sales_revenue_summary_view.sql` lines 40
- **Measured:** 0: Revenue shipped with no Plex part group this month (shown as '(no group)'), dollars (2026-11-13 10:36 MT). Every line has a part group: $0 sits under '(no group)'; Capsule $1.08M, Softgel $144K, Powder $24K, Tablet $14.5K, Liquid $4K, Go-Live Temp $2K, Label $660.

### REV-05 Run rate and % into month use calendar days

- **Rule:** The month-end projection is revenue so far divided by days elapsed, times days in the month. Days are calendar days, not working days. A finished month shows 100% and the projection equals the actual.
- **Why:** Mirrors the old scorecard's own field. A month that starts with a long weekend projects low.
- **Reports:** `sales_revenue_run_rate_report`
- **Enforced in:** `reports/sql/sales_revenue_run_rate_view.sql` lines 23-29, `reports/sql/sales_revenue_run_rate_view.sql` lines 93
- **Measured:** 2,933,360: Month-end revenue projection for the current month (calendar-day run rate), dollars (2026-11-13 10:36 MT). Day 13 of 30 (43.3% in) with $1,271,123 gives a month-end projection of $2,933,360; October, a finished month, shows 100%.

### REV-06 Daily shipping: cartons are containers, 'orders shipped' counts shipments

- **Rule:** For each ship date the report counts packages as the containers on shipped lines, units as shipped quantity, and 'orders shipped' as the number of distinct shipments (not sales orders). Only shipments with status Shipped count.
- **Why:** Jennilyn asked for cartons shipped and orders shipped per day. Plex ties containers to shipment lines, and one sales order can ship on several shipments.
- **Decided:** Jennilyn, 2026-09-01 · status: in force
- **In her words:** "you should be able to pull the number of packages shipped, and then a count of the orders that shipped."
- **Reports:** `shipping_daily_report`
- **Enforced in:** `reports/sql/shipping_daily_report_view.sql` lines 41, `reports/sql/shipping_daily_report_view.sql` lines 54-59
- **Measured:** 249: Shipments counted as 'orders shipped' in the last 30 days (distinct shipments, not sales orders) (2026-11-13 10:36 MT). 249 shipments went out in the last 30 days (packages 9,269) while only 202 distinct sales orders shipped, so 'orders shipped' is shipments, not orders.

### REV-07 Ready to ship: value of the ready quantity only, with a price fallback

- **Rule:** 'Total in Shipping' is the value of units already on a shipment that has not shipped and is not cancelled (Open or Pending). Only the ready quantity counts, never the whole order. Price comes from the shipment line, else the sales order line, else the customer price list, and the row says which was used.
- **Why:** Plex does not finalize the shipment price until the shipment goes out, so without a fallback ready goods read $0.
- **Decided:** Jennilyn, 2026-09-01 · status: in force
- **In her words:** "they might have 10,000 units ordered, but 5,000 units are ready, and we'd only want the value of the 5,000 units that are ready to ship, not the 10,000 total... anything that's open or pending is what we'd want to sum."
- **Reports:** `shipping_pending_revenue_report`
- **Enforced in:** `reports/sql/shipping_pending_revenue_view.sql` lines 105-121, `reports/sql/shipping_pending_revenue_view.sql` lines 161-162
- **Measured:** 26,899: Value of units ready on shipments not yet shipped (Total in Shipping), dollars (2026-11-13 10:36 MT). $26,899 is ready but not shipped, on 4 Open shipper lines, all priced from the order line.

### REV-08 Revenue goal tile: company-wide only and currently a placeholder

- **Rule:** Revenue percent-to-goal compares shipped revenue with the company-wide (blank scope) revenue goal. The revenue goal now in the system is a copy of the company sales goal, labelled as a placeholder, until a real revenue target is entered.
- **Why:** No separate revenue target has been given. Revenue (shipments) and Sales (approved orders) are different numbers, so using one goal for both is an assumption.
- **Decided:** 2026-10-02 · S3 · status: open decision
- **Reports:** `revenue_vs_goal_report`
- **Enforced in:** `reports/sql/revenue_vs_goal_view.sql` lines 63-72
- **Measured:** 25.40: Revenue goal for the current month and percent reached (company-wide placeholder) (2026-11-13 10:36 MT). November revenue is 25.4% of a $5,000,000 goal that is a placeholder copy of the company sales goal.

### REV-09 Revenue is comparable only from November 2026

- **Rule:** October revenue covers only 10-19 to 10-31 (Plex shipments start 10-19) against a full-month goal. November is the first clean month. Plex-only revenue has no history before go-live.
- **Why:** Vox went live on Plex in October; before that shipments were in NetSuite.
- **Decided:** Emilio, 2026-11-04 · S18 · status: open decision
- **Reports:** `shipping_revenue_report`, `sales_revenue_summary_report`, `revenue_vs_goal_report`
- **Enforced in:** `reports/sql/shipping_revenue_report.sql` lines 65
- **Measured:** 1,157,799: Revenue in October (only 10-19 to 10-31) versus November so far, dollars; first shipment date (2026-11-13 10:36 MT). October holds only 10-19 to 10-31 ($1,157,799, 531,795 units) against a full-month goal; November's $1.27M is already ahead on dollars.

## Sales

### SALES-01 Sales = first time an order reaches Pending Fulfillment

- **Rule:** A sale is counted in the month its order first moved into Pending Fulfillment, dated by that status change (not by order date). If it later moves on to another status, or comes back to Pending Fulfillment, it is still counted once, in the first month. Sales and Revenue are deliberately different numbers.
- **Why:** Jennilyn defines Sales MTD as orders that became firm in the month; Revenue is what shipped.
- **Decided:** Jennilyn, 2026-09-04 · status: in force
- **In her words:** "anything that moved into pending fulfillment status during that month is our sales month to date... it's the date of that status change, not the date of the order or anything else."
- **Reports:** `sales_mtd_by_status_change_report`, `sales_mtd_summary_report`, `sales_vs_goal_report`
- **Enforced in:** `reports/sql/sales_mtd_by_status_change_view.sql` lines 87-100, `reports/sql/sales_mtd_by_status_change_view.sql` lines 231-232
- **Measured:** 1,838,222: Sales booked this month to date (first Pending Fulfillment), dollars (2026-11-13 10:36 MT). Sales booked in November so far are $1,838,222 on 140 orders; October reads $7,598,739.

### SALES-02 October 2026 sales are distorted by the Plex go-live load

- **Rule:** On 2026-10-16 the go-live load gave 232 open orders their first Pending Fulfillment, so October Sales shows about $5.4M booked on that one day (about 70% of October). October is not comparable to other months; November is the first clean month. Jennilyn's own scorecard views avoid this by taking history before 2026-11-01 from a static sheet and Plex only from 2026-11-01.
- **Why:** Those orders were entered earlier (in NetSuite or before the load) but Plex stamped their status change on load day.
- **Decided:** Emilio, 2026-11-04 · S18 · status: open decision
- **Reports:** `sales_mtd_by_status_change_report`, `sales_mtd_summary_report`, `sales_vs_goal_report`, `VoxScorecardsLive.vw_sales`
- **Enforced in:** `reports/sql/sales_mtd_by_status_change_view.sql` lines 277, `custom_views/VoxScorecardsLive/vw_sales.sql` lines 1-17
- **Measured:** 5,406,071: Sales booked on 2026-10-16 alone (the go-live load), dollars (2026-11-13 10:36 MT). The 10-16 go-live load booked $5,406,071 on 232 orders in a single day, 71.1% of October's $7.6M.

### SALES-03 Order value = line price x release quantity, no tax or freight

- **Rule:** Dollar values on sales reports are price x quantity per release, using the price agreed on the order line first, then the customer price list. Tax and freight are not included. An order line with no price is valued as blank/0, so that order is understated.
- **Why:** Jennilyn: the line item price is always there; the customer price list is empty in production.
- **Decided:** Jennilyn, 2026-09-04 · S15 FF3 · status: in force
- **In her words:** "No, it'll always have a price in there. So it needs to be the line item price."
- **Reports:** `sales_mtd_by_status_change_report`, `sales_order_value_by_status_report`, `pipeline_plex_value_report`, `sales_orders_report`, `sales_orders_over_10k_report`, `sales_revenue_by_rep_report`, `sales_orders_open_report`
- **Enforced in:** `reports/sql/sales_mtd_by_status_change_view.sql` lines 146-165, `reports/sql/sales_mtd_by_status_change_view.sql` lines 222-225
- **Measured:** 0: Sales lines this month with no price at all (worth $0 in sales value) (2026-11-13 10:36 MT). 0 lines this month have no price (1 of 1,219 across all months), and none needed the price-list fallback.

### SALES-04 Sales rep: order, then customer, then order salesperson

- **Rule:** A sale's rep is the order's Inside Salesperson; if blank, the customer's Assigned To (account owner); if blank, the first row of Order Salesperson. If none, it reads '(no rep assigned)' (or 'Unassigned' in revenue-by-rep). A second rep and commission % exist only from Order Salesperson and are usually blank.
- **Why:** Vox records its rep in the BDM fields on the order and customer, not in Order Salesperson (almost unused in Plex). Before 2026-09-24 every sale read '(no rep assigned)'.
- **Decided:** 2026-09-24 · D24 item 4 · status: in force
- **Reports:** `sales_mtd_by_status_change_report`, `sales_mtd_summary_report`, `sales_vs_goal_report`, `sales_revenue_by_rep_report`, `sales_orders_report`, `pipeline_plex_value_report`
- **Enforced in:** `reports/sql/sales_mtd_by_status_change_view.sql` lines 204-213, `reports/sql/sales_revenue_by_rep_view.sql` lines 94-98, `reports/sql/sales_mtd_summary_view.sql` lines 43
- **Measured:** 103: Sales order lines (all months) with no rep found at all (2026-11-13 10:36 MT). 103 of 1,219 sales lines have no rep; 1,081 take their rep from Order Salesperson and only 35 from the order's Inside Salesperson.
- **Finding:** The order's Inside Salesperson is the first-priority rep but is set on only 35 of 1,219 lines; 1,081 (89%) come from the Order Salesperson fallback, which the older notes called nearly unused.

### SALES-05 WIP is Pending Fulfillment plus Hold, unshipped balance only

- **Rule:** Work in progress is the value of order lines in Pending Fulfillment or Hold, minus what has already shipped. Pending Sales Approval and Deposit Review are not orders yet and are excluded. The gate is Plex's Include in MRP flag on the status.
- **Why:** A held order is still owed to a customer; a not-yet-approved order is not an order. The old filter overstated WIP 2.4x ($43,723 vs $17,950).
- **Decided:** Jennilyn, 2026-09-09 · status: in force
- **In her words:** "really, it should just be pending fulfillment. I guess hold as well would be WIP because it was sold but it hasn't shipped yet. So it just be those two statuses. / we don't want to count pending sales approval because that's not considered an order yet."
- **Reports:** `sales_order_value_by_status_report`
- **Enforced in:** `reports/sql/sales_order_value_by_status_view.sql` lines 225-226
- **Measured:** 6,809,066: Work in progress (Pending Fulfillment + Hold, unshipped balance), dollars (2026-11-13 10:36 MT). WIP is $6,809,066 on 352 Pending Fulfillment orders; there are no orders on Hold today.

### SALES-06 Open orders exclude Closed, Cancelled and quote-stage orders

- **Rule:** An 'open' sales order is anything not Closed and not Cancelled, and not in a quote status. Quote-stage orders are not open orders. Other order reports use looser definitions: aging and rush exclude only Closed and Cancelled (rush also excludes Pending Sales Approval); orders over $10k and over 10k units take every status.
- **Why:** Jennilyn: a quote is not an order. The other reports were built as best-criteria copies of NetSuite searches and not revisited.
- **Decided:** Jennilyn, 2026-10-19 · status: partly built
- **Reports:** `sales_orders_open_report`, `sales_orders_aging_report`, `sales_orders_rush_open_report`, `sales_orders_over_10k_report`, `sales_orders_over_10k_bottles_report`
- **Enforced in:** `reports/sql/sales_orders_open_view.sql` lines 216-217, `reports/sql/sales_orders_aging_view.sql` lines 161-162, `reports/sql/sales_orders_rush_open_view.sql` lines 182-183, `reports/sql/sales_orders_over_10k_view.sql` lines 109, `reports/sql/sales_orders_over_10k_bottles_view.sql` lines 63
- **Measured:** 24: Quote-stage orders that show on the Orders Aging list although they are not open orders, and the size of the two lists (2026-11-13 10:36 MT). The aging list (321 orders, only those 14+ days old) holds 24 quote-stage orders that the open-orders list (423 orders) excludes.
- **Finding:** The aging report also has an age filter the rule does not mention (orders 14+ days old only), so it lists 321 orders against 423 on the open list even though it is described as the looser definition.

### SALES-07 Deposit Review is the accounting stage

- **Rule:** 'Orders pending accounting approval' lists orders in either Deposit Review status (Initiate Payment Request 2587, Bypass Payment Request 2656), matched by name not number. The order path is Quote, Pending Sales Approval, Deposit Review, Pending Fulfillment, then shipped and Closed.
- **Why:** Vox cut the order status list from 10 to 7 on 2026-09-09 and deleted Pending Payment Review; the old filter returned 0 rows and read as 'nothing pending'. Deposit Review is the money gate.
- **Decided:** Jennilyn, 2026-09-11 · status: in force
- **Reports:** `sales_orders_pending_accounting_approval_report`
- **Enforced in:** `reports/sql/sales_orders_pending_accounting_approval_view.sql` lines 183
- **Measured:** 47: Orders waiting in the two Deposit Review statuses (accounting approval), and dollars (2026-11-13 10:36 MT). 47 orders wait in Deposit Review ($348,869): 45 in Initiate Payment Request ($348,869) and 2 in Bypass Payment Request ($0).
- **Finding:** The 2 Bypass Payment Request orders carry $0 value (no price), so the accounting list undercounts dollars.

### SALES-08 Total pipeline (Plex half) counts quotes and not-yet-approved orders, including Deposit Review

- **Rule:** The Plex part of Total Pipeline is the value of orders in a quote status, Pending Sales Approval, or either Deposit Review status, excluding cancelled. It is only half the tile: Monday.com opportunities and forecast are added elsewhere. By contrast the 'Pending Approval Orders' report lists only Pending Sales Approval (2585), not Deposit Review.
- **Why:** Deposit Review orders have not been approved yet. Plex has no pre-quote deals; those stay in Monday.
- **Decided:** Jennilyn, 2026-10-30 · status: in force
- **In her words:** "orders in Deposit Review haven't been approved yet, so they belong in the Pending Approval pipeline number."
- **Reports:** `pipeline_plex_value_report`, `sales_orders_pending_approval_report`, `sales_orders_pending_approval_by_rep_report`
- **Enforced in:** `reports/sql/pipeline_plex_value_view.sql` lines 199-203, `reports/sql/sales_orders_pending_approval_view.sql` lines 170
- **Measured:** 1,553,940: Plex part of Total Pipeline, dollars; detail shows how the stages split (2026-11-13 10:36 MT). The Plex pipeline is $1,553,940: quotes $932,210 plus $621,730 of not-yet-approved orders, of which only $272,861 (21 orders) is Pending Sales Approval and $348,869 is Deposit Review.
- **Finding:** pipeline_plex_value_report labels every Deposit Review order as stage 'Pending Sales Approval' (68 orders, $621,730, of which 47 orders are Deposit Review), so its stage split cannot separate them; it also omits one Pending Sales Approval order (287, no price) that the Pending Approval Orders report lists (22 vs 21).

### SALES-09 Open quotes: only New, Estimating and Quoted

- **Rule:** An open quote is one not yet Won, Lost, Approved, Cancelled or No Quote. Approved is treated as no longer awaiting action.
- **Why:** Best-criteria choice made when no NetSuite definition was available; the Open Quote flag in Plex is 0 on every status.
- **Decided:** 2026-08-21 · status: in force
- **Reports:** `sales_quotes_open_report`
- **Enforced in:** `reports/sql/sales_quotes_open_view.sql` lines 70
- **Measured:** 0: Open quotes (New, Estimating, Quoted) in Plex's quote module (2026-11-13 10:36 MT). Plex's quote module has 0 open quotes; the 41 quote-stage sales orders ($932K) are a different thing and are counted in the pipeline.
- **Finding:** sales_quotes_open_report is empty (Plex's quote module is unused) while 41 quote-stage sales orders exist; open quotes in this report and quote-stage orders are different populations.

### SALES-10 Open returns (RMAs): not Closed or Cancelled

- **Rule:** An open return is any return that is not Closed or Cancelled, so New, Received, Pending Approval, Rejected, Released and Under Review all count as open.
- **Why:** Same status-exclusion approach as open orders; Plex's own flag columns are all zero.
- **Decided:** 2026-08-14 · status: in force
- **Reports:** `sales_returns_open_report`
- **Enforced in:** `reports/sql/sales_returns_open_view.sql` lines 57
- **Measured:** 4: Open returns (RMAs) (2026-11-13 10:36 MT). 4 returns are open, all in status New.

### SALES-11 Customers per rep come from order history, not an account owner

- **Rule:** The 'customers by sales rep' list pairs a rep with a customer when the rep is on at least one of that customer's orders (Order Salesperson). A customer can appear under several reps. It does not use the Inside Salesperson / Assigned To resolution that Sales reports use.
- **Why:** Plex has no single standing account-rep field the report could use; best-criteria proxy.
- **Reports:** `sales_customers_by_rep_report`
- **Enforced in:** `reports/sql/sales_customers_by_rep_view.sql` lines 29-43
- **Measured:** 292: Rows on the customers-by-rep list, versus customers that actually have sales (2026-11-13 10:36 MT). 292 customer-rep pairs for 279 customers; 3 customers appear under several reps. Customers get a different rep than the sales reports use (see spot check).

### SALES-12 Year-to-date Sales/Revenue is short by pre-go-live history

- **Rule:** Plex YTD covers only months Plex has. Earlier months are meant to be added as a static top-up number kept in an editable table, not hardcoded in SQL. Today Jennilyn's own view takes Sales history before 2026-11-01 from a static sheet.
- **Why:** Plex only has data from go-live.
- **Decided:** Jennilyn, 2026-09-04 · status: partly built
- **In her words:** "We'll just pull over whatever we get in Plex and then add a static number to it on the date of transfer, and then let it just keep adding from there..."
- **Reports:** `sales_mtd_summary_report`, `sales_revenue_summary_report`, `VoxScorecardsLive.vw_sales`
- **Enforced in:** `reports/sql/sales_mtd_summary_view.sql` lines 20-35, `custom_views/VoxScorecardsLive/vw_sales.sql` lines 4-17
- **Measured:** 41,327,528: Sales in Jennilyn's scorecard view dated before 2026-11-01 (static history), dollars; Plex-fed part from November (2026-11-13 10:36 MT). Jennilyn's view carries $41.3M of pre-November sales as static history (October $3.80M versus $7.60M from Plex), and Plex feeds November's $1.84M.

## Production

### PROD-01 What counts as production

- **Rule:** Production is the records in Plex's production log (Part_v_Production). Each record is credited to its own work centre and to the day it was recorded (Mountain time). Reports read it through the view part_production_current, which is the raw table, plus Plex screen records only while the screens switch is on (production has no such switch row, so it reads ODBC).
- **Why:** The log is the same one Plex's Job Production screen shows. Going through the job operation lost records whose operation had closed.
- **Reports:** `encap_daily_report`, `blending_daily_report`, `labeling_daily_report`, `packaging_daily_report`, `weekly_production_update_report`, `production_monthly_by_workcenter_group_report`, `quality_fpy_by_area_month_report`, `production_vs_goal_report`
- **Enforced in:** `reports/sql/production_monthly_by_workcenter_group_view.sql` lines 87-104,147-159, `reports/sql/weekly_production_update_view.sql` lines 103-115,146-158, `reports/sql/packaging_daily_report_view.sql` lines 71-85,150, `reports/sql/part_production_current_view.sql` lines 1-60
- **Measured:** 9,950: Production records credited in the month to date (all groups), by the rule's own date and work centre (2026-11-13 10:36 MT). Counting by the record's own work centre and Mountain day gives 9,950 records this month; Labeling alone is 324,206 units and Printing 12,761, which the old job-operation route lost.

### PROD-02 Good output versus scrap

- **Rule:** A production record with Rejected = 0 is good output (actual quantity). Any record with Rejected not 0 is scrap. Scrap is never added to good output. Scrap rate and first pass yield are scrap (or good) divided by everything run, good plus bad.
- **Why:** Plex marks a rejected record as 1, not -1. The old test for -1 counted no scrap at all from 2026-08-23 until it was fixed on 2026-09-24.
- **Decided:** 2026-09-24 · status: in force
- **Reports:** `encap_daily_report`, `blending_daily_report`, `labeling_daily_report`, `packaging_daily_report`, `production_monthly_by_workcenter_group_report`, `quality_fpy_by_area_month_report`, `weekly_production_update_report`, `approaching_msl_report`
- **Enforced in:** `reports/sql/packaging_daily_report_view.sql` lines 111-117, `reports/sql/production_monthly_by_workcenter_group_view.sql` lines 125-138, `reports/sql/quality_fpy_by_area_month_view.sql` lines 66-72,89-92, `reports/sql/weekly_production_update_view.sql` lines 139-140, `reports/sql/approaching_msl_view.sql` lines 131
- **Measured:** 2,896,677: Rejected (scrap) units in the last 90 days that the rule keeps out of good output (2026-11-13 10:36 MT). Scrap stays out of good output: without this rule Encapsulating would read 2,745,294 and Printing 151,383 units higher over the last 90 days (2.9M units in all).
- **Finding:** Printing scrap is large and daily: 292 rejected Printing records this month totalling 151,383 units versus 12,761 good (FPY 7.77%); worth confirming that Rejected is used for real scrap at Printing.

### PROD-03 Bottling 9-parts with an active 5-part BOM are not counted (5/9 rule)

- **Rule:** A Bottling record for a 9-part (finished good, part number starting 9) is dropped while that part still has an active BOM line to a 5-part, because the same output was already counted on the 5-part job. Before 2026-11-01 every Bottling 9-part record is dropped, good and scrap alike. From November only 9-parts that still have a 5-part BOM line are dropped; 9-parts whose 5-part BOM is gone count.
- **Why:** Counting both the 5-part (bottled bulk) and the 9-part (finished good) is double credit for one run of bottles.
- **Decided:** Jennilyn, 2026-11-13 · D27 · status: in force
- **In her words:** "if we can drop those it'd be great. There are only 5 active parts currently in the system that we are still using with this 5/9 double count setup. We are still phasing these out."
- **Reports:** `packaging_daily_report`, `production_monthly_by_workcenter_group_report`, `weekly_production_update_report`, `production_vs_goal_report`
- **Enforced in:** `reports/sql/packaging_daily_report_view.sql` lines 87-96,150-153, `reports/sql/production_monthly_by_workcenter_group_view.sql` lines 106-115,160-163, `reports/sql/weekly_production_update_view.sql` lines 117-126,158-162,176-185
- **Measured:** 11,500: Bottling units on 9-parts with an active 5-part BOM that the 5/9 rule drops, month to date (raw tables, repo logic) (2026-11-13 10:36 MT). Repo logic drops 11,500 Bottling units this month: Bottling reads 690,761 with the rule, 702,261 without it. The live view (13:00 run pending) still counts them.

### PROD-04 Bulk cases (9xxxx-BK) are always counted

- **Rule:** Bottling records for bulk case parts (part number like 93336-BKVOXNU-1, pattern 9, four digits, -BK) are exempt from the 5/9 rule and always count as production.
- **Why:** Bulk cases have no 5-part job, so there is nothing counted twice.
- **Decided:** Jennilyn, 2026-10-22 · status: in force
- **Reports:** `packaging_daily_report`, `production_monthly_by_workcenter_group_report`, `weekly_production_update_report`
- **Enforced in:** `reports/sql/packaging_daily_report_view.sql` lines 119-123,151-152, `reports/sql/production_monthly_by_workcenter_group_view.sql` lines 143-145,162, `reports/sql/weekly_production_update_view.sql` lines 142-143,161
- **Measured:** 76: Bottling units on bulk-case (9xxxx-BK) parts that always count, month to date (2026-11-13 10:36 MT). Bulk cases always count: 76 Bottling records on 21 bulk-case parts stay in Bottling output, and none sits on a part with a 5-part BOM.

### PROD-05 The 5/9 rule applies to Bottling only; Labeling output counts in full

- **Rule:** Only the Bottling work centre group is checked for 9-parts. Labeling output is all 9-parts and is always counted.
- **Why:** A label step makes the finished good once; there is no earlier 5-part run for it.
- **Decided:** Jennilyn, 2026-10-22 · status: in force
- **Reports:** `packaging_daily_report`, `production_monthly_by_workcenter_group_report`, `weekly_production_update_report`
- **Enforced in:** `reports/sql/packaging_daily_report_view.sql` lines 150, `reports/sql/production_monthly_by_workcenter_group_view.sql` lines 160, `reports/sql/weekly_production_update_view.sql` lines 159
- **Measured:** 324,206: Labeling units counted in full, month to date (2026-11-13 10:36 MT). Labeling is never checked: every one of its 324,206 units this month is on a 9-part that has a 5-part BOM, so applying the Bottling rule to Labeling would erase all of it.

### PROD-06 The 5/9 rule reads today's BOM, so past months can move

- **Rule:** Whether a 9-part is dropped depends on the BOM as it is now, not as it was on the production date. When Jennilyn removes a part's 5-part BOM, its earlier records (from 2026-11-01) start counting again. To keep past months fixed the dropped part list would have to be pinned.
- **Why:** The rule has no history of BOM changes to look at.
- **Decided:** not recorded · D27 · status: open decision
- **Reports:** `packaging_daily_report`, `production_monthly_by_workcenter_group_report`, `weekly_production_update_report`, `production_vs_goal_report`
- **Enforced in:** `reports/sql/packaging_daily_report_view.sql` lines 87-96, `reports/sql/production_monthly_by_workcenter_group_view.sql` lines 106-115
- **Measured:** 3: 9-parts that still have an active 5-part BOM (and Bottling output on them since 2026-11-01) (2026-11-13 10:36 MT). Only 3 9-parts still have an active 5-part BOM (11,500 Bottling units this month). Each BOM Jennilyn removes moves that part's past output from dropped back to counted.

### PROD-07 Work centre groups behind each production report

- **Rule:** Encap daily = group Encapsulating (the ten Encapsulation lines plus Schedule Encapsulation). Packaging daily = group Bottling (Plex has no Packaging group). Labeling daily = group Labeling (Labeling 1-6 plus First 48). Blending daily = groups Blending plus Pre-Weigh together. Weekly Production Update = Encap, Bottling, Labeling, Printing. The monthly report has no list: every group Plex has appears automatically.
- **Why:** Names follow the confirmed Plex work centre groups; the sheets' own names (Packaging, Encapsulation) do not match Plex.
- **Decided:** 2026-08-21 · status: in force
- **Reports:** `encap_daily_report`, `packaging_daily_report`, `labeling_daily_report`, `blending_daily_report`, `weekly_production_update_report`, `production_monthly_by_workcenter_group_report`
- **Enforced in:** `reports/sql/encap_daily_report_view.sql` lines 130, `reports/sql/packaging_daily_report_view.sql` lines 150, `reports/sql/labeling_daily_report_view.sql` lines 94, `reports/sql/blending_daily_report_view.sql` lines 87, `reports/sql/weekly_production_update_view.sql` lines 129-135,158,168-170
- **Measured:** 6: Work centre groups with production this month, and their good units (2026-11-13 10:36 MT). Six groups produced this month; the daily reports cover Encapsulating, Bottling, Labeling and Blending, the monthly and goal reports cover all six.

### PROD-08 Week-to-date and month-to-date windows

- **Rule:** Week to date runs from Monday of the current week through today, not Monday to Thursday. Month to date runs from the 1st through today. Both use Mountain time. Percent of month complete is today's day number divided by days in the month.
- **Why:** The sheet's label says (M-T); it was read as standard week-to-date.
- **Decided:** Emilio, 2026-08-26 · status: in force
- **Reports:** `weekly_production_update_report`
- **Enforced in:** `reports/sql/weekly_production_update_view.sql` lines 91-100,177-190
- **Measured:** 15,896,617: Week-to-date (Monday to today) good units across Encap, Bottling, Labeling and Printing, computed from raw tables with the repo logic; detail compares month-to-date with the live weekly view (2026-11-13 10:36 MT). Week to date (Monday 11-09 to today) is 15.9M good units across Encap, Bottling, Labeling and Printing; month to date uses the 1st to today and the month is 43.3% complete. The live weekly view still shows old month-to-date figures for Labeling and Printing.

### PROD-09 First pass yield and DPMO

- **Rule:** First pass yield per work centre group and month is good quantity divided by total quantity run. DPMO is rejected quantity over total quantity times one million, assuming 1 defect opportunity per unit. Sigma level is deliberately not computed.
- **Why:** Quality has not given a real opportunities-per-unit figure; the constant 1 is a placeholder so the tile is not blank.
- **Decided:** 2026-09-01 · S9 · status: partly built
- **Reports:** `quality_fpy_by_area_month_report`
- **Enforced in:** `reports/sql/quality_fpy_by_area_month_view.sql` lines 66-72,89-95
- **Measured:** 100: Bottling first pass yield this month (percent), live FPY view (2026-11-13 10:36 MT). FPY is good units over everything run: Bottling, Encapsulating, Labeling, Blending and Pre-Weigh read 100%, Printing reads 7.77% (151,383 rejected of 164,144 run), a DPMO of 922,257.
- **Finding:** FPY has no 5/9 rule: Bottling FPY total_qty (October 854,846; November 702,261) includes 9-part records the production reports drop (October 323,904 units, 38% of the total; November 11,500).

### PROD-10 Downtime hours versus productive hours on work orders

- **Rule:** On the work orders report, logged hours with no work centre event are productive hours; logged hours with an event (conveyor problem, no raw material, injury and so on) are downtime hours. Planned hours are job quantity divided by the routing rate.
- **Why:** All Plex work centre events are problem events.
- **Decided:** 2026-07-13 · status: in force
- **Reports:** `work_orders_report`
- **Enforced in:** `reports/sql/work_orders_view.sql` lines 33-48,66-88
- **Measured:** 1.60: Downtime hours as a share of logged hours on work orders, operations started in the last 30 days (percent) (2026-11-13 10:36 MT). Of 12,372 logged hours on operations started in the last 30 days, 203 hours (1.6%) carry a work centre event and count as downtime rather than productive time.

## Inventory

### INV-01 What counts as on-hand stock (available stock)

- **Rule:** On-hand stock is quantity in active containers whose status is OK, Hold, Inspection Required or Hold for Design Order. Defective, Expired, Allocated, Shipped, Staged, Lot Hold, Quarantine, Rework and Receiving stock is not on hand.
- **Why:** OK_Status in Plex cannot express this list: it is 0 on Hold and Inspection Required, which Vox counts, and 1 on Shipped, which Vox does not.
- **Decided:** Jennilyn, 2026-09-04 · status: in force
- **Reports:** `part_on_hand_inventory_report`, `inventory_available_to_sell_report`, `inventory_out_of_stock_report`, `approaching_msl_report`, `inventory_top_quantity_report`, `inventory_risk_analysis_report`, `mfg_job_schedule_inventory_availability_report`
- **Enforced in:** `reports/sql/part_on_hand_inventory_view.sql` lines 83-86, `reports/sql/inventory_risk_analysis_view.sql` lines 83-86, `reports/sql/inventory_lot_detail_view.sql` lines 108-109
- **Measured:** 13,187: Containers on hand sitting in statuses the available-stock rule excludes (Defective, Quarantine, Lot Hold and so on) (2026-11-13 10:36 MT). 13,187 containers sit in statuses that are not on hand (Lot Hold 5,459, Expired 2,409, Quarantine 2,313, Allocated 1,742, Defective 743); only 51,603 containers count as available.
- **Finding:** Containers in status RELEASED (484) and LOADED (5) are also treated as not available, but the rule text does not list them.

### INV-02 Demand is open orders in Pending Fulfillment and Hold only

- **Rule:** Order demand for a part is the quantity still to ship (release quantity minus shipped, never below zero) on sales orders whose status Plex flags Include In MRP. Today that is exactly Pending Fulfillment and Hold. Quotes, Pending Sales Approval, Deposit Review, Closed and Cancelled create no demand. Hold counts because it is sold but not shipped.
- **Why:** Jennilyn changed Plex's own flag so unapproved orders stop showing as demand; the report follows Plex rather than a status list in our SQL.
- **Decided:** Jennilyn, 2026-09-09 · status: in force
- **In her words:** "I did change it in Plex because I saw that it was showing demand for deposit review and pending sales approval. We don't count those as demand until they're pending fulfillment."
- **Reports:** `inventory_available_to_sell_report`, `inventory_out_of_stock_report`, `approaching_msl_report`
- **Enforced in:** `reports/sql/inventory_available_to_sell_view.sql` lines 167-196
- **Measured:** 0: Units of order demand coming only from orders on Hold (Include In MRP, still counted) (2026-11-13 10:36 MT). Orders on Hold would be counted as demand, but there are none on Hold today, so all 3.26M units of order demand (499 parts) come from Pending Fulfillment.

### INV-03 Quantity available = on hand minus demand (it can go negative)

- **Rule:** Quantity available is on-hand stock (plus stock on the part's unit-conversion keys, converted) minus the part's own order demand minus its netted component demand. It goes negative on purpose when open orders will consume more than is in stock. Purchase orders on the way and open jobs are not added.
- **Why:** This is the number sales and purchasing use to see out-of-stock, matching Plex's Sales Order Line Inventory Check.
- **Decided:** Jennilyn, 2026-09-09 · status: in force
- **In her words:** "inventory would be quantity on hand. Required is going to be our sold and inventory minus required should be the quantity available."
- **Reports:** `inventory_available_to_sell_report`, `inventory_out_of_stock_report`, `approaching_msl_report`
- **Enforced in:** `reports/sql/inventory_available_to_sell_view.sql` lines 587-591
- **Measured:** 774: Parts whose quantity available after all demand is below zero (2026-11-13 10:36 MT). 774 of 3,020 parts are below zero after demand (345 even on orders alone): availability goes negative on purpose to show the shortfall.

### INV-04 Component demand is netted down the BOM one level at a time

- **Rule:** A part's demand from its parents is not the full sales order exploded to every component. Demand passes down the bill of materials one level at a time, and at each level the part's own stock is used first; only the shortfall goes on to the next level. Example: 50,000 bottles ordered, 40,944 in stock, so 9,056 pass down.
- **Why:** The old flat explosion ignored finished goods already on the shelf and double counted demand for bottles and capsules (capsule 33312-00NUT46-0 read 12.05M instead of 2,182,496).
- **Decided:** Jennilyn, 2026-10-30 · status: in force
- **In her words:** "go down one BOM at a time and only bring over demand for things not stocked"
- **Reports:** `inventory_available_to_sell_report`, `approaching_msl_report`, `inventory_out_of_stock_report`
- **Enforced in:** `reports/sql/inventory_available_to_sell_view.sql` lines 303-350,517-526
- **Measured:** 838: Parts whose netted component demand is lower than the old flat explosion (2026-11-13 10:36 MT). Netting lowers component demand on 838 parts; flat demand would total 329.8M units versus 221.6M netted. Worst case 10001-01VOXNU-1: 50.4M flat vs 7.3M netted.

### INV-05 Both gross and netted demand are published

- **Rule:** Netted demand drives availability, reorder point and out of stock. The old full-explosion figure stays beside it as gross demand so people can see total demand on a component and that demand reduced by stock above it. Do not remove either.
- **Why:** Jennilyn finds the gross figure useful on its own.
- **Decided:** Jennilyn, 2026-10-30 · status: in force
- **In her words:** "I've never been able to see total demand for any component + that demand reduced by bottled inventory"
- **Reports:** `inventory_available_to_sell_report`, `approaching_msl_report`
- **Enforced in:** `reports/sql/inventory_available_to_sell_view.sql` lines 600-608, `reports/sql/approaching_msl_view.sql` lines 249-250,364-366
- **Measured:** 674: MSL rows where gross demand is higher than netted demand (both published) (2026-11-13 10:36 MT). Gross is higher than netted on 674 of 1,694 MSL rows, so both numbers matter; the biggest gap is 10001-01VOXNU-1 (50.4M gross vs 7.3M netted).

### INV-06 What netting does not do (open jobs, due dates, depth)

- **Rule:** Netting counts sales orders only. Open jobs are neither supply nor demand: a job already making a bottle does not reduce the bottle's shortfall, and job material needs are not counted. Stock nets all open demand at once, not earliest-due first. Netting is built for BOM depth 6; a deeper part keeps its gross figure and is flagged.
- **Why:** Counting jobs could double count, since a job is made from an order. Time-phased netting needs due-date demand that is not built.
- **Decided:** 2026-10-30 · D26 · status: partly built
- **Reports:** `inventory_available_to_sell_report`, `approaching_msl_report`
- **Enforced in:** `reports/sql/inventory_available_to_sell_view.sql` lines 488-526,608
- **Measured:** 0: Parts whose BOM is deeper than the 6 netting levels (0 means netting is complete) (2026-11-13 10:36 MT). No part is deeper than the 6 netting stages (0 flagged); the deepest low-level code is 6 and 391 parts sit at levels 5-6, so a net_7 stage is not needed yet.

### INV-07 One part number with several Plex keys counts once (wrapper keys)

- **Rule:** Plex can hold up to four part keys for one part number. Extra keys (wrappers) exist to use the part in another unit. Demand is taken on the stocked key only; stock on a wrapper is converted by its BOM factor and added to the stocked key. Reports roll up per part number.
- **Why:** Counting every key doubled demand (39 parts wrongly at reorder point) and mixed units such as grams and kilos.
- **Decided:** 2026-10-28 · status: in force
- **Reports:** `inventory_available_to_sell_report`, `approaching_msl_report`, `mfg_job_schedule_inventory_availability_report`, `part_usage_monthly`
- **Enforced in:** `reports/sql/inventory_available_to_sell_view.sql` lines 143-158,218-238,257-264, `reports/sql/approaching_msl_view.sql` lines 107-120,233-264
- **Measured:** 45: Parts counted through a unit-wrapper key, and units of wrapper stock converted (2026-11-13 10:36 MT). 45 parts have stock on a wrapper key that is converted and counted once, adding 4,356 units that would otherwise be missed or double counted.

### INV-08 Out of stock definition (part number starts with 33, has a reorder point, and available is negative)

- **Rule:** A part is out of stock when its part number starts with 33, its Plex reorder point (minimum inventory quantity) is above 0, and quantity available is below 0. Parts whose product type starts with Custom are excluded because custom parts are expected to run negative while being made. A reorder point of exactly 0 means not assigned.
- **Why:** Jennilyn: 33 parts are the stocked blends; part type is not reliable enough to define the scope.
- **Decided:** Jennilyn, 2026-09-01 · status: in force
- **In her words:** "for us to be out of stock, it has to start with 33 for the part number, and it has to have a minimum stock level... if the inventory amount is negative, or we have zero inventory and we have demand... sometimes we make custom parts, those are okay to be negative"
- **Reports:** `inventory_out_of_stock_report`
- **Enforced in:** `reports/sql/inventory_out_of_stock_view.sql` lines 95-98
- **Measured:** 21: Parts out of stock right now (33-prefix, reorder point above 0, available below 0) (2026-11-13 10:36 MT). 21 parts are out of stock today; 15 more 33-parts have negative availability but no reorder point, so the rule does not flag them.

### INV-09 Approaching MSL: when a part is at its reorder point

- **Rule:** The reorder point is Plex's minimum inventory quantity only. A part is at reorder point when quantity available (after open-order demand) is at or below its reorder point. A part with no reorder point is flagged only when quantity available is negative. The report lists a part when it has a reorder point or measured usage.
- **Why:** Jennilyn: reorder point from Plex only; at reorder point means after open-order demand; no capsules-only default (her dashboard splits by part type).
- **Decided:** Jennilyn, 2026-10-28 · D21 · status: in force
- **Reports:** `approaching_msl_report`
- **Enforced in:** `reports/sql/approaching_msl_view.sql` lines 326-327,368
- **Measured:** 819: Parts at their reorder point today (2026-11-13 10:36 MT). 819 of 1,694 parts are at or below their reorder point; 408 parts have no reorder point and can never be flagged.

### INV-10 MSL average daily usage: NetSuite is held until Plex has 6 months of history

- **Rule:** Plex usage is the quantity production consumed through the BOM (rejected production left out), averaged over the last 183 days (at least 90) or since Plex's first production if shorter. Plex usage is trusted only once it rests on at least 183 days; until then NetSuite's average from the manual-data app is used if there is one. At about 2027-04-18 Plex takes over.
- **Why:** Plex production history only starts 2026-10-18, so early averages rest on a few days.
- **Decided:** Jennilyn, 2026-11-10 · D21 · status: in force
- **Reports:** `approaching_msl_report`, `mfg_job_schedule_inventory_availability_report`
- **Enforced in:** `reports/sql/approaching_msl_view.sql` lines 59-67,144-177,303-316
- **Measured:** 829: Parts whose usage figure comes from NetSuite because Plex history is under 6 months (2026-11-13 10:36 MT). 829 parts use NetSuite usage because Plex has only 25 of the 183 days needed; 306 use short Plex history and 559 have no usage figure.

### INV-11 MSL data flags: usage disagreement and stale NetSuite figures

- **Rule:** Each MSL row carries a data flag when availability is negative, usage comes from NetSuite or short Plex history, trusted Plex usage and NetSuite usage differ by more than 25 percent, NetSuite figures are older than 45 days, or an on-order PO line is only partly received.
- **Why:** So a number that rests on weak input announces itself.
- **Decided:** 2026-10-26 · status: in force
- **Reports:** `approaching_msl_report`
- **Enforced in:** `reports/sql/approaching_msl_view.sql` lines 72-82,341-357
- **Measured:** 1,146: MSL rows carrying a data flag (2026-11-13 10:36 MT). 1,146 of 1,694 MSL rows carry a flag; 196 are negative availability and most of the rest are the NetSuite/short-history notice. No usage disagreement is flagged yet because Plex has no trusted usage.

### INV-12 On order counts open PO releases; partial releases count in full

- **Rule:** On-order quantity is the sum of purchase order release quantities where the PO is not cancelled or received and the release is not marked Received. A Partial release counts in full because Plex records no received quantity per release; such rows are flagged. Open jobs on a part are those not completed, cancelled or on hold.
- **Why:** Plex has no received quantity per release.
- **Decided:** 2026-10-28 · D22 · status: in force
- **Reports:** `approaching_msl_report`, `purchasing_open_orders_report`, `mfg_job_schedule_inventory_availability_report`
- **Enforced in:** `reports/sql/approaching_msl_view.sql` lines 183-212, `reports/sql/purchasing_open_orders_view.sql` lines 100-102
- **Measured:** 111,206,294: Units on order across open PO releases (partial releases counted in full) (2026-11-13 10:36 MT). 111.2M units are on order across 120 parts; 15 parts include a partly received PO line counted in full.

### INV-13 Monthly part usage (what production consumed)

- **Rule:** Usage per part per month is quantity consumed as a BOM component by recorded production, rejected output excluded, inactive BOM lines and wrapper lines skipped. A finished good appears only if it is itself a component of something produced. The production day is the day Plex recorded it (Report date plus 2 hours). The average is per calendar day over days covered, through yesterday for the current month. The BOM is read when the month is recorded.
- **Why:** Jennilyn asked for usage by item by month for purchasing and production planning.
- **Decided:** Jennilyn, 2026-11-10 · status: in force
- **Reports:** `part_usage_monthly`, `part_usage_month_to_date`
- **Enforced in:** `terraform/part_usage_for_month.sql` lines 41-60,62-78,113-139
- **Measured:** 265: Parts with recorded consumption in the latest month held in part_usage_monthly (October is partial; November is written on the 1st of December) (2026-11-13 10:36 MT). Only October is held (partial, 13 days): 265 parts consumed 108.9M units. November is written on the 1st of December.

### INV-14 Inventory value: every active container except Receiving, primary cost model

- **Rule:** Total inventory value counts every active container except Receiving, valued at the part's per-unit cost in the primary cost model (Go-Live Inventory Cost 2026: material only), only on the current snapshot. Parts with no positive cost add 0. Available inventory value is the same parts on the available-stock rule (INV-01).
- **Why:** This reproduces Plex's own Inventory Valuation screen. Adding all five cost models valued the same stock up to four times.
- **Decided:** Jennilyn, 2026-10-30 · D25 · status: in force
- **Reports:** `inventory_valuation_summary_report`, `inventory_valuation_total_report`, `inventory_lot_detail_report`, `inventory_snapshot_report`
- **Enforced in:** `reports/sql/inventory_valuation_summary_view.sql` lines 176-205,224-232,257-269, `reports/sql/inventory_valuation_total_view.sql` lines 44-53,61-80
- **Measured:** 14,723,241: Total inventory value on the current snapshot (dollars) (2026-11-13 10:36 MT). Inventory is worth $14.72M on the 2026-11-12 snapshot, of which $11.44M is available stock; 1,213 on-hand parts have no cost and add $0.

### INV-15 Only the current inventory snapshot has a value (no month-end trend)

- **Rule:** Earlier snapshots keep their part count and cost but show no total value, because Plex's snapshot has costs and no quantity and only today's stock is extracted. Valuing today's stock at an old cost would draw a trend that is really the cost roll.
- **Why:** Historical on-hand was never captured.
- **Decided:** 2026-09-24 · S10 · status: open decision
- **Reports:** `inventory_valuation_total_report`, `inventory_valuation_summary_report`
- **Enforced in:** `reports/sql/inventory_valuation_summary_view.sql` lines 257-262, `reports/sql/inventory_valuation_total_view.sql` lines 93-100
- **Measured:** 22: Snapshots that show no total value (everything but the latest) (2026-11-13 10:36 MT). 22 of 23 snapshots show no total value; only the current one is valued, since Plex keeps costs for old snapshots but not their stock.

### INV-16 Lot detail: Best By and Expired

- **Rule:** Best By comes from the shelf-life record of the type Plex flags Best By; a date in 2200 or later is a placeholder for does not expire. Expired is Plex's own container status. A lot past its Best By date whose containers are not yet marked Expired shows days to Best By below 0 with is_expired_status false. Rows show stock by part, lot and container status.
- **Why:** Lets Jennilyn drill into Lot Hold, Expired and Quarantine and find lots nearing Best By.
- **Decided:** Jennilyn, 2026-10-30 · D26 · status: partly built
- **Reports:** `inventory_lot_detail_report`
- **Enforced in:** `reports/sql/inventory_lot_detail_view.sql` lines 72-76,98-109
- **Measured:** 28: Lots past their Best By date whose container status is not yet Expired (2026-11-13 10:36 MT). 28 lots are past Best By but still show an active status (183 containers), which is the gap this report exists to show; Plex's own Expired flag covers 291 lots.

### INV-17 Inventory risk: at risk after 90 days with no container activity

- **Rule:** A part is flagged at risk when its newest container activity (container update date) is 90 or more days old, or there is none. The 90 days is a general slow-moving convention, not a Vox policy; days since activity is shown so the threshold can change.
- **Why:** Plex has no packaged slow-moving concept; the NetSuite report needed a best-criteria stand-in.
- **Decided:** 2026-08-21 · status: open decision
- **Reports:** `inventory_risk_analysis_report`
- **Enforced in:** `reports/sql/inventory_risk_analysis_view.sql` lines 117-118
- **Measured:** 2: Parts flagged at risk (90+ days without container activity) (2026-11-13 10:36 MT). Only 2 of 2,180 parts are at risk; the oldest container activity is 29 days ago because Plex went live a month ago.

### INV-18 Cycle count accuracy is a per-location hit rate

- **Rule:** Each counted location is judged once per month on its latest count: accurate if nothing was unaccounted for. Accuracy percent is the share of accurate locations, not weighted by quantity. A month with no counts is normal and shows 0 locations counted, not 0 percent.
- **Why:** That is how the warehouse team already reports it.
- **Decided:** Warehouse team (via Emilio), 2026-09-11 · status: in force
- **Reports:** `part_cycle_count_report`
- **Enforced in:** `reports/sql/part_cycle_count_view.sql` lines 62-110
- **Measured:** 0: Months with cycle count results and locations counted in the latest month (2026-11-13 10:36 MT). Cycle counts are empty today: no month has counted locations yet.

## Label Design

### LBL-01 Which order lines enter the Label Design queue

- **Rule:** A line is in the queue when its release status is Label Design and its order is Pending Fulfillment (approved). Statuses are matched by name, ignoring spaces and capitals.
- **Why:** The old stored procedure filtered only on release status and also returned lines on orders not yet approved.
- **Decided:** Jennilyn, 2026-09-11 · status: in force
- **Reports:** `label_design_report`
- **Enforced in:** `reports/sql/label_design_view.sql` lines 551-552,680-681
- **Measured:** 69: Order lines in the Label Design queue now (2026-11-13 10:36 MT). 69 lines are in the queue, all Label Design lines on Pending Fulfillment orders.

### LBL-02 Orders before 2026-10-18 never reach the queue

- **Rule:** Only orders dated 2026-10-18 or later enter the queue. Orders migrated at go-live (dated early October) are worked by hand. The earlier 14-day window on order date was removed on 2026-10-20 because it dropped orders approved later.
- **Why:** The team handles the migrated orders by hand; the push must not create Monday items for them.
- **Decided:** Emilio, 2026-10-19 · status: in force
- **Reports:** `label_design_report`
- **Enforced in:** `reports/sql/label_design_view.sql` lines 568,682
- **Measured:** 0: Queue rows dated before 2026-10-18 (the rule says there should be none) (2026-11-13 10:36 MT). 0 queue rows are dated before 10-18 (earliest is 10-19); those older migrated lines (20 on 11-12) are worked by hand.

### LBL-03 One queue item per order line

- **Rule:** The queue and Monday get one item per order line, even when two lines carry the same part and even when a line has several releases. A line with several releases shows the earliest due date and the priority of that release, with release_count flagging the split.
- **Why:** Ashley: an order with five lines is five items; the due date that matters is the soonest.
- **Decided:** Ashley, 2026-09-30 · status: in force
- **Reports:** `label_design_report`
- **Enforced in:** `reports/sql/label_design_view.sql` lines 695-713,818
- **Measured:** 0: Queue lines that collapse several releases into one item (2026-11-13 10:36 MT). One item per line: 0 lines have several releases today and there are no duplicate lines in the queue.

### LBL-04 ODBC and the Plex screens are combined for Label Design

- **Rule:** The queue is every line ODBC has, plus any Label Design line the Plex screens show that ODBC does not have yet. Screen lines carry data_source = live and reach Monday within the hour. When ODBC catches up the line comes from ODBC. Screen lines are used only in PlexProd and only while the last screen read is under 3 hours old.
- **Why:** ODBC runs 1 to 5 hours behind Plex; the screens bring new orders fast and ODBC brings the detail.
- **Decided:** Emilio, 2026-11-11 · D38 · status: in force
- **Reports:** `label_design_report`
- **Enforced in:** `reports/sql/label_design_view.sql` lines 603-607,676-692
- **Measured:** 1: Queue lines that only the Plex screens have (data_source = live) right now (2026-11-13 10:36 MT). 1 of 69 lines exists only on the Plex screens; 11 pushed items in the last 30 days were later confirmed by ODBC.

### LBL-05 A line is pushed to Monday once and never re-created

- **Rule:** The push creates one Monday item per new order line. A line already on any board, or already in the push log, is not pushed again, even if the team deleted the item or cleared its code. A run that finds more than 60 new lines pushes nothing and fails, because that means the keys broke.
- **Why:** The team deletes and moves items; a deleted item must not come back.
- **Decided:** 2026-09-30 · L17 · status: in force
- **Reports:** `label_design_report`
- **Enforced in:** `label_design_service/push.py` lines 11-23,106,126-127
- **Measured:** 155: Monday items created by the push in the last 30 days (never re-created) (2026-11-13 10:36 MT). 155 Monday items were created in 30 days and no line was created twice; the log also holds 118 fills, 37 repairs and 2 alerts.

### LBL-06 Late data fills only empty cells, once, and never overwrites

- **Rule:** After an item is on Monday, the push fills its empty cells only: label part number, size, printing material and allergen, and for items created from screens also reps, contact, priority, bottle material, description and customer PO. A value the push sent or the team typed is never overwritten, each cell is filled once, and Data Source becomes confirmed by ODBC.
- **Why:** Label attributes often reach Plex after the order is on Monday (41 of 43 queue label parts had none on 10-28).
- **Decided:** Emilio, 2026-11-11 · status: in force
- **Reports:** `label_design_report`
- **Enforced in:** `label_design_service/fill.py` lines 29-55,87,137-138
- **Measured:** 118: Late-data fills of empty Monday cells in the last 30 days (2026-11-13 10:36 MT). 118 fill actions in 30 days across 106 lines, all on empty cells only.
- **Finding:** 12 lines have two 'filled' log rows in 30 days; the second is the Data Source rewrite 'confirmed by ODBC' (an expected second touch), so 'fills once' holds per cell, not per line.

### LBL-07 Reason Code and Memo come from the job note

- **Rule:** If the first character of the Job Note is a digit 1 to 6, that digit sets the Reason Code and the rest becomes the Memo; otherwise the whole note is the Memo and no Reason Code is written. A note that merely starts with a quantity, like 12ct or 3.5 oz, is not a code. Codes: 1 Customer Initiated Label Edit, 2 Customer initiated Label review, 3 New label design, 4 New label review, 5 Vox Initiated Label Edit/Review, 6 3D Rendering.
- **Why:** The team types the reason as the first character of the note.
- **Decided:** Emilio, 2026-09-29 · status: in force
- **Reports:** `label_design_report`
- **Enforced in:** `reports/sql/label_design_view.sql` lines 765-790
- **Measured:** 61: Queue lines whose job note starts with a digit 1-6 and so carry a Reason Code (2026-11-13 10:36 MT). 61 of 69 lines carry a Reason Code from the note (5 most common, x34); 1 line has a note but no code, so it goes into Memo only.

### LBL-08 Sales Rep is the BDM; Inside Sales Rep is the AM

- **Rule:** Sales Rep on Monday is the BDM (outside salesperson): the lowest-numbered user on the order's Order Salesperson rows, then Outside Sales, then the customer's Assigned To 2. Inside Sales Rep is the AM: the order's Inside Sales, then the customer's Assigned To. Rep names are not matched against Monday's own list.
- **Why:** Plex splits the rep in two and the push had conflated them. The Outside Sales field replicates empty.
- **Decided:** Emilio, 2026-10-08 · L17 · status: in force
- **Reports:** `label_design_report`
- **Enforced in:** `reports/sql/label_design_view.sql` lines 71-77,425-430,623-626
- **Measured:** 0: Queue lines with no Sales Rep (BDM) found (2026-11-13 10:36 MT). Every line has a BDM, but 66 of 69 have no Inside Sales Rep (AM).
- **Finding:** 66 of 69 queue lines have no Inside Sales Rep (AM), so that Monday column is blank for 96% of lines.

### LBL-09 Label attributes come from the label part; Bottle Material from the bottle name

- **Rule:** Label size, printing material, allergen and the other label attributes are read from the LABEL part, found as the BOM component whose name starts LABEL (the nearest level wins), or the ordered part itself when the line orders a label. Bottle Material is read from the bottle component (name starts BOTTLE) and is only HDPE, PET or Glass; a name that does not say it is left blank, not guessed.
- **Why:** QA records attributes on the label part, not the finished good (every column read blank before 2026-10-02). Plex has no bottle attribute.
- **Decided:** Emilio, 2026-10-02 · L8 · status: in force
- **Reports:** `label_design_report`
- **Enforced in:** `reports/sql/label_design_view.sql` lines 262-272,302-330,543-545,741-745
- **Measured:** 5: Queue lines where no label part was found (2026-11-13 10:36 MT). 5 of 69 lines have no label part found; 11 have no bottle material and 52 no label size.

### LBL-10 Priority is the release priority, passed through unchanged

- **Rule:** Priority is the word on the order release's priority dropdown (RUSH, High, Medium, Low, Blanket), taken from the release the row collapses to. It is sent to Monday as is. A priority changed after the item exists is not re-pushed.
- **Why:** The Priority dropdown sits on the release, and the board uses the same five labels.
- **Decided:** Emilio, 2026-10-07 · status: in force
- **Reports:** `label_design_report`
- **Enforced in:** `reports/sql/label_design_view.sql` lines 400,505-506
- **Measured:** 69: Queue lines with a priority, by priority word (2026-11-13 10:36 MT). Priority passes through unchanged: 68 lines Medium, 1 High.

### LBL-11 Monday item name: customer part number or label code

- **Rule:** Each Monday item is named after the customer part number (the full part line when a line has no customer part). Whether it should be the team's label code (like s7187) is undecided.
- **Why:** Changes how every row reads on the board.
- **Decided:** Ashley · L8 · status: open decision
- **Reports:** `label_design_report`
- **Enforced in:** `label_design_service/push.py` lines 100-110

### LBL-12 When the Label Design queue runs

- **Rule:** The queue refreshes every 15 minutes from 5:00 AM to 5:45 PM Mountain, Monday to Friday, with a 6:05 PM sweep. Nothing runs at weekends. Orders entered at the weekend reach the board on Monday morning.
- **Why:** The team works the queue on weekdays only.
- **Decided:** team (hours given by Jennilyn), 2026-10-02 · status: in force
- **Reports:** `label_design_report`
- **Enforced in:** `terraform/main.tf` lines 4771-4775
- **Measured:** 0: Push-log runs in the last 14 days that happened outside the stated window (weekends, or before 5:00 / after 18:10 MT) (2026-11-13 10:36 MT). 0 queue runs happened on a weekend in the last 14 days, and 27 runs were logged, all inside the window.

## Goals and scorecard

### GOAL-01 Goals are typed by people and kept as history

- **Rule:** Sales, production and revenue goals are entered in the Vox Goals web app (v2). Every save adds a new row; nothing is changed or deleted, the newest row for each metric, month and scope wins, and removing a goal adds a retraction row. Who may edit each area is controlled by an access list.
- **Why:** Targets are negotiated (S&OP), so no ERP can supply them. Appending means two people editing at once cannot overwrite each other, and every change stays on record.
- **Decided:** Emilio, 2026-10-19 · S2, D36 · status: in force
- **In her words:** "Make the manual-data app the ONLY writer of prod goals."
- **Reports:** `scorecard_goals_resolved`, `revenue_vs_goal_report`, `sales_vs_goal_report`, `production_vs_goal_report`
- **Enforced in:** `deploy/manual_data_app_v2/Code.gs` lines 7-9, `deploy/manual_data_app_v2/Code.gs` lines 246-248, `reports/sql/scorecard_goals_resolved_view.sql` lines 73-84
- **Measured:** 125: Goal rows ever saved in the app, and how many are superseded or retractions (nothing is deleted) (2026-11-13 10:36 MT). 125 goal rows exist for 116 live goals, so 9 older versions are kept as history; no retractions yet, last save 2026-11-05.

### GOAL-02 The app wins; the old goals table is only a fallback

- **Rule:** For each metric, month and scope, a goal typed in the app wins. Only where the app has no live goal does the legacy scorecard_goals table fill in. A retracted app goal falls back to the legacy value rather than blanking the tile. All three goal reports read this one resolver.
- **Why:** Keeps tiles from going blank during the move from the old Google-sheet goals; the legacy table held the only copy of the 68 rep goals.
- **Decided:** 2026-09-22 · status: in force
- **Reports:** `scorecard_goals_resolved`, `revenue_vs_goal_report`, `sales_vs_goal_report`, `production_vs_goal_report`
- **Enforced in:** `reports/sql/scorecard_goals_resolved_view.sql` lines 61-91, `reports/sql/scorecard_goals_resolved_view.sql` lines 120-137
- **Measured:** 0: Resolved goals that come from the legacy table instead of the app (2026-11-13 10:36 MT). 0 of 116 goals come from the legacy table; the app supplies all of them.

### GOAL-03 Goal scope must match Plex's spelling exactly

- **Rule:** A goal applies to a rep or a work centre group by exact text match. 'Encapsulating' (Plex) is not 'Encapsulation' (the tile). A mismatch gives a goal with no actuals (0%) or actuals with no goal, with no error, so the reports flag it (goal_without_sales / sales_without_goal, goal_without_production / production_without_goal). The app offers only names read from the reports.
- **Why:** A typo otherwise reads as 0% forever.
- **Reports:** `sales_vs_goal_report`, `production_vs_goal_report`
- **Enforced in:** `reports/sql/production_vs_goal_view.sql` lines 64-71, `reports/sql/production_vs_goal_view.sql` lines 87-92, `reports/sql/sales_vs_goal_view.sql` lines 81-88, `deploy/manual_data_app_v2/Code.gs` lines 174-185
- **Measured:** 107: Goal/actual rows that do not match by exact scope text (a goal with no actuals or actuals with no goal), sales + production, all months (2026-11-13 10:36 MT). 107 goal-versus-actual rows have no match by exact text, including this month's Printing, Pre-Weigh and Blending (output but no goal).

### GOAL-04 The company-wide sales goal is its own row; rep goals are not added up

- **Rule:** A company-wide goal (blank scope) is shown as the row '(company-wide)' with actual 0. Never add goal_value across rows: company percent is total actual divided by that row's goal. Rep goals and the company goal may disagree on purpose.
- **Why:** Turnover and negotiation mean the reps' goals do not sum to the team target (Nov: reps total $4.85M against a $5.0M company goal).
- **Decided:** Jennilyn · status: in force
- **Reports:** `sales_vs_goal_report`
- **Enforced in:** `reports/sql/sales_vs_goal_view.sql` lines 58-66, `reports/sql/sales_vs_goal_view.sql` lines 72-88
- **Measured:** 5,000,000: Company-wide sales goal this month, dollars (its own row; not the sum of rep goals) (2026-11-13 10:36 MT). The company-wide goal is $5,000,000 on its own row; summing every goal_value in the month would give $9,675,000 and wrongly halve the percent. Real company percent is 36.8%.

### GOAL-05 A goal scoped 'Sales Representative' belongs to nobody

- **Rule:** One sales goal ($175,000 per month, 7 months) is scoped to the literal text 'Sales Representative', which matches no person. It always reads 0% and is counted nowhere.
- **Why:** Carried over from the old goals sheet; Jennilyn has not said who it is for.
- **Decided:** Jennilyn · S5 · status: open decision
- **Reports:** `sales_vs_goal_report`
- **Enforced in:** `reports/sql/sales_vs_goal_view.sql` lines 60-66
- **Measured:** 7: Goal rows scoped 'Sales Representative' (matching nobody), and dollars per month (2026-11-13 10:36 MT). 7 monthly goals of $175,000 (June to December) are scoped 'Sales Representative' and match no person, so $1,225,000 of goal is counted nowhere.

### GOAL-06 Who can have a sales goal: the Inside Sales roster

- **Rule:** The goal form offers only people in Plex's Inside Sales role (13 people), so a new or quiet rep can be given a goal before they have sales. Outside Sales is deliberately left out.
- **Why:** Before 2026-09-22 the list came from reps who already had a sale this month, so a rep with no sales could not be given a target.
- **Decided:** Emilio, 2026-09-22 · status: open decision
- **Reports:** `sales_reps_report`, `sales_vs_goal_report`
- **Enforced in:** `reports/sql/sales_reps_view.sql` lines 67-74, `deploy/manual_data_app_v2/Code.gs` lines 174-182
- **Measured:** 15: People on the Inside Sales roster (goal form), and roster names with a goal this month (2026-11-13 10:36 MT). 15 people are on the Inside Sales roster (the rule text says 13); 'Sales Representative' is a goal scope that is not on it.
- **Finding:** The Inside Sales roster has 15 people, not the 13 the rule states.

### GOAL-07 Production goals: real for November, placeholders elsewhere, in units

- **Rule:** Production goals are in units, per work centre group. November has real goals set by Jennilyn (Bottling 1.35M, Labeling 750K, Encapsulating 127M); other months still hold labelled placeholders (100M / 1.5M / 700K) seeded 2026-10-02. Groups with output but no goal (Printing, Pre-Weigh, Blending) show production_without_goal.
- **Why:** The placeholders were seeded so the tiles had a reference number; they are not Vox targets.
- **Decided:** Jennilyn · S4 · status: partly built
- **In her words:** "November production goal per Jennilyn"
- **Reports:** `production_vs_goal_report`
- **Enforced in:** `reports/sql/production_vs_goal_view.sql` lines 63-71
- **Measured:** 3: Production goal rows this month, and groups that ran with no goal (2026-11-13 10:36 MT). 3 of 6 production groups have a November goal (Bottling 52%, Labeling 43.2%, Encapsulating 28.9%); Blending, Pre-Weigh and Printing show production with no goal.

### GOAL-08 Revenue-vs-goal drops a goal month that has no revenue

- **Rule:** The revenue goal report starts from revenue months, so a month with a goal but no shipments (January to September 2026) does not appear. Sales and production goal reports show such months at 0%.
- **Why:** Built as 'actuals never vanish because a spreadsheet is behind', which hides the other case.
- **Decided:** not recorded · S13 · status: open decision
- **Reports:** `revenue_vs_goal_report`
- **Enforced in:** `reports/sql/revenue_vs_goal_view.sql` lines 83-85
- **Measured:** 10: Goal months that the revenue-vs-goal report drops because they had no shipments (2026-11-13 10:36 MT). 10 of 12 revenue goal months are dropped because they had no shipments; only 2 months appear.

## Operations

### OPS-01 An open job is not completed, cancelled or on hold

- **Rule:** Open jobs are those whose status is not Completed, not Cancelled and not Hold, matched on Plex's status flags rather than status names. Hold jobs are therefore excluded from open work.
- **Why:** Matches NetSuite's Released/In Process idea and survives new Plex statuses. It fixes the scorecard's Caps Pending, which summed with no status filter.
- **Decided:** 2026-09-01 · status: in force
- **Reports:** `bottling_job_open_report`, `bottling_job_open_with_orders_report`, `mfg_job_open_caps_report`, `labeling_open_work_orders_report`, `printing_open_work_orders_report`, `approaching_msl_report`
- **Enforced in:** `reports/sql/bottling_job_open_view.sql` lines 46-49, `reports/sql/mfg_job_open_caps_view.sql` lines 65-68, `reports/sql/labeling_open_work_orders_view.sql` lines 76-79, `reports/sql/printing_open_work_orders_view.sql` lines 56-59, `reports/sql/approaching_msl_view.sql` lines 201-212
- **Measured:** 84: Open jobs: Bottling open jobs, Encapsulating open jobs and Labeling open work orders (rows each) (2026-11-13 10:36 MT). 84 open Bottling jobs, 42 open capsule jobs and 1 open labeling work order; only Scheduled and Production statuses appear, none Hold.

### OPS-02 Open caps and open bottles are the job's planned quantity, once per job

- **Rule:** Caps pending and open bottles are the planned quantity of each still-open job, counted once per job even if the job has several operations on that work centre. The Encapsulating group includes the scheduling centre Schedule Encapsulation, because jobs wait there before going to a line.
- **Why:** The line-name filter missed the scheduling centre and read 200,000 open caps instead of 1,542,000.
- **Decided:** 2026-09-24 · status: in force
- **Reports:** `mfg_job_open_caps_report`, `bottling_job_open_report`
- **Enforced in:** `reports/sql/mfg_job_open_caps_view.sql` lines 36-44,65, `reports/sql/bottling_job_open_view.sql` lines 46
- **Measured:** 366,564,008: Capsules pending on open Encapsulating jobs, counted once per job (2026-11-13 10:36 MT). 366.6M capsules are pending on 42 open Encapsulating jobs and 1.69M bottles on 84 Bottling jobs, each job counted once.

### OPS-03 Which sales order is behind an open Bottling job

- **Rule:** A job made from an order release is tied to that order directly (order_source Direct). If there is no direct link, the report suggests the Pending Fulfillment orders for the finished 9-parts whose BOM uses the job's part (Suggested). Stock jobs read Stock Job; other job types read N/A with the type.
- **Why:** Plex's Job Distribution view returns no rows, so jobs are tied to orders another way.
- **Decided:** Jennilyn, 2026-10-26 · status: in force
- **Reports:** `bottling_job_open_with_orders_report`
- **Enforced in:** `reports/sql/bottling_job_open_with_orders_view.sql` lines 52-85
- **Measured:** 9: Open Bottling jobs tied to a sales order directly (order_source Direct) (2026-11-13 10:36 MT). Of 84 open Bottling jobs, 9 are tied directly to an order, 50 get suggested orders and 25 have none.

### OPS-04 MFG job success: three gates (yield, no deviation, 84-day turnaround)

- **Rule:** A job succeeds when all three pass: yield (caps made over capsule count) at least 95 percent for stock and 92 percent for custom; no quality deviation; and total days from job added to FG testing released at most 84. Rework jobs are flagged but still counted.
- **Why:** Reverse-engineered from the sheet (about 330 rows, no contradictions); Emilio chose all three gates over a two-of-three reading.
- **Decided:** Emilio, 2026-08-26 · status: partly built
- **Reports:** `mfg_job_schedule_success_metrics_report`, `mfg_job_schedule_gate_stats_report`, `mfg_job_schedule_fg_testing_pending_report`
- **Enforced in:** `reports/sql/mfg_job_schedule_success_metrics_view.sql` lines 194-210, `reports/sql/mfg_job_schedule_gate_stats_view.sql` lines 1-25
- **Measured:** 0: Jobs meeting all three gates of MFG job success (share, percent) (2026-11-13 10:36 MT). 0 of 3,519 jobs are successful: the yield gate passes on 1,657, the deviation gate on all 3,519, and the 84-day gate on none.
- **Finding:** fg_testing_released_date is empty on all 3,519 jobs, so total_days is NULL and the 84-day gate can never pass: 0 jobs are successful by construction.

### OPS-05 Stock versus Custom is guessed from job distribution

- **Rule:** A job counts as Custom when it has a job distribution row (a link to an order release); otherwise Stock. This sets which yield goal applies (92 or 95 percent).
- **Why:** Best available stand-in; not confirmed as the real rule.
- **Decided:** 2026-08-26 · status: open decision
- **Reports:** `mfg_job_schedule_success_metrics_report`, `mfg_job_schedule_gate_stats_report`
- **Enforced in:** `reports/sql/mfg_job_schedule_success_metrics_view.sql` lines 150-152,198-199
- **Measured:** 100: Share of MFG jobs read as Stock (no job distribution row) on production, percent (2026-11-13 10:36 MT). All 3,519 jobs (100%) are read as Stock and none as Custom, so the 95% yield goal applies to every job and the 92% custom goal never does.
- **Finding:** No job has a job distribution row (0 of 3,519), so every job reads Stock and the Custom 92% yield goal is never used.

### OPS-06 Open purchase orders

- **Rule:** An open PO line is one whose PO status is not Cancelled/Denied and not Received, and whose release is not marked Received. A partly received release counts in full.
- **Why:** Plex's workflow has no single Open status.
- **Decided:** 2026-08-10 · status: in force
- **Reports:** `purchasing_open_orders_report`, `purchasing_po_pending_approval_report`
- **Enforced in:** `reports/sql/purchasing_open_orders_view.sql` lines 98-102
- **Measured:** 311: Open purchase order lines, and units on them (2026-11-13 10:36 MT). 311 open PO lines on 171 POs, 112.6M units on order (257 On Order, 38 Approved, 16 New).

### OPS-07 Pending requisitions are approved but not yet on a PO

- **Rule:** A pending order requisition is approved and allowed to become a PO, but has no matching PO release yet.
- **Why:** Confirmed with the report requester; no Plex status is literally Pending Order.
- **Decided:** 2026-08-13 · status: in force
- **In her words:** "Pending Order = requisition is Approved (Allow_PO=1) but has NOT yet been turned into a PO release"
- **Reports:** `purchasing_pending_requisitions_report`
- **Enforced in:** `reports/sql/purchasing_pending_requisitions_view.sql` lines 100-106
- **Measured:** 0: Approved requisitions not yet on a PO (2026-11-13 10:36 MT). No approved requisition is waiting for a PO today.

### OPS-08 POs to approve and supplier returns pending

- **Rule:** POs to approve are those in Plex's own status Pending Approval-NS. Supplier returns pending are every return not yet Shipped, Complete or Cancelled (New, Hold, OK to Ship). The second is a stand-in: no status on this tenant ever reads awaiting approval.
- **Why:** Plex has a literal status for the first; the second has none.
- **Decided:** 2026-08-14 · status: open decision
- **Reports:** `purchasing_po_pending_approval_report`, `quality_supplier_returns_pending_report`
- **Enforced in:** `reports/sql/purchasing_po_pending_approval_view.sql` lines 70, `reports/sql/quality_supplier_returns_pending_view.sql` lines 68-69
- **Measured:** 0: POs waiting for approval (Pending Approval-NS) (2026-11-13 10:36 MT). No PO is in Pending Approval-NS today; 3 supplier returns are pending (the stand-in list).

### OPS-09 Quality problems come from Problem Control (Quality_v_Problem_2)

- **Rule:** Nonconformance records are read from the table behind Plex's new Problem Control screen. The classic Quality_v_Problem table is permanently empty. Turnaround, cost by category and disposition cost all read it.
- **Why:** Reading the classic table made four reports return 0 rows while every job exited 0.
- **Decided:** 2026-09-22 · status: in force
- **Reports:** `quality_nonconformance_report`, `quality_turnaround_time_report`, `quality_cost_by_category_report`, `quality_disposition_cost_report`, `quality_deviation_report`
- **Enforced in:** `reports/sql/quality_nonconformance_view.sql` lines 12-27
- **Measured:** 26: Nonconformance records read from Problem Control (2026-11-13 10:36 MT). 26 nonconformance records in Problem Control since 2026-09-18, 22 of them open; the classic table would show none.

### OPS-10 Destruction is a Scrap disposition; rework cost is Plex's own cost field

- **Rule:** Material destruction is a nonconformance whose final disposition is Scrap. Rework is final disposition Rework. Cost is Plex's own Cost field. A Scrap or Rework record with cost empty or 0 is counted in records_missing_cost. Blank dispositions are split three ways: not yet dispositioned (open), closed with no material, closed with material but disposition missing.
- **Why:** Plex has no Destroy value. Quality types dollar amounts into descriptions, so Cost is 0.00.
- **Decided:** Jennilyn, 2026-09-09 · S8 · status: partly built
- **In her words:** "destructions is like a disposition, but I'm not sure where we would find that... I actually need to ask because I'm not sure where they note that they destroyed something."
- **Reports:** `quality_disposition_cost_report`
- **Enforced in:** `reports/sql/quality_disposition_cost_view.sql` lines 125-173
- **Measured:** 0: Scrap and Rework dispositions recorded with no cost (counted in the table but worth $0) (2026-11-13 10:36 MT). No Scrap or Rework dispositions exist yet (21 records not yet dispositioned), so total cost is $0 and no record is missing a cost.

### OPS-11 Quality turnaround is measured in work days against hand-kept standards

- **Rule:** Turnaround counts from the problem date to the closed date in work days and is compared to Performance and Bonus day standards by part type, with a catch-all row for parts without a type. Records closed in the future are flagged, not dropped. The standards are placeholders today.
- **Why:** Jennilyn keeps the standards table by hand; a typo in the part type yields no standard, not an error.
- **Decided:** Jennilyn, 2026-09-24 · S7 · status: partly built
- **Reports:** `quality_turnaround_time_report`
- **Enforced in:** `reports/sql/quality_turnaround_time_view.sql` lines 45-75,187-215
- **Measured:** 0: Quality records whose turnaround standard is a placeholder or missing (2026-11-13 10:36 MT). All 26 records have a standard: 12 matched by part type and 14 on the catch-all row; none closed in the future.

### OPS-12 Part Lot reports cover active parts only

- **Rule:** Part Lot Attribute Specs and Part Lot Inheritance list active parts only (Part status Active), and active lot attributes. Retired attribute versions are not extracted.
- **Why:** Jennilyn wants a table to see gaps and check things line up.
- **Decided:** Jennilyn, 2026-10-21 · D15 · status: in force
- **In her words:** "only for active parts ... just a table so we can see gaps and ensure things are lining up"
- **Reports:** `part_lot_attribute_specs_report`, `part_lot_inheritance_report`
- **Enforced in:** `reports/sql/part_lot_inheritance_view.sql` lines 135, `reports/sql/part_lot_attribute_specs_view.sql` lines 36
- **Measured:** 153,262: Rows in the Part Lot reports (active parts only) (2026-11-13 10:36 MT). 153,262 attribute spec rows and 16,032 inheritance rows cover only active parts (7,596 parts in the specs).

### OPS-13 Obsolescence and shelf-life reports

- **Rule:** Products to be discontinued are parts whose status is Obsolete or Phase Out. The shelf-life report lists every part; a part with no shelf life appears once with the shelf-life columns blank and shelf_life_missing true, which is the row it exists to find.
- **Why:** Copies Plex's own item list with shelf life details.
- **Decided:** 2026-10-19 · status: in force
- **Reports:** `part_obsolescence_report`, `part_shelf_life_report`
- **Enforced in:** `reports/part_obsolescence.yaml` lines 36
- **Measured:** 232: Parts flagged Obsolete or Phase Out (2026-11-13 10:36 MT). 232 parts are Obsolete (219) or Phase Out (13); 40 of 36,785 parts have no shelf life and show shelf_life_missing.

## Data sources and freshness

### DATA-01 Plex's ODBC data is a copy refreshed about every 4 hours

- **Rule:** Reports built on ODBC can be 1 to 5 hours behind Plex, in jumps at about 09:00, 13:00 and 17:00 MT. That is normal. Six hours behind means a refresh was missed. ODBC has also frozen (11-10, 11-11) while every run still 'succeeded', so freshness is checked separately.
- **Why:** Plex's champion told Jennilyn that ODBC runs up to 4 hours behind; logs confirm it.
- **Decided:** Plex champion via Jennilyn, 2026-11-11 · D33 · status: in force
- **Reports:** `every report built on ODBC`
- **Enforced in:** `terraform/main.tf` lines 6330-6341, `terraform/main.tf` lines 6686-6693
- **Measured:** 120: Minutes ODBC data is behind, per the freshness view (largest across report groups) (2026-11-13 10:36 MT). ODBC is about 60 minutes behind for Label Design and 0 for revenue, inside the normal 1-5 hour window; the production lag is not reported.

### DATA-02 Every report says where its data came from

- **Rule:** 17 reports built on label design, shipping revenue or production end with three columns: data_source (odbc or live), data_as_of (how current) and data_label (text). A new view built on one of those must carry the same wrapper. Monday's 'Data Source' text comes from data_label.
- **Why:** A frozen ODBC copy looks healthy; the label makes an old figure visible to a reader.
- **Decided:** Emilio, 2026-11-10 · status: in force
- **Reports:** `shipping_revenue_report`, `sales_revenue_summary_report`, `sales_revenue_run_rate_report`, `revenue_vs_goal_report`, `label_design_report`, `production_vs_goal_report`
- **Enforced in:** `reports/sql/shipping_revenue_report.sql` lines 79-86, `reports/sql/shipping_revenue_report.sql` lines 209-213, `terraform/main.tf` lines 6686-6693
- **Measured:** 3: Report groups carrying a data-source label in PlexOps.data_freshness (2026-11-13 10:36 MT). Three report groups (production, revenue, label design) carry a data-source label, all currently ODBC.

### DATA-03 Revenue and shipments never switch to the Plex screens

- **Rule:** Revenue and shipping reports always read ODBC. The screens job checks shipments and revenue every 4 hours as an audit only, and emails only if ODBC is more than 12 hours behind (it missed the overnight catch-up).
- **Why:** Jennilyn: revenue and shipments are not time critical; the data arrives every day anyway.
- **Decided:** Jennilyn, 2026-11-11 · status: in force
- **Reports:** `shipping_revenue_report`, `sales_revenue_summary_report`, `sales_revenue_run_rate_report`, `revenue_vs_goal_report`, `shipping_daily_report`
- **Enforced in:** `terraform/main.tf` lines 6166, `scripts/screen_recon.py` lines 78-83, `reports/sql/shipping_revenue_report.sql` lines 87-96
- **Measured:** 0: Revenue shipping rows read from the screens (should be 0; revenue always reads ODBC) (2026-11-13 10:36 MT). 0 of 423 revenue rows read from the screens; the revenue switch is off and ODBC is not behind.

### DATA-04 Label Design combines ODBC with the screens' extra lines

- **Rule:** Label Design takes every ODBC line plus the lines only the Plex releases screen has (new orders ODBC has not caught up to). Screen-only rows show data_source 'live' and their own label. When ODBC catches up, the push fills the item's blank cells and marks it 'confirmed by ODBC'. There is no switching.
- **Why:** New orders reach Monday within the hour instead of waiting up to 4 hours for ODBC, and ODBC still supplies the details.
- **Decided:** Emilio / Jennilyn, 2026-11-12 · D37, D38 · status: in force
- **In her words:** "Keep ODBC + screens combined (proven: order 658 on Monday 2.6 h before ODBC)"
- **Reports:** `label_design_report`
- **Enforced in:** `reports/sql/label_design_view.sql` lines 590-692, `reports/sql/label_design_view.sql` lines 383
- **Measured:** 1: Label Design lines that only the Plex screens have (data_source = live) right now (2026-11-13 10:36 MT). 1 of 69 Label Design lines is screen-only right now; 11 earlier screen-only items were later confirmed by ODBC.

### DATA-05 Weekend runs are probes only; weekday 4 AM is the full refresh

- **Rule:** Weekdays: a full extraction at 04:xx, probes at 1 PM and 6 PM, and a probe at 11 PM. Weekends: probes only (04:xx and 11 PM). So Monday 04:xx is a full run again. A probe re-extracts only tables whose Plex data changed. Test jobs run Monday to Friday.
- **Why:** Saves money (decision 2026-11-12). Report data can therefore be older on weekends and on Monday before 04:xx.
- **Decided:** Emilio, 2026-11-12 · status: in force
- **Reports:** `every prod pipeline`
- **Enforced in:** `PlexOps.etl_schedule (BigQuery table, not a file)` lines rows, `main.py` lines 585-592
- **Measured:** 0: Weekend prod runs that were full runs since the weekend rule began (2026-11-12; the first weekend under it is 11-14) (2026-11-13 10:36 MT). No weekend full run has happened since the rule began on 11-12; the 56 full runs on the last weekend (11-07/08) predate it; the schedule now has 14 weekends-only probe rows, 14 all-days rows and 42 weekday rows.

### DATA-06 ODBC alerts ask whether Plex has changes ODBC lacks

- **Rule:** An 'ODBC is behind' alert fires only if Plex's API shows an order change, older than 6 hours, that ODBC does not have. Quiet nights and weekends no longer alarm. The watchdog mails on two failing checks in a row, weekdays 06:00-18:00 MT, and owns the incident.
- **Why:** The age of ODBC's newest change also grows when nobody works in Plex, which caused false alarms on 11-11 and 11-12.
- **Decided:** Emilio, 2026-11-12 · status: in force
- **Reports:** `watchdog alerts (not a report)`
- **Enforced in:** `plex_api_lag.py` lines 1-60
- **Measured:** 96: ODBC-vs-Plex checks the watchdog ran in the last 48 hours, and how many failed (2026-11-13 10:36 MT). 96 odbc_vs_plex checks in the last 48 hours: 12 failed and 1 alert was sent, so most failing checks did not page anyone.

### DATA-07 A hand edit to a live view lasts only until the next extracting run

- **Rule:** A view edited by hand in the BigQuery console is recreated from the repo SQL at the next run that extracts for that pipeline (probes at 1/6/11 PM, full at 4 AM). To keep an edit it must be copied into the repo and deployed first. Jennilyn's own VoxScorecardsLive views are not touched by the ETL.
- **Why:** The ETL rebuilds every view from SQL in GCS on each extracting run.
- **Decided:** Emilio · status: in force
- **Reports:** `approaching_msl_report`, `bottling_job_open_with_orders_report`, `pipeline_plex_value_report`
- **Enforced in:** `main.py` lines 2548-2557, `custom_views/VoxScorecardsLive/README.md` lines 1-6
- **Measured:** 6.50: Hours since the three hand-edited views were last written (the next extracting run rewrites them from the repo) (2026-11-13 10:36 MT). The three views Jennilyn edits by hand were last rewritten 6.2 to 6.3 hours ago, so a hand edit made before the 13:00 run would be reverted by it.

## Customers

### CUST-01 Customer notes are written through the Plex screen, Note field only

- **Rule:** A customer's Note (Customer Details, NOTES section, the multi-line Note) is set through the screen, because Plex's API accepts the update but saves nothing and ODBC does not export it. Brief Note and the Contact Information note are never touched.
- **Why:** The API call returned 200 and left the note empty on a test customer.
- **Decided:** Emilio, 2026-11-09 · status: in force
- **Reports:** `customer notes in Plex`
- **Enforced in:** `scripts/plex_customer_notes_bulk.py` lines 150-175

### CUST-02 Which customers get a note: exact code, exact name, Active

- **Rule:** A comment is written only when the Plex customer code exists, the name in the file is identical to Plex's, and the customer is Active. An empty Note is filled; an existing Note is appended to (old text kept, new line added), never replaced. Everything else is flagged and not written: 927 inactive, 3 name mismatches, 690 codes not in Plex, 1,395 comments with no code.
- **Why:** Avoids writing to the wrong or retired customer and never destroys an existing note.
- **Decided:** Emilio, 2026-11-09 · D31 · status: open decision
- **Reports:** `customer notes in Plex`
- **Enforced in:** `scripts/plex_customer_notes_bulk.py` lines 159-172

### CUST-03 A customer note shows on the profile only, not on orders

- **Rule:** The note appears on the Customer Details screen but not on the sales order, order notes, Order Line Rapid Entry or the sales order list. Anything that must travel with an order has to go in one of the order's own notes.
- **Why:** Checked read-only on customer L&M Supplements and order 681 on 2026-11-11 (Ashley's question).
- **Decided:** Emilio, 2026-11-11 · status: in force
- **Reports:** `customer notes in Plex`
- **Enforced in:** `docs/CUSTOMER_NOTES_BULK.md` lines Where the note shows

## Where the docs and the code disagree

| Topic | What differs | Status |
|---|---|---|
| Screens switch tolerance | CLAUDE.md and scripts/screen_recon.py say a 120-minute 'behind' tolerance; Terraform runs the job with RECON_LAG_TOLERANCE_MIN=300 (alerts 360, revenue 720). docs/ODBC_VS_SCREENS.md agrees with Terraform. | CLAUDE.md fixed 11-13; code default left at 120 |
| "Pending approval" has three definitions | Pending-approval reports count status 2585 only (22 orders, $272,861); the accounting report counts the Deposit Review statuses 2587 and 2656 (47, $348,869); the pipeline counts all three (68, $621,730) and labels Deposit Review orders 'Pending Sales Approval'. | to decide (Jennilyn) |
| Sales rep on customers-by-rep | sales_customers_by_rep uses Order_Salesperson only; the other sales reports use order, then customer, then salesperson. 31 of 282 customers (11%) get a different rep. | to fix |
| FPY vs production totals | quality_fpy_by_area_month_report has no 9-part / 5-part rule: its Bottling includes 323,904 October units (38%) and 11,500 November units that the production reports drop. | to decide |
| Revenue by rep header | sales_revenue_by_rep_view.sql header says Order_Salesperson only; the code uses the order, customer, salesperson chain. Only 35 of 1,219 lines get the rep from Inside Salesperson. | comment to fix |
| Open-order definitions | Aging has an unstated 14-day minimum age (321 of 423 open orders) and does not exclude quotes; the over-$10k and over-10k-unit lists take every status. | to decide |
| Orders shipped | shipping_daily_report's 'orders shipped' counts distinct shipments, not sales orders. | label to fix |
| Stale SQL headers | inventory_available_to_sell_view.sql lines 39-42 list Pending Sales Approval and Deposit Review as MRP-included (the code and Plex say only Pending Fulfillment and Hold); approaching_msl_view.sql header says demand includes parent jobs (code: sales orders only); weekly_production_update_view.sql says Rejected is -1 (code tests = 0). | comments to fix |
| Stale report docs | part_production_current.md says the daily reports, FPY and weekly skip records with no Job_Op key (they do not); label_design_report.md says checks are held since 11-04 (ODBC recovered 11-08); S2 describes an hourly sheet push, the live app (v2) writes to BigQuery directly. | docs to fix |
| Accounting approval confirmation | The accounting-approval SQL header says Jennilyn still has to confirm; the hub says it was confirmed on 11 Sep. | to confirm |
| Legacy goals table | The legacy scorecard_goals branch is dormant: all 116 resolved goals come from the app. | info |
