# Plex SQL Dev — Quality Database: View Catalog

> **515 base views** confirmed from tree HTML.
> ODBC prefix: `Quality_v_{ViewName}` (e.g. `Quality_v_Problem`)

## Purpose

Plex Quality covers the full quality management lifecycle: supplier quality (SPPAP,
RFQ responses), in-house inspection (Checksheets, Control Plans, Gauges), non-
conformance (Problems, Corrective Actions, Cost Recovery, Deviations), FMEA/APQP,
continuous improvement, and warranty management.

## Relevance to Sales Orders Pipeline

Indirect — but valuable for business analytics:
- `Cost_Recovery` and `Cost_Recovery_Scrap` ⭐ — chargebacks to customers/suppliers that
  affect SO margins
- `Problem` / `Corrective_Action` ⭐ — quality issues tied to specific customer orders
- `PPAP` / `SPPAP` — part approval status relevant to whether parts can be shipped
- `Warranty_Claim` ⭐ — customer warranty claims linked to original sales orders

---

## Views by Category

### APQP (Advanced Product Quality Planning)
`APQP_Project` · `APQP_Project_Process` · `APQP_Project_Status` · `APQP_Revision`

### Audit
`Audit` · `Audit_Element` · `Audit_Element_Result` · `Audit_Form` ·
`Audit_Form_Element` · `Audit_Form_Question` · `Audit_Form_Question_Score` ·
`Audit_Form_Section` · `Audit_Problem` · `Audit_Question` · `Audit_Result` ·
`Audit_Section` · `Audit_Status` · `Audit_Team_Member` · `Audit_Type` · `Auditor_Note`

### Calibration & Gauges
`Calibration_Master_Default` · `Calibration_Measurement` · `Calibration_Standard` ·
`Calibration_Standard_Type` · `Calibration_Test_Point` · `Gage` · `Gage_Brand` ·
`Gage_Drawing` · `Gage_Drawing_Status` · `Gage_Linearity_Measurement` ·
`Gage_Linearity_Position` · `Gage_Linearity_Trial` · `Gage_Measurement` ·
`Gage_Operator` · `Gage_Part` · `Gage_Record` · `Gage_Record_Type` ·
`Gage_Sample` · `Gage_Stability_Date` · `Gage_Stability_Measurement` ·
`Gage_Standard` · `Gage_Status` · `Gage_Trial` · `Gage_Type`

### Checksheet & Inspection
`Checklist` · `Checklist_Answer` · `Checklist_Answer_Template` ·
`Checklist_Dependent_Question` · `Checklist_Question` ·
`Checklist_Question_Color_Rule` · `Checklist_Question_Color_Scheme` ·
`Checklist_Question_Note` · `Checklist_Report_Group` · `Checklist_Report_Member` ·
`Checklist_Report_Questions` · `Checklist_Review` · `Checklist_Section` ·
`Checklist_Section_Type` · `Checklist_Status` · `Checklist_Type` ·
`Checksheet` · `Checksheet_Container` · `Checksheet_Data_Collection_Type` ·
`Checksheet_Disposition` · `Checksheet_Info` · `Checksheet_Print_PPAP_Format` ·
`Checksheet_Snapshot` · `Checksheet_Status` · `Checksheet_Type` ·
`Checksheet_Type_Inspection_Mode` · `Custom_Checksheet_Data_Collection_Type` ·
`Acceptance_Sampling_Count` · `Acceptance_Sampling_Count_Threshold` ·
`Acceptance_Sampling_Mode` · `Inspection_Mode` · `Inspection_Mode_Attribute` ·
`Inspection_Mode_Attribute_Value` · `Sample_Plan` · `Sample_Plan_Type` ·
`Sample_Frequency`

### Claims
`Claim` · `Claim_Group` · `Claim_Status` · `Claim_Type`

### Control Plan
`Control_Plan` · `Control_Plan_Line` · `Control_Plan_Line_Attributes` ·
`Control_Plan_Line_Status` · `Control_Plan_Line2` · `Control_Plan_Line2_Attributes` ·
`Control_Plan_Line2_Control_Method` · `Control_Plan_Line2_Gage_Type` ·
`Control_Plan_Line2_Reaction_Plan` · `Control_Plan_Line2_Specification` ·
`Control_Plan_Line2_Specification_Part` · `Control_Plan_Line2_Specification_Part_Type` ·
`Control_Plan_Section` · `Control_Plan_Standard_Line` · `Control_Plan_Status` ·
`Control_Plan_Type` · `Control_Method` · `DCP_Link`

