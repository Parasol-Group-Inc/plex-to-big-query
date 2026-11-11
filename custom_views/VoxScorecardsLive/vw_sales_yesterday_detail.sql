-- VoxScorecardsLive.vw_sales_yesterday_detail (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-22 13:40 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH yesterday AS (
  SELECT
    CASE
      WHEN EXTRACT(DAYOFWEEK FROM CURRENT_DATE('America/Denver')) = 2
        THEN DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 3 DAY)
      ELSE DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 1 DAY)
    END AS yesterday_date
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
  y.yesterday_date                                        AS activity_date,
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
CROSS JOIN yesterday y
LEFT JOIN `voxdatalake.VoxScorecardsLive.vw_sales_activity_base` b
  ON b.rep_name = r.rep_name
  AND b.activity_date = y.yesterday_date
