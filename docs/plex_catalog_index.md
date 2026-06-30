# Plex SQL Dev — Database Catalog Index

All Plex database spaces visible in the SQL Development Environment tree.
Individual catalog files live in this `docs/` folder.

| Database | Catalog File | Purpose | ETL Priority |
|---|---|---|---|
| **Sales** | [plex_sales_views_catalog.md](plex_sales_views_catalog.md) | Customer orders, quotes, pricing, shipping | ⭐ Primary |
| **Common** | [plex_common_views_catalog.md](plex_common_views_catalog.md) | Customer master, employees, carriers, currencies | ⭐ JOIN source |
| **Part** | [plex_part_views_catalog.md](plex_part_views_catalog.md) | Part master, BOM, routing, containers, tools, workcenters, Customer_Part_Price — **778 views confirmed** | ⭐ JOIN source |
| **Accounting** | [plex_accounting_views_catalog.md](plex_accounting_views_catalog.md) | AR/AP invoices, GL accounts, payments | High |
| **Purchasing** | [plex_purchasing_views_catalog.md](plex_purchasing_views_catalog.md) | Supplier POs, RFQs, receipts — **130 views confirmed** | High |
| **Plexus_Control** | [plex_plexus_control_views_catalog.md](plex_plexus_control_views_catalog.md) | User master (`Plexus_User` ⭐), roles, menus — **213 views confirmed** | ⭐ JOIN source |
| **Warehouse** | [plex_warehouse_views_catalog.md](plex_warehouse_views_catalog.md) | Inventory on-hand, containers, locations | High |
| **Quality** | [plex_quality_views_catalog.md](plex_quality_views_catalog.md) | FMEA, PPAP, Problems, Cost Recovery, Warranty — **515 views confirmed** | Medium |
| **Personnel** | [plex_personnel_views_catalog.md](plex_personnel_views_catalog.md) | HR: Employee master, payroll, training, time-off, safety/incidents — **272 views confirmed** | Medium |
| **Distribution** | [plex_distribution_views_catalog.md](plex_distribution_views_catalog.md) | Order, Order_Line, Shipper, Shipper_Line — **15 views confirmed** | Medium |
| **Accelerated** | [plex_accelerated_views_catalog.md](plex_accelerated_views_catalog.md) | Cross-module analytics engine — `_v` views + report fields — **~22 views confirmed** | Medium |
| **Material** | [plex_material_views_catalog.md](plex_material_views_catalog.md) | MRP, demand/supply planning | Medium |
| **Maintenance** | [plex_maintenance_views_catalog.md](plex_maintenance_views_catalog.md) | Equipment, work orders, PM schedules | Low |
| Cloud | — | Cloud integration utilities | Low |
| Communication | — | Notifications, email, messaging | Low |
| Community | — | Plex Community/user portal | — |
| Document | — | Document management | Low |
| EDI | — | EDI transaction tracking | Low |
| ERLog | — | Error/event logs | Low |
| External | — | External system integrations | Low |
| Label | — | Label templates and printing | Low |
| master | — | SQL Server system database | — |
| Plex_Global | — | Global Plex configuration | — |
| Steel | — | Steel/metals industry add-on | — |
| Web_Services | — | Web service API endpoints | Low |

---

## ⚠ Plex ODBC Naming Convention

**All views are queried as `{Database}_v_{ViewName}` — NOT the bare view name.**

The SQL Dev tree shows the view name only (e.g. `Order_Salesperson`). To query via ODBC:
```sql
-- Tree shows:          Order_Salesperson
-- Query must use:      Sales_v_Order_Salesperson

SELECT TOP 3 * FROM Sales_v_Order_Salesperson
SELECT TOP 3 * FROM Sales_v_PO
SELECT TOP 3 * FROM Common_v_Customer
SELECT TOP 3 * FROM Part_v_Part          -- Part DB, view named "Part"
```

This is also what goes in `PLEX_VIEW` in `.env` and `terraform.tfvars`.

---

## Confirmed ODBC View Names for Sales Orders Pipeline

| ODBC Query Name | Tree Name | Database | Purpose |
|---|---|---|---|
| `Sales_v_PO` | `PO` | Sales | SO header — all primary fields (see confirmed columns below) |
| `Sales_v_PO_Line` | `PO_Line` | Sales | SO lines — part, qty, price |
| `Sales_v_Order_Salesperson` | `Order_Salesperson` | Sales | Salesperson per PO — `Plexus_User_No`, `Sort_Order` |
| `Sales_v_Quote_Order` | `Quote_Order` | Sales | Quote → PO linkage |
| `Sales_v_PO_Status` | `PO_Status` | Sales | Status labels |
| `Sales_v_PO_Type` | `PO_Type` | Sales | Type labels |
| `Common_v_Customer` | `Customer` | Common | Customer name lookup |
| `Part_v_Part` | `Part` | Part | Part master — confirmed working |
| `Part_v_Part_Product_Type` | `Part_Product_Type` | Part | Part type label — confirmed in Part DB |
| `Part_v_Part_Product_Group` | `Part_Product_Group` | Part | Part group label — confirmed in Part DB |
| `Part_v_Customer_Part_Price` | `Customer_Part_Price` | Part | Price EA per customer-part — schema confirmed (see columns below) |
| `Part_v_Customer_Part` | `Customer_Part` | Part | Customer-facing part number and description |
| `Plexus_Control_v_Plexus_User` | `Plexus_User` | Plexus_Control | Sales rep name master — join on `Plexus_User_No` |

