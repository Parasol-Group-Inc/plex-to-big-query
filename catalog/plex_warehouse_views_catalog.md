# Plex SQL Dev — Warehouse Database: View Catalog

## Purpose

Inventory management — on-hand part quantities, container tracking, storage
locations, and inventory movements. This is the source for real-time and historical
stock levels at each plant/location.

---

## Confirmed Live (2026-08-11)

`Warehouse_v_Part_Quantity` and `Warehouse_v_Part_Quantity_Summary` (guessed
names below) do **not** exist — queried against `vox.test.odbc.plex.com` and
got `Base table ... not found`. On-hand inventory in this Plex tenant actually
lives under the **Part** module, not Warehouse:

- **`Part_v_Container`** ⭐ — the real on-hand-inventory carrier. Confirmed
  columns include `Part_Key`, `Quantity`, `Location`, `Container_Status`,
  `Lot_Key`, `Active`, `Job_Op_Key`, `Add_Date`. One row per physical
  container/pallet/tote; sum `Quantity` grouped by `Part_Key` (filtering
  `Active = 1` and an OK-type `Container_Status`, per
  `Part_v_Container_Status.OK_Status`) to get on-hand quantity by part.
- `Part_v_Container_Status` — status lookup with `OK_Status`, `Defective`,
  `Scrap`, `Rejectable` flags for filtering which containers count as
  available stock.
- `Part_v_Container_Track`, `Part_v_Inventory_Allocation`,
  `Part_v_Inventory_Classification`, `Part_v_Inventory_Receipt`,
  `Part_v_Active_Rejection_Container`, `Part_v_FIFO_Container` — all exist,
  live-confirmed columns, all empty on this tenant at check time.

See `catalog/plex_part_views_catalog.md` — this entire Warehouse catalog file
may be a naming-convention artifact; the actual queryable views for these
concepts live under `Part_v_{ViewName}`, not `Warehouse_v_{ViewName}`.

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
