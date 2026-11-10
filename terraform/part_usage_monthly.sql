-- Monthly usage per part: what recorded production consumed through the BOM, per calendar
-- month, with the daily average. Run by the `part_usage_monthly` scheduled query
-- (terraform/main.tf) on the 1st of each month, 13:30 UTC (after the 4 AM MT full prod run),
-- for the PREVIOUS month. Jennilyn asked for it (2026-11-10): a table of usage by item by
-- month for purchasing and production planning reports.
--
-- METHOD: the same as approaching_msl_report's Plex usage (reports/sql/approaching_msl_view.sql,
-- CTEs part / wrap / prod / usage / inv), restricted to one month:
--   qty_used = SUM(part_production_current.Quantity x Part_v_BOM.Quantity) on Part_Operation_Key,
--   rejected production excluded, inactive BOM lines skipped, wrapper BOM lines (stocked key
--   into its own wrapper) skipped, usage on a wrapper key converted into the stocked key's
--   unit by its factor, rolled up per part NUMBER. Summed over the view's window, this table
--   matches the view's plex_avg_daily_usage x usage_days on every part (506/506, 2026-11-10).
-- ONE DIFFERENCE, ON PURPOSE: the production date. ODBC's Report_Date is 22:00 the
--   evening BEFORE the day produced, so the view's DATE(Report_Date) is one day early (a
--   Monday record dates Sunday). The view's 90-day sum does not care; a month boundary does.
--   Here d = DATE(Report_Date + 2 h), the production day (= the calendar date of Plex's
--   Record_Date as stored) on every record
--   (19,748/19,748 on 2026-11-10).
--
-- WHICH PARTS GET ROWS: every part number consumed as a BOM COMPONENT of production recorded
--   in the month: raw materials, components, capsules and blends consumed by a later
--   operation. A finished good gets a row only if it is itself a component of something
--   produced; making a part is not using it. None in October 2026.
--
-- GRAIN: one row per (usage_month, part_no). usage_month is the first of the month.
--   part_key / revision / part_type are the stocked key's (not a wrapper's). Quantities are in
--   the stocked key's unit (blank in Plex for most raw materials, which are kg).
--   days_covered: calendar days of the month with Plex production history, from the first
--   production date Plex has (2026-10-19) or the 1st, to the month end or yesterday.
--   avg_daily_usage = qty_used / days_covered: for every complete month that is
--   qty_used / days_in_month; for October 2026 (13 days from go-live) it avoids understating
--   the rate 2.4x. is_partial_month says which. Calendar days, weekends included, like the view.
--
-- RE-RUN: safe. It deletes the month's rows and inserts them again. The BOM is read as it is at
--   run time, so a re-run after a BOM change gives different numbers: re-run only to fix.
-- BACKFILL / ONE MONTH BY HAND: change the DEFAULT of target_month to that month's first day.
-- BigQuery-only data: also in terraform/backup_snapshots.sql.
-- The measurement SQL lives in terraform/part_usage_for_month.sql (a table function, since
-- 2026-11-10), shared with the month-to-date view PlexProd.part_usage_month_to_date.

DECLARE target_month DATE DEFAULT DATE_TRUNC(DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 1 MONTH), MONTH);
DECLARE month_end    DATE DEFAULT LAST_DAY(target_month);

CREATE TABLE IF NOT EXISTS `voxdatalake.PlexProd.part_usage_monthly` (
  usage_month             DATE      NOT NULL OPTIONS (description = "first day of the month"),
  part_key                INT64              OPTIONS (description = "the part number's stocked key"),
  part_no                 STRING,
  revision                STRING,
  part_name               STRING,
  part_product_type       STRING,
  part_type               STRING,
  part_group              STRING,
  unit                    STRING             OPTIONS (description = "stocked key's unit; blank in Plex for most raw materials (kg)"),
  qty_used                FLOAT64            OPTIONS (description = "consumed by recorded production through the BOM, rejected excluded"),
  days_with_usage         INT64              OPTIONS (description = "production days in the month that consumed the part"),
  days_in_month           INT64,
  days_covered            INT64              OPTIONS (description = "calendar days of the month with Plex production history"),
  is_partial_month        BOOL               OPTIONS (description = "days_covered < days_in_month (October 2026: go-live 10-19)"),
  avg_daily_usage         FLOAT64            OPTIONS (description = "qty_used / days_covered, calendar days"),
  source_tables_loaded_at TIMESTAMP          OPTIONS (description = "oldest last load of raw_Part_v_Production / _BOM / _Part"),
  recorded_at             TIMESTAMP NOT NULL
)
PARTITION BY DATE_TRUNC(usage_month, MONTH)
CLUSTER BY part_no
OPTIONS (description = "Monthly usage per part from recorded production x BOM, same method as approaching_msl_report. Filled by the part_usage_monthly scheduled query.");

-- GUARD (audit 2026-11-10): refuse to record a month that has no production records at all
-- (a failed ETL or a frozen Plex feed), instead of recording it empty. The scheduled query
-- then fails, the watchdog's `usage_monthly` check reports the missing month, and a re-run
-- after the data arrives records it.
ASSERT (
  SELECT COUNT(*) FROM `voxdatalake.PlexProd.part_production_current`
  WHERE COALESCE(SAFE_CAST(Rejected AS INT64), 0) = 0
    AND COALESCE(
      DATE(TIMESTAMP_ADD(
        TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(Report_Date AS STRING) AS INT64), 0), 1000)),
        INTERVAL 2 HOUR)),
      NULLIF(SAFE_CAST(CAST(Report_Date AS STRING) AS DATE), DATE '1970-01-01')
    ) BETWEEN target_month AND month_end
) > 0 AS 'part_usage_monthly: no production records for the month; not recording it (ETL failed or Plex feed frozen?)';

DELETE FROM `voxdatalake.PlexProd.part_usage_monthly`
WHERE usage_month = target_month;

INSERT INTO `voxdatalake.PlexProd.part_usage_monthly`
-- The measurement itself is the table function part_usage_for_month (terraform/part_usage_for_month.sql),
-- shared with the month-to-date view so the two always agree.
SELECT * FROM `voxdatalake.PlexProd.part_usage_for_month`(target_month);