### `Sales_v_PO` Columns (confirmed via live query 2026-06-29)
`PCN` · `PO_Key` · `Customer_No` · `PO_No` · `Order_No` · `PO_Date` · `Add_Date` ·
`PO_Status_Key` · `PO_Type_Key` · `PO_Category_Key` · `Terms` · `Expiration_Date` ·
`FOB` · `FOB_Key` · `Freight_Terms_Key` · `Carrier` · `Carrier_Text` ·
`Master_Price` · `Commission` · `Commissionable` · `Inside_Sales` · `Outside_Sales` ·
`Buyer_No` · `Engineer_No` · `Customer_Address_No` · `Sales_Address` ·
`Purchaser_Address_No` · `Freight_Bill_To_Address_No` · `Bill_Code_Key` ·
`Contact_No` · `Contact_Note` · `Customer_Release_No` · `Ship_To_PO_No` ·
`Customer_Change_Order` · `From_PO_Key` · `Source_Module_Key` ·
`Location_Key` · `Building_Key` · `Region_Key` · `Cust_Prog_Key` ·
`Program_Key` · `Market_Key` · `Accounting_Job_Key` · `Source_Inspection_Key` ·
`Note` · `Shipping_Instructions` · `Shipper_Note` · `Printed_Note` ·
`PO_Review_Note` · `Invoice_Internal_Note` · `Invoice_Printed_Note` · `Packaging_Note` ·
`Certs` · `Master_Price` · `Multiple_Docks_Per_Shipper` · `Multiple_PO_Per_Shipper` ·
`ITAR_Order` · `Invoicing_Hold` · `Signature_Required` · `Bracket_Pricing` ·
`Ship_Complete_Order` · `Third_Party_Ship_To` · `Ultimate_Destination` · `End_User` ·
`PO_No_Revision` · `PO_No_Revision_Date` · `Shipper_Email` ·
`Add_By` · `Update_By` · `Update_Date` · `Multi_Entity_Default_Child_PCN` · `Resource_ID`

### `Sales_v_PO_Change` Columns (confirmed via live query 2026-06-29)
Snapshot table — one row per change event on a PO. Key columns on top of `Sales_v_PO`:
`Change_Key` · `Change_By` · `Change_Date` ⭐ · `Previous_Change_Key_d`
All other columns mirror `Sales_v_PO` (the PO state at time of change).

**Date Approved pattern** — `PO_Status_Key = 2073` confirmed as "Pending Fulfillment":
```sql
SELECT pc.PO_Key, MIN(pc.Change_Date) AS Date_Approved
FROM Sales_v_PO_Change pc
WHERE pc.PO_Status_Key = 2073   -- 'Pending Fulfillment' (confirmed)
GROUP BY pc.PO_Key
```

### `Sales_v_PO_Line` Columns (confirmed via live query 2026-06-29)
`PCN` · `PO_Line_Key` · `PO_Key` · `Part_Key` · `Customer_Part_Key` · `Line_No` ·
`Finished_Part_Key` · `Build_Key` · `Line_Item_Key` ·
`Standard_Pack_Quantity` · `Minimum_Ship_Quantity` · `Quantity_Plus` · `Quantity_Minus` ·
`Spot_Buy_Quantity` · `Containers_Per_Master_Unit` · `Conversion` ·
`Weight_Conversion` · `Price_Conversion` · `Master_Unit_Type_Key` ·
`Container_Type` · `Default_Order_Unit_Key` · `Default_SCAC_Code` ·
`Active` · `Export` · `Export_By` · `Export_Date` · `New_Shipper_Per_Schedule` ·
`New_Shipper_Per_Release_No` · `Show_Components` · `Force_Standard_Pack_Quantity` ·
`Part_Certification_Required` · `EUN_Required` · `ITAR_License_No` ·
`Documentation_Key` · `Transportation_Adjustment` · `Supplemental_Order_No` ·
`Ship_To_PO_No` · `Packaging_Note` · `Note` · `Shipping_Instructions` ·
`Contact_No` · `Ordered_By_Contact_No` · `Mailbox_Key` · `Accounting_Job_Key` ·
`Project_Type_Key` · `Cust_Prog_Key` · `Program_Key` · `Market_Key` ·
`Mill_Supplier_No` · `Add_By` · `Add_Date` · `Update_By` · `Update_Date` ·
`Multi_Entity_Default_Child_PCN` · `Resource_ID`

