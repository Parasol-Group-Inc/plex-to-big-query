# Plex SQL Dev — Personnel Database: View Catalog

> **272 base views** confirmed from tree HTML (corrected 2026-06-29 — prior list was contaminated with Part database views).
> ODBC prefix: `Personnel_v_{ViewName}` (e.g. `Personnel_v_Employee`)

## Purpose

Plex Personnel is the HR module: employee records, recruitment, training, payroll,
time & attendance, safety/incidents, and performance management.

## Relevance to Sales Orders Pipeline

`Personnel_v_Employee` is the **production workforce** master — shop-floor employees,
not the user accounts that serve as sales reps. Sales rep names come from
`Plexus_Control_v_Plexus_User` (confirmed via live query).

---

## Views by Category

### Employee Master ⭐
`Employee` · `Employee_Attribute` · `Employee_Attribute_Type` · `Employee_Attribute_Value` ·
`Employee_Attributes` · `Employee_Backup` · `Employee_Change_Reason` ·
`Employee_Contact` · `Employee_Date` · `Employee_Date_Type` · `Employee_Education` ·
`Employee_Experience` · `Employee_Insurance` · `Employee_Part_Group` ·
`Employee_Pay_Element` · `Employee_Product_Type` · `Employee_Record` ·
`Employee_Record_Type` · `Employee_Reimbursement` · `Employee_Reimbursement_Line` ·
`Employee_Reimbursement_Type` · `Employee_Reimbursement_Type_Line` ·
`Employee_Requisition` · `Employee_Requisition_Status` · `Employee_Review` ·
`Employee_Review_Answer` · `Employee_Review_Form` · `Employee_Review_Form_Section` ·
`Employee_Review_Form_Section_Question` · `Employee_Review_Question` ·
`Employee_Review_Rank` · `Employee_Review_Section` · `Employee_Review_Section_Question` ·
`Employee_Review_Sequence` · `Employee_Review_Status` · `Employee_Skill` ·
`Employee_Skill_Checklist` · `Employee_Status` · `Employee_Time_Off` ·
`Employee_Type` · `Employee_Type_Description` · `Employee_Veteran_Category` ·
`Employee_Work_Status` · `Employment_Status` · `Job_Title` ·
`Additional_Position` · `Time_In_Position` · `Time_In_Position_Description` ·
`Ethnic_Origin` · `Exempt_Status` · `Foreign_Assignment`

### Recruitment / Applicants
`Applicant` · `Applicant_Answer` · `Applicant_Education` · `Applicant_Experience` ·
`Applicant_Learn_About_Employer` · `Applicant_Open_Ended_Answer` ·
`Applicant_Open_Ended_Answer_Type` · `Applicant_Question` · `Applicant_Reference` ·
`Applicant_Skill` · `Applicant_Status` · `Applicant_Update` ·
`Relocation_Preference` · `Risk_Of_Leaving`

### Training & Development
`Course` · `Course_Delivery_Method` · `Course_Grade_Type` · `Course_Prerequisite` ·
`Course_Requirement` · `Course_Session_Sharable_Content_Object` ·
`Course_Sharable_Content_Object` · `Course_Skill` · `Course_Type` ·
`Course_Web_Based_Training` · `LMS_Time` · `LMS_User_Course` ·
`LMS_User_Course_Interaction` · `LMS_User_Course_Interaction_Objective` ·
`LMS_User_Course_Log` · `LMS_User_Course_Score` ·
`LMS_User_Course_Sharable_Content_Object_Language` ·
`Sharable_Content_Object` · `Sharable_Content_Object_Language` ·
`Sharable_Content_Object_Status` · `Training` · `Training_Approval` ·
`Training_Approval_Type` · `Training_Detail` · `Training_In_Process` ·
`Training_In_Process_Grade` · `Training_In_Process_Visitor` ·
`Training_Request` · `Training_Request_Expense` · `Training_Request_Priority` ·
`Training_Request_Status` · `Training_Session` · `Training_Session_In_Process` ·
`Training_Session_Requirement` · `Position_Course` · `Position_Skill` ·
`Skill` · `Skill_Group` · `Skill_Group_Member` · `Skill_Level` ·
`Workcenter_Skill` · `Education_Grade` · `Education_Level`

