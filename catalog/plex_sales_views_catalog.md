# Plex SQL Dev — Sales Database: Complete View & Procedure Catalog

Generated from the Plex SQL Development Environment tree (Sales → Views & Procedures).

## Key Finding: No `Customer_Order_v_Customer_Order_Line`

That view **does not exist** in this environment. In Plex ERP, customer purchase orders
(= sales orders) live in **`PO`** and **`PO_Line`**.

---

## Recommended Views for the Sales Orders Dataset

| Field Requested | Plex View | Notes |
|---|---|---|
| Date Created | `PO` | PO creation timestamp |
| Date Approved (→ Pending Fulfillment) | `PO_Status` or `PO` | Status-change date |
| Type | `PO_Type`, `PO` | PO type lookup |
| Document/SO Number | `PO` | `PO_No` or key field |
| Quote Number / from-quote flag | `Quote_Order` | Links quote to PO |
| Status | `PO_Status`, `PO` | Current status |
| Customer Name | `PO` | Customer on the order |
| Sales Rep / Sales Rep 2 | `Order_Salesperson` | Salesperson assignments |
| Product / Part # | `PO_Line` | Line-level part info |
| Qty Ordered | `PO_Line` | |
| Price EA | `PO_Line`, `Customer_Price` | Unit price |
| Price Total | `PO_Line` | Line total |
| SO Total | Aggregate on `PO_Line` | Sum per PO |
| Part/Product Type | Join `Part.Part_v_Part` (Part DB) | |
| Part/Product Group | Join `Part.Part_v_Part` (Part DB) | |

---

## All Sales Views (non-`_e`, alphabetical)

> Note: Every view has a companion `_e` (edit) variant. Only base views listed here.

### A
- `Accum_Adjustment`
- `Approval_Role`
- `Assembly_Plant`
- `Attribute`
- `Automotive_Program`

### B
- `Bill_Code`
- `Booking`
- `Booking_Address`
- `Booking_Address_Type`
- `Booking_Container`
- `Booking_Container_Status`
- `Booking_Container_Type`
- `Booking_Seal`
- `Booking_Shipper_Field`
- `Booking_Status`
- `Booking_Type`
- `Booking_Vessel`

### C
- `Cancel_Reason`
- `Catalog`
- `Catalog_Breakpoint_Price`
- `Catalog_Price`
- `Catalog_Price_Account`
- `Catalog_Price_Change_Log`
- `Catalog_Price_Component`
- `Charge_Delete_Pending`
- `Charge_Type_Delete_Pending`
- `Clause`
- `COD_Type`
- `Collection`
- `Collection_Shape_Node`
- `Commission`
- `Commission_Owed`
- `Commission_Payment_Method`
- `Commodity_Code`
- `Configurator_Node`
- `Configurator_Node_Collection`
- `Configurator_Option`
- `Configurator_Option_Pricing_Module`
- `Contract_End_User`
- `Contract_Role`
- `Contract_Worksheet`
- `Contract_Worksheet_Group`
- `Cost_Adjustment`
- `Cross_Section_PCN`
- `Customer_Part_Shipment_d`
- `Customer_Price`

### D
- `Decimal_Equiv`
- `Delivery_Requirement`
- `Design_Parent`
- `Disposition`
- `Division`
- `Documentation`
- `Drop_Ship`

### E
- `Engine`
- `Engine_Attribute_Value`
- `Engine_Version`
- `Escalation`
- `Expedite_Reason`
- `Export_Authorization`
- `Export_Authorization_Customer_Flag_Type`
- `Export_Authorization_Export_Authorization`
- `Export_Authorization_Foreign_Consignee`
- `Export_Authorization_Foreign_End_User`
- `Export_Authorization_Foreign_End_User_Country`
- `Export_Authorization_Foreign_Intermediate_Consignee`
- `Export_Authorization_License`
- `Export_Authorization_Line`
- `Export_Authorization_Line_Shipper_Line`
- `Export_Authorization_Line_Transaction`
- `Export_Authorization_Line_Type`
- `Export_Authorization_Note`
- `Export_Authorization_Quote`
- `Export_Authorization_Status`
- `Export_Authorization_Type`
- `Export_Documentation`
- `Export_Reason`

