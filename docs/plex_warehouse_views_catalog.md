# Plex SQL Dev — Warehouse Database: View Catalog

## Purpose

Inventory management — on-hand part quantities, container tracking, storage
locations, and inventory movements. This is the source for real-time and historical
stock levels at each plant/location.

---

## Estimated Views

### Inventory / Part Quantities

| View | Status | Description |
|---|---|---|
| `Part_Quantity` ⭐ | ❓ | On-hand inventory by part and location — qty, UOM |
| `Part_Quantity_Summary` | ❓ | Summarized on-hand across locations |
| `Part_Inventory` | ❓ | Detailed part inventory records |
| `Inventory_Transaction` | ❓ | All inventory movements (receipts, issues, transfers, adjustments) |
| `Inventory_Adjustment` | ❓ | Manual inventory adjustments |
| `Inventory_Transaction_Type` | ❓ | Transaction type lookup |

### Containers

| View | Status | Description |
|---|---|---|
| `Container` | ❓ | Container master — serial number, part, qty, location, status |
| `Container_Status` | ❓ | Container status lookup |
| `Container_Type` | ❓ | Container type (pallet, tote, drum, etc.) |
| `Container_History` | ❓ | Container movement history |
| `Container_Note` | ❓ | Notes on containers |
| `Container_Label` | ❓ | Label information for containers |

### Locations

| View | Status | Description |
|---|---|---|
| `Location` | ❓ | Storage location master (rack, bin, etc.) |
| `Location_Type` | ❓ | Location type lookup |
| `Location_Status` | ❓ | Location status lookup |
| `Warehouse` | ❓ | Warehouse master |
| `Warehouse_Zone` | ❓ | Warehouse zone setup |
| `Aisle` | ❓ | Aisle layout |

### Cycle Count / Physical Inventory

| View | Status | Description |
|---|---|---|
| `Cycle_Count` | ❓ | Cycle count header |
| `Cycle_Count_Line` | ❓ | Cycle count line items (expected vs. counted qty) |
| `Physical_Inventory` | ❓ | Full physical inventory event |
| `Physical_Inventory_Line` | ❓ | Physical inventory count lines |

### Replenishment / Min-Max

| View | Status | Description |
|---|---|---|
| `Replenishment_Request` | ❓ | Internal replenishment requests |
| `Min_Max` | ❓ | Min/max inventory parameters |

### Transfers

| View | Status | Description |
|---|---|---|
| `Transfer` | ❓ | Inventory transfer between locations |
| `Transfer_Line` | ❓ | Transfer line items |
| `Transfer_Status` | ❓ | Transfer status lookup |

---

## How to Get the Full List

In Plex SQL Dev, expand: **Warehouse → Views**, then paste the tree HTML here.

Suggested verification queries:
```sql
SELECT TOP 5 * FROM Part_Quantity
SELECT TOP 5 * FROM Container
SELECT TOP 5 * FROM Location
```
