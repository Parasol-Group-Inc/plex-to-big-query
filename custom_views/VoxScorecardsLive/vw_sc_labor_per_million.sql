-- VoxScorecardsLive.vw_sc_labor_per_million (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-19 16:55 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH cur AS (
  SELECT yesterday_date, yesterday_value / 1e6 AS yday_m, mtd_value / 1e6 AS mtd_m
  FROM `voxdatalake.VoxScorecardsLive.vw_sc_production_daily_mtd`
  WHERE area = 'Encapsulation'
),
holidays AS (
  SELECT d FROM UNNEST([DATE '2026-11-26', DATE '2026-11-27', DATE '2026-12-25', DATE '2027-01-01',
                        DATE '2027-05-31', DATE '2027-07-05', DATE '2027-09-06', DATE '2027-11-25',
                        DATE '2027-11-26', DATE '2027-12-24']) d
),
last3 AS (
  SELECT m.*
  FROM `voxdatalake.VoxScorecardsLive.production_labor_monthly` m, cur
  WHERE m.month_start < DATE_TRUNC(cur.yesterday_date, MONTH)
    AND m.capsules_produced > 0 AND m.workdays > 0
    AND m.temp_labor_cost IS NOT NULL AND m.vox_non_production_cost IS NOT NULL
    AND m.vox_production_cost IS NOT NULL AND m.production_ot_cost IS NOT NULL
    AND m.employee_benefits_cost IS NOT NULL AND m.parasol_admin_fees_cost IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (ORDER BY m.month_start DESC) <= 3
),
base AS (
  SELECT
    MIN(month_start) AS baseline_from, MAX(month_start) AS baseline_to, COUNT(*) AS baseline_months,
    SUM(workdays) AS baseline_workdays,
    SUM(capsules_produced) / 1e6 AS baseline_caps_m,
    AVG(CAST(temp_labor_cost AS FLOAT64)) AS avg_temp,
    AVG(CAST(vox_non_production_cost AS FLOAT64)) AS avg_nonprod,
    AVG(CAST(vox_production_cost AS FLOAT64)) AS avg_prod,
    AVG(CAST(production_ot_cost AS FLOAT64)) AS avg_ot,
    AVG(CAST(employee_benefits_cost AS FLOAT64)) AS avg_benefits,
    CAST(ARRAY_AGG(parasol_admin_fees_cost ORDER BY month_start DESC LIMIT 1)[OFFSET(0)] AS FLOAT64) AS admin_latest,
    SUM(temp_labor_cost + vox_non_production_cost + vox_production_cost + production_ot_cost
        + employee_benefits_cost + parasol_admin_fees_cost) AS baseline_total_labor,
    SUM(temp_labor_cost + vox_production_cost + production_ot_cost) AS baseline_prod_labor
  FROM last3
),
days AS (
  SELECT
    COUNTIF(d <= cur.yesterday_date) AS mtd_workdays,
    COUNT(*) AS month_workdays
  FROM cur, UNNEST(GENERATE_DATE_ARRAY(DATE_TRUNC(cur.yesterday_date, MONTH), LAST_DAY(cur.yesterday_date))) d
  WHERE EXTRACT(DAYOFWEEK FROM d) BETWEEN 2 AND 6 AND d NOT IN (SELECT d FROM holidays)
),
calc AS (
  SELECT b.*, c.*, dy.mtd_workdays, dy.month_workdays,
    b.avg_temp + b.avg_nonprod + b.avg_prod + b.avg_ot + b.avg_benefits + b.admin_latest AS month_total_labor,
    b.avg_temp + b.avg_prod + b.avg_ot AS month_prod_labor
  FROM base b, cur c, days dy
),
calc2 AS (
  SELECT *,
    month_total_labor / month_workdays AS daily_total_labor,
    month_prod_labor  / month_workdays AS daily_prod_labor
  FROM calc
)
SELECT
  yesterday_date,
  CAST(ROUND(yday_m, 3) AS NUMERIC) AS yesterday_caps_m,
  CAST(ROUND(SAFE_DIVIDE(daily_total_labor, yday_m), 0) AS NUMERIC) AS yesterday_total_labor_per_m,
  CAST(ROUND(SAFE_DIVIDE(daily_prod_labor,  yday_m), 0) AS NUMERIC) AS yesterday_prod_labor_per_m,
  mtd_workdays,
  month_workdays,
  CAST(ROUND(mtd_m, 3) AS NUMERIC) AS mtd_caps_m,
  CAST(ROUND(SAFE_DIVIDE(mtd_m, mtd_workdays) * month_workdays, 3) AS NUMERIC) AS projected_month_caps_m,
  CAST(ROUND(daily_total_labor * mtd_workdays, 0) AS NUMERIC) AS mtd_total_labor_est,
  CAST(ROUND(daily_prod_labor  * mtd_workdays, 0) AS NUMERIC) AS mtd_prod_labor_est,
  CAST(ROUND(SAFE_DIVIDE(daily_total_labor * mtd_workdays, mtd_m), 0) AS NUMERIC) AS mtd_total_labor_per_m,
  CAST(ROUND(SAFE_DIVIDE(daily_prod_labor  * mtd_workdays, mtd_m), 0) AS NUMERIC) AS mtd_prod_labor_per_m,
  CAST(ROUND(month_total_labor, 0) AS NUMERIC) AS month_total_labor_est,
  CAST(ROUND(month_prod_labor, 0)  AS NUMERIC) AS month_prod_labor_est,
  baseline_from, baseline_to, baseline_months, baseline_workdays,
  CONCAT(FORMAT_DATE('%b %y', baseline_from), ' - ', FORMAT_DATE('%b %y', baseline_to)) AS baseline_label,
  CAST(ROUND(daily_total_labor, 0) AS NUMERIC) AS daily_total_labor,
  CAST(ROUND(daily_prod_labor, 0)  AS NUMERIC) AS daily_prod_labor,
  CAST(ROUND(baseline_caps_m / baseline_workdays, 3) AS NUMERIC) AS baseline_caps_m_per_day,
  CAST(ROUND(SAFE_DIVIDE(CAST(baseline_total_labor AS FLOAT64), baseline_caps_m), 0) AS NUMERIC) AS baseline_total_labor_per_m,
  CAST(ROUND(SAFE_DIVIDE(CAST(baseline_prod_labor  AS FLOAT64), baseline_caps_m), 0) AS NUMERIC) AS baseline_prod_labor_per_m
FROM calc2