> ⚠ **`Sales_v_PO_Line` has NO Quantity Ordered or Price columns.**
> Quantity is in `Sales_v_Release.Quantity`. Pricing source still unconfirmed — see below.

**16-field report mapping from `Sales_v_PO`:**

| Report Field | Column / Source | Status |
|---|---|---|
| Date Created | `Sales_v_PO.PO_Date` | ✅ confirmed |
| Date Approved | `MIN(Sales_v_PO_Change.Change_Date) WHERE PO_Status_Key = pending_key` | ✅ approach confirmed — need status key |
| Type | `Sales_v_PO.PO_Type_Key` → JOIN `Sales_v_PO_Type` | ✅ need PO_Type label query |
| Document / SO # | `Sales_v_PO.PO_No` | ✅ confirmed |
| From-quote flag | `Sales_v_PO.From_PO_Key` (non-NULL = from quote) | ✅ confirmed |
| Status | `Sales_v_PO.PO_Status_Key` → JOIN `Sales_v_PO_Status` | ✅ need status label query |
| Customer Name | `Sales_v_PO.Customer_No` → JOIN `Common_v_Customer` | ✅ confirmed |
| Sales Order Total | `Sales_v_PO.Master_Price` | ✅ confirmed |
| Sales Rep 1 | `Sales_v_Order_Salesperson` Sort_Order=1 → `Plexus_Control_v_Plexus_User` | ✅ confirmed |
| Sales Rep 2 | `Sales_v_Order_Salesperson` Sort_Order=2 → `Plexus_Control_v_Plexus_User` | ✅ confirmed |
| Product / Part # | `Sales_v_PO_Line.Part_Key` → Part master | ✅ PO_Line confirmed; Part_Key present |
| Qty Ordered | `Sales_v_Release.Quantity` + `Quantity_Unit` (e.g. "eaches") | ✅ confirmed |
| Price EA | `Part_v_Customer_Part_Price.Price` (at matching Breakpoint_Quantity) | ✅ schema confirmed |
| Price Total (line) | `Price × Sales_v_Release.Quantity` — calculated | ✅ |
| Part / Product Type | `Part_v_Part_Product_Type` | ✅ confirmed in Part DB |
| Part / Product Group | `Part_v_Part_Product_Group` | ✅ confirmed in Part DB |

### `Part_v_Customer_Part_Price` Columns (schema confirmed 2026-06-29, no test data)
`PCN` · `Customer_Part_Key` ⭐ · `Customer_Part_Price_Key` · `Price` ⭐ ·
`Breakpoint_Quantity` · `Note` · `Price_Updated_By` · `Price_Updated_Date` ·
`Invoice_Adjustment_Amount` · `Account_No` · `Effective_Date` · `Expiration_Date` ·
`Customer_Address_No`

> No results on test data — the test orders' `Customer_Part_Key` values have no price records yet (orders are in Pending Sales Approval). The view and join are correct.

**Pricing join pattern:**
```sql
-- Get the active price for a customer part at a given quantity
LEFT JOIN Part_v_Customer_Part_Price cpp
  ON cpp.Customer_Part_Key = pol.Customer_Part_Key
  AND cpp.Breakpoint_Quantity <= rel.Quantity        -- quantity break pricing
  AND (cpp.Expiration_Date IS NULL OR cpp.Expiration_Date >= po.PO_Date)
  AND cpp.Effective_Date <= po.PO_Date
-- Price EA = cpp.Price
-- Price Total = cpp.Price * rel.Quantity
```

### `Sales_v_PO_Status` — Confirmed Status Workflow (Vox Nutrition)

| PO_Status_Key | Label | Sort | Open | Notes |
|---|---|---|---|---|
| 2585 | Pending Sales Approval | 0 | ✅ | Starting status — all new orders land here |
| 2587 | Deposit Review | 10 | ✅ | |
| 2586 | Released | 20 | ✅ | |
| **2073** | **Pending Fulfillment** | 30 | ✅ | ⭐ **Date Approved = when PO_Change hits this key** |
| 2638 | Pending Payment Review | 40 | ✅ | |
| 2639 | Pending Shipment | 45 | ✅ | |
| 2075 | Hold | 50 | ✅ | `Hold = 1` |
| 2074 | Closed | 90 | ❌ | `Completed_Status = 1` |
| 2076 | Cancelled | 100 | ❌ | `Cancelled_Status = 1` |

