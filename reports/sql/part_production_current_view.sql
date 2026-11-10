-- part_production_current: raw_Part_v_Production, plus Plex's own production
-- screens while Plex ODBC is frozen (OPEN_ITEMS D20 / D30).
--
-- Same columns, types and conventions as raw_Part_v_Production, so a report
-- reads this view in its place with no other change. Every report that counts
-- production reads it (added 2026-11-06).
--
-- LIVE SOURCE: the hourly laptop task loads Plex's Job Production report and
-- Production History screen into PlexProd.live_production
-- (scripts/plex_live_screens.py, docs/PLEX_SCREEN_EXTRACTION.md), every record
-- since 2026-11-01. On the 2,100 records both held (11-02 and 11-03), the
-- screens matched ODBC on every job op, part operation, part, workcenter,
-- employee, rejected flag, quantity and record time.
--   * While live_switch.use_live: every live record, plus every ODBC record
--     the screens do not have (everything before November). Live wins on a
--     Production_No both hold.
--   * use_live goes FALSE by itself when BOTH hold: PlexOps.odbc_health says
--     ODBC has been stable 6+ h, and ODBC holds every live record more than
--     3 h older than the last load (a frozen copy connects and "succeeds", so
--     connection health alone cannot prove fresh data). Then it is ODBC only.
--     PlexTest and the sandbox never read the screens.
--   * Keys resolve against the raw master tables: Job_Op_Key and
--     Part_Operation_Key by job no + op no, Part_Key by part no + revision,
--     Workcenter_Key by code, Record_By by the employee's full name.
--     A record on a job created after the freeze has no Job_Op row in the
--     frozen copy, so its Job_Op_Key is NULL (232 of 4,828 on 2026-11-06):
--     reports that join Job_Op do not see it. Its Part_Operation_Key falls
--     back to the part's routing (part + op no in raw_Part_v_Part_Operation),
--     which agreed with Job_Op on all 4,596 records that have both.
--   * Record_Date and Report_Date copy ODBC's convention: Mountain wall time
--     stored as if it were UTC, in nanoseconds. ODBC's Report_Date is 22:00
--     the evening before the report date, on every record checked.
--   * Report_Shift: the screens say '1st' (ODBC key 7824) or nothing ('0').
--     Any other shift name comes through as NULL.
--   * Serial_No is blank on some screen rows (47 of 2,100 checked); no report
--     uses it. Weights, Production_Value, Log_Key and the like are NULL.

-- SINCE 2026-11-10 the cloud job plex-live-screens decides (docs/PLEX_SCREEN_EXTRACTION.md,
-- "Reconciliation"): every hour it reads the screens, compares them with ODBC and
-- sets PlexOps.live_source.use_live for this report's group when ODBC is behind or
-- disagrees. Since 2026-11-10 (Emilio) production is NOT compared: live_source has no
-- 'production' row, so this view stays on ODBC. Re-adding the production screen to
-- screen_recon.py GROUPS and the live_source view turns the switch back on.
-- In live mode the job loads only the days it re-reads (RECON_PRODUCTION_DAYS); every
-- other record still comes from ODBC through the merge below.
WITH live_switch AS (
  SELECT
    '{dataset}' = 'PlexProd'
      AND IFNULL((SELECT ls.use_live FROM `{gcp_project}.PlexOps.live_source` ls
                  WHERE ls.report_group = 'production'), FALSE)
      AND IFNULL((SELECT MAX(l.loaded_at) FROM `{gcp_project}.PlexProd.live_production` l)
                 > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 HOUR), FALSE) AS use_live
),

