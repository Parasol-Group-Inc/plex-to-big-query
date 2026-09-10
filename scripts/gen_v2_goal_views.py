# -*- coding: utf-8 -*-
"""Generate reports/sql/v2_<metric>_vs_goal_view.sql from the originals.

The ONLY functional difference is the goal source table: the originals read
`scorecard_goals` (spreadsheet ETL), the v2 copies read
`v2_scorecard_goals_resolved` (app first, sheet fallback).

Re-run this after editing any original so the pair cannot drift. That is the
whole point of generating rather than hand-copying: this repo has already been
bitten once by two files that had to be edited together
(reports/<p>.yaml and reports/test/<p>.yaml).
"""
import io, os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports", "sql")
METRICS = ["revenue", "sales", "production"]

BANNER = """-- ═══════════════════════════════════════════════════════════════════════
-- GENERATED FILE — do not hand-edit. Regenerate with the generator noted
-- below after any change to the original.
--
--   original : {orig}
--   generated: {gen}
--   generator: scripts/gen_v2_goal_views.py
--
-- The ONLY difference from the original is the goal source (the single FROM,
-- plus any header comment naming it, so the comments stay truthful):
--   original  reads  scorecard_goals              (spreadsheet ETL)
--   this file reads  v2_scorecard_goals_resolved  (app first, sheet fallback)
--
-- WHY A PARALLEL VIEW INSTEAD OF CHANGING THE ORIGINAL: Looker Studio data
-- sources point at the originals today. These v2 siblings let the scorecard
-- move over one tile at a time, and behave identically to the originals for
-- any goal the web app has not overridden. When the spreadsheet ETL is
-- sunset, delete the originals, drop the v2_ prefix, and delete this banner.
--
-- To see WHICH source fed a goal, query v2_scorecard_goals_resolved directly
-- - it carries a `goal_source` column ('app' or 'sheet'). Deliberately not
-- surfaced here, so this file stays a minimal diff from the original.
-- ═══════════════════════════════════════════════════════════════════════
"""

OLD = "`{gcp_project}.{dataset}.scorecard_goals`"
NEW = "`{gcp_project}.{dataset}.v2_scorecard_goals_resolved`"
# The guard counts the FROM occurrence only. Some originals also name the
# table in a header comment, and those are rewritten too so the generated
# file's own comments stay truthful.
OLD_FROM = "FROM " + OLD

changed = []
for m in METRICS:
    orig_name = "%s_vs_goal_view.sql" % m
    gen_name = "v2_%s_vs_goal_view.sql" % m
    orig_path = os.path.join(ROOT, orig_name)
    gen_path = os.path.join(ROOT, gen_name)

    src = io.open(orig_path, encoding="utf-8").read()
    n = src.count(OLD_FROM)
    if n != 1:
        sys.exit("ABORT: %s reads the goal table %d times, expected exactly 1. "
                 "The single-source assumption no longer holds - update the generator." % (orig_name, n))

    body = src.replace(OLD, NEW)
    # Point the view's own name at the v2 report in its first comment line.
    body = re.sub(r"^-- %s_vs_goal_report" % m,
                  "-- v2_%s_vs_goal_report" % m, body, count=1)
    out = BANNER.format(orig=orig_name, gen=gen_name) + body

    prev = io.open(gen_path, encoding="utf-8").read() if os.path.exists(gen_path) else None
    if prev != out:
        io.open(gen_path, "w", encoding="utf-8", newline="\n").write(out)
        changed.append(gen_name)

print("regenerated:", changed if changed else "nothing (all up to date)")
