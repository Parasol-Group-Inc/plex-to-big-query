# Plex SQL Dev — Plexus_Control Database: View Catalog

> **213 base views** confirmed from tree HTML.
> ODBC prefix: `Plexus_Control_v_{ViewName}` (e.g. `Plexus_Control_v_Plexus_User`)

## Purpose

`Plexus_Control` is Plex's system administration and platform layer: user accounts,
permissions, roles, menus, labels, notifications, and support tickets. It is also
where the **employee/user master** lives.

## ⭐ Critical for Sales Orders Pipeline

`Sales_v_Order_Salesperson` stores `Plexus_User_No` but not the person's name.
The join target is here:

```sql
-- Get sales rep name from Plexus_User_No
SELECT u.First_Name, u.Last_Name
FROM Plexus_Control_v_Plexus_User u
WHERE u.Plexus_User_No = <value from Order_Salesperson>
```

Key views for sales rep lookup:
- `Plexus_User` ⭐ — user master (confirmed columns below)
- `Plexus_User_No` ⭐ — maps user number to user record
- `Plexus_User_PCN` — user's company (PCN) association
- `Show_As_Employee` ⭐ — may expose users visible as employees/reps

### `Plexus_User` Confirmed Columns (live query 2026-06-29)
`Plexus_User_No` · `Plexus_Customer_No` · `User_ID` · `First_Name` · `Last_Name` ·
`Middle_Name` · `Email` · `Active` · `Phone` · `Mobile` · `Fax` · `Home_Phone` ·
`Extension` · `Pager_No` · `Department_No` · `Position_Key` · `Building_Key` ·
`Language_Key` · `Note` · `Generic_User` · `Document_Approver` · `Document_Champion` ·
`Activity_Manager_Default` · `In_Out_Board` · `In_Out_Status` · `In_Out_Date` ·
`In_Out_Note` · `Date_Week_Format` · `Change_Password` · `Password_Changed_By` ·
`Password_Changed_Date` · `Lockout` · `Print_Bar_Code_On_Badge` ·
`Add_By` · `Add_Date` · `Update_By` · `Update_Date` · `Main_Plexus_Customer_No`

> `Active = -1` means active (Plex uses -1 for boolean true).

**Join pattern for sales rep names:**
```sql
SELECT os.PO_Key, os.Sort_Order, u.First_Name, u.Last_Name, u.Email
FROM Sales_v_Order_Salesperson os
JOIN Plexus_Control_v_Plexus_User u ON os.Plexus_User_No = u.Plexus_User_No
-- Sort_Order = 1 → Rep 1, Sort_Order = 2 → Rep 2
```

---

## Views by Category

### User Master ⭐
`Plexus_User` ⭐ · `Plexus_User_Messaging` · `Plexus_User_No` ⭐ ·
`Plexus_User_PCN` · `Plexus_User_Physical_Printer` · `Plexus_User_Security_Attributes` ·
`Show_As_Employee` ⭐ · `Login` · `Login_Origin` · `User_Customer` ·
`User_Customer_Access` · `User_Customer_Access_Pending` · `User_Customer_Key` ·
`User_Group` · `User_Group_Member` · `User_Message` · `User_Permission` ·
`User_Permission_History` · `User_Query` · `User_Role` · `User_Supplier`

### Permissions & Roles
`Classic_Access` · `Permission` · `Permission_Status` · `Privilege_Conflict` ·
`Privilege_Conflict_Privilege_Group` · `Privilege_Group` · `Privilege_Group_Action` ·
`Privilege_Group_Permission` · `Privilege_Group_Screen_Action` · `Profile_Key` ·
`Role` · `Role_Action_History` · `Role_History` · `Role_History_User` ·
`Role_History_User_Action` · `Role_Permission` ·
`Application_Permission` · `Customer_Permission` · `Customer_Permission_Group` ·
`Customer_Permission_Group_Member` · `Group_Administrator` ·
`Module_Role` · `Setup_Table_Role` · `Valid_IP_Address`

### Application & Module Configuration
`Application` · `Application_Field_Sequence` · `Application_Field_Sequence_Value` ·
`Application_Glossary` · `Module` · `Module_Group` · `Module_Industry` ·
`Module_Industry_Language` · `Module_Revision` · `Setting` · `Setting_Group` ·
`Setting_Value_History` · `Setup_Field` · `Setup_Table` · `Setup_Table_Column` ·
`Setup_Table_History` · `Customer_Module` · `Customer_No` ·
`Plexus_Champion` · `Plexus_Customer_No` · `Plexus_Customer_Setting` ·
`Sub_Menu_PCN` · `Implementation_Phase` · `Implementation_Status`