job_ops AS (
  SELECT
    j.Job_No,
    SAFE_CAST(o.Op_No AS INT64)              AS Op_No,
    SAFE_CAST(o.Job_Op_Key AS INT64)         AS Job_Op_Key,
    SAFE_CAST(o.Part_Operation_Key AS INT64) AS Part_Operation_Key
  FROM `{gcp_project}.{dataset}.raw_Part_v_Job` AS j
  JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Op` AS o
    ON SAFE_CAST(o.Job_Key AS INT64) = SAFE_CAST(j.Job_Key AS INT64)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY j.Job_No, SAFE_CAST(o.Op_No AS INT64)
                             ORDER BY SAFE_CAST(o.Job_Op_Key AS INT64) DESC) = 1
),

part_ops AS (
  SELECT
    SAFE_CAST(po.Part_Key AS INT64)     AS Part_Key,
    SAFE_CAST(po.Operation_No AS INT64) AS Operation_No,
    ARRAY_AGG(SAFE_CAST(po.Part_Operation_Key AS INT64)
              ORDER BY SAFE_CAST(po.Part_Operation_Key AS INT64) DESC LIMIT 1)[OFFSET(0)]
                                        AS Part_Operation_Key
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Operation` AS po
  WHERE IFNULL(CAST(po.Active AS STRING), '1') NOT IN ('0', 'false')
  GROUP BY 1, 2
),

