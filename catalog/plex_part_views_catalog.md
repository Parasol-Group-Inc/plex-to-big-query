# Plex SQL Dev — Part Database: View Catalog

> **778 base views** confirmed from tree HTML (corrected 2026-06-29).
> ODBC prefix: `Part_v_{ViewName}` (e.g. `Part_v_Part`, `Part_v_Customer_Part_Price`)

## Purpose

Plex Part is the core manufacturing database: part master, BOM, routing, operations,
containers, inventory, jobs, tools, workcenters, and — critically — customer part
pricing. This is a large, central module.

## Confirmed Live (2026-08-11) — MFG job-schedule fields

Queried against `vox.test.odbc.plex.com`, driven by mapping the manually
maintained "MFG Job Schedule" tracker to real Plex views. All exist; empty on
this tenant except lookups noted:

- **Lot**: `Part_v_Lot` (`Lot_No`, `Part_Key`, `Manufactured_Date`,
  `Supplier_Lot_No`), `Part_v_Lot_Attribute`, `Part_v_Lot_Shelf_Life`
  (`Shelf_Life_Type_Key`, `Lot_Shelf_Life` — likely the expiration-date
  source), `Part_v_Lot_Trace`, `Part_v_Lot_Format` (**has rows**).
  `Part_v_Job.Lot_Key` FK links a job straight to its lot.
- **BOM / formulation**: `Part_v_BOM` (**has rows** — `Component_Part_Key`,
  `Quantity`, `Depletion_Unit` per part/operation; this is the likely source
  for "MG Per Cap"-style dosage, via component quantity), `Part_v_BOM_Yield_Factor`
  (`Yield_Percentage`, `Fixed_Loss`), `Part_v_Cost_BOM` (**has rows**).
- **Attributes**: `Part_v_Part_Attribute` (**has rows** — generic
  `Attribute_Key`/`Value` pairs, likely where "Cap Specs" like "00 Veggy"
  live) and `Part_v_Part_Attributes` (**has rows** — fixed-schema part
  properties, different table despite the near-identical name).
- **Containers / on-hand inventory**: `Part_v_Container` ⭐ — the real
  on-hand-inventory carrier (see `catalog/plex_warehouse_views_catalog.md`
  "Confirmed Live" note — this is where "Available Inventory" actually
  comes from, not a Warehouse-module view). `Part_v_Container_Status`
  **has rows** (OK/Defective/Scrap/Rejectable flags for filtering which
  containers count as available stock). `Part_v_Container_Track`,
  `Part_v_Inventory_Allocation`, `Part_v_Inventory_Classification`,
  `Part_v_Inventory_Receipt`, `Part_v_Active_Rejection_Container`,
  `Part_v_FIFO_Container` also confirmed to exist.

## ⭐ Critical for Sales Orders Pipeline

| ODBC Name | Purpose |
|---|---|
| `Part_v_Part_Product_Type` | Part product type label — confirmed here (NOT in Common) |
| `Part_v_Part_Product_Group` | Part product group label — confirmed here (NOT in Common) |
| `Part_v_Customer_Part_Price` | **Price EA per customer-part** — join via `Sales_v_PO_Line.Customer_Part_Key` |
| `Part_v_Customer_Part` | Customer-facing part number, description, unit |
| `Part_v_Part` | Part master (already in use — confirmed working) |

**Pricing query:**
```sql
SELECT TOP 3 * FROM Part_v_Customer_Part_Price
-- join: Sales_v_PO_Line.Customer_Part_Key = Part_v_Customer_Part_Price.Customer_Part_Key
```

---

## Views by Category

