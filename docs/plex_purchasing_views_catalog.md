# Plex SQL Dev — Purchasing Database: View Catalog

> **130 base views** confirmed from tree HTML (`Views` folder node excluded).
> ODBC prefix: `Purchasing_v_{ViewName}` (e.g. `Purchasing_v_PO`)

## Purpose

Plex Purchasing covers **supplier-side** purchasing: supplier POs, RFQs,
receipts, and releases. This is distinct from the Sales module which covers
customer-facing sales orders (`Sales_v_PO`).

## Relevance to Sales Orders Pipeline

- `Purchasing_v_PO_Sales_PO` ⭐ — links a purchasing PO back to a sales PO (cross-reference)
- `Purchasing_v_Release` and `Release_Ship` — can track supplier delivery against an SO
- `Purchasing_v_RFQ_Quote` — if quotes from suppliers tie to customer quotes
- Supplier cost data (`Item_Price`, `Item_Supplier_Price`) useful for margin analysis

---

## Views by Category

### Purchase Orders (supplier-facing)
`PO` · `PO_Approver` · `PO_Bill_To` · `po_category` · `PO_Clause` · `po_country` ·
`PO_Freight_Terms` · `PO_h` · `PO_Note` · `PO_Output_History` · `PO_Revision` ·
`PO_Revision_Release` · `PO_Sales_PO` ⭐ · `PO_Ship_To` · `PO_Ship_Via` ·
`PO_Status` · `PO_Type` · `PO_Type_Clause`

> `PO_Sales_PO` links a supplier PO to the originating sales PO — useful for
> back-to-back order tracing.

### Line Items
`Item` · `Item_Alternate_Item` · `Item_Building` · `Item_Category` ·
`Item_Group` · `Item_Localization` · `Item_Location` · `Item_Owner_Inventory` ·
`Item_Owner_Transaction` · `Item_Owner_Transaction_Type` ·
`Item_Owner_Transaction_Type_Language` · `Item_Price` · `Item_Priority` ·
`Item_Substitution` · `Item_Supplier` · `Item_Supplier_Price` ·
`Item_Tax` · `Item_Type` · `Item_Usage` · `Item_Usage_Transaction_Type` ·
`Line_Item` · `Line_Item_Category` · `Line_Item_Check` · `Line_Item_Customer` ·
`Line_Item_Dimension` · `Line_Item_Localization` · `Line_Item_Note` ·
`Line_Item_Price` · `Line_Item_Receipt_Charge` · `Line_Item_Receipt_Charge_Value` ·
`Line_Item_Receipt_Charge_Value_Tax` · `Line_Item_Status` · `Line_Item_Tax` ·
`Line_Item_Unit_Price` · `Line_Item_Unit_Price_Value`

### Receipts (supplier deliveries)
`Receipt` · `Receipt_Change` · `Receipt_Charge` · `Receipt_Check` ·
`Receipt_Description` · `Receipt_Estimate` · `Receipt_Settlement` ·
`Receipt_Uninvoice`

### Releases
`Release` · `Release_Acknowledgement` · `Release_Container` · `Release_h` ·
`Release_Job` · `Release_Ship` · `Release_Status` · `Release_Type` ·
`Req_PO_Release`

### Requisitions
`Requisition` · `Requisition_Status` · `Requisition_Type`

### RFQ (Request for Quotation — supplier-facing)
`RFQ` · `RFQ_Building` · `RFQ_Change_History` · `RFQ_Doc` · `RFQ_Doc_Step` ·
`RFQ_ECR` · `RFQ_Email` · `RFQ_Line` · `RFQ_Line_Change_History` ·
`RFQ_Line_Op` · `RFQ_Line_Qty` · `RFQ_Price_Point` · `RFQ_Priority` ·
`RFQ_Quote` · `RFQ_Status` · `RFQ_Type` · `RFQ_UAS_Change_History`

### Responses (supplier quote responses)
`Response` · `Response_Change_History` · `Response_Line` ·
`Response_Line_LTA_Reduction` · `Response_Price` · `Response_RFQ_Doc` ·
`Response_Status` · `Op_Response_Price` · `Qty_Response_Price`

### Pricing & Costs
`Price_Point` · `Surcharge` · `Surcharge_Component` · `Surcharge_Group` ·
`Surcharge_Group_Member` · `Surcharge_Note` · `Surcharge_Template` ·
`Surcharge_Template_Component` · `Supplier_Offer`

### Tax & Compliance
`Tax_Classification` · `Tax_Code` · `Tax_Code_Item_Tax` · `Tax_EDI_Clause` ·
`Tax_Group` · `Tax_Group_Tax_Code` · `Tax_Type` · `VAT_Method` ·
`VAT_Method_Tax_Code` · `VAT_Type`

### Reference / Setup
`Clause` · `Commodity` · `FOB` · `Inbound_Truck` · `Inbound_Truck_Status` ·
`Inbound_Truck_Type` · `Review` · `Review_Setup` · `Routing` ·
`Service` · `Service_Localization` · `Source_Status`

---

## Notes

- **Supplier PO vs Sales PO:** `Purchasing_v_PO` = orders sent to suppliers.
  `Sales_v_PO` = sales orders from customers. Different directions.
- `PO_Sales_PO` is the bridge view between the two.
- `Purchasing_v_Receipt` = goods received against a supplier PO (not a sales receipt).