### F
- `Forecast`
- `Forecast_Cost`
- `Forecast_Cost_Type`
- `Forecast_Group`
- `Forecast_Group_Member`
- `Forecast_Period`
- `Forecast_Period_Exchange_Rate`
- `Forecast_Period_Frequency`
- `Forecast_Row`
- `Forecast_Value`
- `Forecast_Value_Detail`
- `Forecast_Value_Week`
- `Forecast_Version`
- `Forecast_Version_Status`
- `Forecast_Year`
- `Forecast_YTD`
- `Freight_Classification`
- `Freight_Terms`
- `Freight_Terms_Adjustment`
- `Freight_Terms_Adjustment_Customer`
- `Freight_Terms_Adjustment_Customer_Type`
- `Freight_Weight_Class`

### G
- `General_Shipper`
- `General_Shipper_Line`
- `General_Shipper_Status`
- `General_Shipper_Type`
- `Grade_Type_Part_Group_Minimum_Markup`
- `Grade_Type_Part_Group_Quote_Goal`

### H
- `Harmonized_Tariff_Code`

### I
- `Incentive_Penalty`
- `Incentive_Quota_Type`
- `INCO_Terms`
- `Integrated_Shipper`
- `IRN_License`

### J (JIS — Just-In-Sequence)
- `JIS_Customer_Address_Setup`
- `JIS_Demand`
- `JIS_Demand_Detail`
- `JIS_Demand_Detail_Message`
- `JIS_Demand_Detail_Release`
- `JIS_Demand_Format`
- `JIS_Demand_Format_Column`
- `JIS_Demand_Format_Constant`
- `JIS_Demand_Format_PO_Rule`
- `JIS_Demand_Format_Release_Rule`
- `JIS_Demand_Format_Type`
- `JIS_Kit`
- `JIS_Kit_Status`
- `JIS_Line_Sequence_Setup`
- `JIS_Line_Sequence_Setup_Kit_Name_Rule`
- `JIS_Line_Sequence_Setup_Kit_Rule`
- `JIS_Line_Sequence_Setup_Part`
- `JIS_Line_Sequence_Setup_Part_Field`
- `JIS_Line_Sequence_Setup_Rack_Cell`
- `JIS_Line_Sequence_Setup_Rack_Layer`
- `JIS_Line_Sequence_Setup_Rack_Rule`
- `JIS_Line_Sequence_Setup_Sequence_Format`
- `JIS_Manifest_Sequence`
- `JIS_Model`
- `JIS_Model_Part`
- `JIS_Pack_Audit_Level`
- `JIS_PO_Creation_Type`
- `JIS_Production_Recording_Type`
- `JIS_Rack`
- `JIS_Rack_Status`
- `JIS_Release`
- `JIS_Release_Container`
- `JIS_Release_Status`
- `JIS_Scan_Type`
- `JIS_Sequence_Packing_Type`
- `JIS_Sequencing_Source`
- `JIS_Transform_Expression`
- `JIS_Transform_Expression_Parameter`
- `JIS_Transform_Expression_Parameter_Attribute`
- `JIS_Transform_Function`
- `JIS_Transform_Function_Parameter`
- `JIS_Transform_Function_Parameter_Attribute`

### K
- `Kitting_Sheet`
- `Kitting_Sheet_Release`

### L
- `Late_Delivery_Reason`
- `Lead_Source`
- `Lead_Source_Type`
- `Line_Sequence_Rack`
- `Line_Sequence_Rack_Release`
- `Line_Sequence_Setup`
- `Loaded_Container`
- `Lookup_Table`
- `Lookup_Table_Values`

### M
- `Market1`
- `Market2`
- `Market3`
- `Master_Price_PO_Customer_PO`
- `Material`
- `Milk_Run`
- `Milk_Run_Status`
- `Mix_And_Match_Price_Group`
- `Mix_And_Match_Price_Group_Customer`
- `Mix_And_Match_Price_Group_Customer_Type`
- `Mix_And_Match_Price_Group_Part`
- `Multi_Entity_PO_Line_Link`