### Part Master ⭐
`Part` ⭐ · `Part_Attribute` · `Part_Attributes` · `Part_Building` · `Part_Charge` ·
`Part_Checklist` · `Part_Container_Type` · `Part_Control_Level` ·
`Part_Coordinate` · `Part_Coordinate_Setup` · `Part_Cost` · `Part_Cost_History` ·
`Part_Detail` · `Part_Estimate` · `Part_Group` · `Part_Image` ·
`Part_Inventory_Attributes` · `Part_Localization` · `Part_Material` ·
`Part_Node_Heirarchical` · `Part_Node_Heirarchical_Xml` · `Part_Op_Type` ·
`Part_Piece_Setup` · `Part_Planning_Parameters` · `Part_Plexus_User` ·
`Part_Prefix` · `Part_Price_Element` · `Part_Priority` ·
`Part_Product_Group` ⭐ · `Part_Product_Type` ⭐ ·
`Part_Production_Attributes` · `Part_Purchasing_Attributes` ·
`Part_Receiving_Attributes` · `Part_Revision` · `Part_Scheduling_Attributes` ·
`Part_Shelf_Life` · `Part_Shipping_Attributes` · `Part_Source` · `Part_Status` ·
`Part_Sub_Type` · `Part_Substitution` · `Part_Template` · `Part_Type` ·
`Part_Type_Sub_Type` · `Part_Unit` · `Master_Part` · `Master_Part_Share` ·
`Master_Part_Type` · `Master_Part_Type_Effective_Date` · `Linked_Part` ·
`Part_Lot_Format` · `Part_Shelf_Life` · `Allowable_Revision` · `Allowable_Value`

### Customer Part ⭐
`Customer_Part` ⭐ · `Customer_Part_Attributes` · `Customer_Part_Drop_Ship` ·
`Customer_Part_EDI_Attribute` · `Customer_Part_EDI_Attribute_Type` ·
`Customer_Part_EPW_Backup` · `Customer_Part_Inventory_Attributes` ·
`Customer_Part_Lot_Attribute` · `Customer_Part_Lot_Attribute_List_Specification` ·
`Customer_Part_Lot_Attribute_Numeric_Specification` ·
`Customer_Part_Lot_Attribute_Report` · `Customer_Part_Lot_Attribute_Test_Method` ·
`Customer_Part_Lot_Attribute_Test_Result` ·
`Customer_Part_Lot_Attribute_Text_Specification` ·
`Customer_Part_Lot_Attribute_UAS_Specification` ·
`Customer_Part_National_Stock_No` · `Customer_Part_Note` ·
`Customer_Part_Package_Configuration` · `Customer_Part_Price` ⭐ ·
`Customer_Part_Product_Type` · `Customer_Part_Program` ·
`Customer_Part_Program_Forecast` · `Customer_Part_Ship_Doc` ·
`Customer_Part_Type` · `Customer_Part_Vehicle` ·
`Customer_Approval_Status` · `Customer_Cost_Algorithm` · `Customer_Dock_Code` ·
`Customer_Inventory` · `Customer_Inventory_Setup` · `Customer_Inventory_Usage` ·
`Customer_Receipt` · `Customer_Receipt_Container` ·
`Defense_Customer_Part` · `Defense_Part`

### BOM (Bill of Materials)
`BOM` · `BOM_Flat_BOM` · `BOM_History` · `BOM_Manufacturer_Part` ·
`BOM_Workcenter_Source_Position` · `BOM_Yield_Factor` · `Flat_BOM` ·
`Flat_Tool_Sub` · `Cost_BOM` · `Cost_BOM_History` ·
`Answer_BOM` · `Answer_BOM_Group` · `Answer_Combo_Answers` ·
`Answer_Combo_BOM` · `Answer_Operation`

### Container & Inventory
`Container` · `Container_Acceptance_Sampling` · `Container_Action_Authorization` ·
`Container_Attributes` · `Container_Attributes_Change` · `Container_Authorization` ·
`Container_Certification` · `Container_Change` · `Container_Change2` ·
`Container_Contact` · `Container_Core` · `Container_Cost_History` ·
`Container_Counter` · `Container_Country` · `Container_EDI_Code` ·
`Container_EUN` · `Container_Failure_Reason` · `Container_Failure_Status` ·
`Container_Heat` · `Container_Job_Template` · `Container_Label` ·
`Container_Last_Action` · `Container_Mill_Status` · `Container_Package_Log` ·
`Container_Part_Scan_Log` · `Container_Quality` · `Container_Quality_Trace` ·
`Container_Receipt` · `Container_RFID` · `Container_Scrap_Allocation` ·
`Container_Shelf_Life` · `Container_Status` · `Container_Trace` ·
`Container_Trace_Disassembly` · `Container_Track` ·
`Container_Track_Adjustment_Reason` · `Container_Transaction` ·
`Container_Type` · `Container_Type_Group` · `Container_Type_Item` ·
`FIFO_Container` · `Active_Rejection_Container` · `Cargo_Container` ·
`Cargo_Container_Shipper` · `Cargo_Container_Type` · `Return_Container` ·
`Ret_Container_EDI_Code` · `Inventory_Allocation` · `Inventory_Classification` ·
`Inventory_Receipt` · `Inventory_Receipt_Container` · `Inventory_Receipt_Lot` ·
`Inventory_Shipment` · `Inventory_Shipment_Container` ·
`Inventory_Shipment_Depletion` · `Inventory_Snapshot` ·
`Inventory_Snapshot_Container` · `Inventory_Type` ·
`Cycle_Count_Type` · `Cycle_Frequency` · `Cycle_Inventory` ·
`Cycle_Inventory_Container` · `Cycle_Inventory_Item_Location` ·
`Cycle_Inventory_Tool_Inventory` · `Cycle_Parameter` · `Cycle_Status` ·
`Current_Inventory_Code` · `Snapshot` · `Snapshot_Container` ·
`Snapshot_Cost_BOM` · `Snapshot_Cost_Component` · `Snapshot_Cost_Sub_Type_Breakdown`