> Note: Test SOs in sample data all have `PO_Status_Key = 2585` (Pending Sales Approval) —
> they have not yet been approved, so `Sales_v_PO_Change` will not have a 2073 row for them.

### `Sales_v_Release` Columns (confirmed via live query 2026-06-29)
`PCN` · `Release_Key` · `Release_No` · `PO_Line_Key` ⭐ · `Release_Type_Key` ·
`Ship_To` · `Ship_Date` · `Due_Date` · `Customer_Due_Date` · `Preliminary_Due_Date` ·
`Quantity` ⭐ · `Order_Quantity` · `Quantity_Unit` ⭐ · `Quantity_Shipped` ·
`Quantity_Shipped_DEC` · `Quantity_Variance_Plus` · `Quantity_Variance_Minus` ·
`Minimum_Container_Quantity` · `Maximum_Container_Quantity` · `Maximum_Source_Containers` ·
`Release_Status_Key` · `Release_Source_Key` · `Priority_Key` · `Confirmed` ·
`Building_Key` · `Ship_From` · `Sold_To` · `Bill_To` · `Printed_Ship_To` ·
`PO_Key_d` · `Fully_Shipped` · `PO_Confirmation_Key` · `Work_Table_Key` ·
`Multi_Entity_Child_PCN` · `Schedule_No` · `Schedule_Date` ·
`EDI_Kanban_No` · `EDI_Dock_Code` · `EDI_Line_Code` · `EDI_Document` ·
`EDI_Reference_No` · `EDI_R_Code` · `EDI_Intermediate_Consignee` ·
`EDI_Order_No` · `EDI_Dealer_No` · `EDI_Lot_No` · `EDI_Batch` ·
`EDI_Load_Sequence_No` · `EDI_Key_Add` · `EDI_Key_Update` ·
`EDI_Line_11` through `EDI_Line_17` · `EDI_Material_Handling_Code` ·
`Raw_Authorization_No` · `Fab_Authorization_No` · `Time_Frame_Code` ·
`CONV_Order_No` · `CONV_Order_Line_No` · `Note` · `Printed_Note` · `Packaging_Note` ·
`Add_By` · `Add_Date` · `Update_By` · `Update_Date` · `Resource_ID`

> ⚠ **`Sales_v_Release` has NO price columns.**
> `Quantity` (ordered qty) and `Quantity_Unit` are confirmed here.
> Pricing source still unconfirmed — `Master_Price` on `Sales_v_PO` was 0 on all test records.
> Next query: `SELECT TOP 5 * FROM Common_v_Customer_Part_Price`
> (join via `Sales_v_PO_Line.Customer_Part_Key`)

### Sales Rep Column Structure (confirmed via live query)
`Sales_v_Order_Salesperson` returns: `PCN`, `PO_Key`, `Plexus_User_No`, `Commission`, `Sort_Order`, `Update_By`
- `Sort_Order = 1` → Sales Rep 1, `Sort_Order = 2` → Sales Rep 2
- Join to `Plexus_Control_v_Plexus_User` on `Plexus_User_No`

### `Plexus_Control_v_Plexus_User` Columns (confirmed via live query)
`Fax` · `Mobile` · `Home_Phone` · `Extension` · `Plexus_User_No` · `Plexus_Customer_No` ·
`User_ID` · `Last_Name` · `First_Name` · `Middle_Name` · `Note` · `Change_Password` ·
`Department_No` · `Position_Key` · `Email` · `Active` · `Document_Approver` ·
`Activity_Manager_Default` · `In_Out_Board` · `In_Out_Status` · `In_Out_Date` ·
`In_Out_Note` · `Building_Key` · `Language_Key` · `Date_Week_Format` ·
`Add_By` · `Add_Date` · `Update_By` · `Update_Date` · `Password_Changed_By` ·
`Print_Bar_Code_On_Badge` · `Password_Changed_Date` · `Lockout` · `Phone` ·
`Pager_No` · `Document_Champion` · `Generic_User` · `Main_Plexus_Customer_No`

**Sales rep join pattern:**
```sql
SELECT
  os.PO_Key,
  os.Sort_Order,
  u.First_Name,
  u.Last_Name,
  u.Email
FROM Sales_v_Order_Salesperson os
JOIN Plexus_Control_v_Plexus_User u
  ON os.Plexus_User_No = u.Plexus_User_No
-- Sort_Order = 1 → Rep 1, Sort_Order = 2 → Rep 2
-- Filter: WHERE u.Active = -1 to exclude deactivated users
```

---

## Key for Individual Catalog Files

- ✅ **Verified** — view confirmed in Plex SQL Dev tree or live query
- ❓ **Estimated** — likely exists based on Plex naming conventions; verify before use
- ⭐ **ETL target** — relevant to the active BigQuery pipeline
