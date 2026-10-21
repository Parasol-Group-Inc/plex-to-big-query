"""The 'Current' value of each Scorecard-view figure: one BigQuery query per figure,
computed from the report view that replaces the Looker source.

`scripts/hub/snapshot_data.py` runs these (with {ds} set to PlexProd or PlexTest) and
the hub's Expected / Current toggle shows the result next to the Looker value of 31 Jul 2026.

Each query returns exactly one row: `value`, optionally `value2` (the second number a
figure shows, e.g. goal beside actual) and, for the funnel, a STRING `detail`.
format: usd | usd_short | pct | int | short | days.  pct_scale: 1 = ratio, 100 = already a percent.
Dates use CURRENT_DATE() (UTC), the same clock the report views use.
"""

MONTH = "DATE_TRUNC(CURRENT_DATE(), MONTH)"


def _daily(view, group):
    """Yesterday's total for one production area, from its daily report."""
    return f"""SELECT SUM(SAFE_CAST(actual_qty AS FLOAT64)) AS value
FROM `voxdatalake.{{ds}}.{view}`
WHERE production_date = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
  AND workcenter_group = '{group}'"""


def _bar(group):
    """Month-to-date produced (good + scrap) beside the month's goal."""
    return f"""SELECT SUM(SAFE_CAST(total_qty AS FLOAT64)) AS value,
       MAX(SAFE_CAST(goal_value AS FLOAT64)) AS value2
FROM `voxdatalake.{{ds}}.production_vs_goal_report`
WHERE production_month = {MONTH} AND workcenter_group = '{group}'"""


def _goal(group):
    return f"""SELECT SAFE_DIVIDE(SUM(SAFE_CAST(total_qty AS FLOAT64)), MAX(SAFE_CAST(goal_value AS FLOAT64))) AS value
FROM `voxdatalake.{{ds}}.production_vs_goal_report`
WHERE production_month = {MONTH} AND workcenter_group = '{group}'"""


def _fpy(area):
    return f"""SELECT MAX(SAFE_CAST(fpy AS FLOAT64)) AS value
FROM `voxdatalake.{{ds}}.quality_fpy_by_area_month_report`
WHERE fpy_month = {MONTH} AND area = '{area}'"""


FPY_NOTE = ("Good over total quantity for the month, from production records (ratio); "
            "Looker showed the same kind of ratio from the YTD FPYs sheet.")


def _production(area, label, view, group, looker):
    return {
        f"{area}-bar": {"sql": _bar(group), "format": "short", "view": "production_vs_goal_report",
            "note": f"{label} good plus scrap this month to date (value) against the month's goal (value2); Looker's bar ({looker}) blended its own daily sheet with the goals sheet."},
        f"{area}-yday": {"sql": _daily(view, group), "format": "short", "view": view,
            "note": f"Yesterday's {label.lower()} good quantity from Plex job-operation records; Looker read the Production_Daily sheet."},
        f"{area}-goal": {"sql": _goal(group), "format": "pct", "pct_scale": 1, "view": "production_vs_goal_report",
            "note": f"Month-to-date {label.lower()} total over the month's goal (ratio); same formula as Looker, different source."},
    }