### Costing
`Cost_By_Size` · `Cost_Component` · `Cost_Component_Formula` ·
`Cost_Component_Formula_Breakdown` · `Cost_Component_Formula_Element` ·
`Cost_Component_History` · `Cost_Component_Workcenter` ·
`Cost_Component_Workcenter_History` · `Cost_Model` · `Cost_Model_Algorithm` ·
`Cost_Recalc_History` · `Cost_Rollup` · `Cost_Sub_Type_Breakdown` ·
`Cost_Sub_Type_Breakdown_History` · `Cost_Workcenter` · `Fixed_Overhead_Cost` ·
`Overhead_By_Volume` · `Material_Cost` · `Material_Cost_History` ·
`Split_Merge_Cost_Log` · `Standard_Value_Analysis`

### Delivery Schedule
`Delivery_Area` · `Delivery_Area_Location` · `Delivery_Area_Part` ·
`Delivery_Method` · `Delivery_Route` · `Delivery_Route_Type` ·
`Delivery_Schedule` · `Delivery_Schedule_Completion_Code` ·
`Delivery_Schedule_Container` · `Delivery_Schedule_Demand_Status` ·
`Delivery_Schedule_Group` · `Delivery_Schedule_Status` · `Delivery_Schedule_Type` ·
`Supplier_Delivery_Schedule` · `Supplier_Delivery_Schedule_Type`

### ECR (Engineering Change Request)
`ECR` · `ECR_Accounting_Job` · `ECR_Building` · `ECR_Cost_Function` ·
`ECR_Cost_Function_Title` · `ECR_Cost_Reduction` · `ECR_Doc` · `ECR_Effect` ·
`ECR_Group` · `ECR_Iteration` · `ECR_Net_Present_Value` · `ECR_Note` ·
`ECR_Part` · `ECR_Part_Inventory` · `ECR_Priority` · `ECR_Reason` ·
`ECR_Revision_Type` · `ECR_Status` · `ECR_Tool` · `ECR_Tool_Assembly` ·
`ECR_Tool_Disposition` · `ECR_Training` · `ECR_Type` · `ECR_Workcenter`

### Job / Production
`Job` · `Job_Allocation` · `Job_Attributes` · `Job_Attributes_Status` ·
`Job_Bom` · `Job_BOM_Manufacturer_Part` · `Job_BOM_Workcenter_Source_Position` ·
`Job_Budget` · `Job_Budget_Section` · `Job_Cert` · `Job_Distribution` ·
`Job_EUN` · `Job_Material` · `Job_Op` · `Job_Op_Approved_Workcenter` ·
`Job_Op_Batch` · `Job_Op_Batch_Container` · `Job_Op_Batch_Status` ·
`Job_Op_Batch_Workcenter` · `Job_Op_Checksheet` · `Job_Op_Complete_w` ·
`Job_Op_Completed_Reason` · `Job_Op_Status` · `Job_Op_Tool_Assembly` ·
`Job_Op_Type` · `Job_Production_Attribute` · `Job_Scenario_Detail` ·
`Job_Set` · `Job_Set_Member` · `Job_Status` · `Job_Status_Next` ·
`Job_Template` · `Job_Template_Cost` · `Job_Template_Status` · `Job_Type` ·
`Job_Work_Step` · `Job_Work_Step_Operation_Process_Step_Tool` ·
`Job_Work_Step_Tool` · `Job_Work_Step_Type` · `Production` · `Production_Batch` ·
`Production_Batch_Detail` · `Production_Part_Material` · `Production_PLC_Response` ·
`Production_Reapplication` · `Production_Reapplication_Log` · `Production_Tool_Status` ·
`Build` · `Build_Access` · `Build_Answer` · `Build_Answer_BOM` ·
`Build_Answer_Combo` · `Build_Answer_Operation` · `Build_Section_Note` ·
`Build_Status` · `Build_Template` · `Build_Template_Answer` ·
`Build_Template_Answer_Combo` · `Build_Template_Answer_Off` ·
`Build_Template_Answer_Part_Component` · `Build_Template_Page` ·
`Build_Template_Part` · `Build_Template_QA_Relation` · `Build_Template_Question` ·
`Build_Template_Section` · `Build_Template_Subsection` · `Build_Template_Type`

