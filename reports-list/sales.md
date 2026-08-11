# Reports List — Sales

Source file: `Reports List - Sales.csv`. Columns: Report Name, Source,
Function, Users, Link, Priority.

**Almost every row here is a native NetSuite saved search** (`searchid=`
URLs) — ❌ out of scope for this Plex→BigQuery pipeline. Catalogued for
completeness, not because any of these are candidates.

| Report | Status | Notes |
|---|---|---|
| Sample Orders, Pending Certificates, Pending Approval Orders, Orders waiting to be completed, Open RMA's, Orders Pending Approval by Sales Rep, Orders Pending Approval by Accounting, Work Orders partial buildable (labeling), Printing Open Work Orders, Orders over $10k, Orders over 10k bottles, SO's with discounts, Report for orders past 14 days old, One for Rush orders, Available Inventory, Orders in Design, Allocation reports, Open Quotes, Customer List by Sales Rep, Revenue per sales rep, Revenue for Vox, Inventory consumption | ❌ Out of scope | All native NetSuite saved searches |
| One for customers who are top/strategic, reports for orders with oos skus, One for SO's with credits applied, One for international customers, One for FBA sellers, Report that lets us type in a product and see all open orders | 💡 Idea, no source yet | Marked "Nice to have" with no backing system — not implemented anywhere, so nothing to map against yet |
| Design in Monday - NEW | ❌ Out of scope | A Google Sheet, but it imports data *from* NetSuite into Monday.com — still fundamentally NetSuite-sourced |

## Note

"Available Inventory" appears here too (NetSuite-sourced, "real-time view
of inventory... committed, on hand and in order") — same concept name as
`part_on_hand_inventory_report`, but this one is NetSuite's own view, not a
Plex gap. Worth being aware both exist under the same name in different
systems if this ever comes up in conversation with Sales.