parts AS (
  SELECT pp.Part_No, pp.Revision, SAFE_CAST(pp.Part_Key AS INT64) AS Part_Key
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part` AS pp
  QUALIFY ROW_NUMBER() OVER (PARTITION BY pp.Part_No, pp.Revision
                             ORDER BY SAFE_CAST(pp.Part_Key AS INT64) DESC) = 1
),

workcenters AS (
  SELECT w.Workcenter_Code, SAFE_CAST(w.Workcenter_Key AS INT64) AS Workcenter_Key
  FROM `{gcp_project}.{dataset}.raw_Part_v_Workcenter` AS w
  QUALIFY ROW_NUMBER() OVER (PARTITION BY w.Workcenter_Code
                             ORDER BY SAFE_CAST(w.Workcenter_Key AS INT64) DESC) = 1
),

users AS (
  SELECT
    CONCAT(TRIM(u.First_Name), ' ', TRIM(u.Last_Name)) AS full_name,
    SAFE_CAST(u.Plexus_User_No AS INT64)                AS Plexus_User_No
  FROM `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` AS u
  -- an ambiguous full name stays unresolved rather than credited to the wrong person
  QUALIFY COUNT(*) OVER (PARTITION BY CONCAT(TRIM(u.First_Name), ' ', TRIM(u.Last_Name))) = 1
),

live_rows AS (
  SELECT
    CAST(NULL AS INT64)                                   AS Plexus_Customer_No,
    l.production_no                                       AS Production_No,
    NULLIF(l.serial_no, '')                               AS Serial_No,
    UNIX_MICROS(TIMESTAMP_SUB(TIMESTAMP(l.report_date), INTERVAL 2 HOUR)) * 1000
                                                          AS Report_Date,
    CASE WHEN l.shift = '1st' THEN '7824'
         WHEN l.shift IS NULL OR l.shift = '' THEN '0' END AS Report_Shift,
    l.quantity                                            AS Quantity,
    UNIX_MICROS(TIMESTAMP(DATETIME(l.record_time, 'America/Denver'))) * 1000
                                                          AS Record_Date,
    us.Plexus_User_No                                     AS Record_By,
    pa.Part_Key                                           AS Part_Key,
    COALESCE(jo.Part_Operation_Key, ro.Part_Operation_Key) AS Part_Operation_Key,
    wc.Workcenter_Key                                     AS Workcenter_Key,
    CAST(NULL AS STRING)                                  AS Note,
    CAST(NULL AS FLOAT64)                                 AS Piece_Weight,
    CAST(NULL AS FLOAT64)                                 AS Gross_Weight,
    CAST(NULL AS FLOAT64)                                 AS Tare_Weight,
    CAST(NULL AS FLOAT64)                                 AS Net_Weight,
    CAST(NULL AS INT64)                                   AS Timeblock_Key,
    CAST(NULL AS INT64)                                   AS Log_Key,
    jo.Job_Op_Key                                         AS Job_Op_Key,
    l.rejected                                            AS Rejected,
    CAST(NULL AS INT64)                                   AS PRIMARY_Cost_Key,
    CAST(NULL AS INT64)                                   AS Multi_Out_Child,
    CAST(NULL AS INT64)                                   AS Multi_Out_Parent,
    CAST(NULL AS FLOAT64)                                 AS Production_Value,
    CAST(NULL AS STRING)                                  AS Cavity_No,
    CAST(NULL AS INT64)                                   AS Setup_Key,
    'live'                                                AS data_source
  FROM `{gcp_project}.PlexProd.live_production` AS l
  LEFT JOIN job_ops     AS jo ON jo.Job_No = l.job_no AND jo.Op_No = l.op_no
  LEFT JOIN parts       AS pa ON pa.Part_No = l.part_no AND pa.Revision = l.revision
  LEFT JOIN workcenters AS wc ON wc.Workcenter_Code = l.workcenter_code
  LEFT JOIN part_ops    AS ro ON ro.Part_Key = pa.Part_Key AND ro.Operation_No = l.op_no
  LEFT JOIN users       AS us ON us.full_name = l.employee
),

odbc_rows AS (
  SELECT
    SAFE_CAST(r.Plexus_Customer_No AS INT64) AS Plexus_Customer_No,
    SAFE_CAST(r.Production_No AS INT64)      AS Production_No,
    CAST(r.Serial_No AS STRING)              AS Serial_No,
    SAFE_CAST(r.Report_Date AS INT64)        AS Report_Date,
    CAST(r.Report_Shift AS STRING)           AS Report_Shift,
    SAFE_CAST(r.Quantity AS FLOAT64)         AS Quantity,
    SAFE_CAST(r.Record_Date AS INT64)        AS Record_Date,
    SAFE_CAST(r.Record_By AS INT64)          AS Record_By,
    SAFE_CAST(r.Part_Key AS INT64)           AS Part_Key,
    SAFE_CAST(r.Part_Operation_Key AS INT64) AS Part_Operation_Key,
    SAFE_CAST(r.Workcenter_Key AS INT64)     AS Workcenter_Key,
    CAST(r.Note AS STRING)                   AS Note,
    SAFE_CAST(r.Piece_Weight AS FLOAT64)     AS Piece_Weight,
    SAFE_CAST(r.Gross_Weight AS FLOAT64)     AS Gross_Weight,
    SAFE_CAST(r.Tare_Weight AS FLOAT64)      AS Tare_Weight,
    SAFE_CAST(r.Net_Weight AS FLOAT64)       AS Net_Weight,
    SAFE_CAST(r.Timeblock_Key AS INT64)      AS Timeblock_Key,
    SAFE_CAST(r.Log_Key AS INT64)            AS Log_Key,
    SAFE_CAST(r.Job_Op_Key AS INT64)         AS Job_Op_Key,
    SAFE_CAST(r.Rejected AS INT64)           AS Rejected,
    SAFE_CAST(r.PRIMARY_Cost_Key AS INT64)   AS PRIMARY_Cost_Key,
    SAFE_CAST(r.Multi_Out_Child AS INT64)    AS Multi_Out_Child,
    SAFE_CAST(r.Multi_Out_Parent AS INT64)   AS Multi_Out_Parent,
    SAFE_CAST(r.Production_Value AS FLOAT64) AS Production_Value,
    CAST(r.Cavity_No AS STRING)              AS Cavity_No,
    SAFE_CAST(r.Setup_Key AS INT64)          AS Setup_Key,
    'odbc'                                   AS data_source
  FROM `{gcp_project}.{dataset}.raw_Part_v_Production` AS r
)

SELECT o.*
FROM odbc_rows AS o
CROSS JOIN live_switch AS sw
WHERE NOT sw.use_live
   OR IFNULL(o.Production_No, -1) NOT IN (SELECT lr.Production_No FROM live_rows AS lr)
UNION ALL
SELECT v.*
FROM live_rows AS v
CROSS JOIN live_switch AS sw
WHERE sw.use_live