### N
- `No_Quote_Reason`
- `Note`

### O
- `Object`
- `Object_Variable`
- `OEM`
- `OEM_Plant`
- `Opportunity`
- `Opportunity_Activity`
- `Opportunity_Building`
- `Opportunity_Competitor`
- `Opportunity_Contact`
- `Opportunity_Contract`
- `Opportunity_Customer`
- `Opportunity_Group`
- `Opportunity_History`
- `Opportunity_Level`
- `Opportunity_Meeting`
- `Opportunity_Note`
- `Opportunity_Partner`
- `Opportunity_Plexus_User`
- `Opportunity_Quote`
- `Opportunity_Status`
- `Opportunity_Target`
- `Opportunity_Type`
- `Option_Type`
- `Order_Charge`
- `Order_Charge_Change`
- `Order_Contract`
- `Order_Contract_Note`
- `Order_Contract_Renewal_Fee_Type`
- `Order_Contract_Type`
- `Order_Note`
- `Order_Salesperson` ⭐
- `Order_Salesperson_Change`
- `Order_Source_Inspection`

### P
- `Packaging_Type`
- `Part_Configurator`
- `Part_Configurator_Conditional_Formula`
- `Part_Configurator_Debug`
- `Part_Configurator_Freight_Location`
- `Part_Configurator_Material`
- `Part_Configurator_Material_Pricing_Module`
- `Part_Configurator_Node`
- `Part_Configurator_Node_Variable`
- `Part_Configurator_Note`
- `Part_Configurator_Option`
- `Part_Configurator_Price`
- `Part_Configurator_Pricing_Module`
- `Part_Configurator_Pricing_Type`
- `Part_Configurator_Quantity`
- `Part_Configurator_Unit`
- `Part_Configurator_Washer`
- `Part_Configurator_Washer_Default_Pricing_Module`
- `Part_Configurator_Washer_Option`
- `Part_Configurator_Washer_Pricing`
- `Part_Configurator_Washer_Pricing_Module`
- `Part_Configurator_Washer_Type`
- `Part_Product_Type_Customer`
- `Pick_Schedule`
- `Pick_Schedule_Container`
- `Pick_Schedule_User`
- `Pickup_Location`
- `Platform`
- `Platform_Status`
- `PO` ⭐ (Sales Order header)
- `PO_Attributes`
- `PO_Bill_To`
- `PO_Category`
- `PO_Change`
- `PO_Confirmation`
- `PO_Contact`
- `po_contract`
- `PO_Contract_End_User`
- `PO_Contract_Funding`
- `PO_Contract_Funding_Type`
- `PO_Contract_Requirement`
- `PO_Contract_Team_Member`
- `PO_Contract_Worksheet`
- `PO_EDI_Attribute`
- `PO_Export_Documentation`
- `PO_Export_License`
- `PO_Generic_Shipping_Document`
- `PO_Hold`
- `PO_Incentive_Penalty`
- `PO_Instance`
- `PO_Line` ⭐ (Sales Order line items — part, qty, price)
- `PO_Line_Assembly_Sequence`
- `PO_Line_Attributes`
- `PO_Line_BOM`
- `PO_Line_BOM_Action`
- `PO_Line_Budget`
- `PO_Line_Change`
- `PO_Line_Localization`
- `PO_Line_Note`
- `PO_Line_Preprint_Label`
- `PO_Line_Price_Adjustment`
- `PO_Part_Product_Type`
- `PO_Price_Adjustment`
- `PO_Prime_Contract`
- `PO_Ship_To`
- `PO_Ship_To_Localization`
- `PO_Shipping_Inspection`
- `PO_Shipping_Location`
- `PO_Status`
- `PO_Type`
- `PO_Type_Part_Product_Group`
- `Price`
- `Price_Account`
- `Price_Adjustment`
- `Price_Adjustment_Customer`
- `Price_Adjustment_Customer_Address`
- `Price_Adjustment_Type`
- `Price_Adjustment_Type_Customer`
- `Price_Adjustment_Type_PO`
- `Price_Change`
- `Price_Change_Reason`
- `Price_Charge`
- `Price_Charge_Change`
- `Price_Component`
- `Price_Element`
- `Price_Element_Detail`
- `Price_Element_Log`
- `Price_Index`
- `Price_Index_Formula`
- `Price_Index_Generate_Log`
- `Price_Index_Generate_Log_PO_Line`
- `Price_Index_Generate_Log_Price`
- `Price_Index_Price`
- `Price_Point`
- `Price_Source`
- `Price_Type`
- `Price_Type_Config`
- `Pricing_Module`
- `Pricing_Module_Conditional_Formula`
- `Prime_Contract_Type`
- `Priority`
- `Procurement_Type`
- `Product_Destination`
- `Profit_Point`

