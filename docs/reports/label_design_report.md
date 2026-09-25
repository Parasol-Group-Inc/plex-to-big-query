# Label Design Queue

> **Status:** ✅ Built and verified — `label_design_report` exists and is queryable on `PlexTest` · **Category:** Sales · **Runs:** 9:30 AM and 1:30 PM Mountain, every day

## What this tells you

Which sales orders are sitting in **Label Design** right now and need artwork
before they can move — with the customer, the label SKU, the job note, and the
name of the sales rep to ask if something is unclear.

It exists to replace a twice-daily manual loop: download a report from
NetSuite, paste it into a Google Sheet, check it for duplicates by hand, upload
the new rows to Monday. The sales and design teams work the queue itself; this
just keeps it filled and de-duplicated.

## Where it fits

Replaces Jennilyn's Plex stored procedure "Label Design Report"
(`sproc338756_18319605_1407579`) and the manual NetSuite → Sheet → Monday loop
around it, agreed on the 2026-09-11 call.

This is **not** a scorecard tile. It is an operational queue, which is why it
runs midday and twice a day rather than riding the overnight `sales_orders`
pipeline.

## How it's built (high level)

Takes every sales-order release whose status is **Label Design**, keeps only
those on an order that is **Pending Fulfillment** (approved), and limits it to
orders placed in the **last 14 days**. Each row is joined to the customer, the
customer part number and description, the job note, and the sales reps on the
order.

Seven of its ten source tables are already extracted by `sales_orders`. They
are extracted again here on purpose: this runs at midday, hours after that
pipeline ran overnight, and a label-design queue built on a 14-hour-old order
list would miss exactly the new orders it exists to surface.

- **Pipeline:** `reports/label_design.yaml` → `label_design_report`
- **SQL:** `reports/sql/label_design_view.sql`
- **Downstream:** `deploy/label_design_sync/` — the Apps Script that decides
  which rows are new, writes them to the sheet, and pushes them to Monday.

## Flags and open questions

- **Ten part-level columns**, pulled from Plex's generic Part Attribute
  system and keyed on `Part_Key` (the underlying Plex part, not the
  customer-specific part number):

  | Plex attribute | Column | Values populated? |
  |---|---|---|
  | Size | `part_size` | no |
  | Allergen | `part_allergen` | no (14 parts assigned, all blank) |
  | Hazardous | `part_hazardous` | no (14 parts assigned, all blank) |
  | Certifications | `part_certifications` | no |
  | Printing Material | `part_printing_material` | no |
  | Bottle Material | `part_bottle_material` | no |
  | California PDP | `part_california_pdp` | no |
  | Prop 65 Requirement | `part_prop_65_requirement` | no |
  | Trademark | `part_trademark` | no |
  | Material Classification | `part_material_classification` | no |

  Confirmed with Jennilyn: one value per attribute per part — a need for
  several flags at once (e.g. Prop 65 *and* Organic) is handled by Plex's own
  dropdown having pre-defined combined entries ("Prop 65 + Organic") as a
  single value, passed through untouched rather than parsed.

  **The list grew from five to ten on 2026-09-21** — Jennilyn added California
  PDP, Prop 65 Requirement, Trademark, Bottle Material and Material
  Classification in Plex. They are present in **both** PlexProd and PlexTest
  with identical catalogs, so this is real production configuration, not
  test-tenant scratch work. All ten are exposed here rather than pre-selecting
  the ones that look relevant: the build originally *guessed* at two attribute
  names ('Bottle Material', 'Regulatory') before any real data existed and both
  were wrong, so names are now always read from Plex, never assumed.

  **Every value is currently blank.** 28 assignments exist (14 parts ×
  Allergen + Hazardous) and all 28 carry an empty `Value` — the structure has
  been set up in Plex but nobody has filled anything in. The previously
  documented populated example (`part_allergen = "Yes"` on `Part_Key
  11003458`) is gone; that part is no longer in the table, so the data was
  reloaded at some point. **All ten columns therefore read `NULL` today.**

  **Still open, not blocking:** which of these maps to which *Monday* column.
  Ashley confirmed 2026-09-16 that Monday's "Bottle Material" (the container —
  HDPE/PET/Glass) and Plex's "Printing Material" (label stock — white BOPP,
  metallic, laminated) are genuinely different concepts; Plex now carries its
  own separate Bottle Material attribute, so that one mapping finally has a
  real source. The rest is pending Jennilyn's internal team meeting, and she
  has separately signalled that bottle/label size probably don't need a Monday
  column at all. Not wired to any Monday push yet either way.

- **Two sales reps ship, not one.** Plex holds a primary and a secondary rep
  and nobody has ever stated which one Vox calls the BDM, so both are exposed
  and the consumer picks. Nothing here silently decides.

- **Two sheet columns cannot be filled from Plex.** *WO Number* (the work order
  is raised *after* the label is approved, so an order still in Label Design
  usually has none) and *Item* (the NetSuite item name, which no Plex column
  reproduces). They are written blank and flagged in every run email so the
  team knows they stay that way rather than assuming the data was lost.

- **Four more are blank by design** — *Reason Code*, *Label*, *Bottle
  Material*, *LCR* are filled in by a person during review. That review is the
  reason rows land on a **holding** board rather than the live one.

- **Email and Phone are the customer's account-level details**, not a per-order
  contact. Plex holds a per-line contact as well; which one the label team
  actually wants to reach has never been asked.

- **The dedupe depends on order numbers matching across two spellings** — the
  sheet says "Sales Order #SO0110212" and Plex says "SO0110212". If that ever
  stops matching, *every* row looks new at once. The Apps Script watches for
  exactly that shape and holds the run back to a dated review tab instead of
  re-importing the queue onto the board.

- **The `historical` tab is read and never written.** Notes and reason codes are
  hand-edited there, and re-writing a row would destroy that work.

- **Monday column IDs are still placeholders.** They are per-board and are not
  the column titles, so the push cannot be finished until the holding board
  exists.

## More detail

- [`deploy/label_design_sync/README.md`](../../deploy/label_design_sync/README.md)
  — the Apps Script half: dedupe rules, tabs, notifications, the Monday traps.
- [`CHANGELOG.md`](../../CHANGELOG.md) — 2026-09-11 and 2026-09-12 entries.
