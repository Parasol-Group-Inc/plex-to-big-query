# Label Design — fast follow from the 2026-09-21 Emilio / Jennilyn call

> Source: `meetings-reference/sep-21/` (transcript, Otter summary, Gemini notes).
> Everything below that is checked against live data says so and shows the
> figure. Everything else is what was said on the call.
>
> This is a **fast follow**, not a status file — [`STATUS.md`](STATUS.md) stays
> the canonical state of the project.

## The short version

Two decisions on that call change what we build, and one of them undoes part
of what shipped on 2026-09-21:

1. **Part attributes stay in Plex. They are not going into Monday.**
2. **Attributes will only ever be placed on "sevens" — the label part numbers.
   The parts our queue carries are "nines", the finished goods.** So the ten
   attribute columns we just built will be structurally empty for every row of
   the label-design queue, not empty-pending-data-entry.

Plus the Monday write blocker finally has a named cause: the account has a
**CRM** license, not **Work Management**. That is a product license, not a
board permission, which is why every permission fix we tried made no
difference.

---

## 1. Attributes stay out of Monday

Jennilyn, on the call: *"they decided today that we want most of those to just
stay in Plex — we won't need to bring them in."* And later, on the Monday
board: *"I'm gonna guess that they're gonna delete a bunch of these columns."*

**What this means for us**

- The push service does **not** map `part_*` columns onto Monday items. Don't
  build that mapping; it would be deleted on the board side anyway.
- The columns stay in `label_design_report`. They cost nothing to keep, they
  are correct, and Plex remains the place anyone looks an attribute up.
- The Monday column catalogue (`monday_board_catalog*.md`) should be re-read
  against the real board once the licence is fixed — expect fewer columns than
  it currently documents, not more.

**What this does not mean.** The 2026-09-21 attribute work was not wasted: it
is what made the next finding visible at all, and the `NULLIF(TRIM(...))` fix
in it is still right regardless of where the values are consumed.

## 2. Sevens and nines — the part-numbering rule, and why it breaks the pivot

Jennilyn: *"the label part numbers are sevens, and the finished good part
numbers are nines"* … *"the part numbers you're going to be bringing over won't
have these part attributes. We're only going to put them on the sevens, not the
nines."*

**Checked against `PlexProd` on 2026-09-22** — the naming is real and the split
is lopsided:

| Part family | Distinct parts in `raw_Part_v_Part` |
|---|---|
| `73…` (label parts) | **5,370** |
| `71…` | 28 |
| `75…` | 15 |
| `12…` | 583 |
| `93…` (finished goods) | 7 |

And the queue is built off **sales order lines**, which carry the nines:

| Part prefix on `raw_Sales_v_PO_Line` (prod) | Lines |
|---|---|
| `93…` | 2 (1 distinct part) |

`label_design_view.sql` pivots attributes with
`ON pap.Part_Key = SAFE_CAST(pol.Part_Key AS INT64)` — the **order line's**
part. That is a nine. The attributes are going onto sevens. **The join can
never match**, no matter how much attribute data Vox enters.

Today's attribute rows are still scattered across families, which is why this
hasn't bitten yet — of ~30 attributed parts in prod, 25 are `12…`, only 2 are
`73…` and 1 is `93…`. As Vox follows through on "sevens only", our columns go
to all-NULL permanently.

### The fix, and it is already provable

The bill of materials links them. **Checked in `PlexProd`:**

| BOM parent | BOM component | Rows |
|---|---|---|
| `93…` | **`73…`** | **4** |
| `93…` | `53…` | 7 |
| `53…` | `33…` / `16…` / `17…` | 6 each |
| `23…` | `12…` | 69 |

So a finished good (`93…`) already has its label part (`73…`) sitting under it
as a BOM component. The chain we need is:

```
order line part (93…)  →  raw_Part_v_BOM component (73…)  →  raw_Part_v_Part_Attribute
```

`raw_Part_v_BOM` and `raw_Part_v_Flat_BOM` both already exist in both datasets
— the out-of-stock report's BOM explosion uses them — so this is a view change,
no new extraction.

**Three things to settle before building it**, because a wrong guess here is
worse than a NULL:

- **Is there exactly one label part per finished good?** If a `93…` carries two
  `73…` components, the pivot multiplies rows in a queue that is deduplicated
  on order + customer part. Needs checking against real data, not assumed.
- **Is it always one BOM level?** `93 → 53 → 33 …` exists too, so the label
  part may sit deeper for some products. `raw_Part_v_Flat_BOM` would handle
  that, at the cost of having to pick the right level.
- **Is it wanted at all?** Given decision 1 — attributes are not going to
  Monday — the honest question is who consumes these columns. If the answer is
  "nobody, they're read in Plex", then this stays documented and unbuilt, which
  is a perfectly good outcome. **Ask before building.**

