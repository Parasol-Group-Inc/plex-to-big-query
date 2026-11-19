# Customer notes on sales orders: what Plex can do (tested 2026-11-19)

**Status: parked, nothing built.** Jennilyn wants the Vox ERP team to own this. This page is
the reference for them: what was asked, what Plex does, what was tested and how to repeat it,
and the options with their trade-offs. OPEN_ITEMS D41.

## The question

Ashley Quintana (Sales Operations), 2026-11-19, about the 1,542 customer Notes written on
2026-11-09 ([CUSTOMER_NOTES_BULK.md](CUSTOMER_NOTES_BULK.md)):

> If we wanted to add these notes in a note field that would show up each time on each SO,
> where can we put them? And is there a way to transfer them to that note field automatically
> or would that be a manual thing?

Already answered on 2026-11-11: the customer Note shows only on the customer's profile, on no
order screen (sales order form, its Notes tab, Rapid Entry).

## Short answer

- Plex never copies the **customer Note** onto an order.
- Plex **does** pre-fill an order from one customer-side field: the ship-to address's
  **Shipping Instructions** become the new order's **Special Instructions** as soon as the
  customer is picked on the order screen, and they are saved with the order.
- Special Instructions **print on shippers** (Plex's own field help), so that route puts the
  note on paperwork that travels with the shipment.
- A staff-only note on every order means the order's **Internal Note**, which nothing fills
  automatically; a job could, through the API.

## The note fields

| Note | Where people see it | REST API | ODBC (view.column) | Pre-fills a new order? | Prints? |
|---|---|---|---|---|---|
| Customer Note (Customer Details) | customer screen only | `note` on `/mdm/v1/customers/{id}`: read **and write** (see below) | not in any view | no | no |
| Ship-to Shipping Instructions | Customer Addresses | `shippingInstructions` on `/mdm/v1/customers/{id}/addresses/{id}`: read, write | `Common_v_customer_address.Shipping_Instructions` | **yes, into Special Instructions** | via the order |
| Ship-to address Note | Customer Addresses | `note` (same endpoint): read, write | `Common_v_customer_address.Note` | no | no |
| Order Internal Note | order form | `note` on `/sales/v1/orders/{id}`: read, write | `Sales_v_PO.Note` | no | no (staff only) |
| Order Printed Note | order form | not exposed | `Sales_v_PO.Printed_Note` | no | "Prints on the Order Acknowledgement/Quote and on the Shipper" |
| Order Special Instructions | order form | not exposed | `Sales_v_PO.Shipping_Instructions` | from the ship-to | "special instructions that print on shippers" |
| Order Shipper Note | order form | not exposed | `Sales_v_PO.Shipper_Note` | no | not checked |
| Invoice internal / printed note | order (invoice section) | `invoiceInternalNote`, `invoicePrintedNote`: read, write | `Sales_v_PO.Invoice_Internal_Note`, `.Invoice_Printed_Note` | no | printed one: invoice |

The quoted print rules are the field help on Plex's order form (the (i) icon next to the field).
The address columns exist in ODBC but the ETL does not extract `Common_v_customer_address`.

## Evidence

### 1. Production data, read only (ODBC copy in BigQuery)

- 106 orders were added after the notes load (2026-11-09 22:02 UTC to 11-19); 60 belong to 44
  customers who got a Note.
- 5 of the 60 contain the customer's note, all in Special Instructions: 2 identical copies, 1
  note plus extra text, 1 near copy, 1 partial. Those 4 customers' earlier orders never had it.
- 55 do not, several with every note field empty. The same order-entry people appear on both
  sides (one person: 4 with the note, 33 without), so the copies are typed by hand.
- Before any notes: Shipping Instructions were on 407 of 718 orders and vary per order (46 of
  the 50 customers with several such orders use different text), so they are typed per order.

### 2. Plex TEST, through the API, the SQL Development screen and the order screen

All writes were in the test tenant (banner "Test Environment - Updates will not persist"),
as the company user `gcp.odbc.vox`, and were put back afterwards (below).

| # | Test | Result |
|---|---|---|
| T1 | `PUT /sales/v1/orders/{id}` (whole object) with `note` changed | 200; read back through the API and in SQL Development (`Sales_v_PO.Note`) at once |
| T2 | `PATCH` the same order with only `note` | 405: not supported, `PUT` the whole object |
| T3 | `PUT` with extra keys `shippingInstructions`, `printedNote`, `shipperNote`, ... | ignored; only `note` and the two invoice notes save |
| T4 | `PUT /mdm/v1/customers/{id}` with `note` | **saved, and shown on the Customer Details screen.** On 2026-11-09 the same call returned 200 and saved nothing; since 11-19 it works (new API app on `gcp.odbc.vox`, or a Plex change: not known which) |
| T5 | `PUT /mdm/v1/customers/{id}/addresses/{id}` with `shippingInstructions` and `note` | saved (SQL Development shows them) |
| T6 | `POST /sales/v1/orders` to that customer | 201; **no note pre-filled** |
| T7 | Order screen: Add, customer picked, ship-to with **no** Shipping Instructions, saved | all four note boxes empty |
| T8 | Same, ship-to **with** Shipping Instructions | **Special Instructions pre-filled the moment the customer was picked**, saved with the order |
| T9 | Customer (i) icon on the order | shows the field's database name only; no customer note popup |
| T10 | `DELETE /sales/v1/orders/{id}` | 405; test orders were deleted on the screen (Delete, Yes) |

Two quirks for whoever automates this:

- On order 785 the API's `shipToAddressId` and `billToAddressId` were the **reverse** of the
  screen and ODBC (`Sales_v_PO.Customer_Address_No` is the ship-to). The first address write
  in T5 therefore landed on the bill-to. Pick addresses by `shipTo: true` and the code, not by
  the order's `shipToAddressId`.
- SQL Development rejects a query (HTTP 400) unless every column is qualified by a table
  alias (`SELECT x.Note FROM Sales_v_PO AS x`).

In the test tenant, 28 ship-to addresses already carry Shipping Instructions, and 24 of the 76
orders to them contain that text. That alone cannot say which way it was copied; T7/T8 do.

## Options

| | Where the note lands | How | Customer sees it? | Ongoing work |
|---|---|---|---|---|
| A | Special Instructions on every new order | copy each customer Note into its ship-to address's Shipping Instructions once (API, T5), then Plex does it | **yes, on shippers** | none; edit the address when the note changes. Existing text on an address must be kept (append, not overwrite) |
| B | Internal Note on every new order | a scheduled job: new order whose Internal Note is empty → write the customer Note (API, T1) | no | a job that writes into live orders; needs sign-off and an owner |
| C | Internal Note on open orders only | one-off run of B | no | none, but new orders miss it |
| D | Next to each order in a report / Monday | read the Note through the API, join to orders | no | none in Plex; people look elsewhere |
| E | Manual | order entry copies it into Internal Note | no | habit; today a few people paste into Special Instructions, which prints |

Before A, someone has to decide which notes are safe to print: the 11-09 notes came from the
old system's free-text Comments and were never written for customers.

## Repeating the tests

Nothing here is in the repo as a tool; the scripts used are kept with the screenshots in
`etl-manual/customer_note/notes_on_orders_test_20261119/` on Emilio's Mac (gitignored, customer
data). They are short and use only what the repo already has:

