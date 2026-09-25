# Sales Reps (Inside Sales roster)

> **Status:** ✅ Deployed and verified 2026-09-22 — 13 reps in test, covering all 7 who currently carry a goal · **Category:** Sales · **Runs:** rides the Sales Orders pipeline

## What this tells you

Who Vox counts as a sales rep, taken from Plex's own **Inside Sales** role —
name, email, the role they're in, and whether that role is marked
commissionable.

## Why it exists

The manual-data web app's sales-goal form asks "which rep is this goal for?"
That list used to be built from *reps who already sold something this month*.
So a new rep, or a quiet one, simply did not appear in the dropdown — and you
cannot set a goal for somebody the form won't offer you. Which is backwards:
a target matters most exactly where there are no sales yet.

Plex already knew the answer. This report reads the role roster instead.

## What changed in practice

Verified against the test tenant the day it was deployed:

- The roster returns **13 reps**. The old list would have shown at most the
  handful with sales this month.
- **All 7 reps who carry a real sales goal today are in it** — so nobody is
  lost by switching, and six more become reachable.
- One existing goal is scoped to the literal string **"Sales Representative"**,
  which is not a person and matches no rep. It was invisible while the dropdown
  only listed reps with sales. Somebody should clean that row up in the goals
  data.

## How it's built (high level)

Plex keeps roles and role membership in two places: the role itself (its name,
whether it's active) and a membership list tying users to roles. This joins
those to the user master and keeps the people in the **Inside Sales** role who
are still active.

Names are emitted as `First Last`, the same format every other rep-name report
here uses — and that matters more than it looks: a goal is matched to a rep by
**exact string**, so a different spelling produces no error, just a goal that
never lines up with any sales.

- **Pipeline:** `reports/sales_orders.yaml` → `sales_reps_report`
- **SQL:** `reports/sql/sales_reps_view.sql`

## Flags and open questions

- **Matched on the role NAME, not its key.** A numeric key vanishing under a
  status consolidation is what silently killed the accounting-approval report
  once already; a role key is no more permanent. Widening this to another role
  means adding a string to the SQL.
- **"Commissionable" is not how Vox marks a sales role.** Plex has that flag,
  and `Inside Sales` has it set to **false** — so filtering on it would have
  returned nobody. The column is still published so the next person doesn't
  have to rediscover that.
- **Outside Sales is deliberately excluded.** It's a different roster that
  overlaps on one person and otherwise contains people who match no known rep.
  If BDMs should be able to carry goals too, that's a decision, not an
  oversight.
- **Nobody has confirmed that Inside Sales is the definitive list.** It fits
  every rep who currently has a goal, which is strong evidence, not
  confirmation.