### Q
- `Question`
- `Quote` ⭐ (Quote linked to PO via Quote_Order)
- `Quote_Activity`
- `Quote_Approval`
- `Quote_Approval_Status`
- `Quote_Charge`
- `Quote_Clause`
- `Quote_Constant`
- `Quote_Constant_Default`
- `Quote_Contact`
- `Quote_Cost`
- `Quote_Cost_Component_Type`
- `Quote_Cost_Element`
- `Quote_Cost_Element_Default`
- `Quote_Cost_Other`
- `Quote_Cost_Other_Component`
- `Quote_Cost_Status`
- `Quote_Cost_Subtype`
- `Quote_Cost_Summary`
- `Quote_Cost_Type`
- `Quote_Cost_Type_Rate`
- `Quote_Currency`
- `Quote_Customer_Program`
- `Quote_Delivery_Method`
- `Quote_Desirability`
- `Quote_Difficulty`
- `Quote_Disposition`
- `Quote_Documentation`
- `Quote_Element_Option`
- `Quote_Equipment`
- `Quote_Equipment_Component`
- `Quote_Equipment_Component_Type`
- `Quote_Equipment_Modification`
- `Quote_Event`
- `Quote_Exception`
- `Quote_Exception_Tolerance_Symbol`
- `Quote_Group`
- `Quote_Group_Charge_Type`
- `Quote_Iteration_Attribute`
- `Quote_Meeting`
- `Quote_No_Quote_Reason`
- `Quote_Operation`
- `Quote_Order` ⭐ (links Quote → PO)
- `Quote_Part`
- `Quote_Part_Attributes`
- `Quote_Part_Build`
- `Quote_Part_Building`
- `Quote_Part_Building_Group`
- `Quote_Part_Charge`
- `Quote_Part_Component`
- `Quote_Part_Cost`
- `Quote_Part_Date`
- `Quote_Part_Dimension`
- `Quote_Part_Forecast`
- `Quote_Part_Material_Cost`
- `Quote_Part_Note`
- `Quote_Part_Note_Group`
- `Quote_Part_Note_SubGroup`
- `Quote_Part_Note_Type`
- `Quote_Part_Operation_Cost`
- `Quote_Part_Packaging`
- `Quote_Part_Plexus_User`
- `Quote_Part_Region`
- `Quote_Part_Release`
- `Quote_Part_Req`
- `Quote_Part_Req_Line`
- `Quote_Part_Scenario`
- `Quote_Part_Ship_To`
- `Quote_Part_Status`
- `Quote_Part_Tool`
- `Quote_Part_Tooling`
- `Quote_Price`
- `Quote_Price_Attributes`
- `Quote_Price_Cost`
- `Quote_Price_Group`
- `Quote_Price_Operation`
- `Quote_Price_Type`
- `Quote_Price_Year`
- `Quote_Print_Option`
- `Quote_Probability`
- `Quote_Quantity_Default`
- `Quote_Question`
- `Quote_Quote_Constant`
- `Quote_Reason`
- `Quote_Recipient`
- `Quote_Result`
- `Quote_Role`
- `Quote_Role_Distribution`
- `Quote_Role_User`
- `Quote_Schedule`
- `Quote_Service`
- `Quote_Status`
- `Quote_Status_Change`
- `Quote_Summary_Definition`
- `Quote_Summary_Definition_Line`
- `Quote_Transport`
- `Quote_Type`
- `Quote_Type_Clause`
- `Quote_Year_Quote_Constant_Default`