## 3. The Monday write blocker has a name: CRM vs Work Management

From the call, walking through the account list live: *"It has CRM, but not
work management… we're gonna have to get you the other one"* — and *"that's
paid, right?" "Yeah, so they're just different products."*

This resolves the open item recorded as a seat-licence problem. It is not a
board permission, not a workspace membership, and not a token scope, which is
why nothing on our side ever fixed it. The account in use is **Jennette's
login**, shared, and it holds a CRM licence.

- **Owner:** Jennilyn — *"we'll get that changed for you."*
- **Until then:** writes to the real **Plex Import Board** will keep failing,
  and no amount of retrying or re-scoping the token changes that.
- **When it lands:** re-run the push against the real board before assuming
  anything else about the column IDs, which are per-board and are not the
  column titles.

## 4. Where the data lands in the meantime

- The board that used to sit in the **Label Design** workspace **is gone** —
  Jennilyn: *"I think somebody deleted it."*
- The working target is a board in the **Lang Landing Page** workspace (created
  by Jennette). Jennilyn confirmed on the call that she can open it.
- Emilio can create boards there; Jennilyn offered to tell the team not to
  delete them — worth taking her up on that explicitly, given what happened to
  the last one.
- Current test dumping ground is Emilio's own rudimentary board, which is now
  pulling the sales rep correctly (the fix was getting the Plexus customer and
  category right).

## 5. Test data has an owner

- Jennilyn is verifying that test order data exists in the landing board.
- **Ashley** — or her team — will create more test orders on request, and
  Jennilyn was explicit that we should just message her: *"if you ever need
  test data, please feel free to just go ahead and message Ashley too, and
  she'll make some or have her team make some."* Ashley is the person who will
  be working through this day to day.

This removes what had been a standing excuse for untested paths. Any "we can't
test this without data" from here needs a message to Ashley first.

---

## Checklist

| # | Action | Owner |
|---|---|---|
| 1 | Do **not** map `part_*` attribute columns into the Monday push | us |
| 2 | Ask whether the FG → label-part BOM hop is wanted at all before building it | us → Jennilyn |
| 3 | If yes: check one-label-part-per-FG and BOM depth against real data first | us |
| 4 | Change the Monday account from CRM to **Work Management** licence | Jennilyn |
| 5 | Re-read the real board's column IDs once writes work | us |
| 6 | Get the Lang Landing Page board marked do-not-delete | Jennilyn |
| 7 | Confirm test orders exist in the landing board | Jennilyn |
| 8 | Message Ashley whenever more test orders are needed | us |
| 9 | Re-check `monday_board_catalog*.md` against the real board — expect columns to have been deleted | us |

## Appendix — the queries behind the figures

```sql
-- Part families in production
SELECT SUBSTR(Part_No,1,2) AS prefix, COUNT(DISTINCT Part_No) AS parts
FROM `voxdatalake.PlexProd.raw_Part_v_Part` GROUP BY prefix ORDER BY parts DESC;

-- What the queue's order lines actually carry
SELECT SUBSTR(pp.Part_No,1,2) AS prefix, COUNT(*) AS po_lines
FROM `voxdatalake.PlexProd.raw_Sales_v_PO_Line` pol
JOIN `voxdatalake.PlexProd.raw_Part_v_Part` pp
  ON SAFE_CAST(pol.Part_Key AS INT64) = SAFE_CAST(pp.Part_Key AS INT64)
GROUP BY prefix ORDER BY po_lines DESC;

-- The BOM hop that would connect them
SELECT SUBSTR(parent.Part_No,1,2) AS parent_prefix,
       SUBSTR(child.Part_No,1,2)  AS component_prefix, COUNT(*) AS bom_rows
FROM `voxdatalake.PlexProd.raw_Part_v_BOM` b
JOIN `voxdatalake.PlexProd.raw_Part_v_Part` parent
  ON SAFE_CAST(b.Part_Key AS INT64) = SAFE_CAST(parent.Part_Key AS INT64)
JOIN `voxdatalake.PlexProd.raw_Part_v_Part` child
  ON SAFE_CAST(b.Component_Part_Key AS INT64) = SAFE_CAST(child.Part_Key AS INT64)
GROUP BY parent_prefix, component_prefix ORDER BY bom_rows DESC;
```

## Not label design, noted so it isn't lost

The same call covered the scorecard's manual-data web app: the **part costs tab
is removed** (keep Goals, Safety incidents, Turnaround standards), sales-rep
goals need their rep list pulled from BigQuery rather than typed, and there is
an open question on **what "effective from" date the turnaround standards
should carry**. That belongs to the scorecard workstream — see the Migration
Board and `deploy/manual_data_app/`.
