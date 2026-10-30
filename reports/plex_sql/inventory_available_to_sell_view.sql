-- inventory_available_to_sell_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/inventory_available_to_sell_view.sql
-- confidence: medium
-- plex_views: Sales_v_Release, Sales_v_PO_Line, Sales_v_PO, Sales_v_PO_Status, Part_v_Flat_BOM, Part_v_BOM, Part_v_Container, Part_v_Part, Part_v_Part_Product_Type
-- notes: 2026-10-30: component demand NETTED level by level (docs/BOM_DEMAND_NETTING.md): recursive CTE for low-level codes, seven unrolled stages, CROSS APPLY (VALUES) for the BigQuery UNNEST; the flat explosion stays as gross_component_demand_qty. The recursive CTE and CROSS APPLY are unverified in Plex SQL Developer (if it rejects recursion, compute llc from Part_v_Flat_BOM: MAX(BOM_Level) per Component_Part_Key). 2026-10-28: component demand on stocked keys only, wrapper-key stock converted into the stocked key's availability. Upstream part_on_hand_inventory_report inlined as CTE; STRING_AGG(DISTINCT) rewritten via a DISTINCT subquery; Container.Active = 1 assumes a bit column (unverified in Plex).
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- Per part: on hand vs open order demand vs BOM component demand, netted level by level
-- (a parent passes down only what its own stock does not cover; gross kept separately).
-- Demand = unshipped release qty on orders whose status counts in MRP; Hold = held orders.
-- On hand = active containers with status OK / HOLD / INSPECTION REQUIRED / HOLD FOR DESIGN ORDER.
WITH
wrap AS (
  -- wrapper keys: one BOM line to the stocked key of the same Part_No; Quantity converts units
  SELECT b.Part_Key AS wrapper_key, b.Component_Part_Key AS root_key, MAX(b.Quantity) AS factor
  FROM Part_v_BOM AS b
  JOIN Part_v_Part AS pw ON pw.Part_Key = b.Part_Key
  JOIN Part_v_Part AS pc ON pc.Part_Key = b.Component_Part_Key
  WHERE pw.Part_No = pc.Part_No
    AND pw.Part_Key <> pc.Part_Key
    AND ISNULL(b.Active, 1) <> 0
    AND b.Quantity > 0
  GROUP BY b.Part_Key, b.Component_Part_Key
),
order_demand AS (
  -- open order demand per part: unshipped release qty on orders counted in MRP
  SELECT
    l.Part_Key AS part_key,
    SUM(CASE WHEN r.Quantity - ISNULL(r.Quantity_Shipped, 0) > 0
             THEN r.Quantity - ISNULL(r.Quantity_Shipped, 0) ELSE 0 END)   AS demand_qty,
    SUM(CASE WHEN ps.Hold = 1 AND r.Quantity - ISNULL(r.Quantity_Shipped, 0) > 0
             THEN r.Quantity - ISNULL(r.Quantity_Shipped, 0) ELSE 0 END)   AS demand_held_qty,
    COUNT(DISTINCT l.PO_Key)                                               AS open_order_count
  FROM Sales_v_Release AS r
  JOIN Sales_v_PO_Line AS l ON r.PO_Line_Key = l.PO_Line_Key
  JOIN Sales_v_PO AS po ON l.PO_Key = po.PO_Key
  JOIN Sales_v_PO_Status AS ps ON po.PO_Status_Key = ps.PO_Status_Key
  WHERE ps.Include_In_MRP = 1
  GROUP BY l.Part_Key
),
component_demand AS (
  -- demand pushed down to BOM components (flat BOM explosion)
  SELECT
    fb.Component_Part_Key                      AS part_key,
    SUM(od.demand_qty * fb.Quantity)           AS demand_qty,
    SUM(od.demand_held_qty * fb.Quantity)      AS demand_held_qty,
    COUNT(DISTINCT fb.Part_Key)                AS parent_part_count
  FROM order_demand AS od
  JOIN Part_v_Flat_BOM AS fb ON fb.Part_Key = od.part_key
  LEFT JOIN wrap AS w ON w.wrapper_key = fb.Component_Part_Key  -- stocked keys only
  WHERE w.wrapper_key IS NULL
  GROUP BY fb.Component_Part_Key
),
container_loc AS (
  SELECT d.part_key, STRING_AGG(d.loc, ', ') WITHIN GROUP (ORDER BY d.loc) AS container_locations
  FROM (
    SELECT DISTINCT c.Part_Key AS part_key, NULLIF(LTRIM(RTRIM(c.Location)), '') AS loc
    FROM Part_v_Container AS c
    WHERE c.Active = 1
      AND UPPER(LTRIM(RTRIM(c.Container_Status))) IN ('OK', 'HOLD', 'INSPECTION REQUIRED', 'HOLD FOR DESIGN ORDER')
      AND NULLIF(LTRIM(RTRIM(c.Location)), '') IS NOT NULL
  ) AS d
  GROUP BY d.part_key
),
on_hand AS (
  -- part_on_hand_inventory_report: active containers in on-hand statuses
  SELECT
    c.Part_Key                  AS part_key,
    p0.Part_No                  AS part_no,
    p0.Revision                 AS revision,
    p0.Name                     AS part_name,
    pt0.Product_Type            AS part_product_type,
    p0.Unit                     AS unit,
    SUM(c.Quantity)             AS on_hand_qty,
    SUM(c.Net_Weight)           AS on_hand_weight,
    COUNT(*)                    AS container_count,
    MAX(cl.container_locations) AS container_locations
  FROM Part_v_Container AS c
  JOIN Part_v_Part AS p0 ON c.Part_Key = p0.Part_Key
  LEFT JOIN Part_v_Part_Product_Type AS pt0 ON p0.Product_Type_Key = pt0.Product_Type_Key
  LEFT JOIN container_loc AS cl ON c.Part_Key = cl.part_key
  WHERE c.Active = 1
    AND UPPER(LTRIM(RTRIM(c.Container_Status))) IN ('OK', 'HOLD', 'INSPECTION REQUIRED', 'HOLD FOR DESIGN ORDER')
  GROUP BY c.Part_Key, p0.Part_No, p0.Revision, p0.Name, pt0.Product_Type, p0.Unit
),
wrapper_stock AS (
  -- stock on wrapper keys, converted into the stocked key's unit
  SELECT w1.root_key AS part_key, SUM(oh2.on_hand_qty * w1.factor) AS on_hand_qty
  FROM on_hand AS oh2
  JOIN wrap AS w1 ON w1.wrapper_key = oh2.part_key
  GROUP BY w1.root_key
),
bom_edge AS (
  -- single-level BOM: quantity of the component per ONE unit of its direct parent
  SELECT b2.Part_Key AS parent_key, b2.Component_Part_Key AS component_key, SUM(b2.Quantity) AS qty
  FROM Part_v_BOM AS b2
  WHERE ISNULL(b2.Active, 1) <> 0
    AND b2.Quantity > 0
  GROUP BY b2.Part_Key, b2.Component_Part_Key
),
bom_walk AS (
  -- every path down the BOM (recursive); stops at depth 20, deepest at Vox is 6
  SELECT be.parent_key AS part_key, 0 AS depth FROM bom_edge AS be
  UNION ALL
  SELECT be2.component_key, bw.depth + 1
  FROM bom_walk AS bw
  JOIN bom_edge AS be2 ON be2.parent_key = bw.part_key
  WHERE bw.depth < 20
),
bom_llc AS (
  -- low-level code: a part's DEEPEST depth, so every parent is netted before it
  SELECT bw2.part_key, MAX(bw2.depth) AS llc FROM bom_walk AS bw2 GROUP BY bw2.part_key
),
bom_node AS (
  -- wrapper keys net nothing: their demand passes to the stocked key x factor
  SELECT
    nk.part_key,
    ISNULL(lc.llc, 0)               AS llc,
    ISNULL(od3.demand_qty, 0)       AS own_demand_qty,
    CASE WHEN wk3.wrapper_key IS NOT NULL THEN 0
         ELSE ISNULL(oh3.on_hand_qty, 0) + ISNULL(ws3.on_hand_qty, 0) END AS netting_stock_qty
  FROM (
    SELECT bl.part_key FROM bom_llc AS bl
    UNION
    SELECT od2.part_key FROM order_demand AS od2
  ) AS nk
  LEFT JOIN bom_llc AS lc        ON lc.part_key = nk.part_key
  LEFT JOIN order_demand AS od3  ON od3.part_key = nk.part_key
  LEFT JOIN on_hand AS oh3       ON oh3.part_key = nk.part_key
  LEFT JOIN wrapper_stock AS ws3 ON ws3.part_key = nk.part_key
  LEFT JOIN (SELECT DISTINCT w3.wrapper_key FROM wrap AS w3) AS wk3 ON wk3.wrapper_key = nk.part_key
),
net_0 AS (
  SELECT bn.part_key, bn.llc, bn.own_demand_qty AS gross_qty,
         CASE WHEN bn.own_demand_qty - bn.netting_stock_qty > 0
              THEN bn.own_demand_qty - bn.netting_stock_qty ELSE 0 END AS shortfall_qty
  FROM bom_node AS bn
  WHERE bn.llc = 0
),
net_1 AS (
  -- parts with llc <= 1; reads net_0 once: each netted row becomes itself plus one
  -- contribution per BOM line, then is grouped by part
  SELECT
    n.part_key,
    n.llc,
    CASE WHEN n.llc < 1 THEN a.self_gross_qty
         ELSE n.own_demand_qty + ISNULL(a.incoming_qty, 0) END AS gross_qty,
    CASE WHEN n.llc < 1 THEN a.self_shortfall_qty
         WHEN n.own_demand_qty + ISNULL(a.incoming_qty, 0) - n.netting_stock_qty > 0
         THEN n.own_demand_qty + ISNULL(a.incoming_qty, 0) - n.netting_stock_qty
         ELSE 0 END AS shortfall_qty
  FROM bom_node AS n
  LEFT JOIN (
    SELECT
      x.part_key,
      MAX(CASE WHEN x.is_self = 1 THEN x.gross_qty END)     AS self_gross_qty,
      MAX(CASE WHEN x.is_self = 1 THEN x.shortfall_qty END) AS self_shortfall_qty,
      SUM(CASE WHEN x.is_self = 1 THEN 0 ELSE x.qty END)    AS incoming_qty
    FROM net_0 AS s
    LEFT JOIN bom_edge AS e ON e.parent_key = s.part_key
    CROSS APPLY (VALUES
      (s.part_key, 1, s.gross_qty, s.shortfall_qty, CAST(0 AS float)),
      (e.component_key, 0, NULL, NULL, s.shortfall_qty * e.qty)
    ) AS x (part_key, is_self, gross_qty, shortfall_qty, qty)
    WHERE x.part_key IS NOT NULL
    GROUP BY x.part_key
  ) AS a ON a.part_key = n.part_key
  WHERE n.llc <= 1
),
net_2 AS (
  -- parts with llc <= 2; reads net_1 once: each netted row becomes itself plus one
  -- contribution per BOM line, then is grouped by part
  SELECT
    n.part_key,
    n.llc,
    CASE WHEN n.llc < 2 THEN a.self_gross_qty
         ELSE n.own_demand_qty + ISNULL(a.incoming_qty, 0) END AS gross_qty,
    CASE WHEN n.llc < 2 THEN a.self_shortfall_qty
         WHEN n.own_demand_qty + ISNULL(a.incoming_qty, 0) - n.netting_stock_qty > 0
         THEN n.own_demand_qty + ISNULL(a.incoming_qty, 0) - n.netting_stock_qty
         ELSE 0 END AS shortfall_qty
  FROM bom_node AS n
  LEFT JOIN (
    SELECT
      x.part_key,
      MAX(CASE WHEN x.is_self = 1 THEN x.gross_qty END)     AS self_gross_qty,
      MAX(CASE WHEN x.is_self = 1 THEN x.shortfall_qty END) AS self_shortfall_qty,
      SUM(CASE WHEN x.is_self = 1 THEN 0 ELSE x.qty END)    AS incoming_qty
    FROM net_1 AS s
    LEFT JOIN bom_edge AS e ON e.parent_key = s.part_key
    CROSS APPLY (VALUES
      (s.part_key, 1, s.gross_qty, s.shortfall_qty, CAST(0 AS float)),
      (e.component_key, 0, NULL, NULL, s.shortfall_qty * e.qty)
    ) AS x (part_key, is_self, gross_qty, shortfall_qty, qty)
    WHERE x.part_key IS NOT NULL
    GROUP BY x.part_key
  ) AS a ON a.part_key = n.part_key
  WHERE n.llc <= 2
),
net_3 AS (
  -- parts with llc <= 3; reads net_2 once: each netted row becomes itself plus one
  -- contribution per BOM line, then is grouped by part
  SELECT
    n.part_key,
    n.llc,
    CASE WHEN n.llc < 3 THEN a.self_gross_qty
         ELSE n.own_demand_qty + ISNULL(a.incoming_qty, 0) END AS gross_qty,
    CASE WHEN n.llc < 3 THEN a.self_shortfall_qty
         WHEN n.own_demand_qty + ISNULL(a.incoming_qty, 0) - n.netting_stock_qty > 0
         THEN n.own_demand_qty + ISNULL(a.incoming_qty, 0) - n.netting_stock_qty
         ELSE 0 END AS shortfall_qty
  FROM bom_node AS n
  LEFT JOIN (
    SELECT
      x.part_key,
      MAX(CASE WHEN x.is_self = 1 THEN x.gross_qty END)     AS self_gross_qty,
      MAX(CASE WHEN x.is_self = 1 THEN x.shortfall_qty END) AS self_shortfall_qty,
      SUM(CASE WHEN x.is_self = 1 THEN 0 ELSE x.qty END)    AS incoming_qty
    FROM net_2 AS s
    LEFT JOIN bom_edge AS e ON e.parent_key = s.part_key
    CROSS APPLY (VALUES
      (s.part_key, 1, s.gross_qty, s.shortfall_qty, CAST(0 AS float)),
      (e.component_key, 0, NULL, NULL, s.shortfall_qty * e.qty)
    ) AS x (part_key, is_self, gross_qty, shortfall_qty, qty)
    WHERE x.part_key IS NOT NULL
    GROUP BY x.part_key
  ) AS a ON a.part_key = n.part_key
  WHERE n.llc <= 3
),
net_4 AS (
  -- parts with llc <= 4; reads net_3 once: each netted row becomes itself plus one
  -- contribution per BOM line, then is grouped by part
  SELECT
    n.part_key,
    n.llc,
    CASE WHEN n.llc < 4 THEN a.self_gross_qty
         ELSE n.own_demand_qty + ISNULL(a.incoming_qty, 0) END AS gross_qty,
    CASE WHEN n.llc < 4 THEN a.self_shortfall_qty
         WHEN n.own_demand_qty + ISNULL(a.incoming_qty, 0) - n.netting_stock_qty > 0
         THEN n.own_demand_qty + ISNULL(a.incoming_qty, 0) - n.netting_stock_qty
         ELSE 0 END AS shortfall_qty
  FROM bom_node AS n
  LEFT JOIN (
    SELECT
      x.part_key,
      MAX(CASE WHEN x.is_self = 1 THEN x.gross_qty END)     AS self_gross_qty,
      MAX(CASE WHEN x.is_self = 1 THEN x.shortfall_qty END) AS self_shortfall_qty,
      SUM(CASE WHEN x.is_self = 1 THEN 0 ELSE x.qty END)    AS incoming_qty
    FROM net_3 AS s
    LEFT JOIN bom_edge AS e ON e.parent_key = s.part_key
    CROSS APPLY (VALUES
      (s.part_key, 1, s.gross_qty, s.shortfall_qty, CAST(0 AS float)),
      (e.component_key, 0, NULL, NULL, s.shortfall_qty * e.qty)
    ) AS x (part_key, is_self, gross_qty, shortfall_qty, qty)
    WHERE x.part_key IS NOT NULL
    GROUP BY x.part_key
  ) AS a ON a.part_key = n.part_key
  WHERE n.llc <= 4
),
net_5 AS (
  -- parts with llc <= 5; reads net_4 once: each netted row becomes itself plus one
  -- contribution per BOM line, then is grouped by part
  SELECT
    n.part_key,
    n.llc,
    CASE WHEN n.llc < 5 THEN a.self_gross_qty
         ELSE n.own_demand_qty + ISNULL(a.incoming_qty, 0) END AS gross_qty,
    CASE WHEN n.llc < 5 THEN a.self_shortfall_qty
         WHEN n.own_demand_qty + ISNULL(a.incoming_qty, 0) - n.netting_stock_qty > 0
         THEN n.own_demand_qty + ISNULL(a.incoming_qty, 0) - n.netting_stock_qty
         ELSE 0 END AS shortfall_qty
  FROM bom_node AS n
  LEFT JOIN (
    SELECT
      x.part_key,
      MAX(CASE WHEN x.is_self = 1 THEN x.gross_qty END)     AS self_gross_qty,
      MAX(CASE WHEN x.is_self = 1 THEN x.shortfall_qty END) AS self_shortfall_qty,
      SUM(CASE WHEN x.is_self = 1 THEN 0 ELSE x.qty END)    AS incoming_qty
    FROM net_4 AS s
    LEFT JOIN bom_edge AS e ON e.parent_key = s.part_key
    CROSS APPLY (VALUES
      (s.part_key, 1, s.gross_qty, s.shortfall_qty, CAST(0 AS float)),
      (e.component_key, 0, NULL, NULL, s.shortfall_qty * e.qty)
    ) AS x (part_key, is_self, gross_qty, shortfall_qty, qty)
    WHERE x.part_key IS NOT NULL
    GROUP BY x.part_key
  ) AS a ON a.part_key = n.part_key
  WHERE n.llc <= 5
),
net_6 AS (
  -- parts with llc <= 6; reads net_5 once: each netted row becomes itself plus one
  -- contribution per BOM line, then is grouped by part
  SELECT
    n.part_key,
    n.llc,
    CASE WHEN n.llc < 6 THEN a.self_gross_qty
         ELSE n.own_demand_qty + ISNULL(a.incoming_qty, 0) END AS gross_qty,
    CASE WHEN n.llc < 6 THEN a.self_shortfall_qty
         WHEN n.own_demand_qty + ISNULL(a.incoming_qty, 0) - n.netting_stock_qty > 0
         THEN n.own_demand_qty + ISNULL(a.incoming_qty, 0) - n.netting_stock_qty
         ELSE 0 END AS shortfall_qty
  FROM bom_node AS n
  LEFT JOIN (
    SELECT
      x.part_key,
      MAX(CASE WHEN x.is_self = 1 THEN x.gross_qty END)     AS self_gross_qty,
      MAX(CASE WHEN x.is_self = 1 THEN x.shortfall_qty END) AS self_shortfall_qty,
      SUM(CASE WHEN x.is_self = 1 THEN 0 ELSE x.qty END)    AS incoming_qty
    FROM net_5 AS s
    LEFT JOIN bom_edge AS e ON e.parent_key = s.part_key
    CROSS APPLY (VALUES
      (s.part_key, 1, s.gross_qty, s.shortfall_qty, CAST(0 AS float)),
      (e.component_key, 0, NULL, NULL, s.shortfall_qty * e.qty)
    ) AS x (part_key, is_self, gross_qty, shortfall_qty, qty)
    WHERE x.part_key IS NOT NULL
    GROUP BY x.part_key
  ) AS a ON a.part_key = n.part_key
  WHERE n.llc <= 6
),
netted_demand AS (
  -- what reached the part from its parents; 0 on wrapper keys (the stocked key carries it)
  SELECT
    n6.part_key,
    CASE WHEN wk4.wrapper_key IS NOT NULL THEN 0 ELSE n6.gross_qty - bn6.own_demand_qty END AS demand_qty
  FROM net_6 AS n6
  JOIN bom_node AS bn6 ON bn6.part_key = n6.part_key
  LEFT JOIN (SELECT DISTINCT w4.wrapper_key FROM wrap AS w4) AS wk4 ON wk4.wrapper_key = n6.part_key
),
part_keys AS (
  SELECT oh1.part_key FROM on_hand AS oh1
  UNION
  SELECT od1.part_key FROM order_demand AS od1
  UNION
  SELECT cd1.part_key FROM component_demand AS cd1
  UNION
  SELECT ws1.part_key FROM wrapper_stock AS ws1
)
SELECT
  k.part_key                                              AS part_key,
  p.Part_No                                               AS part_no,
  p.Revision                                              AS revision,
  p.Name                                                  AS part_name,
  pt.Product_Type                                         AS part_product_type,
  p.Unit                                                  AS unit,
  p.Minimum_Inventory_Quantity                            AS minimum_inventory_quantity,
  ISNULL(oh.on_hand_qty, 0)                               AS on_hand_qty,
  oh.on_hand_weight                                       AS on_hand_weight,
  ISNULL(oh.container_count, 0)                           AS container_count,
  oh.container_locations                                  AS container_locations,
  ISNULL(od.demand_qty, 0)                                AS order_demand_qty,
  ISNULL(od.demand_held_qty, 0)                           AS order_demand_from_held_orders_qty,
  ISNULL(od.open_order_count, 0)                          AS open_order_count,
  ISNULL(nd.demand_qty, ISNULL(cd.demand_qty, 0))         AS component_demand_qty,
  ISNULL(cd.demand_held_qty, 0)                           AS component_demand_from_held_orders_qty,
  ISNULL(cd.parent_part_count, 0)                         AS bom_parent_part_count,
  ISNULL(od.demand_qty, 0) + ISNULL(nd.demand_qty, ISNULL(cd.demand_qty, 0)) AS total_demand_qty,
  ISNULL(oh.on_hand_qty, 0) + ISNULL(ws.on_hand_qty, 0)
    - ISNULL(od.demand_qty, 0)                            AS available_vs_orders,
  ISNULL(oh.on_hand_qty, 0) + ISNULL(ws.on_hand_qty, 0)
    - (ISNULL(od.demand_qty, 0) + ISNULL(nd.demand_qty, ISNULL(cd.demand_qty, 0))) AS available_vs_total_demand,
  CASE WHEN oh.part_key IS NULL THEN 1 ELSE 0 END         AS no_inventory_on_hand,
  CASE WHEN od.part_key IS NULL AND cd.part_key IS NULL THEN 1 ELSE 0 END AS no_open_demand,
  CASE WHEN cd.part_key IS NOT NULL THEN 1 ELSE 0 END     AS demand_includes_bom_explosion,
  ISNULL(ws.on_hand_qty, 0)                               AS wrapper_on_hand_qty,
  CASE WHEN wk.wrapper_key IS NOT NULL THEN 1 ELSE 0 END  AS is_unit_wrapper,
  ISNULL(cd.demand_qty, 0)                                AS gross_component_demand_qty,
  lc2.llc                                                 AS bom_low_level_code,
  CASE WHEN lc2.llc > 6 THEN 1 ELSE 0 END                 AS bom_depth_beyond_netting
FROM part_keys AS k
LEFT JOIN on_hand AS oh          ON k.part_key = oh.part_key
LEFT JOIN order_demand AS od     ON k.part_key = od.part_key
LEFT JOIN component_demand AS cd ON k.part_key = cd.part_key
LEFT JOIN netted_demand AS nd    ON k.part_key = nd.part_key
LEFT JOIN bom_llc AS lc2         ON k.part_key = lc2.part_key
LEFT JOIN wrapper_stock AS ws    ON k.part_key = ws.part_key
LEFT JOIN (SELECT DISTINCT w2.wrapper_key FROM wrap AS w2) AS wk ON k.part_key = wk.wrapper_key
JOIN Part_v_Part AS p ON k.part_key = p.Part_Key
LEFT JOIN Part_v_Part_Product_Type AS pt ON p.Product_Type_Key = pt.Product_Type_Key
