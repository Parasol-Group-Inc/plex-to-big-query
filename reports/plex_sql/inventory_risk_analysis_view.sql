-- inventory_risk_analysis_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/inventory_risk_analysis_view.sql
-- confidence: high
-- plex_views: Part_v_Container, Part_v_Part, Part_v_Part_Product_Type
-- notes: Mechanical translation; is_at_risk returned as 1/0. The 90-day threshold is a best-criteria assumption carried over from the BigQuery view.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per part.
-- RULE: at risk = no container activity date, or 90+ days since the latest container Update_Date.
WITH container_activity AS (
  SELECT
    c.Part_Key                          AS part_key,
    SUM(c.Quantity)                     AS on_hand_qty,
    COUNT(*)                            AS container_count,
    MAX(CAST(c.Update_Date AS date))    AS last_activity_date
  FROM Part_v_Container AS c
  WHERE c.Active = 1
    AND UPPER(LTRIM(RTRIM(c.Container_Status))) IN ('OK', 'HOLD', 'INSPECTION REQUIRED', 'HOLD FOR DESIGN ORDER')
  GROUP BY c.Part_Key
),

enriched AS (
  SELECT
    p.Part_No                                                           AS part_no,
    p.Name                                                              AS part_name,
    p.Part_Type                                                         AS part_type,
    pt.Product_Type                                                     AS part_product_type,
    ca.on_hand_qty,
    ca.container_count,
    ca.last_activity_date,
    DATEDIFF(day, ca.last_activity_date, CAST(GETDATE() AS date))       AS days_since_activity
  FROM container_activity AS ca
  JOIN Part_v_Part AS p
    ON ca.part_key = p.Part_Key
  LEFT JOIN Part_v_Part_Product_Type AS pt
    ON p.Product_Type_Key = pt.Product_Type_Key
)

SELECT
  e.part_no,
  e.part_name,
  e.part_type,
  e.part_product_type,
  e.on_hand_qty,
  e.container_count,
  e.last_activity_date,
  e.days_since_activity,
  CASE WHEN e.last_activity_date IS NULL OR e.days_since_activity >= 90 THEN 1 ELSE 0 END AS is_at_risk
FROM enriched AS e;
