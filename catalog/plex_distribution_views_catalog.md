# Plex SQL Dev — Distribution Database: View Catalog

> **15 base views** confirmed from tree HTML.
> ODBC prefix: `Distribution_v_{ViewName}` (e.g. `Distribution_v_Order`)

## Purpose

Plex Distribution is a small module focused on order fulfillment and outbound
shipping — distinct from the customer-facing `Sales_v_PO` and warehouse modules.
Appears to cover drop-ship, direct distribution, and external distribution partners.

## Relevance to Sales Orders Pipeline

- `Order` and `Order_Line` ⭐ — distribution orders (likely tied to sales orders)
- `Shipper` and `Shipper_Line` ⭐ — outbound shipment records; Ship Date lives here
- `Contract_Price` — contracted pricing that may override standard pricing

---

## All Views (15)

| ODBC Name | Notes |
|---|---|
| `Distribution_v_Contract_Price` | Contracted pricing by customer/part |
| `Distribution_v_Customer_Part` | Customer-specific part config for distribution |
| `Distribution_v_Material` | Material tracking in distribution flow |
| `Distribution_v_Order` ⭐ | Distribution order header |
| `Distribution_v_Order_Line` ⭐ | Distribution order line items |
| `Distribution_v_Order_Status` | Status codes for distribution orders |
| `Distribution_v_Part` | Part master (distribution-side view) |
| `Distribution_v_Part_Type` | Part type reference |
| `Distribution_v_Part_Type_Price` | Pricing by part type |
| `Distribution_v_Plating` | Surface treatment / plating spec |
| `Distribution_v_Plexus_Customer_No` | Customer number lookup |
| `Distribution_v_Ship_Via` | Carrier / shipping method codes |
| `Distribution_v_Shipper` ⭐ | Outbound shipper header |
| `Distribution_v_Shipper_Line` ⭐ | Shipper line items |
| `Distribution_v_Supplier_Part` | Supplier-specific part in distribution context |

---

## Notes

Very small module — likely a specialized add-on for companies doing direct
distribution or drop-ship. The 4 starred views (`Order`, `Order_Line`, `Shipper`,
`Shipper_Line`) are the most valuable for tracing order fulfillment timelines.