### Kanban & Kitting
`Kanban_Rack` · `Kanban_Rack_Leveling_Method` · `Kanban_Rack_Leveling_Method_Days` ·
`Kanban_Status` · `Kit` · `Kit_Component` · `Kit_Component_Container` ·
`Kit_Component_Job_Op` · `Kit_Recommendation` · `Kit_Recommendation_BOM` ·
`Kit_Recommendation_Item` · `Kit_Status` · `Kitting_Allocation_w` ·
`Kitting_Production_Log` · `Kitting_Production_w`

### Labor & Workforce
`Labor_Capacity` · `Shop_Assignment` · `Shop_Assignment_Employee` ·
`Operator` · `Operator_Schedule` · `Resource` · `Resource_Shift`

### Lot Traceability
`Lot` · `Lot_Attribute` · `Lot_Attribute_EDI_Group` · `Lot_Attribute_EDI_Group_Member` ·
`Lot_Attribute_Group` · `Lot_Attribute_Group_Report_Section` ·
`Lot_Attribute_Group_Report_Section_Customer_Part_Override` ·
`Lot_Attribute_Numeric_Value` · `Lot_Attribute_Report_Display_Type` ·
`Lot_Attribute_Report_Type` · `Lot_Attribute_Template` · `Lot_Attribute_Test_Method` ·
`Lot_Attribute_Test_Result` · `Lot_Attribute_Text_Value` ·
`Lot_Attribute_UAS_Validation_Type` · `Lot_Attribute_Value_Change_Log` ·
`Lot_Attributes_Part_Conformance_w` · `Lot_Format` · `Lot_Shelf_Life` · `Lot_Trace` ·
`Part_Lot_Attribute` · `Part_Lot_Attribute_Display_Type` ·
`Part_Lot_Attribute_List_Specification` · `Part_Lot_Attribute_List_Value` ·
`Part_Lot_Attribute_Numeric_Specification` · `Part_Lot_Attribute_Numeric_Value` ·
`Part_Lot_Attribute_Report` · `Part_Lot_Attribute_Specification` ·
`Part_Lot_Attribute_Test` · `Part_Lot_Attribute_Test_Method` ·
`Part_Lot_Attribute_Test_Result` · `Part_Lot_Attribute_Text_Specification` ·
`Part_Lot_Attribute_Text_Value` · `Part_Lot_Attribute_UAS_Record` ·
`Part_Lot_Attribute_UAS_Specification` · `Part_Lot_Attribute_UAS_Value` ·
`Part_Lot_Attribute_Value_Entry` · `Part_Lot_Attributes_Snapshot` ·
`System_Lot_Attribute_Group_Report_Display_Type` · `System_Lot_Event` ·
`System_Part_Lot_Attribute_Specification_Mapping`

### Manufacturer Parts
`Manufacturer_Part` · `Manufacturer_Part_Status` · `Manufacturer_Part_Supplier` ·
`BOM_Manufacturer_Part`

### MRP / Demand
`MRP_Demand` · `MRP_Demand_Forecast` · `MRP_Demand_Info_w` ·
`MRP_Demand_Inventory` · `MRP_Demand_Log` · `MRP_Demand_Type`

