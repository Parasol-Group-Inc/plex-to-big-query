-- inventory_activity_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/inventory_activity_view.sql
-- confidence: high
-- plex_views: Part_v_Cell_Production, Part_v_Cell_Depletion, Part_v_Part
-- notes: Mechanical translation; date decoding dropped, DATE_TRUNC -> DATEFROMPARTS. Both source views were empty on the test tenant when built.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per part per calendar month.
WITH production_dated AS (
  SELECT
    cp.Part_Key AS Part_Key,
    cp.Quantity AS Quantity,
    CAST(cp.Production_Date AS date) AS production_date
  FROM Part_v_Cell_Production AS cp
),

depletion_dated AS (
  SELECT
    cd.Part_Key AS Part_Key,
    cd.Quantity AS Quantity,
    CAST(cd.Production_Date AS date) AS depletion_date
  FROM Part_v_Cell_Depletion AS cd
),

production_monthly AS (
  SELECT
    pd.Part_Key,
    DATEFROMPARTS(YEAR(pd.production_date), MONTH(pd.production_date), 1) AS activity_month,
    SUM(pd.Quantity) AS produced_quantity
  FROM production_dated AS pd
  WHERE pd.production_date IS NOT NULL
  GROUP BY pd.Part_Key, DATEFROMPARTS(YEAR(pd.production_date), MONTH(pd.production_date), 1)
),

depletion_monthly AS (
  SELECT
    dd.Part_Key,
    DATEFROMPARTS(YEAR(dd.depletion_date), MONTH(dd.depletion_date), 1) AS activity_month,
    SUM(dd.Quantity) AS depleted_quantity
  FROM depletion_dated AS dd
  WHERE dd.depletion_date IS NOT NULL
  GROUP BY dd.Part_Key, DATEFROMPARTS(YEAR(dd.depletion_date), MONTH(dd.depletion_date), 1)
)

SELECT
  COALESCE(prod.Part_Key, dep.Part_Key)               AS part_key,
  p.Part_No                                           AS part_number,
  p.Name                                              AS part_name,
  COALESCE(prod.activity_month, dep.activity_month)   AS activity_month,
  COALESCE(prod.produced_quantity, 0)                 AS produced_quantity,
  COALESCE(dep.depleted_quantity, 0)                  AS depleted_quantity,
  COALESCE(prod.produced_quantity, 0) - COALESCE(dep.depleted_quantity, 0) AS net_change
FROM production_monthly AS prod
FULL OUTER JOIN depletion_monthly AS dep
  ON prod.Part_Key = dep.Part_Key AND prod.activity_month = dep.activity_month
LEFT JOIN Part_v_Part AS p
  ON COALESCE(prod.Part_Key, dep.Part_Key) = p.Part_Key;