FIGURES = {
    "rev-mtd": {
        "sql": f"""SELECT SUM(SAFE_CAST(shipping_revenue AS FLOAT64)) AS value
FROM `voxdatalake.{{ds}}.sales_revenue_summary_report`
WHERE revenue_month = {MONTH}""",
        "format": "usd_short", "view": "sales_revenue_summary_report",
        "note": "Plex shipped revenue for the current month to date; Looker summed a hand-kept Rev_MTD sheet."},
    "rev-into-month": {
        "sql": f"""SELECT MAX(SAFE_CAST(pct_into_month AS FLOAT64)) AS value,
       MAX(SAFE_CAST(run_rate_projection AS FLOAT64)) AS value2
FROM `voxdatalake.{{ds}}.sales_revenue_run_rate_report`
WHERE revenue_month = {MONTH}""",
        "format": "pct", "pct_scale": 1, "view": "sales_revenue_run_rate_report",
        "note": "Days elapsed over days in the month (ratio), with the run-rate projection as the second number; Looker took it from a view with hardcoded goals."},
    "rev-goal": {
        "sql": f"""SELECT MAX(SAFE_CAST(goal_value AS FLOAT64)) AS value
FROM `voxdatalake.{{ds}}.revenue_vs_goal_report`
WHERE revenue_month = {MONTH}""",
        "format": "usd_short", "view": "revenue_vs_goal_report",
        "note": "The month's revenue goal from the goals table; the current-month goal may still be a placeholder (see the view's goal_note)."},
    "rev-to-goal": {
        "sql": f"""SELECT MAX(SAFE_CAST(pct_to_goal AS FLOAT64)) AS value
FROM `voxdatalake.{{ds}}.revenue_vs_goal_report`
WHERE revenue_month = {MONTH}""",
        "format": "pct", "pct_scale": 1, "view": "revenue_vs_goal_report",
        "note": "Month-to-date Plex shipped revenue over the month's goal (ratio); Looker used MAX(MTD Revenue) / MAX(Goal) on its sheet."},
    "shipping": {
        "sql": """SELECT SUM(SAFE_CAST(ready_value AS FLOAT64)) AS value
FROM `voxdatalake.{ds}.shipping_pending_revenue_report`""",
        "format": "usd_short", "view": "shipping_pending_revenue_report",
        "note": "Value of quantity ready on open shippers right now; Looker summed a daily snapshot column, so this is a live total, not a dated one."},
    "safe-days": {
        "sql": """SELECT DATE_DIFF(CURRENT_DATE(), MAX(incident_date), DAY) AS value
FROM `voxdatalake.{ds}.safety_incidents`
WHERE COALESCE(is_deleted, FALSE) = FALSE AND LOWER(CAST(recordable AS STRING)) = 'true'""",
        "format": "days", "view": "safety_incidents (manual form table)",
        "note": "Days since the newest recordable incident entered in the manual-data app (NULL if none); Plex has no safety data, and Looker used a hand-typed 'Last OSHA' date."},
    "oos": {
        "sql": """SELECT COUNT(DISTINCT part_no) AS value
FROM `voxdatalake.{ds}.inventory_out_of_stock_report`""",
        "format": "int", "view": "inventory_out_of_stock_report",
        "note": "Distinct parts with nothing available (on hand less demand); Looker counted item names in a sheet with no filter."},
    "wip": {
        "sql": """SELECT SUM(SAFE_CAST(wip_value AS FLOAT64)) AS value
FROM `voxdatalake.{ds}.sales_order_value_by_status_report`""",
        "format": "usd_short", "view": "sales_order_value_by_status_report",
        "note": "Value of open Pending Fulfillment order lines (quantity pending times price); Looker summed the Amount of rows marked WIP in the Flow sheet."},
    "sales-mtd": {
        "sql": f"""SELECT SUM(SAFE_CAST(sales_value AS FLOAT64)) AS value
FROM `voxdatalake.{{ds}}.sales_mtd_summary_report`
WHERE sales_month = {MONTH}""",
        "format": "usd_short", "view": "sales_mtd_summary_report",
        "note": "Plex orders approved this month to date, today included; Looker excluded today."},
    "sales-to-goal": {
        "sql": f"""SELECT SAFE_DIVIDE(SUM(IF(sales_rep = '(company-wide)', 0, SAFE_CAST(actual_sales AS FLOAT64))),
                   MAX(IF(sales_rep = '(company-wide)', SAFE_CAST(goal_value AS FLOAT64), NULL))) AS value
FROM `voxdatalake.{{ds}}.sales_vs_goal_report`
WHERE sales_month = {MONTH}""",
        "format": "pct", "pct_scale": 1, "view": "sales_vs_goal_report",
        "note": "Month-to-date sales over the company-wide goal (ratio); the view's company-wide row carries the goal with actual 0, so actuals are summed from the rep rows."},
    "sales-goal": {
        "sql": f"""SELECT MAX(SAFE_CAST(goal_value AS FLOAT64)) AS value
FROM `voxdatalake.{{ds}}.sales_vs_goal_report`
WHERE sales_month = {MONTH} AND sales_rep = '(company-wide)'""",
        "format": "usd_short", "view": "sales_vs_goal_report",
        "note": "The company-wide sales goal for the month from the goals tables; Looker had it hardcoded per month in a view."},
    "sales-ytd": {
        "sql": """SELECT SUM(SAFE_CAST(sales_value AS FLOAT64)) AS value
FROM `voxdatalake.{ds}.sales_mtd_summary_report`
WHERE sales_year = EXTRACT(YEAR FROM CURRENT_DATE())""",
        "format": "usd_short", "view": "sales_mtd_summary_report",
        "note": "Plex orders approved since 1 January, today included; the view only holds the months the pipeline has loaded, so it can sit below Looker's year to date."},
    "pipeline-funnel": {
        "sql": """SELECT SUM(stage_total) AS value,
       STRING_AGG(CONCAT(pipeline_stage, ' $', CAST(ROUND(stage_total) AS STRING)), ' · ' ORDER BY stage_total DESC) AS detail
FROM (
  SELECT pipeline_stage, SUM(SAFE_CAST(pipeline_value AS FLOAT64)) AS stage_total
  FROM `voxdatalake.{ds}.pipeline_plex_value_report`
  GROUP BY pipeline_stage
)""",
        "format": "usd_short", "view": "pipeline_plex_value_report",
        "note": "Only the Quote and Pending Sales Approval stages come from Plex; Opportunities and Forecast were Monday-fed and have no Plex source, so this is a partial funnel."},
    "pipeline-total": {
        "sql": """SELECT SUM(SAFE_CAST(pipeline_value AS FLOAT64)) AS value
FROM `voxdatalake.{ds}.pipeline_plex_value_report`""",
        "format": "usd_short", "view": "pipeline_plex_value_report",
        "note": "Plex quotes and pending-approval orders only; Looker's total also included Monday opportunities and forecast, so Plex is expected to be far smaller."},
    **_production("encap", "Encapsulation", "encap_daily_report", "Encapsulating", "106.65M vs 100.00M"),
    **_production("bottling", "Bottling", "packaging_daily_report", "Bottling", "1.67M vs 1.50M"),
    **_production("labeling", "Labeling", "labeling_daily_report", "Labeling", "892.17K vs 700.00K"),
    "reworks": {
        "sql": """SELECT COUNT(*) AS value
FROM `voxdatalake.{ds}.quality_nonconformance_report`
WHERE final_disposition = 'Rework'
  AND problem_date >= DATE_TRUNC(CURRENT_DATE(), MONTH) AND problem_date < CURRENT_DATE()""",
        "format": "int", "view": "quality_nonconformance_report",
        "note": "Nonconformances this month to date (today excluded) with Final Disposition = Rework; which Plex meaning of 'rework' Vox intends is still open, and Final Disposition is blank on most records."},
    "deviations": {
        "sql": """SELECT COUNT(*) AS value
FROM `voxdatalake.{ds}.quality_deviation_report`
WHERE add_date >= DATE_TRUNC(CURRENT_DATE(), MONTH) AND add_date < CURRENT_DATE()""",
        "format": "int", "view": "quality_deviation_report",
        "note": "Deviations initiated this month to date (today excluded), the same window as Looker."},
    "destruction": {
        "sql": f"""SELECT SUM(SAFE_CAST(total_cost AS FLOAT64)) AS value
FROM `voxdatalake.{{ds}}.quality_disposition_cost_report`
WHERE problem_month = {MONTH} AND final_disposition = 'Scrap'""",
        "format": "usd", "view": "quality_disposition_cost_report",
        "note": "Cost of nonconformances dispositioned Scrap this month; Vox types the dollars into descriptions and logs destructions by form, so this stays NULL or 0 until that changes (Looker also showed no data)."},
    "fpy-encap": {"sql": _fpy("Encapsulating"), "format": "pct", "pct_scale": 1,
                  "view": "quality_fpy_by_area_month_report", "note": FPY_NOTE},
    "fpy-bottling": {"sql": _fpy("Bottling"), "format": "pct", "pct_scale": 1,
                     "view": "quality_fpy_by_area_month_report", "note": FPY_NOTE},
    "fpy-labeling": {"sql": _fpy("Labeling"), "format": "pct", "pct_scale": 1,
                     "view": "quality_fpy_by_area_month_report", "note": FPY_NOTE},
    "tat": {
        "sql": """SELECT AVG(SAFE_CAST(turnaround_work_days AS FLOAT64)) AS value,
       AVG(SAFE_CAST(performance_standard_days AS FLOAT64)) AS value2
FROM `voxdatalake.{ds}.quality_turnaround_time_report`
WHERE closed_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) AND closed_date <= CURRENT_DATE()""",
        "format": "days", "view": "quality_turnaround_time_report",
        "note": "Average work days to close over the last 30 days (value) and the average performance standard (value2) across all stock types; Looker charted both per stock type, and NULL means nothing closed in the window."},
    "open-caps": {
        "sql": """SELECT SUM(SAFE_CAST(caps_pending AS FLOAT64)) AS value
FROM `voxdatalake.{ds}.mfg_job_open_caps_report`""",
        "format": "short", "view": "mfg_job_open_caps_report",
        "note": "Capsules still to make on open Plex jobs; Looker summed Caps Pending in the MFG_Job sheet."},
    "open-bottles": {
        "sql": """SELECT SUM(SAFE_CAST(qty_pending AS FLOAT64)) AS value
FROM `voxdatalake.{ds}.bottling_job_open_report`""",
        "format": "short", "view": "bottling_job_open_report",
        "note": "Bottles still to fill on open Plex bottling jobs; Looker summed QTY in the Bottling_Job sheet."},
}
