# Plex SQL Dev — Common Database: View Catalog

> **386 base views** confirmed from tree HTML (corrected 2026-06-29 — prior 1,160-view list was contaminated with other databases).
> ODBC prefix: `Common_v_{ViewName}` (e.g. `Common_v_Customer`)

## Purpose

Plex Common is the shared master-data layer: customers, suppliers, buildings,
locations, shipping, currencies, departments, metrics, and reference codes.
It does **not** contain Part master, Customer_Part pricing, or Part_Product_Type/Group
— those belong to other databases (Part, Personnel, or Sales).

## Relevance to Sales Orders Pipeline

- `Customer` ⭐ — customer name lookup (join via `Sales_v_PO.Customer_No`)
- `Customer_Outside_Sales` ⭐ — customer-to-outside-sales-rep assignment (explore for rep names)
- `Ship_Via` — carrier / shipping method labels
- `Terms` — payment terms labels
- `Currency` — for multi-currency order values
- `Department` — department reference

> ⚠ `Part_Product_Type` and `Part_Product_Group` are **NOT** in Common.
> Their correct database needs to be verified in SQL Dev.

---

## Views by Category

### Customer Master ⭐
`Customer` ⭐ · `Customer_Account` · `Customer_Account_Type` · `Customer_Accounting` ·
`customer_address` · `Customer_Address_Accounting` · `Customer_Address_Document_Layout` ·
`Customer_Address_EDI` · `Customer_Address_Food_Establishment` ·
`Customer_Address_Freight_Rate` · `Customer_Address_Grade_Type_Certification` ·
`Customer_Address_Integrated_Shipping_Service_Account` · `Customer_Address_Label` ·
`Customer_Address_Localization` · `Customer_Address_Market` · `Customer_Address_Notation` ·
`Customer_Address_Notice` · `Customer_Address_Outside_Sales` ·
`Customer_Address_Ship_From_Default` · `Customer_Address_Shipment_Hold` ·
`Customer_Address_Shipping` · `Customer_Address_Shipping_Intransit_Ship_From` ·
`Customer_Address_Street` · `Customer_Address_Tax_Charge` · `Customer_Address_Type` ·
`Customer_Address_Usepoint` · `Customer_Assignment` · `Customer_Attribute` ·
`Customer_Attributes` · `Customer_Attributes_Value` · `Customer_Bank_Account` ·
`Customer_Category` · `Customer_Class` · `Customer_Credit` · `Customer_Group` ·
`Customer_Group_Member` · `Customer_Industry` ·
`Customer_Integrated_Shipping_Service_Account` · `Customer_Link` ·
`Customer_Localization` · `Customer_NAICS` · `Customer_Notation` ·
`Customer_Outside_Sales` ⭐ · `Customer_Parent` · `Customer_Rating` ·
`Customer_Satisfaction` · `Customer_Satisfaction_Level` · `Customer_Satisfaction_Reason` ·
`Customer_Satisfaction_Reasons` · `Customer_Shipper` · `Customer_Shipping` ·
`Customer_Source` · `Customer_Status` · `Customer_Supplier` · `Customer_Type` ·
`Automated_Email_Customer` · `Automated_Email_Customer_Address` ·
`Automated_Email_Customer_Address_Contact` · `Automated_Email_Customer_Contact` ·
`Back_Order` · `Defense_Customer` · `Online_Part_Entry_Customer_Setup` ·
`Online_Part_Entry_Customer_Supplier` · `Status_With_Customer`

### Supplier Master
`Supplier` · `Supplier_Accounting` · `Supplier_Address` ·
`Supplier_Address_Email_List` · `Supplier_Address_Food_Establishment` ·
`Supplier_Address_Localization` · `Supplier_Address_Street` · `Supplier_Address_Type` ·
`Supplier_Annual_Revenue` · `Supplier_Bank_Remittance` · `Supplier_Building_Metric` ·
`Supplier_Buyer` · `Supplier_Capability` · `Supplier_Carrier` · `Supplier_Category` ·
`Supplier_Certification` · `Supplier_Certification_Capability_Group` ·
`Supplier_Certification_List` · `Supplier_Customer` · `Supplier_Deposit_Balance` ·
`Supplier_Document` · `Supplier_Document_Description` · `Supplier_EDI` ·
`Supplier_Group` · `Supplier_Link` · `Supplier_Localization` · `Supplier_Metric` ·
`Supplier_Part` · `Supplier_Part_Cost_Detail` · `Supplier_Part_Level` ·
`Supplier_Part_Ship_Time` · `Supplier_PPM_Category` · `Supplier_Purchasing` ·
`Supplier_Quality` · `Supplier_Rating` · `Supplier_Replication_w` · `Supplier_Scale` ·
`Supplier_Set` · `Supplier_Set_Member` · `Supplier_Shipping` · `Supplier_Sign_Off` ·
`Supplier_Status` · `Supplier_Summary` · `Supplier_Tax_Charge` · `Supplier_Type` ·
`Supplier_Union` · `Master_Supplier_Suppliers` · `Minority` · `Minority_Supplier` ·
`Conditional_Supplier_Certification_Response`

