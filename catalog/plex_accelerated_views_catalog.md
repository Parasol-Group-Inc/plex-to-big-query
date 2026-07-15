# Plex SQL Dev — Accelerated Database: View Catalog

> **~19 queryable views** + **~183 report field names** confirmed from tree HTML.
> ODBC prefix (for `_v` views): `Accelerated_v_{ViewName}`

## What "Accelerated" Is

Plex Accelerated Analytics is a cross-module reporting engine built on top of the
Plex OLTP database. The SQL Dev tree for this module shows two kinds of nodes:

1. **`_v` suffix views** — actual ODBC-queryable data sources that aggregate across modules
2. **Field names** (e.g. `Account_No`, `Amount`, `Balance`) — column names available
   within the Accelerated report builder; not standalone queryable views

The `_v` views are the ETL-relevant ones. They may overlap with or provide
convenience equivalents to views in their source databases (Sales, Purchasing, etc.).

## ⭐ Queryable Views (ETL candidates)

| ODBC Name (likely) | Source Module | Notes |
|---|---|---|
| `Accelerated_v_Sales_PO_v` | Sales | Sales order header — may mirror `Sales_v_PO` |
| `Accelerated_v_Sales_Release_v` | Sales | Sales release data |
| `Accelerated_v_Sales_Shipper_Line_v` | Sales | Shipper line details |
| `Accelerated_v_Purchasing_PO_v` | Purchasing | Supplier PO header |
| `Accelerated_v_Purchasing_PO_Line_Item_v` | Purchasing | Supplier PO line items |
| `Accelerated_v_AP_Invoice_v` | Accounting | Accounts payable invoices |
| `Accelerated_v_AR_Invoice_v` | Accounting | Accounts receivable invoices |
| `Accelerated_v_Checksheet_v` | Quality | Checksheet results |
| `Accelerated_v_Container_v` | Personnel/WH | Container records |
| `Accelerated_v_Cost_v` | Costing | Cost data |
| `Accelerated_v_Customer_v` | Common | Customer master |
| `Accelerated_v_Job_v` | Personnel | Job records |
| `Accelerated_v_Job_Status_Job_Active_iv_v` | Personnel | Active job status |
| `Accelerated_v_Part_v` | Part | Part master |
| `Accelerated_v_Part_Operation_v` | Personnel | Part operations |
| `Accelerated_v_Problem_2_v` | Quality | Quality problems |
| `Accelerated_v_Production_v` | Personnel | Production records |
| `Accelerated_v_Standard_Cost_Part_v` | Costing | Standard cost by part |
| `Accelerated_v_Standard_Cost_Part_Operation_v` | Costing | Standard cost by operation |
| `Accelerated_v_Workcenter_Log_v` | Personnel | Workcenter activity log |
| `Accelerated_v_GL_Account_Activity_Detail_v` | Accounting | GL detail |
| `Accelerated_v_Data_Snapshot_And_Availability_Dates_v` | System | Data availability info |

> **Note:** ODBC names above need verification — the Accelerated module's actual
> query names may differ from the pattern above. Run `SELECT TOP 1 * FROM ...`
> to confirm.

---

## Report Field Names (available in Accelerated report builder)

These are column names selectable within Accelerated reports — not standalone
ODBC views. Grouped by likely data domain:

**Identity / Keys:**
`Account_No` · `Author_PUN` · `Last_Altered_PUN` · `PCN` · `Plexus_Customer_Code` ·
`Plexus_Customer_No` · `Stored_Procedure_Key` · `Stored_Procedure_Name` ·
`Stored_Procedure_Text`

**Dates & Time:**
`Availability_Date` · `Begin_Time` · `Completed_Date` · `Created_Date` ·
`Cost_Date` · `Due_Date` · `End_Time` · `Inspection_Date` · `Invoice_Date` ·
`Last_Altered` · `Log_Date` · `PO_Date` · `Preliminary_Due_Date` ·
`Problem_Date` · `Record_Date` · `Recorded_Date` · `Report_Date` ·
`Response_Due_Date` · `Ship_Date` · `Snapshot_Date`

