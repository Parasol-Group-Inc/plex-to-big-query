-- label_design_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/label_design_view.sql
-- confidence: medium
-- plex_views: Sales_v_PO, Sales_v_PO_Line, Sales_v_Release, Sales_v_Release_Status, Sales_v_PO_Status, Sales_v_PO_Line_Note, Sales_v_Order_Salesperson, Part_v_Priority, Part_v_Customer_Part, Part_v_Part, Part_v_Flat_BOM, Part_v_Attribute, Part_v_Part_Attribute, Common_v_Customer, Plexus_Control_v_Plexus_User
-- notes: Regexes (bottle material, reason-code prefix, memo strip) rewritten with LIKE/PATINDEX; the BigQuery {dataset} switch for Plex URLs is hardcoded to prod (vox.on.plex.com) and the 2026-10-18 start date is carried over. Unverified in Plex SQL Developer.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per PO line (the earliest-due Label Design release wins), orders from the last 14 days, PO status Pending Fulfillment.
-- RULE: reason code is the leading digit 1-6 of the Job_Note (a decimal like 1.5 does not count); the rest is the memo.
-- RULE: bottle and label are the nearest Flat_BOM component whose name starts BOTTLE / LABEL; part attributes come from the label part.
-- URL BASE: prod shown; for the test host use https://vox.test.on.plex.com.
WITH rep_outside AS (
  SELECT
    sp.PO_Key           AS PO_Key,
    MIN(sp.Plexus_User_No) AS Plexus_User_No
  FROM Sales_v_Order_Salesperson AS sp
  GROUP BY sp.PO_Key
),

users AS (
  SELECT
    u.Plexus_User_No                 AS Plexus_User_No,
    u.First_Name + ' ' + u.Last_Name AS user_name
  FROM Plexus_Control_v_Plexus_User AS u
),

-- newest Job_Note per PO line (highest note key)
job_notes AS (
  SELECT x.PO_Line_Key, x.Note AS Job_Note
  FROM (
    SELECT
      n.PO_Line_Key AS PO_Line_Key,
      n.Note        AS Note,
      ROW_NUMBER() OVER (PARTITION BY n.PO_Line_Key ORDER BY n.PO_Line_Note_Key DESC) AS rn
    FROM Sales_v_PO_Line_Note AS n
    WHERE n.Note_Type = 'Job_Note'
  ) AS x
  WHERE x.rn = 1
),

part_attribute_types AS (
  SELECT a.Attribute_Key, a.Attribute_Name
  FROM Part_v_Attribute AS a
),

part_attributes_pivoted AS (
  SELECT
    pa.Part_Key AS Part_Key,
    MAX(CASE WHEN pt.Attribute_Name = 'Label Size'              THEN NULLIF(LTRIM(RTRIM(pa.Value)), '') END) AS part_label_size,
    MAX(CASE WHEN pt.Attribute_Name = 'Size'                    THEN NULLIF(LTRIM(RTRIM(pa.Value)), '') END) AS part_size,
    MAX(CASE WHEN pt.Attribute_Name = 'Allergen'                THEN NULLIF(LTRIM(RTRIM(pa.Value)), '') END) AS part_allergen,
    MAX(CASE WHEN pt.Attribute_Name = 'Hazardous'               THEN NULLIF(LTRIM(RTRIM(pa.Value)), '') END) AS part_hazardous,
    MAX(CASE WHEN pt.Attribute_Name = 'Certifications'          THEN NULLIF(LTRIM(RTRIM(pa.Value)), '') END) AS part_certifications,
    MAX(CASE WHEN pt.Attribute_Name = 'Printing Material'       THEN NULLIF(LTRIM(RTRIM(pa.Value)), '') END) AS part_printing_material,
    MAX(CASE WHEN pt.Attribute_Name = 'Bottle Material'         THEN NULLIF(LTRIM(RTRIM(pa.Value)), '') END) AS part_bottle_material,
    MAX(CASE WHEN pt.Attribute_Name = 'California PDP'          THEN NULLIF(LTRIM(RTRIM(pa.Value)), '') END) AS part_california_pdp,
    MAX(CASE WHEN pt.Attribute_Name = 'Prop 65 Requirement'     THEN NULLIF(LTRIM(RTRIM(pa.Value)), '') END) AS part_prop_65_requirement,
    MAX(CASE WHEN pt.Attribute_Name = 'Trademark'               THEN NULLIF(LTRIM(RTRIM(pa.Value)), '') END) AS part_trademark,
    MAX(CASE WHEN pt.Attribute_Name = 'Material Classification' THEN NULLIF(LTRIM(RTRIM(pa.Value)), '') END) AS part_material_classification
  FROM Part_v_Part_Attribute AS pa
  JOIN part_attribute_types AS pt
    ON pt.Attribute_Key = pa.Attribute_Key
  GROUP BY pa.Part_Key
),