### Corrective Action
`Corrective_Action` · `Exception` · `Exception_Corrective_Action` ·
`Exception_Repair_Method` · `Exception_Sort_Method` · `Exception_Type` ·
`Five_Why` · `Five_Why_Line` · `Five_Why_Line_Code` · `Five_Why_Line_Type` ·
`Five_Why_Type`

### Cost Recovery ⭐
`Cost_Recovery` ⭐ · `Cost_Recovery_Activity` · `Cost_Recovery_Approval` ·
`Cost_Recovery_Debit_Memo` · `Cost_Recovery_Notification` ·
`Cost_Recovery_Response_Status` · `Cost_Recovery_Scrap` · `Cost_Recovery_Status` ·
`Cost_Scrap` · `cost_activity` · `Cost_Approval_Area`

### Defects & Rejections
`Defect_Att_Group` · `Defect_Attribute` · `Defect_Detail` ·
`Defect_Detail_Description` · `Defect_Log` · `Defect_Log_Operator` ·
`Defect_Log_Type` · `Defect_Record` · `Defect_Record_Attribute` · `Defect_Type` ·
`Defect_Type_Description` · `Failure_Mode` · `Failure_Mode_Action`

### Deviations
`Deviation` · `Deviation_Description` · `Deviation_Description_Type` ·
`Deviation_Job` · `Deviation_Part` · `Deviation_Problem` ·
`Deviation_Specification` · `Deviation_Status` · `Deviation_Type` ·
`Deviation_Workcenter`

### Documents & Specs
`CAD_Format` · `Document` · `Document_Matrix` · `Drawing` · `Drawing_Location` ·
`Drawing_Origin` · `Drawing_Paper_Size` · `Drawing_Type` · `Engineering_File` ·
`File_Distribution` · `File_Format` · `File_Origin` · `File_Storage_Type` ·
`File_Type` · `Spec_Doc` · `Spec_Doc_Customer` · `Spec_Doc_Grade` ·
`Spec_Doc_Group` · `Spec_Doc_Job` · `Spec_Doc_Material` · `Spec_Doc_Option` ·
`Spec_Doc_Part` · `Spec_Doc_Part_Operation` · `Spec_Doc_Source` · `Spec_Doc_Status` ·
`Spec_Doc_Type` · `Spec_Doc_Type_Operation` · `Spec_Doc_Type_Operation_Type` ·
`Spec_Rev` · `Spec_Template` · `Spec_Template_Line` · `Specification` ·
`Specification_Dimension_Type` · `Specification_Failure_Mode` ·
`Specification_Formula` · `Specification_Type` · `Specification_Upload` ·
`Specification_Upload_Group` · `Standard_Spec_Link` ·
`Component_Part_Specification` · `Body_Part`

### FMEA (Failure Mode & Effects Analysis)
`FM_Cause` · `FM_Cause_Action` · `FM_Cause_Template` · `FMEA` · `FMEA_Action` ·
`FMEA_Action2` · `FMEA_Cause` · `FMEA_Cause2` · `FMEA_Cause2_FMEA_Control` ·
`FMEA_Detection` · `FMEA_Failure_Mode` · `FMEA_Failure_Mode2` ·
`FMEA_Failure_Mode2_Effect` · `FMEA_Occurrence` · `FMEA_Part` ·
`FMEA_Problem_Adjustment` · `FMEA_Requirement` · `FMEA_Rule` · `FMEA_Rule_Range` ·
`FMEA_Rule_Scope` · `FMEA_Severity` · `FMEA_Status` · `FMEA_Subject` · `FMEA_Type`

### Flowcharts
`Flowchart` · `Flowchart_Shape` · `Flowchart_Shape_Menu_Node` ·
`Flowchart_Shape_Type` · `Flowchart_Type`

### Improvement Projects
`Improvement` · `Improvement_Area` · `Improvement_Control_Status` ·
`Improvement_Control_Type` · `Improvement_Customer_Type` ·
`Improvement_Focus_Tool` · `Improvement_Photo` · `Improvement_Process_Failure_Mode` ·
`Improvement_Product_Failure_Mode` · `Improvement_Progress` ·
`Improvement_Project` · `Improvement_Project_Category` ·
`Improvement_Project_Checklist` · `Improvement_Project_Group` ·
`Improvement_Project_Notes` · `Improvement_Project_Operation` ·
`Improvement_Project_Review` · `Improvement_Project_Review_Status` ·
`Improvement_Project_Standard_Note` · `Improvement_Project_Status` ·
`Improvement_Project_Sub_Type` · `Improvement_Project_Test` ·
`Improvement_Project_Type` · `Improvement_Reference` · `Improvement_Sponsor_Member` ·
`Improvement_Team_Member` · `Improvement_Type`

