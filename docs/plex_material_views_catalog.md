# Plex SQL Dev — Material Database: View Catalog

## Purpose

Material Requirements Planning (MRP) — demand signals, supply signals, planned
orders, material requirements, and planner workbench data. This is the "what do
we need to buy/make and when" layer of Plex.

---

## Estimated Views

### MRP / Planning

| View | Status | Description |
|---|---|---|
| `Material_Plan` | ❓ | MRP plan header — planning run date, horizon |
| `Material_Requirement` | ❓ | Material requirements (demand minus supply) |
| `Demand` | ❓ | Demand signals (from Sales releases, forecasts) |
| `Supply` | ❓ | Supply signals (from POs, work orders, on-hand) |
| `Planned_Order` | ❓ | Planned purchase orders and work orders from MRP |
| `Planned_Order_Type` | ❓ | Planned order type lookup |
| `Pegging` | ❓ | Demand-to-supply pegging / traceability |

### Planning Parameters

| View | Status | Description |
|---|---|---|
| `Planning_Parameter` | ❓ | Part-level planning parameters (lot size, lead time, safety stock) |
| `Safety_Stock` | ❓ | Safety stock levels by part and plant |
| `Reorder_Point` | ❓ | Reorder point settings |
| `Lead_Time` | ❓ | Lead time by part and supplier |

### Planners

| View | Status | Description |
|---|---|---|
| `Planner` | ❓ | Material planner master |
| `Planner_Part` | ❓ | Parts assigned to each planner |

### Forecasting (if in Material, not Sales)

| View | Status | Description |
|---|---|---|
| `Forecast` | ❓ | Demand forecasts (may also live in Sales.Forecast) |
| `Forecast_Period` | ❓ | Forecast periods |
| `Forecast_Version` | ❓ | Forecast version control |

---

## Note

Plex's Material module is primarily a planning / MRP layer. The actual inventory
quantities live in **Warehouse**. The demand signals come from **Sales** (releases).

---

## How to Get the Full List

In Plex SQL Dev, expand: **Material → Views**, then paste the tree HTML here.

Suggested verification queries:
```sql
SELECT TOP 5 * FROM Material_Requirement
SELECT TOP 5 * FROM Planned_Order
SELECT TOP 5 * FROM Demand
```