**People:**
`Assigned_To_First_Name` · `Assigned_To_Last_Name` · `Champion_First_Name` ·
`Champion_Last_Name` · `First_Name` · `Inspector_First_Name` · `Inspector_Last_Name` ·
`Issued_First_Name` · `Issued_Last_Name` · `Last_Name` ·
`Reported_By_First_Name` · `Reported_By_Last_Name` · `Response_By_First_Name` ·
`Response_By_Last_Name`

**Order / Part / Job reference:**
`From_Job_Key` · `Job_Key` · `Job_No` · `Job_Op_No` · `Job_Operation_Code` ·
`Job_Sort_Order` · `Job_Status` · `Job_Status_Key` · `Job_Status_Sort_Order` ·
`Job_Type` · `Job_Type_Key` · `Order_No` · `Part_Group` · `Part_Key` ·
`Part_No` · `Part_Operation_Code` · `Part_Operation_Key` · `Part_Operation_No` ·
`Part_Operation_Type_Description` · `Part_Status` · `Part_Type` ·
`PO_Category` · `PO_No` · `PO_Ship_To` · `PO_Ship_Via` · `PO_Status` · `PO_Type` ·
`Release_No` · `Release_Status` · `Release_Type` · `Revision` · `Serial_No`

**Financial:**
`Amount` · `Balance` · `Cost` · `Cost_Sub_Type` · `Cost_Type` · `Credit` ·
`Credit_Account_No` · `Currency_Code` · `Debit` · `Extended_Cost` ·
`Invoice_No` · `Invoice_Type` · `Line_Item_Total` · `Price` ·
`System_Cost_Point` · `Terms` · `Total_PO_Value` · `Unit_Cost` · `Unit_Price` ·
`Voucher_No`

**Inventory / Container:**
`Active_Inventory_Net_Weight` · `Active_Inventory_Quantity` · `Container_Status` ·
`Container_Type` · `Control_Level` · `Gross_Weight` · `Heat_Code` · `Heat_No` ·
`Inventory_Type` · `Location` · `Material_Code` · `Net_Weight` · `Quantity` ·
`Quantity_Shipped` · `Shipped` · `Tare_Weight`

**Quality / Status:**
`Defect_Type` · `Final_Disposition` · `Hold_Status` · `Initial_Disposition` ·
`Inspection_Mode` · `Internal_Problem_No` · `Customer_Problem_No` · `Out_Of_Spec` ·
`Problem_Category` · `Problem_No` · `Problem_Status` · `Problem_Type` ·
`Root_Cause` · `Severity` · `Started_Status` · `Status` · `Type`

**Customer / Supplier:**
`Carrier` · `Customer_Address_Code` · `Customer_Category` · `Customer_Class` ·
`Customer_Code` · `Customer_Rating` · `Customer_Status` · `Customer_Type` ·
`Supplier_Category` · `Supplier_Code` · `Supplier_Type`

**Manufacturing:**
`Blanket_Order` · `Brief_Description` · `Building_Code` · `Business_Type` ·
`Checksheet_Description` · `Checksheet_Type` · `Color` · `Control_Plan_No` ·
`Current_Operation` · `Department_Code` · `Description` · `Full_Description` ·
`Item_No` · `Line_Item_Count` · `Line_Item_No` · `Line_Item_Status` ·
`Log_Hours` · `Name` · `Note` · `Number` · `Operation_Code` · `Operation_No` ·
`Period` · `Period_Display` · `Priority` · `Priority_Key` · `Produced_Quantity` ·
`Product_Type` · `Region` · `Sample_Frequency` · `Shift` · `Specific_Name` ·
`Standard_Job_Quantity` · `Standard_Quantity` · `Unit` ·
`Workcenter_Code` · `Workcenter_Event` · `Workcenter_Status`
