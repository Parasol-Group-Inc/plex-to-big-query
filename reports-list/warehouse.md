# Reports List — Warehouse

Source file: `Reports List - Warehouse.csv`. Columns: Report Name, Source,
Function, Users, Link, Priority.

Only one real row:

| Report | Source | Status | Notes |
|---|---|---|---|
| Cycle Count | Google Sheet | 🎯 **Buildable — awaiting a scope decision** (was 🔍) | Link field is literal text "Cycle count," not a URL, so the sheet's own content still isn't available. But **Plex has the data**, confirmed 2026-09-09. Priority: High (nearly daily use) |

**Resolved 2026-09-09 — this stopped being a research question.** The
`Warehouse_v_Cycle_Count` / `_Line` views this row used to point at are
**confirmed absent** ("Base table not found"), which is what the ❓ marks in
`catalog/plex_warehouse_views_catalog.md` meant. But cycle counting is alive
under the **Part** module:

- **`Part_v_Cycle_Inventory`** — `Location`, `Accuracy`, `Accounted_For`,
  `Moved`, `Unaccounted_For`, `Cycle_Inventory_Date`, `Cycle_Inventory_By`,
  `Accuracy_Quantity`. This is a count-accuracy result set per location per
  date, which is what a Cycle Count dashboard is made of.
- **`Part_v_Cycle_Count_Type`**, **`Part_v_Cycle_Frequency`** (carries
  `Accuracy_Threshold`) — the classification and the target.
- **`Part_v_Container.Cycle_Inventory_Status`** — per-container state.

Same Part-not-Warehouse pattern as on-hand inventory. **Nothing is blocked on
research any more** — what's needed is a yes/no on whether Cycle Count is in
scope for the scorecard, and ideally the sheet's real content so the build
matches what the team already looks at. None of these tables is extracted yet;
row counts on this tenant are unknown.