### Operation / Routing
`Operation` · `Operation_Attribute` · `Operation_Container_Status` ·
`Operation_Costing` · `Operation_Type` · `Operation_Type_Description` ·
`Operation_Type_Suffix` · `Next_Operation` · `Process_Step` ·
`Routing_Version` · `Routing_Version_Status` ·
`Work_Step` · `Work_Step_Operation` · `Work_Step_Operation_Process_Step` ·
`Work_Step_Priority` · `Part_Operation` · `Part_Operation_Approved_Container` ·
`Part_Operation_Approved_Equipment` · `Part_Operation_Attribute` ·
`Part_Operation_Cost` · `Part_Operation_Cost_History` · `Part_Operation_History` ·
`Part_Operation_Lot_Attribute_Inheritance` · `Part_Operation_Lot_Date_Inheritance` ·
`Part_Operation_Lot_No_Inheritance_Override` ·
`Part_Operation_Lot_No_Inheritance_Override_Component_Part` ·
`part_operation_planning_parameters` · `Part_Operation_Resource` ·
`Part_Operation_Return_Operation` · `Part_Work_Step` · `Part_Work_Step_BOM` ·
`Part_Work_Step_Dependent_Part` · `Part_Work_Step_Dependent_Part_Type` ·
`Part_Work_Step_Operation_Process_Step` · `Part_Work_Step_Operation_Process_Step_BOM` ·
`Part_Work_Step_Operation_Process_Step_Tool` · `Part_Work_Step_Tool` ·
`Part_Work_Step_Type` · `Quote_Operation` · `Quote_Tooling`

### APS (Advanced Planning & Scheduling)
`APS_Capacity_Resource` · `APS_Capacity_Workcenter` · `APS_Delay` · `APS_Launch` ·
`APS_Launch_Item` · `APS_Launch_Item_Run` · `APS_Launch_Log` · `APS_Sequence` ·
`APS_Sequence_Approved_Workcenter` · `APS_Sequence_Filter` · `APS_Sequence_Op`

### Scrap & Rejection
`Rejection` · `Rejection_Action` · `Rejection_Action_Approval` · `Rejection_Cause` ·
`Rejection_Cause_Detail` · `Rejection_Checksheet` · `Rejection_Container` ·
`Rejection_Status` · `Rejection_Type` · `Scrap` · `Scrap_Allocation_Type` ·
`Scrap_Part_Coordinate` · `Scrap_Reason` · `Scrap_Reason_Category` ·
`Scrap_Reason_Link` · `Quality`

### Setup / Scheduling
`Setup` · `Setup_BOM` · `Setup_Container` · `Setup_h` · `Setup_Log` ·
`Setup_Log_Delay_Reason` · `Setup_Log_Setup` · `Setup_Log_Team_Member` ·
`Setup_Workcenter_Clear_w` · `Scheduled_Production_Code` ·
`Scheduling_Method` · `Scheduling_Queue` · `Scheduling_Sort_Method` ·
`Shift_Override` · `Shift_Override_Type` · `Shift_Priority` · `Shift_Scenario`

### Shipper & Receipts
`Shipper` · `Shipper_Container` · `Shipper_Localization` · `Shipper_Status` ·
`Shipping_Reapplication` · `Shipping_Reapplication_Log` ·
`Receipt` · `Receipt_Checksheet` · `Receiving_Notification` ·
`Receiving_Notification_Line` · `Receiving_Schedule` · `Return_Shipper` ·
`Return_Shipper_Lines` · `Return_Shipper_Receipt` · `Return_Reason` ·
`Purchasing_Receipt` · `Purchasing_Receipt_Estimate` · `Purchasing_Receipt_Settlement` ·
`Supplier_Inventory_Usage` · `Supplier_Price_Component` · `Supplier_Schedule` ·
`Supplier_Delivery_Schedule` · `Supplier_Delivery_Schedule_Type`

