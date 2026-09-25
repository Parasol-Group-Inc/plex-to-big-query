-- quality_disposition_cost_report — nonconformance cost and quantity grouped
-- by what was actually DONE with the material, which is the grain the
-- scorecard's "Destruction $" and "Rework $" tiles need.
--
-- NEW 2026-09-09, and it answers an open question rather than guessing at it.
--
-- ─────────────────────────────────────────────────────────────────────────
-- WHERE DESTRUCTIONS ARE LOGGED — ANSWERED FROM THE DATA
-- ─────────────────────────────────────────────────────────────────────────
-- Jennilyn, 2026-09-09: "destructions is like a disposition, but I'm not sure
-- where we would find that... I actually need to ask because I'm not sure
-- where they note that they destroyed something."
--
-- She was right about the mechanism. Vox's permitted disposition values were
-- extracted (raw_Quality_v_Final_Disposition / _Initial_Disposition, added the
-- same day) and read in full:
--
--   Final_Disposition   : (blank) · Re-introduce · Return · Rework · Scrap · Use as is
--   Initial_Disposition : (blank) · Hold · Return · Rework · Scrap ·
--                         Sort & Rework · Sort & Scrap · Use as is
--
-- **There is no "Destroy" or "Destruction" value. Plex calls it `Scrap`.**
-- That is why searching for a destruction field found nothing: the concept is
-- there, under a different word. Destroyed material is a nonconformance record
-- whose FINAL disposition is `Scrap`.
--
-- `Quality_v_Disposition_Type` was extracted at the same time as the other
-- candidate home for this concept and came back with **zero rows**, so it is
-- eliminated rather than left as an open maybe.
--
-- ─────────────────────────────────────────────────────────────────────────
-- ⚠ TRICKY PART 1: "Rework" EXISTS IN TWO PLACES AND WE HAVE NOT PICKED
-- ─────────────────────────────────────────────────────────────────────────
-- Rework is both a disposition here AND a container inventory status, and
-- Jennilyn named the CONTAINER one for the Rework $ tile: "so rework should
-- have the inventory status of rework." So:
--
--   * **Destruction $** — use THIS view, `disposition_class = 'Destruction'`.
--     There is no competing source; Scrap is the only destruction concept.
--   * **Rework $** — this view gives the *nonconformance* view of rework
--     (records dispositioned to Rework, with Plex's own cost). The container
--     status gives the *inventory* view (material currently sitting in a
--     Rework status). They are different populations and will not agree: a
--     container can be reworked without a nonconformance record, and a record
--     can be dispositioned Rework long after the container moved on.
--
-- This view deliberately exposes rework rather than hiding it, so the two can
-- be compared once there is real data — but **the container-status version is
-- what she asked for and is not built here** (it needs a cost per container,
-- which is a separate unsolved problem; see TRICKY PART 3).
--
-- ─────────────────────────────────────────────────────────────────────────
-- ⚠ TRICKY PART 2: FINAL vs INITIAL DISPOSITION
-- ─────────────────────────────────────────────────────────────────────────
-- This view groups on FINAL disposition — the outcome. Initial disposition is
-- the first call someone made and can differ (it carries `Hold`, and the
-- `Sort & …` options, which are triage decisions rather than outcomes). For
-- "how much did we destroy", the final outcome is the honest number; using
-- initial would count material that was initially marked Scrap and later
-- re-introduced.
--
-- Records with a BLANK final disposition are kept — dropping them would make
-- the report silently understate an open month — but SPLIT THREE WAYS since
-- 2026-09-24, because "blank" meant two very different things and the tile
-- read every one as open work:
--
--   `(not yet dispositioned)`       OPEN, blank — the genuine work in progress.
--   `(closed, no material)`         CLOSED, blank, and the record carries no
--                                   material at all — audit CARs, safety 8Ds,
--                                   risk assessments. There is nothing to
--                                   disposition, so it never will be.
--   `(closed, disposition missing)` CLOSED, blank, but the record DOES carry
--                                   material — a real data gap for Quality,
--                                   kept visible rather than folded into
--                                   either of the other two.
--
-- CLOSED = a Closed_Date is set OR Problem_Status is 'Closed' — the same test
-- the turnaround report uses (closed_date), widened by status in case Plex
-- shows 'Closed' before a date is typed. On 2026-09-24 the real records had
-- one of each shape: NC #2 'Closed' with a date, NC #9 'Submitted for
-- Closure' with a (future) Closed_Date.
-- MATERIAL = a part on the record, or any non-zero Quantity /
-- Quantity_Rejected / Quantity_Scrapped. Of the 28 real records, 17 have no
-- part and 0 in every quantity — the audit/safety forms this split is for.
--
-- ─────────────────────────────────────────────────────────────────────────
-- ⚠ TRICKY PART 3: WHERE THE MONEY COMES FROM (and where it does NOT)
-- ─────────────────────────────────────────────────────────────────────────
-- `total_cost` is Plex's OWN `Quality_v_Problem.Cost` field, carried through
-- `quality_nonconformance_report`. It is not derived from a part cost.
--
-- That matters because the obvious alternative does NOT work. Vox has a cost
-- table at `VoxScorecardsLive.Product_Cost` (199 rows, `part` + `cost_ea`),
-- and it was tested as a valuation source on 2026-09-09: it matches **5 of
-- 6,221** Plex parts and **none** of the `33` parts. Its `part` values are
-- bare stems (`12335`) against Plex's full numbers (`12335-01VOXNU-1`), it
-- contains duplicate rows, and even stem-matching fails almost everywhere.
-- **Do not reach for it as a cost source without asking what its `part`
-- column keys to.** Using Plex's own Cost field avoids the question entirely.
--
-- The catch on Plex's Cost: nothing guarantees it is filled in. A record with
-- a real Scrap disposition and no cost contributes to `nc_count` and
-- `qty_rejected` but not to `total_cost`, so **`records_missing_cost` is
-- published alongside** — a Destruction $ figure built on half-populated
-- costs should announce itself rather than read as a small number.
--
-- ⚠ "NO COST" MEANS NULL **OR 0** — FIXED 2026-09-24. An unfilled Plex Cost
-- arrives as 0.00, not NULL (0.0 on all 28 real records, verified
-- 2026-09-24), so counting only NULLs meant the flag could never fire. It now
-- counts NULL-or-0 on records whose final disposition implies money was spent
-- — Scrap and Rework. A Return / Use as is / Re-introduce at $0 is plausible
-- and is not flagged.
--
-- ─────────────────────────────────────────────────────────────────────────
-- REAL RECORDS SINCE 2026-09-22 (this block said "0 rows" until then)
-- ─────────────────────────────────────────────────────────────────────────
-- The source report was repointed to Quality_v_Problem_2 on 2026-09-22 and
-- real nonconformances flow through (28 in PlexTest on 2026-09-24). Final
-- disposition is blank and Cost is 0.00 on every one of them, so today every
-- row lands in one of the three blank classes above at $0.
--
-- Not re-extracted — bq_view entry in reports/quality_nonconformance.yaml.
-- MUST be listed AFTER quality_nonconformance_report, which it reads.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (final disposition, month).

SELECT

  -- The raw Plex value, so nobody has to trust the mapping below.
  COALESCE(NULLIF(TRIM(final_disposition), ''), '(blank)') AS final_disposition,

  -- The scorecard's language, mapped from Plex's. Only Scrap -> Destruction
  -- is an interpretation; the rest pass through, and anything Vox adds to the
  -- disposition list later shows up under its own name rather than being
  -- silently bucketed as "other".
  CASE
    WHEN UPPER(TRIM(final_disposition)) = 'SCRAP'        THEN 'Destruction'
    WHEN UPPER(TRIM(final_disposition)) = 'REWORK'       THEN 'Rework'
    WHEN UPPER(TRIM(final_disposition)) = 'RETURN'       THEN 'Return'
    WHEN UPPER(TRIM(final_disposition)) = 'USE AS IS'    THEN 'Use as is'
    WHEN UPPER(TRIM(final_disposition)) = 'RE-INTRODUCE' THEN 'Re-introduce'
    -- Blank, split three ways — see TRICKY PART 2 in the header.
    WHEN (final_disposition IS NULL OR TRIM(final_disposition) = '')
     AND closed_date IS NULL
     AND UPPER(TRIM(IFNULL(problem_status, ''))) != 'CLOSED'
                                                         THEN '(not yet dispositioned)'
    WHEN (final_disposition IS NULL OR TRIM(final_disposition) = '')
     AND part_no IS NULL
     AND COALESCE(quantity, 0) = 0
     AND COALESCE(quantity_rejected, 0) = 0
     AND COALESCE(quantity_scrapped, 0) = 0
                                                         THEN '(closed, no material)'
    WHEN final_disposition IS NULL OR TRIM(final_disposition) = ''
                                                         THEN '(closed, disposition missing)'
    ELSE final_disposition
  END                                                     AS disposition_class,

  DATE_TRUNC(problem_date, MONTH)                         AS problem_month,

  COUNT(*)                                                AS nc_count,
  SUM(COALESCE(quantity_rejected, 0))                     AS qty_rejected,
  SUM(cost)                                               AS total_cost,

  -- Provenance flag, same habit as price_source / goal_without_sales
  -- elsewhere in this repo: an incomplete figure should say so.
  -- NULL or 0 — an unfilled Plex Cost is 0.00 — and only where the
  -- disposition implies a cost. See TRICKY PART 3 in the header.
  COUNTIF((cost IS NULL OR cost = 0)
          AND UPPER(TRIM(final_disposition)) IN ('SCRAP', 'REWORK'))                                   AS records_missing_cost

FROM `{gcp_project}.{dataset}.quality_nonconformance_report`

WHERE problem_date IS NOT NULL

GROUP BY final_disposition, disposition_class, problem_month
ORDER BY problem_month DESC, total_cost DESC
