-- part_obsolescence_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/part_obsolescence_view.sql
-- confidence: high
-- plex_views: Part_v_Part
-- notes: Extraction-time filter (Part_Status IN ('Obsolete','Phase Out')) applied as WHERE.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per part.
SELECT
  p.Part_No                       AS part_number,
  p.Name                          AS part_name,
  p.Part_Type                     AS part_type,
  p.Part_Status                   AS part_status,
  CAST(p.Updated_Date AS date)    AS status_last_updated
FROM Part_v_Part AS p
WHERE p.Part_Status IN ('Obsolete', 'Phase Out');