-- nearest BOM component named BOTTLE...
bottles AS (
  SELECT x.Part_Key, x.part_no, x.name
  FROM (
    SELECT
      fb.Part_Key AS Part_Key,
      c.Part_No   AS part_no,
      c.Name      AS name,
      ROW_NUMBER() OVER (PARTITION BY fb.Part_Key ORDER BY fb.BOM_Level, c.Part_No) AS rn
    FROM Part_v_Flat_BOM AS fb
    JOIN Part_v_Part AS c
      ON c.Part_Key = fb.Component_Part_Key
    WHERE UPPER(LTRIM(RTRIM(c.Name))) LIKE 'BOTTLE%'
  ) AS x
  WHERE x.rn = 1
),

-- nearest BOM component named LABEL...
labels AS (
  SELECT x.Part_Key, x.label_part_key, x.part_no, x.name
  FROM (
    SELECT
      fb.Part_Key AS Part_Key,
      c.Part_Key  AS label_part_key,
      c.Part_No   AS part_no,
      c.Name      AS name,
      ROW_NUMBER() OVER (PARTITION BY fb.Part_Key ORDER BY fb.BOM_Level, c.Part_No) AS rn
    FROM Part_v_Flat_BOM AS fb
    JOIN Part_v_Part AS c
      ON c.Part_Key = fb.Component_Part_Key
    WHERE UPPER(LTRIM(RTRIM(c.Name))) LIKE 'LABEL%'
  ) AS x
  WHERE x.rn = 1
),