### Costing
`Cost` · `Cost_Account` · `Cost_Accounting_Job` · `Cost_Activity` ·
`Cost_Activity_Container_Transaction` · `Cost_Activity_Generation` ·
`Cost_Activity_Transaction` · `Cost_AP_Link` · `Cost_Detail` · `Cost_Earnings_Code` ·
`Cost_Entry` · `Cost_Expense_Project` · `Cost_Journal` · `Cost_Multi_Out_w` ·
`Cost_Note` · `Cost_Rejection` · `Cost_Service` · `Cost_Snapshot` ·
`Cost_Snapshot_Detail` · `Cost_Sub_Type` · `Cost_Sub_Type_Category` · `Cost_Type` ·
`System_Cost_Point` · `Hourly_Rate` · `Charge` · `Charge_Type`

### Currency & Finance
`Currency` · `Currency_Customer` · `Currency_Exchange` · `Currency_Exchange_Type` ·
`Currency_h` · `Currency_Report_Header` · `Terms` · `Term_Discount_Due_Date` ·
`Term_Due_Date` · `Term_Installment` · `Commercial_Invoice_Payment_Terms` ·
`Credit_Code` · `Credit_Rating` · `Credit_Status` · `Payment_Method` ·
`Payment_Status` · `Posting_Type` · `Tax_ID_Type` · `Tax_Payment_Type` ·
`Third_Party_Tax_Integration_Customer_Address` · `Sales_Account_Type` ·
`Sales_Matrix` · `Sales_Matrix_Account`

### Shipping & Carriers
`Ship_Via` ⭐ · `Ship_Via_Package` · `Ship_Via_Service` ·
`Carrier_Integrated_Shipping_Service` · `Integrated_Shipping_Account` ·
`Integrated_Shipping_Bill_To` · `Integrated_Shipping_Bill_To_Type` ·
`Integrated_Shipping_Provider` · `Integrated_Shipping_Provider_Type` ·
`Integrated_Shipping_Service` · `Integrated_Shipping_Service_Type` ·
`Customer_Address_Integrated_Shipping_Service_Account` ·
`Customer_Integrated_Shipping_Service_Account` ·
`BOL_Default_Settings` · `BOL_Settings` · `FOB` · `Freight_Type` ·
`Fuel_Surcharge` · `Customs` · `Intrastat_Transport_Mode` ·
`Master_Packing_List` · `Packaging` · `Packaging_Type` · `Transit_Date` ·
`Truck_Route` · `Invoice_Delivery`

### Buildings & Locations
`Building` · `Building_Adjustment_Reason` · `Building_Food_Establishment` ·
`Building_Group` · `Building_Group_Member` · `Building_Packaging` ·
`Building_Supplier` · `Building_Type` · `Sub_Building` ·
`Area` · `Area_User` · `Location` · `Location_Class` · `Location_Condition` ·
`Location_Customer` · `Location_Description` · `Location_Group` · `Location_Sequence` ·
`Location_Shipment` · `Location_Shipment_Report` · `Location_Status` · `Location_Type` ·
`Part_Location` · `Zone` · `Zone_Location` · `Zone_Part_Op` ·
`Tank` · `Tank_Lot_Log` · `Tank_Production_Source` · `Tank_Sanitization_Event`

### Departments & Positions
`Department` · `Department_Description` · `Department_Group` ·
`Department_Group_Department` · `Position` · `Position_Category` ·
`Position_Description` · `Position_Group` · `Position_Role` · `Position_Shift` ·
`Position_Tier` · `Position_Track` · `Position_Track_Position` · `Position_Type` ·
`Labor_Status`

