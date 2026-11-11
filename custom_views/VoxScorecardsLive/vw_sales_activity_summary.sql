-- VoxScorecardsLive.vw_sales_activity_summary (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-22 21:05 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH

-- ── Date anchors ──────────────────────────────────────────────
anchors AS (
  SELECT
    -- Yesterday (previous workday)
    CASE
      WHEN EXTRACT(DAYOFWEEK FROM CURRENT_DATE('America/Denver')) = 2  -- Monday
        THEN DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 3 DAY)  -- Friday
      WHEN EXTRACT(DAYOFWEEK FROM CURRENT_DATE('America/Denver')) = 1  -- Sunday (shouldn't happen)
        THEN DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 2 DAY)
      ELSE DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 1 DAY)
    END AS yesterday,

    -- WTD start: Monday of current week
    -- On Mondays, use previous Monday (show last full week)
    CASE
      WHEN EXTRACT(DAYOFWEEK FROM CURRENT_DATE('America/Denver')) = 2  -- Monday
        THEN DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 7 DAY)
      ELSE DATE_TRUNC(CURRENT_DATE('America/Denver'), WEEK(MONDAY))
    END AS wtd_start,

    -- MTD start: first of current month
    DATE_TRUNC(CURRENT_DATE('America/Denver'), MONTH) AS mtd_start,

    -- Today (for MTD working days calc)
    CURRENT_DATE('America/Denver') AS today
),

-- ── Working days so far this month (for MTD goal denominator) ──
-- Count Mon-Fri between mtd_start and yesterday inclusive
mtd_working_days AS (
  SELECT COUNT(*) AS working_days
  FROM UNNEST(
    GENERATE_DATE_ARRAY(
      (SELECT mtd_start FROM anchors),
      (SELECT yesterday FROM anchors)
    )
  ) AS d
  WHERE EXTRACT(DAYOFWEEK FROM d) NOT IN (1, 7)  -- exclude Sun (1) and Sat (7)
),

-- ── Rep spine (all reps, so we always show all 7) ─────────────
rep_spine AS (
  SELECT rep_name FROM UNNEST([
    'Kami Butcher',
    'Tyler Hall',
    'Janet Pacheco',
    'Ruben Espinosa',
    'Landen Epperson',
    'Aishah Alqasim',
    'Zeljan Avdic'
  ]) AS rep_name
),

-- ── Base data joined to anchors ───────────────────────────────
base AS (
  SELECT
    b.*,
    a.yesterday,
    a.wtd_start,
    a.mtd_start
  FROM `voxdatalake.VoxScorecardsLive.vw_sales_activity_base` b
  CROSS JOIN anchors a
),

-- ── Yesterday ─────────────────────────────────────────────────
yesterday_agg AS (
  SELECT
    rep_name,
    SUM(effective_activities)  AS yesterday_activities,
    MAX(daily_goal)            AS yesterday_goal,
    MAX(goal_status)           AS yesterday_status,
    MAX(pct_of_goal)           AS yesterday_pct,
    MAX(CAST(is_pto AS INT64)) AS yesterday_pto
  FROM base
  WHERE activity_date = yesterday
  GROUP BY rep_name
),

-- ── WTD working days (fixed denominator regardless of submissions) ──
wtd_working_days AS (
  SELECT COUNT(*) AS working_days
  FROM UNNEST(
    GENERATE_DATE_ARRAY(
      (SELECT wtd_start FROM anchors),
      (SELECT yesterday FROM anchors)
    )
  ) AS d
  WHERE EXTRACT(DAYOFWEEK FROM d) NOT IN (1, 7)
),

-- ── WTD ───────────────────────────────────────────────────────
wtd_agg AS (
  SELECT
    rep_name,
    SUM(effective_activities)                                          AS wtd_activities,
    (SELECT working_days FROM wtd_working_days) * 40                  AS wtd_goal,
    ROUND(SUM(effective_activities) /
      NULLIF((SELECT working_days FROM wtd_working_days) * 40.0, 0), 4) AS wtd_pct
  FROM base
  WHERE activity_date BETWEEN wtd_start AND yesterday
  GROUP BY rep_name
),

-- ── MTD ───────────────────────────────────────────────────────
mtd_agg AS (
  SELECT
    rep_name,
    SUM(effective_activities)         AS mtd_activities,
    SUM(leads_assigned)               AS mtd_leads_assigned,
    SUM(leads_contacted)              AS mtd_leads_contacted,
    -- MTD goal = working days this month × 40
    (SELECT working_days FROM mtd_working_days) * 40 AS mtd_goal,
    ROUND(
      SUM(effective_activities) /
      NULLIF((SELECT working_days FROM mtd_working_days) * 40.0, 0)
    , 4) AS mtd_pct
  FROM base
  WHERE activity_date BETWEEN mtd_start AND yesterday
  GROUP BY rep_name
)

-- ── Final join ────────────────────────────────────────────────
SELECT
  r.rep_name,

  -- Yesterday
  COALESCE(y.yesterday_activities, 0)  AS yesterday_activities,
  COALESCE(y.yesterday_goal, 40)       AS yesterday_goal,
  COALESCE(y.yesterday_pct, 0)         AS yesterday_pct,
  COALESCE(y.yesterday_status, 'Missed') AS yesterday_status,
  COALESCE(y.yesterday_pto, 0) = 1     AS yesterday_is_pto,

  -- WTD
  COALESCE(w.wtd_activities, 0)        AS wtd_activities,
  COALESCE(w.wtd_goal, 0)              AS wtd_goal,
  COALESCE(w.wtd_pct, 0)              AS wtd_pct,

  -- MTD
  COALESCE(m.mtd_activities, 0)        AS mtd_activities,
  COALESCE(m.mtd_goal, 0)              AS mtd_goal,
  COALESCE(m.mtd_pct, 0)              AS mtd_pct,

  -- Leads MTD
  COALESCE(m.mtd_leads_assigned, 0)   AS mtd_leads_assigned,
  COALESCE(m.mtd_leads_contacted, 0)  AS mtd_leads_contacted

FROM rep_spine r
LEFT JOIN yesterday_agg y ON r.rep_name = y.rep_name
LEFT JOIN wtd_agg        w ON r.rep_name = w.rep_name
LEFT JOIN mtd_agg        m ON r.rep_name = m.rep_name