### Menu & Navigation
`Default_Starting_Menu_Node` · `Main_Menu_Node` · `Main_Mobile_Menu_Node` ·
`Menu_Favorite` · `Menu_Node` · `Menu_Node_Help` · `Menu_Node_Language` ·
`Menu_Show` · `Mobile_Menu_Node` · `Mobile_Menu_Node_Role` ·
`Starting_Menu_Node`

### Printing & Labels
`Autoprint_Server` · `Autoprint_Server_Logical_Printer` ·
`Autoprint_Server_Printer_Group` · `Label_Building` · `Label_Format` ·
`Label_Type` · `Logical_Printer` · `Logical_Printer_Group` ·
`Logical_Printer_Group_Member` · `Open_Label` · `Physical_Printer` ·
`Print_Spool` · `Print_Spool_History` · `Customer_Label_Format` ·
`Customer_Printer_Language`

### Notifications & Messaging
`Email_Notification` · `Email_Notification_Customer` ·
`Email_Notification_Customer_Fields` · `Email_Notification_Customer_Group` ·
`Email_Notification_User` · `Email_Notification_User_Fields` ·
`Fax` · `Message` · `Pending_Notification` · `Pending_Notification_Archive` ·
`Pending_Notification_Failed` · `Pending_Notification_Recipient` ·
`Pending_Notification_Recipient_Archive` · `Pending_Notification_Recipient_Failed` ·
`Separate_Customer_Email` · `Auto_Email`

### Ad Hoc Reporting
`Ad_Hoc` · `Ad_Hoc_Column` · `Ad_Hoc_Filter` · `Ad_Hoc_Order` ·
`Report_Favorite` · `Report_Group` · `Report_Header` · `Report_Header_Type` ·
`Report_Output_History` · `Report_Output_Reference` · `Report_Stored_Procedure` ·
`User_Query` · `Upload_Feed` · `Upload_Feed_Detail` · `Upload_Feed_Type`

### Support Tickets
`Support` · `Support_Approval` · `Support_Assign` · `Support_Assign_h` ·
`Support_Category` · `Support_Contact` · `support_contact_support_category` ·
`Support_Customer_Approval` · `Support_Customer_Status` · `Support_h` ·
`Support_Instructions` · `Support_Permission` · `Support_Priority` ·
`Support_Quote` · `Support_Quote_Expired` · `Support_Response` ·
`Support_Responsibility_User` · `Support_Setting` · `Support_Status` ·
`Support_Type`

### Shop Screens (Production UI)
`Shop_Screen` · `Shop_Screen_Click_Action` · `Shop_Screen_Element` ·
`Shop_Screen_Icon` · `Shop_Screen_Icon_Image` · `Shop_Screen_Icon_Status` ·
`Shop_Screen_Icon_Type` · `POL_Resource`

### Glossary & Language
`Customer_Help` · `Customer_Language` · `Customer_Report` · `Customer_Report_Group` ·
`Glossary_Customer_Module_Word` · `Glossary_Customer_Word` · `Glossary_Word` ·
`Language` · `Menu_Node_Language` · `Module_Industry_Language`

### Reference / System
`Attachment` · `Attachment_backup2` · `Barcode_Field` · `Barcode_Field_Type` ·
`Call` · `Call_Type` · `Comment` · `Comment_Group` · `Comment_Group_Comment` ·
`Customer_Address_No` · `Customer_Currency` · `Customer_Group_Member` ·
`Data_Change_Reason` · `Data_Change_Reason_Column` · `Data_Change_Schedule` ·
`Data_Change_Schedule_Column` · `Dates` · `Defense_Customer` · `DST_Offset` ·
`Electronic_Signature` · `Electronic_Signature_Status` · `Error_Status` ·
`Error_Type` · `Event` · `Event_Registrant` · `Form_Message` · `Fraction` ·
`Function` · `Listing_Type` · `Logical_Timezone` · `Phone` ·
`Quote_Part_Quote_Group` · `Record_Change_History` · `Responsible_Party` ·
`Responsible_Party_Type` · `Responsible_Party_User` · `Sequence` ·
`Sort_Order` · `Time_Log` · `Web_Content` · `Web_Content_Type` ·
`Web_Listing` · `Web_Site` · `Web_Site_Hit` · `Web_Site_Page` ·
`Web_Site_User` · `Web_Site_User_Zone` · `Web_Site_Zone` ·
`Wizard` · `Wizard_Button` · `Wizard_Page`