release_lines AS (
  SELECT
    po.Order_No                                   AS order_number,
    po.PO_No                                      AS customer_po,
    cust.Name                                     AS customer_name,
    cp.Customer_Part_No                           AS customer_part_no,
    rs.Release_Status                             AS line_status,
    pr.Description                                AS priority,
    CAST(rel.Due_Date AS date)                    AS due_date_resolved,
    CAST(po.PO_Date AS date)                      AS order_date,
    jn.Job_Note                                   AS job_note,
    NULLIF(LTRIM(RTRIM(jn.Job_Note)), '')         AS _note,

    ui.user_name                                  AS sales_rep_inside,
    ua.user_name                                  AS customer_account_rep,
    COALESCE(ui.user_name, ua.user_name)          AS am,
    COALESCE(uo2.user_name, uo.user_name, ub.user_name) AS bdm,

    cust.Email                                    AS customer_email,
    cust.Phone                                    AS customer_phone,
    cp.Customer_Part_Description                  AS customer_part_description,
    ps.PO_Status                                  AS order_status,

    po.PO_Key                                     AS po_key,
    pol.Part_Key                                  AS part_key,
    part.Part_No                                  AS part_no,
    part.Revision                                 AS part_revision,
    part.Name                                     AS part_name,
    bt.part_no                                    AS bottle_part_no,
    bt.name                                       AS bottle_name,
    lb.label_part_key                             AS label_part_key,
    lb.part_no                                    AS label_part_no,
    lb.name                                       AS label_part_name,

    pap.part_label_size                           AS part_label_size,
    pap.part_size                                 AS part_size,
    pap.part_allergen                             AS part_allergen,
    pap.part_hazardous                            AS part_hazardous,
    pap.part_certifications                       AS part_certifications,
    pap.part_printing_material                    AS part_printing_material,
    pap.part_bottle_material                      AS part_bottle_material,
    pap.part_california_pdp                       AS part_california_pdp,
    pap.part_prop_65_requirement                  AS part_prop_65_requirement,
    pap.part_trademark                            AS part_trademark,
    pap.part_material_classification              AS part_material_classification,

    pol.PO_Line_Key                               AS po_line_key,
    rel.Release_Key                               AS _tiebreak_release_key

  FROM Sales_v_PO AS po
  JOIN Sales_v_PO_Line AS pol
    ON pol.PO_Key = po.PO_Key
  JOIN Sales_v_Release AS rel
    ON rel.PO_Line_Key = pol.PO_Line_Key
  JOIN Sales_v_Release_Status AS rs
    ON rs.Release_Status_Key = rel.Release_Status_Key
  LEFT JOIN Part_v_Priority AS pr
    ON pr.Priority_Key = rel.Priority_Key
  JOIN Sales_v_PO_Status AS ps
    ON ps.PO_Status_Key = po.PO_Status_Key
  LEFT JOIN job_notes AS jn
    ON jn.PO_Line_Key = pol.PO_Line_Key
  LEFT JOIN Part_v_Customer_Part AS cp
    ON cp.Customer_Part_Key = pol.Customer_Part_Key
  LEFT JOIN Part_v_Part AS part
    ON part.Part_Key = pol.Part_Key
  LEFT JOIN Common_v_Customer AS cust
    ON cust.Customer_No = po.Customer_No

  LEFT JOIN users       AS ui  ON ui.Plexus_User_No  = po.Inside_Sales
  LEFT JOIN users       AS ua  ON ua.Plexus_User_No  = cust.Assigned_To
  LEFT JOIN rep_outside AS ro  ON ro.PO_Key          = po.PO_Key
  LEFT JOIN users       AS uo2 ON uo2.Plexus_User_No = ro.Plexus_User_No
  LEFT JOIN users       AS uo  ON uo.Plexus_User_No  = po.Outside_Sales
  LEFT JOIN users       AS ub  ON ub.Plexus_User_No  = cust.Assigned_To2

  LEFT JOIN bottles AS bt
    ON bt.Part_Key = pol.Part_Key
  LEFT JOIN labels AS lb
    ON lb.Part_Key = pol.Part_Key
  LEFT JOIN part_attributes_pivoted AS pap
    ON pap.Part_Key = lb.label_part_key

  WHERE UPPER(LTRIM(RTRIM(rs.Release_Status))) = 'LABEL DESIGN'
    AND UPPER(LTRIM(RTRIM(ps.PO_Status))) = 'PENDING FULFILLMENT'
    AND CAST(po.PO_Date AS date) >= DATEADD(day, -14, CAST(GETDATE() AS date))
    AND CAST(po.PO_Date AS date) >= '2026-10-18'   -- carried over from the BigQuery view (go-live floor)
),

ranked AS (
  SELECT
    r.*,
    MIN(r.due_date_resolved) OVER (PARTITION BY r.po_line_key) AS due_date,
    COUNT(*) OVER (PARTITION BY r.po_line_key)                 AS release_count,
    ROW_NUMBER() OVER (PARTITION BY r.po_line_key
                       ORDER BY r.due_date_resolved ASC, r._tiebreak_release_key) AS rn,
    -- 1 when the note starts with a reason digit 1-6 (not a decimal such as 1.5)
    CASE WHEN r._note IS NOT NULL
          AND LEFT(r._note, 1) LIKE '[1-6]'
          AND ( LEN(r._note) = 1
             OR SUBSTRING(r._note, 2, 1) LIKE '[^0-9.,]'
             OR (SUBSTRING(r._note, 2, 1) LIKE '[.,]'
                 AND (LEN(r._note) = 2 OR SUBSTRING(r._note, 3, 1) LIKE '[^0-9]')) )
         THEN 1 ELSE 0 END AS is_coded,
    -- position of the first character after the digit that is not whitespace, '-', ':' or '.'
    PATINDEX('%[^ ' + CHAR(9) + CHAR(10) + CHAR(13) + ':.-]%', SUBSTRING(r._note, 2, 8000)) AS memo_start
  FROM release_lines AS r
)

