-- VoxScorecardsLive.vw_sales_daily_detail (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-22 21:05 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH

all_dates AS (
  SELECT DISTINCT activity_date
  FROM `voxdatalake.VoxScorecardsLive.daily_sales_activity`
),

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
)

SELECT
  r.rep_name,
  d.activity_date,
  COALESCE(b.is_pto, FALSE)                               AS is_pto,
  COALESCE(b.emails_sent, 0)                              AS emails_sent,
  COALESCE(b.calls_made, 0)                               AS calls_made,
  COALESCE(b.meetings, 0)                                 AS meetings,
  COALESCE(b.visits_to_vox, 0)                            AS visits_to_vox,
  COALESCE(b.social_dms, 0)                               AS social_dms,
  COALESCE(b.other, 0)                                    AS other,
  COALESCE(b.effective_activities, 0)                     AS total_activities,
  40                                                      AS goal,
  COALESCE(b.pct_of_goal, 0.0)                            AS pct_of_goal,
  COALESCE(b.goal_status, 'Missed')                       AS goal_status,
  COALESCE(b.leads_assigned, 0)                           AS leads_assigned,
  COALESCE(b.leads_contacted, 0)                          AS leads_contacted,
  COALESCE(b.notes, '')                                   AS notes

FROM rep_spine r
CROSS JOIN all_dates d
LEFT JOIN `voxdatalake.VoxScorecardsLive.vw_sales_activity_base` b
  ON b.rep_name = r.rep_name
  AND b.activity_date = d.activity_date