### Tool Management
`Tool` · `Tool_Assembly` · `Tool_Assembly_Part` · `Tool_Assembly_Status` ·
`Tool_Assembly_Type` · `Tool_Attribute` · `Tool_Attribute_Value` · `Tool_Attributes` ·
`Tool_Audit_Type` · `Tool_BOM` · `Tool_Building` · `Tool_Category` · `Tool_Check` ·
`Tool_Control_Plan` · `Tool_Control_Plan_Status` · `Tool_Cycle` ·
`Tool_Cycle_Inventory` · `Tool_Cycle_Status` · `Tool_Delivery_Status` ·
`Tool_Disposition` · `Tool_Failure` · `Tool_Failure_Mode` · `Tool_Failure_Reason` ·
`Tool_Failure_Status` · `Tool_Failure_Workcenter_Log` · `Tool_Group` ·
`Tool_Heat_Status` · `Tool_History` · `Tool_Image` · `Tool_Inspection_Point` ·
`Tool_Inventory` · `Tool_Inventory_Attributes` · `Tool_Inventory_Cavity_Code` ·
`Tool_Inventory_Cavity_Code_Part` · `Tool_Inventory_Status` · `Tool_Job` ·
`Tool_Job_Default_Task` · `Tool_Job_Machine_Type` · `Tool_Job_Op` ·
`Tool_Job_Op_Production` · `Tool_Job_Op_Status` · `Tool_Job_Op_Task` ·
`Tool_Job_Priority` · `Tool_Job_Serial` · `Tool_Job_Status` · `Tool_Job_Type` ·
`Tool_Life` · `Tool_Life_Action` · `Tool_Localization` · `Tool_Log` ·
`Tool_Master_Routing_Approved_Workcenter` · `Tool_Op` · `Tool_Op_Approved_Workcenter` ·
`Tool_Op_Hours_Available` · `Tool_Op_Part_Life` · `Tool_Op_Price` · `Tool_Op_Type` ·
`Tool_Order` · `Tool_Order_Change` · `Tool_Order_Salesperson` · `Tool_Order_Status` ·
`Tool_Order_Step` · `Tool_Order_Template` · `Tool_Order_Tool` · `Tool_Product_Line` ·
`Tool_Production` · `Tool_Program` · `Tool_Program_Sub` · `Tool_Project` ·
`Tool_Project_Part` · `Tool_Record_Status` · `Tool_Revision` ·
`Tool_Rework_Hold_Location` · `Tool_Set` · `Tool_Set_Event` · `Tool_Set_Labor` ·
`Tool_Set_Log` · `Tool_Set_Log_Sign_Off` · `Tool_Set_Log_Task` ·
`Tool_Set_Maintenance` · `Tool_Set_Maintenance_Task` · `Tool_Set_Sign_Off` ·
`Tool_Set_Status` · `Tool_Set_Status_Action` · `Tool_Set_Task` ·
`Tool_Set_Task_Template` · `Tool_Set_Timeblock` · `Tool_Source` · `Tool_Spec` ·
`Tool_Spec_Point` · `Tool_Status` · `Tool_Status_Cost` · `Tool_Sub` ·
`Tool_Supplier` · `Tool_Supplier_Price` · `Tool_Task` · `Tool_Type` ·
`Tool_Type_Attribute` · `Tool_Usage_Code` · `Tool_Workcenter`

### Workcenter
`Workcenter` · `Workcenter_Attributes` · `Workcenter_Component` ·
`Workcenter_Component_Group` · `Workcenter_Delivery_Method` · `Workcenter_Event` ·
`Workcenter_Event_Detail_Reason` · `Workcenter_Event_Status` ·
`Workcenter_Event_Workcenter` · `Workcenter_Group` · `Workcenter_History` ·
`Workcenter_Log` · `Workcenter_Log_Equipment` · `Workcenter_Log_Inspection_Mode` ·
`Workcenter_Log_Specification` · `Workcenter_Log_Work_Request` ·
`Workcenter_Printer` · `Workcenter_Rate` · `Workcenter_Region_Cost` ·
`Workcenter_Scrap_Reason` · `Workcenter_Shift` · `Workcenter_Side_Code` ·
`Workcenter_Source_Inventory_d` · `Workcenter_Source_Location` ·
`Workcenter_Source_Position` · `Workcenter_Status` · `Workcenter_Type` ·
`Workcenter_Type_Scheduling_Sort_Method` · `Workcenter_Type_Utilization_Forecast` ·
`Approved_Workcenter` · `Approved_Workcenter_History` · `Approved_Workcenter_Kanban` ·
`Approved_Workcenter_Rate_History`

### Work Orders & Maintenance
`Work_Order` · `Work_Order_Op_Status` · `Work_Order_Operation` · `Work_Order_Status` ·
`Maintenance_Status`

