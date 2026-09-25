"""
The human-entered sources: goals and safety incidents.

These go into the SAME tables the manual-data app writes (scorecard_goals_app,
safety_incidents), with the app's own columns, so the goal and Safe Days tiles
are fed exactly the way they will be at go-live. Nothing here is invented:

  Sales goals       already in the sandbox: the 68 real goals the app imported
                    from the legacy table, plus whatever has been saved in the
                    app since. Copied from PlexTest, untouched.
  Revenue goals     the legacy COMPANY-WIDE sales goal, one per month — exactly
                    what the app held before its sheet was replaced on
                    2026-09-24. Still an unconfirmed assumption: Revenue and
                    Sales are deliberately different numbers, and nobody has
                    given a separate revenue goal. The note on every row says so.
  Production goals  the live scorecard's own monthly goals (scale.py):
                    Encapsulating 100M, Bottling 1.5M, Labeling 700K. The live
                    board shows one month's figures, so the same goal is used
                    for every month — an assumption, stated in the note.
  Safety            the one incident the live scorecard records: the last OSHA
                    recordable on 2026-07-23. Its area and type were never
                    captured on the old sheet, so they are left as 'Other'
                    rather than guessed.
"""

import datetime as dt

import scale

APP_USER = "sandbox-build (manual-data app shape)"


def _now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def generate(sb):
    now = _now()
    months = [dt.date(2026, m, 1) for m in range(1, 13)]
    have = {(r["metric"], r["period_month"], r["scope"] or "")
            for r in sb.query("SELECT metric, period_month, scope FROM `{ds}.scorecard_goals_app`")}

    company = {r["period_month"]: float(r["goal_value"]) for r in sb.query(
        "SELECT period_month, goal_value FROM `{ds}.scorecard_goals` "
        "WHERE metric = 'sales' AND (scope IS NULL OR scope = '')")}

    goals = []
    for m in months:
        if m in company and ("revenue", m, "") not in have:
            goals.append(dict(
                metric="revenue", period_month=m.isoformat(), scope="",
                goal_value=company[m], unit="USD",
                note=("SANDBOX: the legacy company-wide SALES goal reused as the revenue "
                      "goal, as the app held it before 2026-09-24. Unconfirmed — revenue "
                      "and sales are different numbers."),
                updated_by=APP_USER, updated_at=now, is_deleted=False))
        for group, value in scale.PRODUCTION_GOALS.items():
            if ("production", m, group) in have:
                continue
            goals.append(dict(
                metric="production", period_month=m.isoformat(), scope=group,
                goal_value=float(value), unit="units",
                note=("SANDBOX: the live scorecard's monthly goal for this area "
                      "(7/31/2026 snapshot), assumed constant across the year."),
                updated_by=APP_USER, updated_at=now, is_deleted=False))

    written = {"scorecard_goals_app": sb.append("scorecard_goals_app", goals)}

    safety = [dict(
        incident_date=scale.LAST_RECORDABLE, area="Other", incident_type="Other",
        recordable=True, days_lost=None,
        description=("SANDBOX: the last OSHA recordable shown on the live scorecard's "
                     "Safety sheet. Area, type and details were never recorded there."),
        updated_by=APP_USER, updated_at=now, is_deleted=False)]
    have_safety = sb.query("SELECT COUNT(*) n FROM `{ds}.safety_incidents` "
                           f"WHERE incident_date = DATE '{scale.LAST_RECORDABLE}'")[0]["n"]
    written["safety_incidents"] = 0 if have_safety else sb.append("safety_incidents", safety)
    return written