### Iterations (Engineering change iterations)
`Iteration` · `Iteration_Accounting_Job` · `Iteration_Attribute` ·
`Iteration_Attribute_Value` · `Iteration_Balance` · `Iteration_Budget` ·
`Iteration_Charge_To` · `Iteration_Contact` · `Iteration_Detail` ·
`Iteration_Detail_Note_Type` · `Iteration_Detail_Status` · `Iteration_Detail_Type` ·
`Iteration_Distribution` · `Iteration_Estimate_Budget_Cost_Type` ·
`Iteration_Estimate_Cost_Type` · `Iteration_Estimate_Cost_Type_Comment` ·
`Iteration_Job_Type` · `Iteration_Part` · `Iteration_Phase` · `Iteration_PO` ·
`Iteration_Quote` · `Iteration_Revenue_Recognized` · `Iteration_Revenue_Recognized_w` ·
`Iteration_Risk` · `Iteration_Status` · `Iteration_Team_Member` ·
`Iteration_Tool_Type` · `Iteration_Type`

### Lessons Learned
`Lessons_Learned` · `Lessons_Learned_Damper_Type` · `Lessons_Learned_Gate` ·
`Lessons_Learned_Issue_Sub_Type` · `Lessons_Learned_Issue_Type` ·
`Lessons_Learned_Part_Sub_Group` · `Lessons_Learned_Status` ·
`Lessons_Learned_Text` · `Lessons_Learned_Type`

### Measurements & SPC
`CPK` · `Chart_Setup` · `Chart_Type` · `Measurement` · `Measurement_Cause2` ·
`Measurement_Container` · `Measurement_Failure_Mode` · `Measurement_Piece` ·
`Metric_Summary_Upload_Data` · `Scorecard_Metric_Group` ·
`Scorecard_Metric_Group_Color_Range` · `Scorecard_Supplier_Status_Exclusion` ·
`Scorecard_Supplier_Type_Exclusion` · `Subgroup` · `Subgroup_Stream` ·
`Tolerance_Type` · `Variation_Source`

### PPAP (Production Part Approval Process)
`PPAP` · `PPAP_Comment` · `PPAP_Disposition` · `PPAP_Doc` · `PPAP_Doc_Action` ·
`PPAP_Doc_Status` · `PPAP_Level_Requirement` · `PPAP_Level2` · `PPAP_Reason` ·
`PPAP_Requirement_PPAP` · `PPAP_Requirement2` · `PPAP_Status` ·
`PPAP_Submission_Reason`

### Problems & NCRs ⭐
`Problem` ⭐ · `Problem_2` · `Problem_2_Action_Section_Fields` ·
`Problem_2_Attributes` · `Problem_2_Checklist` · `Problem_2_Date` ·
`Problem_2_Key_Fields` · `Problem_2_Responsible` · `Problem_2_Supplier_Type` ·
`Problem_2_Text_Attributes` · `Problem_Action` · `Problem_Action_2` ·
`Problem_Action_2_Activity_Note` · `Problem_Action_2_Default` ·
`Problem_Action_Assigned` · `Problem_Action_Impact` · `Problem_Action_Section` ·
`Problem_Action_Section_Description` · `Problem_Action_Type` · `Problem_Approval` ·
`Problem_Approver` · `Problem_Category` · `Problem_Category_Description` ·
`Problem_Close_Reason` · `Problem_Container` · `Problem_Controlled_Shipping` ·
`Problem_Demerit` · `Problem_FMEA` · `Problem_Form` · `Problem_Form_Description` ·
`Problem_Form_Field_Answer` · `Problem_Form_Fields` · `Problem_Form_Sections` ·
`Problem_Group` · `Problem_Help` · `Problem_Improvement_Project` ·
`Problem_Job_Classification` · `Problem_Nonconformance` · `Problem_Notification` ·
`Problem_Nuisance` · `Problem_Product_Age` · `Problem_Revision` ·
`Problem_Revision_2` · `Problem_Root_Cause` · `Problem_Severity` ·
`Problem_Source` · `Problem_Source_Description` · `Problem_Status` ·
`Problem_Status_Description` · `Problem_Team_Member` · `Problem_Team_Member_2` ·
`Problem_Type` · `Problem_Type_Description`

