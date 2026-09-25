# Vox Scorecard | NC Cost by Disposition (Destruction/Rework)

> **Status:** ⚠ Built 2026-09-09 · **returning rows since 2026-09-22, but every real record has a blank disposition and $0 cost** — see the warning below · 🔧 **missing-cost flag and blank-disposition split fixed 2026-09-24, deployed 2026-09-25** · **Category:** Quality · **Runs:** rides the Quality Nonconformance pipeline

> **What changed 2026-09-22, and why this tile still can't go live.** The report it reads was pointing at the wrong Plex table and has been repointed — 22 real nonconformance records now flow through. Two things about those records stop this tile working as designed: **Final Disposition is blank on all of them**, and **cost is 0 on all of them**. Vox records a destruction by choosing the **Material Destruction form** when the record is created, not by dispositioning material as Scrap afterwards, and the dollar value is being typed into the description ("$2305.57") rather than into Plex's Cost field. So this report is correct and its inputs aren't there yet. Deliberately **not** repointed at the form in the meantime: which of the two Vox means is a question for Quality, and quietly switching it is how a tile ends up confidently wrong. The form name is available on [Quality Nonconformance](quality_nonconformance_report.md) the moment that answer arrives.

## What this tells you

Nonconformance cost and quantity grouped by **what was actually done with the
material** — scrapped, reworked, returned, used as is — which is the grain the
scorecard's **Destruction $** and **Rework $** tiles need.

## Where destructions are logged — the question is answered

Jennilyn's open question from the 2026-09-09 call:

> *"Destructions is like a disposition, but I'm not sure where we would find
> that... I actually need to ask because I'm not sure where they note that they
> destroyed something."*

She was right about the mechanism. Vox's permitted disposition values were
extracted and read in full:

| List | Values |
|---|---|
| **Final_Disposition** | *(blank)* · Re-introduce · Return · **Rework** · **Scrap** · Use as is |
| **Initial_Disposition** | *(blank)* · Hold · Return · Rework · Scrap · Sort & Rework · Sort & Scrap · Use as is |

**There is no "Destroy" or "Destruction" value — Plex calls it `Scrap`.** That
is why looking for a destruction field found nothing: the concept was there
under a different word. Destroyed material is a nonconformance record whose
**final disposition is `Scrap`**.

`Quality_v_Disposition_Type` was extracted at the same time as the other
plausible home for the concept and came back with **zero rows**, so it's
eliminated rather than left as an open maybe. Nobody needs to ask around.

## How it's built (high level)

One row per (final disposition, month), reading
[`quality_nonconformance_report`](quality_nonconformance_report.md). Each row
carries the raw Plex disposition value *and* a `disposition_class` mapped into
the scorecard's language, so nobody has to trust the mapping — `Scrap` →
`Destruction` is the only interpretation, everything else passes through under
its own name.

- **Pipeline:** `reports/quality_nonconformance.yaml` → `quality_disposition_cost_report`
- **SQL:** `reports/sql/quality_disposition_cost_view.sql`

## Flags and open questions

- **Fixed 2026-09-24, deployed 2026-09-25: two things that made the tile look better or worse than it was.**
  - **The "missing cost" flag could never fire.** It counted records with *no* cost, but Plex stores an unfilled Cost as **0.00**, not blank — 0.00 on all 28 real records. `records_missing_cost` now counts a cost of blank **or** 0, on records whose final disposition is **Scrap or Rework** (the two that imply money was spent; a Return or Use as is at $0 is plausible and isn't flagged). Tested in the scorecard sandbox with every cost set to 0.00, as on the real records: the flag goes from 0 to **41 of 41** Destruction and **28 of 28** Rework records.
  - **"(not yet dispositioned)" overstated open work.** It held every record with a blank disposition, including *closed* records that never involved any material — audit CARs, safety 8Ds, risk assessments — which will never get a disposition. Blank records are now split three ways: **`(not yet dispositioned)`** (still open — real work in progress), **`(closed, no material)`** (closed, no part and zero quantities — nothing to disposition), and **`(closed, disposition missing)`** (closed, carries material, but nobody recorded what was done with it — a gap for Quality). "Closed" means a closed date is set or the status is Closed. On the real records this is 26 / 1 / 1; in the sandbox the old 91 "not yet dispositioned" became **32 open, 58 closed with no material, 1 closed with material missing**.
- **⚠ "Rework" exists in two places, and we have not picked for you.** Rework
  is both a disposition here *and* a container inventory status — and Jennilyn
  named the **container** one for the Rework $ tile: *"so rework should have
  the inventory status of rework."* So:
  - **Destruction $** → use this report, `disposition_class = 'Destruction'`.
    There's no competing source.
  - **Rework $** → this report gives the *nonconformance* view (records
    dispositioned to Rework, with Plex's own cost). The container status gives
    the *inventory* view (material sitting in a Rework status right now).
    **They are different populations and will not agree** — a container can be
    reworked with no nonconformance record, and a record can be dispositioned
    Rework long after the container moved on. The container-status version is
    what she asked for and is **not built**, because it needs a cost per
    container (see below).
- **This groups on FINAL disposition, not initial.** Initial is the first call
  someone made and carries triage-only options (`Hold`, `Sort & Scrap`,
  `Sort & Rework`). For "how much did we destroy", the outcome is the honest
  number — using initial would count material that was first marked Scrap and
  later re-introduced.
- **Blank dispositions are kept**, split into the three classes above.
  Dropping them would silently understate an open month.
- **⚠ The money is Plex's own Cost field (on `Quality_v_Problem_2` since
  2026-09-22), and it may be patchy.** A record with a real Scrap disposition but no cost (blank or 0.00) adds to
  `nc_count` and `qty_rejected` and nothing to `total_cost`, so
  **`records_missing_cost`** is published beside it — a Destruction $ figure
  built on half-filled costs should say so rather than read as a small number.
- **⚠ Do not reach for `VoxScorecardsLive.Product_Cost` to fill that gap.**
  Tested 2026-09-09: 199 rows of `part` + `cost_ea` that join to **5 of 6,221**
  Plex parts and **none** of the `33` parts. Its keys are bare stems (`12335`)
  against Plex's full numbers (`12335-01VOXNU-1`), with duplicate rows. It is
  the obvious thing to grab and it does not work — **ask what its `part`
  column keys to first.**
- **Real records, but not yet the right inputs.** This said "0 rows" until
  2026-09-22. Real nonconformances now flow through (28 in PlexTest on
  2026-09-24), but with a blank final disposition and 0.00 cost on every one,
  so today the report shows only the three blank classes at $0.
- **Relationship to [`quality_cost_by_category_report`](quality_cost_by_category_report.md):**
  that one groups by *problem category* (why it went wrong), this one by
  *disposition* (what happened to the material). Both read the same records;
  neither replaces the other.

## More detail

The SQL header carries the full reasoning, including the value lists as read.
[`meetings-reference/sep-9/`](../../meetings-reference/sep-9/) has the
conversation.