SELECT
  k.order_number,
  k.customer_po,
  k.customer_name,
  k.customer_part_no,
  k.line_status,
  k.priority,
  k.due_date,
  k.order_date,
  k.job_note,
  k.sales_rep_inside,
  k.customer_account_rep,
  k.am,
  k.bdm,
  k.customer_email,
  k.customer_phone,
  k.customer_part_description,
  k.order_status,
  k.po_key,
  k.po_line_key,
  k.part_key,
  k.part_no,
  k.part_revision,
  k.part_name,
  NULLIF(CONCAT_WS(' | ',
    CASE WHEN k.part_no IS NULL THEN NULL
         ELSE k.part_no + CASE WHEN NULLIF(LTRIM(RTRIM(k.part_revision)), '') IS NULL
                               THEN '' ELSE ' ' + LTRIM(RTRIM(k.part_revision)) END END,
    NULLIF(LTRIM(RTRIM(k.part_name)), '')), '')                              AS line_description,
  k.bottle_part_no,
  k.bottle_name,
  k.label_part_key,
  k.label_part_no,
  k.label_part_name,
  -- whole-word match, padded so the ends count as boundaries
  CASE
    WHEN ' ' + UPPER(k.bottle_name) + ' ' LIKE '%[^A-Z0-9_]HDPE[^A-Z0-9_]%'  THEN 'HDPE'
    WHEN ' ' + UPPER(k.bottle_name) + ' ' LIKE '%[^A-Z0-9_]PET[^A-Z0-9_]%'   THEN 'PET'
    WHEN ' ' + UPPER(k.bottle_name) + ' ' LIKE '%[^A-Z0-9_]GLASS[^A-Z0-9_]%' THEN 'Glass'
  END                                                                        AS bottle_material,
  k.part_label_size,
  k.part_size,
  k.part_allergen,
  k.part_hazardous,
  k.part_certifications,
  k.part_printing_material,
  k.part_bottle_material,
  k.part_california_pdp,
  k.part_prop_65_requirement,
  k.part_trademark,
  k.part_material_classification,
  k.release_count,

  CASE WHEN k.is_coded = 1 THEN CAST(LEFT(k._note, 1) AS int) END            AS reason_code,
  CASE WHEN k.is_coded = 1
       THEN CASE LEFT(k._note, 1)
              WHEN '1' THEN 'Customer Initiated: Label Edit'
              WHEN '2' THEN 'Customer initiated: Label review'
              WHEN '3' THEN 'New label design (Vox design)'
              WHEN '4' THEN 'New label review (Customer design)'
              WHEN '5' THEN 'Vox Initiated: Label Edit/Review'
              WHEN '6' THEN '3D Rendering'
            END END                                                          AS reason_code_label,
  CASE WHEN k.is_coded = 1
       THEN NULLIF(CASE WHEN k.memo_start = 0 THEN ''
                        ELSE SUBSTRING(SUBSTRING(k._note, 2, 8000), k.memo_start, 8000) END, '')
       ELSE k._note END                                                      AS memo,

  CASE WHEN k.part_key IS NULL THEN NULL ELSE
    'https://vox.on.plex.com'
    + '/Engineering/Part/ViewForm?__sk=5&__sak=2&FromPartMenu=True&PartKey=' + CAST(k.part_key AS varchar(20))
    + '&PartNo=' + REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
        ISNULL(k.part_no, ''), '%', '%25'), ' ', '%20'), '&', '%26'), '#', '%23'),
        '+', '%2B'), '?', '%3F'), '/', '%2F'), '=', '%3D')
    + '&Revision=' + REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
        ISNULL(k.part_revision, ''), '%', '%25'), ' ', '%20'), '&', '%26'), '#', '%23'),
        '+', '%2B'), '?', '%3F'), '/', '%2F'), '=', '%3D')
  END                                                                        AS part_url,
  CASE WHEN k.po_key IS NULL THEN NULL ELSE
    'https://vox.on.plex.com'
    + '/SalesAndCRM/SalesOrders/PoFormView?OriginLocation=SalesOrders&POKey=' + CAST(k.po_key AS varchar(20))
  END                                                                        AS customer_po_url,
  CASE WHEN k.po_key IS NULL THEN NULL ELSE
    'https://vox.on.plex.com'
    + '/SalesAndCRM/OrderEntry/ViewOrderForm?POKey=' + CAST(k.po_key AS varchar(20))
  END                                                                        AS sales_order_url,

  CAST(k.order_number AS varchar(50)) + '|L' + CAST(k.po_line_key AS varchar(20)) AS dedupe_key

FROM ranked AS k
WHERE k.rn = 1
ORDER BY k.order_date DESC, k.order_number, k.customer_part_no;