### R
- `Range_Table_Value`
- `Release` ⭐ (delivery requirement against PO line)
- `Release_Allocation`
- `release_attributes`
- `Release_Change`
- `Release_Container`
- `Release_EDI_Attribute`
- `Release_EUN`
- `Release_Job`
- `release_note`
- `Release_Source`
- `Release_Status`
- `Release_Type`
- `Request`
- `Request_Group`
- `Request_Line`
- `Request_Status`
- `Request_Type`
- `Return`
- `Return_AR_Invoice`
- `Return_Category`
- `Return_Component_Part`
- `Return_Container`
- `Return_Line`
- `Return_Problem`
- `Return_Reason`
- `Return_Status`
- `Return_Type`
- `Revenue_Rank`

### S
- `Sales_Offer`
- `Sales_Offer_Container`
- `Sales_Parent`
- `Scheduled_Release`
- `Scrap_Transaction`
- `Scrap_Type`
- `Security_Classification`
- `Service`
- `Service_Category`
- `Service_Group`
- `Service_Status`
- `Service_Type`
- `Shape_Node`
- `Shape_Node_Branch`
- `Shape_Node_Pricing_Module`
- `Shape_Node_Pricing_Type`
- `Shape_Node_Type`
- `Ship_Document`
- `Shipment_Notification`
- `Shipper` ⭐ (shipment header)
- `Shipper_AR_Invoice`
- `Shipper_Attributes`
- `Shipper_Charge`
- `Shipper_Container`
- `Shipper_Container_FIFO_Override`
- `Shipper_Delivery`
- `Shipper_Delivery_Status`
- `Shipper_Line` ⭐ (what shipped per line)
- `Shipper_Line_Box_Component`
- `Shipper_Line_Freight`
- `Shipper_Line_Package_Item`
- `Shipper_Line_Price_Adjustment`
- `Shipper_Line_Price_Component`
- `Shipper_Line_Release`
- `Shipper_Localization`
- `Shipper_Note`
- `Shipper_PO_Charge`
- `Shipper_Ship_Container`
- `Shipper_Sproc_Log1`
- `Shipper_Sproc_Log2`
- `Shipper_Status`
- `Shipper_Tracking_No`
- `Shipping_Date`
- `Shipping_Date_Customer`
- `Shipping_Date_Customer_Address`
- `Shipping_Dock`
- `Shipping_Inspection`
- `Shipping_Location`
- `Special_Price_Request`
- `Special_Price_Request_Line`
- `Special_Price_Request_Status`
- `Special_Price_Request_Type`
- `Special_Pricing`
- `Special_Pricing_Cost`
- `Special_Pricing_Cost_Type`
- `Special_Pricing_Markup_Type`
- `Special_Pricing_Pricing_Module`
- `Special_Pricing_Setup`
- `Special_Pricing_Type`
- `Standard_Note`
- `Standard_Note_Type`
- `Standard_Order_Note`
- `Standard_Shipper_Note`
- `Strategic_Degree`
- `Strategic_Mode`
- `Strategic_Rating`
- `Strategic_Role`

### T
- `Toyota_SCS_Kanban`
- `Toyota_SCS_Skid`
- `Trans_Mode`
- `Transfer_Order`
- `Transfer_Order_Status`
- `Transfer_Order_Type`
- `Transmission`
- `Transmission_Attribute_Value`
- `Transmission_Version`
- `Transport_Method`
- `Truck`
- `Truck_Attributes`
- `Truck_Category`
- `Truck_Freight`
- `Truck_Status`
- `Truck_Type`

### V
- `Variable`
- `Vehicle`
- `Vehicle_Attribute_Value`
- `Vehicle_Production`
- `Vehicle_Type`

### W
- `Warranty`
- `Warranty_Type`
- `Web_Contact`
- `Web_Contact_Lead_Source`
- `Web_Contact_Status`
- `Weight_Config`
- `Weight_Config_Dimension`
- `Weight_Config_Element`

