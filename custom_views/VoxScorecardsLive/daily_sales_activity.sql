-- VoxScorecardsLive.daily_sales_activity (base table), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-15 21:28 UTC by jennilyn.tockstein@parasolgroupinc.com
-- a TABLE: this is the statement that last built it; its data is a snapshot

CREATE TABLE IF NOT EXISTS `voxdatalake.VoxScorecardsLive.daily_sales_activity` (
  rep_name             STRING    NOT NULL,
  activity_date        DATE      NOT NULL,
  submitted_at         TIMESTAMP NOT NULL,
  is_pto               BOOL      NOT NULL,
  activities_completed INT64     NOT NULL,
  emails_sent          INT64     NOT NULL,
  calls_made           INT64     NOT NULL,
  meetings             INT64     NOT NULL,
  visits_to_vox        INT64     NOT NULL,
  social_dms           INT64     NOT NULL,
  other                INT64     NOT NULL,
  total_activities     INT64     NOT NULL,
  leads_assigned       INT64     NOT NULL,
  leads_contacted      INT64     NOT NULL,
  notes                STRING
)
PARTITION BY activity_date
OPTIONS (
  description = 'Daily sales activity log submitted via the Vox Sales Activity web form'
);