### Payroll & Compensation
`Payroll` · `Payroll_Code` · `Payroll_Code_Time_Off_Type` · `Payroll_Frequency` ·
`Pay_Element` · `Pay_Grade` · `Pay_Grade_Wage_Rate` · `Pay_Rate_Change_Reason` ·
`Pay_Rate_History` · `Pay_Type` · `Pension_Type` · `Incentive_Pay` ·
`Incentive_Pay_Production` · `Offered_Overtime` ·
`Offered_Overtime_Overtime_Action` · `Overtime_Multiple` · `Overtime_Reason` ·
`Cost_Element` · `Labor` · `Labor_Type` · `Labor_Workcenter` ·
`Frequency_Unit` · `Hewitt` · `School_District`

### Time & Attendance
`Clockin` · `Clockin_Attribute_Type` · `Clockin_Type` · `Clockin_Type_Classification` ·
`Time_Off` · `Time_Off_Availability` · `Time_Off_Balance_Threshold` ·
`Time_Off_Carry_Over_Type` · `Time_Off_Clockin` · `Time_Off_Day` ·
`Time_Off_Day_Period` · `Time_Off_Pending` · `Time_Off_Period` ·
`Time_Off_Reduction` · `Time_Off_Request` · `Time_Off_Request_Type` ·
`Time_Off_Status` · `Time_Off_Type` · `Time_Off_Type_Reset` ·
`Vacation_Request` · `Vacation_Request_Status` · `Vacation_Type` ·
`Timeclock_Login` · `Timesheet_Attribute` · `Attendance_Status` ·
`Offered_Overtime` · `Point` · `Point_Status` · `Point_Type`

### Safety & Incidents
`Incident` · `Incident_Employee` · `Incident_Location` · `Incident_Response` ·
`Incident_Status` · `Incident_Sub_Type` · `Incident_Type` ·
`Injury` · `Injury_Action` · `Injury_Action_Assigned` · `Injury_Answer` ·
`Injury_Category` · `Injury_Category_Description` · `Injury_Cause` ·
`Injury_Cause_Description` · `Injury_Claim` · `Injury_Claim_Supplier` ·
`Injury_Class` · `Injury_Class_Description` · `Injury_Contributing_Cause` ·
`Injury_Customer` · `Injury_Customer_Body_Part` · `Injury_Date_Range` ·
`Injury_Days` · `Injury_Form` · `Injury_Form_Body_Part` · `Injury_Form_Cause` ·
`Injury_Form_Customer` · `Injury_Form_Nature` · `Injury_Group` ·
`Injury_Group_Description` · `Injury_Initial_Treatment` · `Injury_Insurer` ·
`Injury_Insurer_Type` · `Injury_Lost_Time` · `Injury_Lost_Time_Description` ·
`Injury_Nature` · `Injury_Part` · `Injury_Question` · `Injury_Record_Type` ·
`Injury_Record_Type_Description` · `Injury_Recurrence` · `Injury_Severity` ·
`Injury_Severity_Description` · `Injury_Status` · `Injury_Status_Description` ·
`Injury_Team_Member` · `Injury_Treatment` · `Injury_Treatment_Supplier` ·
`Injury_Type` · `Injury_Type_Description` · `Injury_Witness` · `Injury_WSIB` ·
`Injury_WSIB_Injury_Type` · `WSIB_Claim_Status` · `WSIB_Injury_Type` ·
`MSDS` · `MSDS_Department` · `MSDS_Flammability` · `MSDS_Group` ·
`MSDS_Health` · `MSDS_Personal_Protection` · `MSDS_Physical_Hazard` ·
`MSDS_Risk` · `MSDS_Status` · `MSDS_Type` ·
`Body_Part` · `Customer_Body_Part` · `Witness_Type` · `Witness_Type_Description`

### Performance & Suggestions
`Performance_Rating` · `Suggestion` · `Suggestion_Assignee` ·
`Suggestion_Award_Status` · `Suggestion_Award_Type` · `Suggestion_Employee` ·
`Suggestion_Status` · `Suggestion_Type`

### Grievances
`Grievance` · `Grievance_Article` · `Grievance_Group` · `Grievance_Note` ·
`Grievance_Status` · `Grievance_Type` · `Union_Status`

### Insurance & Benefits
`Insurance_Carrier` · `Insurance_Category` · `Insurance_Type` ·
`Family_Member` · `Termination` · `Termination_Category` · `Termination_Cause` ·
`Termination_Code` · `Veteran_Category`

### Reference
`Action_Code` · `Action_Reason` · `Answer` · `Answer_Data_Type` ·
`Choice` · `Company_Code` · `Department_Staffing` · `Disclosure` ·
`Disclosure_Type` · `LMS_User_Course_Sharable_Content_Object_Language` ·
`Loss_Time_Description` · `Procedures` · `Question` ·
`Reimbursement_Service_Type` · `Test` · `Test_Record` ·
`Visa_Type`
