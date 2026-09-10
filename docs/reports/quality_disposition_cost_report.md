# Vox Scorecard | NC Cost by Disposition (Destruction/Rework)

> **Status:** ✅ Built and deployed 2026-09-09 — 0 rows because the quality tables are empty; the **disposition value lists behind it are real and confirmed** · **Category:** Quality · **Runs:** rides the Quality Nonconformance pipeline

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
- **Blank dispositions are kept**, classed as `(not yet dispositioned)`.
  They're work in progress; dropping them would silently understate an open
  month.
- **⚠ The money is Plex's own `Quality_v_Problem.Cost`, and it may be
  patchy.** A record with a real Scrap disposition but no cost adds to
  `nc_count` and `qty_rejected` and nothing to `total_cost`, so
  **`records_missing_cost`** is published beside it — a Destruction $ figure
  built on half-filled costs should say so rather than read as a small number.
- **⚠ Do not reach for `VoxScorecardsLive.Product_Cost` to fill that gap.**
  Tested 2026-09-09: 199 rows of `part` + `cost_ea` that join to **5 of 6,221**
  Plex parts and **none** of the `33` parts. Its keys are bare stems (`12335`)
  against Plex's full numbers (`12335-01VOXNU-1`), with duplicate rows. It is
  the obvious thing to grab and it does not work — **ask what its `part`
  column keys to first.**
- **0 rows today, expected.** The quality tables are empty in both datasets.
  The value lists are populated — that's what made this answerable now — but
  the records aren't. Same situation as deviations, where Jennilyn said *"I
  need them to test this more."*
- **Relationship to [`quality_cost_by_category_report`](quality_cost_by_category_report.md):**
  that one groups by *problem category* (why it went wrong), this one by
  *disposition* (what happened to the material). Both read the same records;
  neither replaces the other.

## More detail

The SQL header carries the full reasoning, including the value lists as read.
[`meetings-reference/sep-9/`](../../meetings-reference/sep-9/) has the
conversation.