- **API:** headers `X-Plex-Connect-Api-Key` / `X-Plex-Connect-Api-Secret` (`.env`
  `PLEX_GCP_API_CONSUMER_KEY` / `_SECRET`), base `https://test.connect.plex.com`. Back up the
  record with a GET, change it with a PUT of the whole object, restore with a PUT of the backup.
- **SQL Development (live, not the ODBC copy):** `scripts/plex_web_export.py`'s `login()` and
  `download()` with `SDE` pointed at `https://vox.test.on.plex.com/BusinessIntelligence/SqlDevelopmentEnvironment`.
- **Order screen:** after the same login, `/SalesAndCRM/OrderEntry` → Add; the fields are
  `input[name=CustomerNo]`, `CustomerAddressNo` (ship-to), `SalesAddressNo` (sold-to),
  `textarea[name=InternalNote|PrintedNote|ShippingInstructions|ShipperNote]`. Type in a picker,
  Enter, Tab.
- Playwright runs natively on a Mac (a venv with `playwright`); Docker on the Mac does not
  (emulated Chromium times out).

Records touched in TEST, all restored on 11-19: order 785 (Internal and invoice notes),
customer LUISO (Note), its two addresses; test orders ZZCLAUDE-NOTE-TEST-1..3 deleted (0 left).
