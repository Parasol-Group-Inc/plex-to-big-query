# Plex SQL Dev — Maintenance Database: View Catalog

## Purpose

Equipment and facility maintenance — asset master data, corrective and preventive
maintenance work orders, PM schedules, failure codes, and maintenance labor tracking.
Lower priority for the sales orders pipeline but useful for operational efficiency KPIs.

---

## Estimated Views

### Equipment / Assets

| View | Status | Description |
|---|---|---|
| `Equipment` | ❓ | Equipment / asset master — No, Name, type, status, location |
| `Equipment_Status` | ❓ | Equipment status lookup |
| `Equipment_Type` | ❓ | Equipment type lookup |
| `Equipment_Note` | ❓ | Notes on equipment |
| `Equipment_Attribute` | ❓ | Custom attributes on equipment |

### Work Orders (Maintenance)

| View | Status | Description |
|---|---|---|
| `Work_Order` | ❓ | Maintenance work order header — date, equipment, priority, status |
| `Work_Order_Status` | ❓ | Work order status lookup (Open, In Progress, Complete) |
| `Work_Order_Type` | ❓ | Work order type (Corrective, Preventive, Predictive) |
| `Work_Order_Priority` | ❓ | Priority lookup |
| `Work_Order_Note` | ❓ | Notes on work orders |
| `Work_Order_Labor` | ❓ | Labor recorded against work orders |
| `Work_Order_Part` | ❓ | Parts used on work orders |

### Preventive Maintenance

| View | Status | Description |
|---|---|---|
| `PM_Schedule` | ❓ | PM schedule header — frequency, next due date |
| `PM_Schedule_Type` | ❓ | PM schedule type lookup |
| `PM_Task` | ❓ | Individual PM tasks / checklist items |
| `PM_History` | ❓ | PM completion history |

### Failure / Repair Codes

| View | Status | Description |
|---|---|---|
| `Failure_Code` | ❓ | Equipment failure code lookup |
| `Failure_Mode` | ❓ | Failure mode lookup |
| `Repair_Code` | ❓ | Repair action code lookup |
| `Root_Cause` | ❓ | Root cause lookup (may overlap with Quality.Root_Cause) |

### Maintenance Labor

| View | Status | Description |
|---|---|---|
| `Maintenance_Labor` | ❓ | Labor time entries for maintenance work |
| `Maintenance_Technician` | ❓ | Maintenance technician / crew master |

---

## How to Get the Full List

In Plex SQL Dev, expand: **Maintenance → Views**, then paste the tree HTML here.

Suggested verification queries:
```sql
SELECT TOP 5 * FROM Equipment
SELECT TOP 5 * FROM Work_Order
SELECT TOP 5 * FROM PM_Schedule
```