### Process Control Recipes
`Process_Control_Recipe` · `Process_Control_Recipe_Family` ·
`Process_Control_Recipe_Family_Note` · `Process_Control_Recipe_Family_Part` ·
`Process_Control_Recipe_Family_Type` · `Process_Control_Recipe_Note` ·
`Process_Control_Recipe_Workcenter` · `Process_Element` · `Process_Input_Category`

### Programs & Customers
`Cust_Prog_Market` · `Cust_Prog_Plant` · `Cust_Prog_Production` ·
`Cust_Prog_Stat` · `Cust_Program` · `Market` · `Program` ·
`Program_Attribute_Value` · `Program_Budget` · `Program_Budget_Setup` ·
`Program_Contact` · `Program_Group` · `Program_Note` · `Program_Opportunity` ·
`Program_Production` · `Program_Production_Version` · `Program_Status` ·
`Program_Type` · `Program_User` · `Program_Vehicle` ·
`Product_Category_Description` · `Product_Code_Description`

### R&D Projects
`RD_Project` · `RD_Project_Group` · `RD_Project_Note` · `RD_Project_NPD_Project` ·
`RD_Project_Opportunity` · `RD_Project_Priority` · `RD_Project_Program` ·
`RD_Project_Status` · `RD_Project_Type`

### SPPAP (Supplier PPAP)
`SPPAP` · `SPPAP_Approval` · `SPPAP_Approval_Answer` · `SPPAP_Attribute` ·
`SPPAP_Building` · `SPPAP_Checklist` · `SPPAP_Doc` · `SPPAP_Group_Type` ·
`SPPAP_Level` · `SPPAP_Level_Requirement` · `SPPAP_Program` · `SPPAP_Reason` ·
`SPPAP_Requirement` · `SPPAP_Status` · `SPPAP_Status_Change` ·
`SPPAP_Status_Validation`

### Specifications & Tests
`Part_Phase` · `Part_Test` · `Part_Test_Range` · `Part_Test_Row` ·
`Reaction_Plan` · `Results` · `Step` · `Step_Contributor` · `Step_Group` ·
`Step_Template` · `Step_Template_Line` · `Step_Type` ·
`Test` · `Test_Column` · `Test_Container` · `Test_Direction` ·
`Test_Grid_Result` · `Test_Job` · `Test_Result` · `Test_Row` ·
`Test_Status` · `Test_Supplier` · `Test_Type` · `Tester`

### Supplier Quality
`Supplier_Issue` · `Supplier_Issue_Part_Status` · `Supplier_Issue_Status` ·
`Supplier_Issue_To` · `Supplier_Issue_Type` · `Supplier_Return` ·
`Supplier_Return_Additional_Charge_Type` · `Supplier_Return_Category` ·
`Supplier_Return_Container` · `Supplier_Return_Line` · `Supplier_Return_Reason` ·
`Supplier_Return_Status` · `Supplier_Return_Type`

### Templates & Questions
`Template` · `Template_Dependent_Question` · `Template_Question` ·
`Template_Review` · `Template_Section` · `Action_Assigned_To` ·
`Action_Section_Type_Description` · `Contribution` · `Contributor` ·
`Design_Basis` · `Design_Output` · `Design_Type` · `Difficulty` ·
`Disruption_Type` · `Distribution_Point` · `Effect` · `Engineer` ·
`Equipment_Type` · `Form_Type` · `Formula_Type` ·
`Function_Requirement_Type` · `Function_Requirement_Type_Failure_Mode_Template` ·
`Functional_Approval` · `Notification_Method` · `Notification_Method_Description` ·
`Notification_Type` · `Question_Category` · `Required_Status` ·
`Resolution_Type` · `Review_Status` · `Root_Cause_Code` ·
`Root_Cause_Code_Description` · `Root_Cause_Detail` ·
`Root_Cause_Detail_Description` · `Section_Status` · `Special_Symbol` ·
`Standard_Attribute_Description` · `Standard_Attribute_Value`

### Warranty ⭐
`Warranty_Claim` ⭐ · `Warranty_Claim_Attribute` · `Warranty_Claim_Final_Decision` ·
`Warranty_Claim_Note` · `Warranty_Claim_Problem` · `Warranty_Failure_Code` ·
`Warranty_Status`

### Reference / Codes
`Body_Part` · `Cause` · `Cause2` · `Disposition_Type` · `Disposition_Type_Description` ·
`Final_Disposition` · `Final_Disposition_Description` ·
`Initial_Disposition` · `Initial_Disposition_Description` ·
`Locality` · `Project_Category` · `Project_Category_Description` ·
`Reason` · `Work_Step_Operation_Process_Step_Process_Element`
