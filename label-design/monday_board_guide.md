# The Monday "Design & QA" Board — What It Tracks

> **Looking for column ids or the full technical option list?** See
> [`monday_board_catalog.md`](monday_board_catalog.md) instead. This page is
> the plain-language version.

This is the board every label goes through from "an order needs a label" to
"the label is approved and printed." Each item on the board is one label
job — one Label SKU — moving through design, QA, and regulatory review.

## The stages, in order

1. **Assets** — do we have what we need to start? (`Asset Status`)
2. **Design** — the label gets built. (`Design Status`, `Designer`, plus the
   actual files: `Design File`, `Customer Label Files`, `Global Vision Report`)
3. **QA** — checked before it goes to the customer. (`QA Status`, `QA Lead`,
   `QA Notes`)
4. **Regulatory** — trademark, organic, Prop 65, and similar checks.
   (`Regulatory Status`, `PDP or Prop 65 Letters`, `RA Lead`)
5. **Customer approval** — the customer signs off. (`Customer Approval`,
   `Customer Signoff`, `Customer Requests`)
6. **Released** — final files go out. (`Files Released on Drive`,
   `Label Disposition`)

A `PM` (project manager) and a weekly check-in status ride alongside the
whole thing, and a set of date columns (`Design Date`, `QA Received Date`,
`QA Approved Date`, `RA Approved Date`, `Customer Approval Date`, …) record
when each stage actually happened, so `Design Total Days` / `QA Total Days` /
`Days Total` can measure how long each part of the process takes.

## Where an item's information comes from

Everything under the customer/order heading — `Sales Order`, `Customer Name`,
`Email`, `Item`, `Memo` — is meant to arrive automatically from Plex through
the Label Design pipeline (see the [hub README](README.md) for how). Nobody
should have to retype it by hand.

Everything under design/QA/regulatory is filled in **by the team** as the
label moves through the stages above — that part of the board is the actual
workflow tool, not a data feed.

## Two things worth knowing before you rely on a field

**There are two "Sales Rep" columns on the board.** One is a fixed dropdown of
names; the other lets you tag an actual Monday user. If you're not sure which
one is current, ask before assuming — they can disagree.

**There are two phone-number fields** (`Phone` and `Phone Number`). If one
looks blank, check the other before assuming the data is missing.

## Reason Code has a LOT of options

Over 40, several of which read as near-duplicates of each other (e.g.
multiple variations of "Vox initiated: Label edit/review" with slightly
different wording or capitalization). That's not a data problem on this
page — it just means the dropdown has grown organically over time. Worth a
cleanup pass by whoever owns the board, but not something the pipeline can
fix.

## More detail

- [`README.md`](README.md) — the Label Design hub: what feeds this board,
  where the code lives, and what's still in progress.
- [`monday_board_catalog.md`](monday_board_catalog.md) — every column's real
  id and complete option list, for anyone changing the Apps Script push.