---

## Sales Procedures

- `Sales_p_Automatic_Price_Lookup_Get`
- `Sales_p_Bookings_Report_Get`
- `Sales_p_Container_Truck_Check`
- `Sales_p_Delivery_Performance_Report_Get`
- `Sales_p_Demand_Caster_Release_Export`
- `Sales_p_Demand_Caster_Release_Offset`
- `Sales_p_Demand_Caster_Shipper_Release_Offset`
- `Sales_p_Invoice_per_Shipper_AR_Invoice_Void_Get`
- `Sales_p_Invoice_per_Shipper_Get`
- `Sales_p_Master_Price_Default_Order_Unit_Get`
- `Sales_p_Part_Inventory_Unit_Get`
- `Sales_p_PO_Status_Default_Get`
- `Sales_p_PO_Type_Default_Get`
- `Sales_p_PO_Type_Ecommerce_Get`
- `Sales_p_Production_Jobs_Get`
- `Sales_p_Quote_Part_Routing_Get`
- `Sales_p_Release_Part_Quantity_Ready_Get`
- `Sales_p_Release_Part_Quantity_Scheduled_Get`
- `Sales_p_Release_Part_Weight_Get`
- `Sales_p_Release_Price_Available_Get`
- `Sales_p_Release_Schedule_Credit_Limit_Check_Get`
- `Sales_p_Release_Status_Default_Get`
- `Sales_p_Release_Trucks_Get`
- `Sales_p_Report_Customer_Schedule_Analysis_Periods_Get`
- `Sales_p_Report_Open_Releases_Get`
- `Sales_p_Report_Open_Releases_Job_Get`
- `Sales_p_Report_Open_Releases_Wrapper_Get`
- `Sales_p_Retail_Container_Split_Load_Validate`
- `Sales_p_Retail_Shipper_Commit_Validate`
- `Sales_p_Retail_Shipper_Get`
- `Sales_p_Retail_Shipper_Label_Get`
- `Sales_p_Retail_Shipper_Line_Label_Get`
- `Sales_p_Retail_Shipper_Lines_Get`
- `Sales_p_Shipper_Active_Get`
- `Sales_p_Shipper_Document_Get`
- `Sales_p_Shipper_Document_Part_Summary_Get`
- `Sales_p_Shipper_Instance_Errors_Get`
- `Sales_p_Shipper_Integrated_Shipping_Service_LTL_Get`
- `Sales_p_Shipper_Line_Shipment_Price_Data_Get`
- `Sales_p_Shipper_Master_Unit_Shipping_Parcels_Get`
- `Sales_p_Shipper_Master_Units_Detail_Get`
- `Sales_p_Shipper_PO_No_Get`
- `Sales_p_Shipper_Releases_Get`
- `Sales_p_Shipper_Ship_Fields_Get`
- `Sales_p_Shipper_Ship_Invoice_AR_Account_Get`
- `Sales_p_Shipper_Ship_Invoice_Line_Revenue_Account_Get`
- `Sales_p_Shipper_Status_Shipped_Get`
- `Sales_p_Shippers_Get`
- `Sales_p_Shippers_Get_All`
- `Sales_p_Shipping_Dates_Get`
- `Sales_p_Shipping_Outlook_Components_Get`
- `Sales_p_Super_Staging_Get`
- `Sales_p_Truck_Document_Get`
- `Sales_p_Truck_Freight_Bill_To_Address_Get`
- `Sales_p_Truck_Mill_Weight_Summary_Get`
- `Sales_p_Truck_Ship_From_Get`

---

## Cross-Database Joins Needed

For the full 16-field sales orders dataset, join these views in BigQuery after pulling raw tables:

| Data | Database | View |
|---|---|---|
| SO header (dates, type, status, customer) | Sales | `PO` |
| SO lines (part, qty, price) | Sales | `PO_Line` |
| Sales rep assignments | Sales | `Order_Salesperson` |
| Quote linkage | Sales | `Quote_Order` |
| Part type & group | Part | `Part_v_Part` |
| Customer name detail | Common or Sales | TBD — check Common DB |
