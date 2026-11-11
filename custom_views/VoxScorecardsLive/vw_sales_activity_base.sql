-- VoxScorecardsLive.vw_sales_activity_base (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-22 21:05 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH deduped AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY rep_name, activity_date
      ORDER BY submitted_at DESC
    ) AS rn
  FROM `voxdatalake.VoxScorecardsLive.daily_sales_activity`
)

SELECT
  rep_name,
  activity_date,
  submitted_at,
  is_pto,

  -- Activity fields (0 on PTO days for raw storage)
  emails_sent,
  calls_made,
  meetings,
  visits_to_vox,
  social_dms,
  other,
  total_activities,
  leads_assigned,
  leads_contacted,
  notes,

  -- Effective activities: PTO = full credit (40), otherwise actual
  CASE WHEN is_pto THEN 40 ELSE total_activities END AS effective_activities,

  -- Goal is always 40
  40 AS daily_goal,

  -- Goal status based on effective activities
  CASE
    WHEN is_pto                                        THEN 'PTO'
    WHEN total_activities >= 40                        THEN 'Met'
    WHEN total_activities >= 28                        THEN 'Near'   -- 70%+
    ELSE                                                    'Missed'
  END AS goal_status,

  -- Pct of goal (PTO = 100%)
  CASE
    WHEN is_pto THEN 1.0
    ELSE ROUND(total_activities / 40.0, 4)
  END AS pct_of_goal

FROM deduped
WHERE rn = 1