### Other Reference
`Action_Type` · `Adjustment` · `Adjustment_Reason` · `Alert` ·
`Allocation_Partial_Bundle` · `Approved_Container_Master_Unit_Type` ·
`Approved_Operator` · `Approved_Supplier` · `Approved_Supplier_History` ·
`Approved_Supplier_JIT_Window` · `Approved_Supplier_Price` ·
`Approved_Supplier_Price_Component` · `Approved_Supplier_Price_Component_Note` ·
`Approved_Supplier_Price_Note` · `Attribute` · `Attribute_Type` · `Attribute_Value` ·
`Authority` · `Authority_Statement` · `Authorization_Code` · `Authorization_Status` ·
`Authorization_Type` · `Batch_Detail` · `Budget_Code` · `Capability_Run` ·
`Casting_Foam_Factor` · `Cavity_Status` · `Cell_Depletion` · `Cell_Production` ·
`Class` · `Controller_Type` · `Damper_Design_Data` · `Damper_Design_File` ·
`Declaration` · `Declaration_Class` · `Declaration_Type` · `Defense_Tooling_Status` ·
`Delay_Reason` · `Delay_Reason_Category` · `Detail_Reason` · `Detail_Reason_Group` ·
`Device` · `Device_Group` · `Device_Type` · `Die_Set_Design` · `Directive` ·
`Directive_Status` · `Directive_Type` · `Dock_Time` · `Effect` · `End_Usage_Type` ·
`Event_Type` · `Excluded_Attachments` · `Extra_Hours` · `Fixed_Assist_Tag` ·
`Flowchart_Symbol` · `Furnace_Load` · `Furnace_Load_Container` ·
`Furnace_Load_Cycle` · `Furnace_Load_Parameter` · `Furnace_Load_Status` ·
`Heat_Treat_Parameter` · `Internal_Approval_Status` · `Interplant_Import_Tracking` ·
`Interplant_Shipper` · `Interplant_Shipper_Container` ·
`Interplant_Shipper_Container_Requirements` · `Interplant_Shipper_Status` ·
`Interplant_Shipper_Transfer_Order` · `Interplant_Shipper_Type` ·
`Interplant_Truck` · `Interplant_Truck_Status` · `Key_Date` · `Lift_Entry_Setup` ·
`Master` · `Master_Building` · `Master_Control_Document` · `Master_Status` ·
`Master_Type` · `Master_Unit` · `Master_Unit_Auto_Plan` · `Master_Unit_Child` ·
`Master_Unit_Dimension` · `Master_Unit_Part` · `Master_Unit_Plan` ·
`Master_Unit_Type` · `Master_Unit_Type_Item` · `Matched_Set` ·
`Mill_Backout_Log` · `Mill_Invoice` · `Mill_Results_Detail` · `Mill_Test_Results` ·
`Mill_Test_Type` · `Mode` · `Multi_Out` · `Multi_Out_Mode` · `National_Stock_No` ·
`Node` · `Node_Value` · `On_Order_Code` · `Package_Configuration` ·
`Package_Configuration_Container_Type` · `Package_Configuration_Master_Unit_Type` ·
`Packaging_Requirement` · `Packing_Group` · `Piece` · `Piece_Status` ·
`Piece_Trace` · `PLC_Response_Status` · `Priority` · `Procedures` ·
`Quality` · `Quench_Medium` · `Recipe` · `Recipe_Device` · `Recipe_Download` ·
`Recipe_Setting` · `Registry_Group` · `Result_Type` · `RP` · `Run` ·
`Scale_House_Haul` · `Scale_House_Inspection_Status` · `Scale_House_Load` ·
`Scale_House_Vehicle_Type` · `Scenario` · `Scenario_Change` · `Setting` ·
`Setting_Limit` · `Shelf_Life_Type` · `Side` · `Standard_Cert_Note` ·
`Standard_Job_Shipper_Note` · `Station` · `Steel_Delivery_Status` ·
`Subcontract_Container_Split` · `Subcontract_Schedule_Container` ·
`Subcontract_Schedule_Job_Op` · `Subcontract_Schedule_Status` ·
`Substance` · `Substance_Category` · `Substance_Category_Substance` ·
`Substance_Registry_Group` · `Substance_Source` · `Template` ·
`Template_Attribute` · `Template_Node` · `Temper` · `Temper_Grade` ·
`Test_Command` · `Test_Command_Component` · `Test_Command_Dependent_Part` ·
`Test_Command_Instruction` · `Test_Command_Part` · `Test_Command_Status` ·
`Test_Command_Type` · `Timeblock` · `Tracking_Type` · `Transfer_Company` ·
`Value_Node` · `Value_Property` · `Virtual_Tag`