### Shifts & Scheduling
`Shift` · `Shift_Attribute` · `Shift_Cycle` · `Shift_Cycle_Setup` · `Shift_Schedule` ·
`schedule` · `Schedule_Day_Of_Month` · `Schedule_Day_Of_Week` ·
`Schedule_Weekday_Of_Month` · `Schedule_Yearly_Day_Of_Month` ·
`Schedule_Yearly_On_Date` · `Work_Date` · `Work_Schedule` · `Work_Schedule_Group` ·
`Work_Shift` · `Dimension` · `Dimension_Period` · `Period` · `Evaluation_Period` ·
`Frequency` · `Time_Details` · `Time_Sheet_Checklist`

### Metrics & KPIs
`Measurable` · `Measurable_Activity` · `Measurable_Building` · `Measurable_Data` ·
`Measurable_Group` · `Measurable_Operation_Type` · `Measurable_Period` ·
`Measurable_Procedure` · `Measurable_Procedure_Run` · `Measurable_Set` ·
`Measurable_Set_Member` · `Measurable_Type` · `Metric` · `Metric_Building` ·
`Metric_Data` · `Metric_Data_Note` · `Metric_Group` · `Metric_Group_Range` ·
`Metric_Module` · `Metric_Query` · `Metric_Range` · `Metric_Source_Data_Attribute` ·
`Goal` · `Objective` · `Objective_Activity` · `Objective_Group` ·
`Objective_Measurable` · `Objective_Priority` · `Objective_Project` ·
`Objective_Status` · `Objective_Type` · `Dashboard_Config` · `Graph_Type` ·
`Rating` · `Rating_Category` · `Scale` · `Scale_Element` · `Scale_Element_Member` ·
`Scale_Generate_Type` · `Scale_Part` · `Scale_Suggestion_Type` · `Segment` ·
`Split` · `Strategic_Plan` · `Advancement_Category`

### Assessment & Capabilities
`Assessment` · `Assessment_Answer` · `Assessment_Choice` · `Assessment_Input_Type` ·
`Assessment_Question` · `Assessment_Section` · `Assessment_Template` ·
`Capability` · `Capability_Building` · `Capability_Description` · `Capability_Group` ·
`Capability_Group_Description` · `Capability_Group_Optional_Cert` ·
`Capability_Group_Type` · `Capability_Group_Type_Conditional_Cert` ·
`Capability_Group_Type_Description` · `Capability_Status` ·
`Sign_Off` · `Sign_Off_Status` · `Auditor`

### Geography & Compliance
`Country` · `Country_Code` · `Country_Code_Type` · `Country_Language` ·
`Region` · `Region_Country` · `Region_Customer_Type` · `State` ·
`NAICS` · `PCN_NAICS` · `Goods_Services_Country_Classification` ·
`Part_Goods_Services_Country_Classification` · `Government_Office_Division` ·
`Government_Office_State` · `Regulatory_Country` · `Regulatory_Rule` ·
`Industry` · `Minority` · `Food_Establishment`

### Reference / System
`AAP_Code` · `Address` · `Address_Group` · `Address_Group_Member` ·
`Agreement` · `Agreement_Status` · `Agreement_Type` ·
`Appointment_Master` · `Appointment_Reservation` ·
`Assigned_To_Group` · `Assignment_Status` ·
`Attribute` · `Attribute_Group` · `Attribute_Value_Type` ·
`Business_Type` · `Class` · `Data_Type` ·
`Lead_Level` · `License` · `Manufacturer` · `Member` ·
`Operations_Schedule_CS_Report_w` · `Order_Fulfillment_Method` ·
`Plexus_Customer_Procedure` · `Procedures` ·
`Project_Status` · `RFQ_Preferred_Delivery` ·
`Responsible_Area` · `Responsible_Area_Description` · `Responsible_Area_Detail` ·
`Responsible_Area_Detail_Description` · `Responsible_Area_Process` ·
`Responsible_Area_Process_Description` ·
`Software` · `Tolerance_Group` · `Tree` · `Tree_Position` ·
`Unit` · `Unit_Conversion` · `Unit_Group` · `Unit_Group_Member` · `Unit_Standard` ·
`Usepoint` · `User_Building` · `Verbiage` · `Verbiage_Description`
