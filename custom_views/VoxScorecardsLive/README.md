# VoxScorecardsLive

Backed up by `scripts/backup_custom_views.py VoxScorecardsLive`: 60 views and 25 tables.
These are built by hand in the BigQuery console (mostly by Jennilyn), not by the ETL, so the ETL never
recreates or reverts them. A view's `.sql` is exactly what BigQuery stores. A table's `.sql` is the
statement that last built it (its rows are a snapshot from then); `.schema.json` means no statement
was found in 180 days of job history, so only the columns are kept.

| Object | Type | Rows | Last changed | Last built by | SQL | Reads |
| --- | --- | --- | --- | --- | --- | --- |
| `DN_15_MO_Expiring` | table | 2188 | 2026-11-01 |  | schema only |  |
| `Overstock_NS` | table | 1305 | 2026-11-08 |  | schema only |  |
| `Product_Cost` | table | 199 | 2026-05-28 |  | schema only |  |
| `SalesDB_YTD` | table | 7463 | 2026-11-11 |  | schema only |  |
| `SalesQuotesLanding` | table | 4789 | 2026-11-02 |  | schema only |  |
| `daily_sales_activity` | table | 772 | 2026-11-11 | jennilyn.tockstein | yes |  |
| `high_risk_snapshots` | table | 785 | 2026-11-08 | jennilyn.tockstein | yes |  |
| `new_activities_18405028203` | table | 520 | 2026-11-11 |  | schema only |  |
| `new_forecast_18415088271` | table | 187 | 2026-11-11 |  | schema only |  |
| `new_opportunities_18405027980` | table | 223 | 2026-11-11 |  | schema only |  |
| `pipeline_snapshot` | table | 27 | 2026-11-08 | jennilyn.tockstein | yes |  |
| `sales_goals` | table | 56 | 2026-10-12 |  | schema only |  |
| `sales_history_static` | table | 6864 | 2026-11-09 | jennilyn.tockstein | yes | `VoxScorecardsLive.vw_sales_legacy_sheet` |
| `sales_rep_roster` | table | 7 | 2026-11-04 | jennilyn.tockstein | yes |  |
| `scorecard_monthly_history` | table | 110 | 2026-11-09 | jennilyn.tockstein | yes |  |
| `shipping_daily_ops` | table | 105 | 2026-11-11 | jennilyn.tockstein | yes |  |
| `shipping_revenue_blanket_daily` | table | 100 | 2026-11-02 | jennilyn.tockstein | yes |  |
| `shipping_revenue_daily` | table | 102 | 2026-11-02 | jennilyn.tockstein | yes |  |
| `shipping_revenue_shipped_daily` | table | 90 | 2026-10-16 | jennilyn.tockstein | yes |  |
| `stalled_win_lost_18409621334` | table | 120 | 2026-06-05 |  | schema only |  |
| `stalled_won_lost_18409621334` | table | 638 | 2026-11-11 |  | schema only |  |
| `tmp_container_20261102` | table | 79909 | 2026-11-09 | jennilyn.tockstein | yes | `PlexProd.raw_Part_v_Container` |
| `usage_update_20261105` | table | 790 | 2026-11-05 | jennilyn.tockstein | yes |  |
| `vw_approaching_msl_with_held` | table | 1672 | 2026-11-11 | jennilyn.tockstein | yes | `VoxScorecardsLive.vw_approaching_msl_with_held_live` |
| `vw_approaching_msl_with_held_live` | view |  | 2026-11-11 | jennilyn.tockstein | yes | `PlexProd.approaching_msl_report`, `PlexProd.inventory_lot_detail_report`, `PlexProd.raw_Part_v_BOM`, `PlexProd.raw_Part_v_Lot_Shelf_Life`, `PlexProd.raw_Part_v_Part`, `PlexProd.raw_Part_v_Shelf_Life_Type` |
| `vw_avg_days_to_close` | view |  | 2026-06-10 | jennilyn.tockstein | yes | `VoxScorecardsLive.stalled_won_lost_18409621334` |
| `vw_cost_lookup` | view |  | 2026-05-28 | jennilyn.tockstein | yes | `VoxScorecardsLive.Overstock_NS`, `VoxScorecardsLive.Product_Cost` |
| `vw_expiring_lots` | view |  | 2026-06-01 | jennilyn.tockstein | yes | `VoxScorecardsLive.DN_15_MO_Expiring`, `VoxScorecardsLive.vw_cost_lookup` |
| `vw_forecast_by_rep_month` | view |  | 2026-07-17 | jennilyn.tockstein | yes | `VoxScorecardsLive.SalesDB_YTD`, `VoxScorecardsLive.new_forecast_18415088271` |
| `vw_forecast_decrementing` | view |  | 2026-07-17 | jennilyn.tockstein | yes | `VoxScorecardsLive.SalesDB_YTD`, `VoxScorecardsLive.new_forecast_18415088271` |
| `vw_high_risk` | view |  | 2026-05-28 | jennilyn.tockstein | yes | `VoxScorecardsLive.vw_expiring_lots`, `VoxScorecardsLive.vw_inventory_base` |
| `vw_high_risk_weekly_changes` | view |  | 2026-06-22 | jennilyn.tockstein | yes | `VoxScorecardsLive.high_risk_snapshots` |
| `vw_inventory_base` | view |  | 2026-05-28 | jennilyn.tockstein | yes | `VoxScorecardsLive.Overstock_NS`, `VoxScorecardsLive.vw_cost_lookup` |
| `vw_opportunities_clean` | view |  | 2026-06-09 | jennilyn.tockstein | yes | `VoxScorecardsLive.new_opportunities_18405027980` |
| `vw_overstock_by_bucket` | view |  | 2026-05-28 | jennilyn.tockstein | yes | `VoxScorecardsLive.vw_expiring_lots`, `VoxScorecardsLive.vw_inventory_base` |
| `vw_overstock_with_expiry` | view |  | 2026-05-28 | jennilyn.tockstein | yes | `VoxScorecardsLive.vw_expiring_lots`, `VoxScorecardsLive.vw_inventory_base` |
| `vw_pipeline` | view |  | 2026-10-30 | jennilyn.tockstein | yes | `PlexProd.pipeline_plex_value_report`, `VoxScorecardsLive.new_opportunities_18405027980`, `VoxScorecardsLive.vw_forecast_decrementing` |
| `vw_plex_expiring_inventory` | table | 745 | 2026-11-11 | jennilyn.tockstein | yes | `VoxScorecardsLive.vw_plex_expiring_inventory_live` |
| `vw_plex_expiring_inventory_live` | view |  | 2026-11-11 | jennilyn.tockstein | yes | `PlexProd.inventory_lot_detail_report`, `PlexProd.inventory_net_demand_report`, `PlexProd.raw_Part_v_Lot_Shelf_Life`, `PlexProd.raw_Part_v_Shelf_Life_Type` |
| `vw_plex_order_header` | view |  | 2026-11-11 | jennilyn.tockstein | yes | `PlexProd.raw_Common_v_Customer`, `PlexProd.raw_Plexus_Control_v_Plexus_User`, `PlexProd.raw_Sales_v_Order_Salesperson`, `PlexProd.raw_Sales_v_PO`, `PlexProd.raw_Sales_v_PO_Line`, `PlexProd.raw_Sales_v_PO_Status` ... |
| `vw_raw_materials_expiring_90` | view |  | 2026-06-18 | jennilyn.tockstein | yes | `VoxScorecardsLive.DN_15_MO_Expiring`, `VoxScorecardsLive.vw_cost_lookup` |
| `vw_rep_pipeline_performance` | view |  | 2026-06-10 | jennilyn.tockstein | yes | `VoxScorecardsLive.new_opportunities_18405027980`, `VoxScorecardsLive.stalled_won_lost_18409621334` |
| `vw_rep_snapshot` | view |  | 2026-11-04 | jennilyn.tockstein | yes | `PlexProd.pipeline_plex_value_report`, `VoxScorecardsLive.new_opportunities_18405027980`, `VoxScorecardsLive.vw_forecast_decrementing`, `VoxScorecardsLive.vw_sales` |
| `vw_rep_top_customers` | view |  | 2026-11-04 | jennilyn.tockstein | yes | `VoxScorecardsLive.new_opportunities_18405027980`, `VoxScorecardsLive.vw_sales` |
| `vw_sales` | view |  | 2026-11-04 | jennilyn.tockstein | yes | `PlexProd.sales_mtd_by_status_change_report`, `VoxScorecardsLive.sales_history_static` |
| `vw_sales_activity_base` | view |  | 2026-06-22 | jennilyn.tockstein | yes | `VoxScorecardsLive.daily_sales_activity` |
| `vw_sales_activity_summary` | view |  | 2026-06-22 | jennilyn.tockstein | yes | `VoxScorecardsLive.vw_sales_activity_base` |
| `vw_sales_by_rep_month` | view |  | 2026-11-04 | jennilyn.tockstein | yes | `PlexProd.v2_scorecard_goals_resolved`, `VoxScorecardsLive.sales_rep_roster`, `VoxScorecardsLive.vw_sales` |
| `vw_sales_daily_detail` | view |  | 2026-06-22 | jennilyn.tockstein | yes | `VoxScorecardsLive.daily_sales_activity`, `VoxScorecardsLive.vw_sales_activity_base` |
| `vw_sales_daily_pace` | view |  | 2026-11-04 | jennilyn.tockstein | yes | `PlexProd.v2_scorecard_goals_resolved`, `VoxScorecardsLive.vw_sales` |
| `vw_sales_legacy_sheet` | view |  | 2026-11-04 | jennilyn.tockstein | yes | `VoxScorecardsLive.SalesDB_YTD` |
| `vw_sales_line_status` | view |  | 2026-11-11 | jennilyn.tockstein | yes | `PlexProd.raw_Part_v_Part`, `PlexProd.raw_Sales_v_PO`, `PlexProd.raw_Sales_v_PO_Line`, `PlexProd.raw_Sales_v_Price`, `PlexProd.raw_Sales_v_Release`, `PlexProd.raw_Sales_v_Release_Status` |
| `vw_sales_mtd_vs_goal` | view |  | 2026-11-04 | jennilyn.tockstein | yes | `PlexProd.v2_scorecard_goals_resolved`, `VoxScorecardsLive.vw_sales` |
| `vw_sales_open_order_aging` | view |  | 2026-11-11 | jennilyn.tockstein | yes | `PlexProd.sales_orders_aging_report`, `VoxScorecardsLive.vw_plex_order_header`, `VoxScorecardsLive.vw_sales_line_status` |
| `vw_sales_orders_over_10k` | view |  | 2026-11-11 | jennilyn.tockstein | yes | `PlexProd.sales_orders_over_10k_report`, `VoxScorecardsLive.vw_plex_order_header`, `VoxScorecardsLive.vw_sales_line_status` |
| `vw_sales_rep_yesterday_wtd` | view |  | 2026-11-04 | jennilyn.tockstein | yes | `VoxScorecardsLive.sales_rep_roster`, `VoxScorecardsLive.vw_sales`, `a.top_yday.amount`, `a.top_yday.customer` |
| `vw_sales_rush_orders` | view |  | 2026-11-11 | jennilyn.tockstein | yes | `PlexProd.sales_orders_rush_open_report`, `VoxScorecardsLive.vw_plex_order_header`, `VoxScorecardsLive.vw_sales_line_status` |
| `vw_sales_top_wip_orders` | view |  | 2026-11-11 | jennilyn.tockstein | yes | `VoxScorecardsLive.vw_sc_wip_status_lines` |
| `vw_sales_wip_by_rep` | view |  | 2026-11-04 | jennilyn.tockstein | yes | `VoxScorecardsLive.sales_rep_roster`, `VoxScorecardsLive.vw_sales_top_wip_orders` |
| `vw_sales_yesterday_detail` | view |  | 2026-06-22 | jennilyn.tockstein | yes | `VoxScorecardsLive.vw_sales_activity_base` |
| `vw_sales_ytd_vs_goal` | view |  | 2026-11-04 | jennilyn.tockstein | yes | `PlexProd.v2_scorecard_goals_resolved`, `VoxScorecardsLive.vw_sales` |
| `vw_sc_base` | view |  | 2026-10-30 | jennilyn.tockstein | yes | `VoxScorecardsLive.scorecard_monthly_history` |
| `vw_sc_inventory_at_risk` | view |  | 2026-11-11 | jennilyn.tockstein | yes | `PlexProd.inventory_lot_detail_report`, `PlexProd.raw_Part_v_Lot_Shelf_Life`, `PlexProd.raw_Part_v_Shelf_Life_Type` |
| `vw_sc_inventory_split` | view |  | 2026-11-10 | jennilyn.tockstein | yes | `PlexProd.inventory_valuation_summary_report`, `PlexProd.raw_Part_v_Approved_Supplier` |
| `vw_sc_inventory_split_by_partno` | view |  | 2026-11-10 | jennilyn.tockstein | yes | `PlexProd.inventory_valuation_summary_report` |
| `vw_sc_last_month` | view |  | 2026-11-01 | jennilyn.tockstein | yes | `PlexProd.v2_scorecard_goals_resolved`, `VoxScorecardsLive.vw_sc_monthly_wide` |
| `vw_sc_monthly_wide` | view |  | 2026-10-30 | jennilyn.tockstein | yes | `VoxScorecardsLive.vw_sc_base` |
| `vw_sc_production_daily_mtd` | view |  | 2026-10-30 | jennilyn.tockstein | yes | `PlexProd.production_area_summary_report`, `PlexProd.v2_production_vs_goal_report` |
| `vw_sc_production_indexed` | view |  | 2026-10-30 | jennilyn.tockstein | yes | `VoxScorecardsLive.vw_sc_monthly_wide` |
| `vw_sc_rev_ready_to_ship` | view |  | 2026-10-30 | jennilyn.tockstein | yes | `PlexProd.part_on_hand_inventory_report`, `PlexProd.raw_Sales_v_PO`, `PlexProd.raw_Sales_v_PO_Line`, `PlexProd.raw_Sales_v_PO_Status`, `PlexProd.raw_Sales_v_Price`, `PlexProd.raw_Sales_v_Release` ... |
| `vw_sc_revenue_adjustments` | view |  | 2026-11-09 | jennilyn.tockstein | yes | `PlexProd.raw_Accounting_v_AR_Invoice`, `PlexProd.raw_Accounting_v_AR_Invoice_Dist`, `PlexProd.raw_Sales_v_Shipper`, `PlexProd.raw_Sales_v_Shipper_Line` |
| `vw_sc_revenue_mtd_tile` | view |  | 2026-11-09 | jennilyn.tockstein | yes | `PlexProd.sales_revenue_summary_report`, `PlexProd.v2_scorecard_goals_resolved`, `VoxScorecardsLive.scorecard_monthly_history`, `VoxScorecardsLive.vw_sc_revenue_adjustments` |
| `vw_sc_safe_days` | view |  | 2026-11-05 | jennilyn.tockstein | yes | `PlexProd.safety_incidents` |
| `vw_sc_sales_mtd_tile` | view |  | 2026-11-01 | jennilyn.tockstein | yes | `PlexProd.sales_mtd_by_status_change_report`, `PlexProd.v2_scorecard_goals_resolved`, `VoxScorecardsLive.scorecard_monthly_history` |
| `vw_sc_scrap_mtd` | view |  | 2026-11-11 | jennilyn.tockstein | yes | `PlexProd.production_monthly_by_workcenter_group_report`, `PlexProd.raw_Part_v_Container`, `PlexProd.raw_Part_v_Production`, `PlexProd.raw_Part_v_Workcenter` |
| `vw_sc_wip_status_lines` | view |  | 2026-11-11 | jennilyn.tockstein | yes | `PlexProd.part_on_hand_inventory_report`, `PlexProd.raw_Part_v_Job`, `PlexProd.raw_Part_v_Job_Status`, `PlexProd.raw_Sales_v_PO_Line`, `PlexProd.raw_Sales_v_Release`, `PlexProd.raw_Sales_v_Release_Job` ... |
| `vw_sc_wip_status_summary` | view |  | 2026-11-11 | jennilyn.tockstein | yes | `VoxScorecardsLive.vw_sc_wip_status_lines` |
| `vw_sc_wip_where_is_it` | view |  | 2026-11-11 | jennilyn.tockstein | yes | `PlexProd.part_on_hand_inventory_report`, `PlexProd.raw_Part_v_BOM`, `PlexProd.raw_Part_v_Job`, `PlexProd.raw_Part_v_Job_Status`, `PlexProd.raw_Part_v_Part`, `VoxScorecardsLive.vw_sc_wip_status_lines` |
| `vw_sc_ytd_cards` | view |  | 2026-10-30 | jennilyn.tockstein | yes | `VoxScorecardsLive.vw_sc_monthly_wide` |
| `vw_shipping_daily_snapshot` | view |  | 2026-11-09 | jennilyn.tockstein | yes | `PlexProd.shipping_revenue_report`, `VoxScorecardsLive.shipping_daily_ops`, `VoxScorecardsLive.shipping_revenue_blanket_daily`, `VoxScorecardsLive.shipping_revenue_daily`, `VoxScorecardsLive.vw_sc_revenue_adjustments` |
| `vw_shipping_daily_snapshot_old` | view |  | 2026-11-06 | jennilyn.tockstein | yes | `VoxScorecardsLive.shipping_daily_ops`, `VoxScorecardsLive.shipping_revenue_blanket_daily`, `VoxScorecardsLive.shipping_revenue_daily`, `VoxScorecardsLive.shipping_revenue_shipped_daily` |
| `vw_shoutouts` | view |  | 2026-06-10 | jennilyn.tockstein | yes | `VoxScorecardsLive.new_opportunities_18405027980`, `VoxScorecardsLive.stalled_won_lost_18409621334` |
| `vw_top_opp_by_rep` | view |  | 2026-06-09 | jennilyn.tockstein | yes | `VoxScorecardsLive.new_opportunities_18405027980` |
| `vw_top_overstock` | view |  | 2026-07-17 | jennilyn.tockstein | yes | `VoxScorecardsLive.Overstock_NS` |
| `vw_win_loss_rates` | view |  | 2026-06-10 | jennilyn.tockstein | yes | `VoxScorecardsLive.new_opportunities_18405027980`, `VoxScorecardsLive.stalled_won_lost_18409621334` |

## Columns

- **`DN_15_MO_Expiring`**: `inventory`, `reorderpoint`, `stocking_unit`, `part_number`, `name`, `part_class`, `purchasing_class`, `sales_class`, `part_type`, `shelf_life_remaining`, `percent_expired`, `created_date`, `date_of_expiration`, `location`, `warehouse`, `create_type`, `lpn`, `display_identifier`, `barcode`, `vendor_lot_number`, `assigned_to`, `mfg_note`, `bom_name_version`
- **`Overstock_NS`**: `name`, `display_name`, `on_hand`, `average_monthly_usage`, `average_daily_usage`, `average_cost`, `item_stock_type`
- **`Product_Cost`**: `part`, `cost_ea`
- **`SalesDB_YTD`**: `date`, `date_approved`, `type`, `document_number`, `status`, `name`, `sales_rep`, `sales_rep_2`, `amount`, `source`, `po`
- **`SalesQuotesLanding`**: `date`, `type`, `document_number`, `status`, `sales_rep`, `amount`, `name`, `po`
- **`daily_sales_activity`**: `rep_name`, `activity_date`, `submitted_at`, `is_pto`, `emails_sent`, `calls_made`, `meetings`, `visits_to_vox`, `social_dms`, `other`, `total_activities`, `leads_assigned`, `leads_contacted`, `notes`
- **`high_risk_snapshots`**: `snapshot_date`, `part_number`, `product_name`, `lot_inventory`, `date_of_expiration`, `expiration_bucket`, `lot_value`, `total_on_hand`, `average_monthly_usage`
- **`new_activities_18405028203`**: `board_id`, `board_name`, `item_id`, `item_name`, `person`, `color_mm1qbw8h`, `date_mm1qsr4r`, `date_mm1qs3j9`, `long_text_mm1q919n`, `board_relation_mm1q24ak`, `lookup_mm1qat8c`, `pulse_log_mm2p4yzr`
- **`new_forecast_18415088271`**: `board_id`, `board_name`, `item_id`, `item_name`, `subtasks_mm3zthme`, `date4`, `numeric_mm3ry8p5`, `date_mm3rcye8`, `person`, `status`, `formula_mm3rakvr`, `formula_mm3w7cgm`
- **`new_opportunities_18405027980`**: `board_id`, `board_name`, `item_id`, `item_name`, `person`, `status`, `text_mm35yakj`, `color_mm347pbr`, `date_mm1zhv48`, `date_mm1z67ja`, `date_mm3ywaac`, `formula_mm1z3me9`, `color_mm2nzmd0`, `color_mm1r7nzs`, `lookup_mm1racqv`, `board_relation_mm1q7qrc`, `board_relation_mm1q86ea`, `numeric_mm1ry7gm`, `formula_mm1z196v`, `formula_mm1zejs3`, `date_mm1rb9g0`, `color_mm1rd44d`, `color_mm1rdw7v`, `color_mm1rczba`, `color_mm1rz1n8`, `color_mm1r965q`, `color_mm1rteed`, `board_relation_mm1qte58`, `date_mm1r7mhn`, `date4`, `date_mm1qdtds`, `formula_mm1q55jm`, `formula_mm1r2awn`, `text_mm1qkehx`, `board_relation_mm1r6v66`, `color_mm1r3v74`, `subtasks_mm1zfzxp`, `custom_mm35qgac`, `date_mm396vaj`, `date_mm3yzw0e`, `lookup_mm7epeqv`, `lookup_mm7ea69w`, `lookup_mm7e6pm1`
- **`pipeline_snapshot`**: `snapshot_date`, `pipeline_total`
- **`sales_goals`**: `month`, `sales_rep`, `goal`
- **`sales_history_static`**: `date_approved`, `name`, `sales_rep`, `sales_rep_2`, `amount`, `source_system`
- **`sales_rep_roster`**: `sales_rep`, `sort_order`, `active`
- **`scorecard_monthly_history`**: `month_start`, `metric`, `workcenter`, `value`, `agg_type`, `source_system`
- **`shipping_daily_ops`**: `snapshot_date`, `sales_orders_shipped`, `packages_shipped`, `new_sales_orders_received`, `sales_orders_in_shipping_dept`
- **`shipping_revenue_blanket_daily`**: `snapshot_date`, `total_blanket_revenue`
- **`shipping_revenue_daily`**: `snapshot_date`, `total_unshipped_revenue`
- **`shipping_revenue_shipped_daily`**: `snapshot_date`, `total_shipped_revenue`
- **`stalled_win_lost_18409621334`**: `board_id`, `board_name`, `item_id`, `item_name`, `person`, `status`, `date_mm1zhv48`, `date_mm1z67ja`, `date_mm1zz7tw`, `formula_mm1z3me9`, `date_mm3zms4q`, `color_mm1r7nzs`, `lookup_mm1racqv`, `board_relation_mm1q7qrc`, `board_relation_mm1q86ea`, `numeric_mm1ry7gm`, `formula_mm1z196v`, `formula_mm1zejs3`, `date_mm1rb9g0`, `color_mm1rd44d`, `color_mm1rdw7v`, `color_mm1rczba`, `color_mm1rz1n8`, `color_mm1r965q`, `color_mm1rteed`, `board_relation_mm1qte58`, `date_mm1r7mhn`, `date4`, `date_mm1qdtds`, `formula_mm1q55jm`, `formula_mm1r2awn`, `text_mm1qkehx`, `board_relation_mm1r6v66`, `color_mm1r3v74`, `subtasks_mm1zfzxp`, `text_mm3g3e45`, `color_mm3g4j23`, `color_mm3g23yk`
- **`stalled_won_lost_18409621334`**: `board_id`, `board_name`, `item_id`, `item_name`, `person`, `status`, `date_mm1zhv48`, `date_mm1z67ja`, `date_mm1zz7tw`, `formula_mm1z3me9`, `date_mm3zms4q`, `color_mm1r7nzs`, `lookup_mm1racqv`, `board_relation_mm1q7qrc`, `board_relation_mm1q86ea`, `numeric_mm1ry7gm`, `formula_mm1z196v`, `formula_mm1zejs3`, `date_mm1rb9g0`, `color_mm1rd44d`, `color_mm1rdw7v`, `color_mm1rczba`, `color_mm1rz1n8`, `color_mm1r965q`, `color_mm1rteed`, `board_relation_mm1qte58`, `date_mm1r7mhn`, `date4`, `date_mm1qdtds`, `formula_mm1q55jm`, `formula_mm1r2awn`, `text_mm1qkehx`, `board_relation_mm1r6v66`, `color_mm1r3v74`, `subtasks_mm1zfzxp`, `text_mm3g3e45`, `color_mm3g4j23`, `color_mm3g23yk`
- **`tmp_container_20261102`**: `Plexus_Customer_No`, `Serial_No`, `Part_Key`, `Part_Operation_Key`, `Part_Operation_Weight`, `Material_Key`, `Heat_Key`, `Location`, `Card_No`, `Container_Status`, `Defect_Type`, `Rework_Operation`, `Container_Type`, `Quantity`, `Tare_Weight`, `Gross_Weight`, `Net_Weight`, `Receipt_Key`, `Add_By`, `Add_Date`, `Update_By`, `Update_Date`, `Last_Action`, `Cycle_Inventory_Note`, `Cycle_Inventory_Status`, `From_Container`, `Active`, `Moved_To_Workcenter`, `Note`, `Lot_Key`, `Master_Unit_Key`, `Special_Instructions`, `Containers`, `Size`, `Length`, `Tracking_No`, `Job_Op_Key`, `Job_Key`, `Master_Unit_Plan_Key`, `Remnant`, `Sort_Order`, `Defect_Detail_Key`, `Shelf_Date`, `BOM_Key`, `Container_Key`, `Account_No`, `Accounting_Job_Key`
- **`usage_update_20261105`**: `part_no`, `old_part_no`, `avg_daily`
- **`vw_approaching_msl_with_held`**: `part_no`, `description`, `reorder_point`, `on_hand_qty`, `quantity_available`, `at_reorder_point`, `avg_daily_usage`, `usage_days`, `days_on_hand`, `days_to_reorder`, `on_order_qty`, `open_job_qty`, `in_mfg_or_ordered`, `usage_source`, `plex_avg_daily_usage`, `ns_avg_daily_usage`, `plex_reorder_point`, `ns_reorder_point`, `ns_as_of`, `data_flag`, `unit`, `product_type`, `part_type`, `part_group_key`, `part_group`, `part_source_key`, `demand_qty`, `gross_demand_qty`, `lot_hold_qty`, `quarantine_qty`, `expired_qty`, `held_qty`, `on_hand_incl_held_qty`, `past_use_by_qty`, `refreshed_at`
- **`vw_approaching_msl_with_held_live`**: `part_no`, `description`, `reorder_point`, `on_hand_qty`, `quantity_available`, `at_reorder_point`, `avg_daily_usage`, `usage_days`, `days_on_hand`, `days_to_reorder`, `on_order_qty`, `open_job_qty`, `in_mfg_or_ordered`, `usage_source`, `plex_avg_daily_usage`, `ns_avg_daily_usage`, `plex_reorder_point`, `ns_reorder_point`, `ns_as_of`, `data_flag`, `unit`, `product_type`, `part_type`, `part_group_key`, `part_group`, `part_source_key`, `demand_qty`, `gross_demand_qty`, `lot_hold_qty`, `quarantine_qty`, `expired_qty`, `held_qty`, `on_hand_incl_held_qty`, `past_use_by_qty`
- **`vw_avg_days_to_close`**: `sales_rep`, `avg_days_to_close`
- **`vw_cost_lookup`**: `part`, `cost_ea`, `cost_source`
- **`vw_expiring_lots`**: `part_number`, `product_name`, `part_type`, `product_class`, `inventory`, `stocking_unit`, `shelf_life_remaining`, `date_of_expiration`, `location`, `warehouse`, `lpn`, `vendor_lot_number`, `display_identifier`, `days_remaining`, `expiration_bucket`, `sale_by_date`, `sale_by_urgent`, `cost_ea`, `cost_source`, `lot_value`
- **`vw_forecast_by_rep_month`**: `forecast_month`, `sales_rep`, `forecast_total`
- **`vw_forecast_decrementing`**: `board_id`, `board_name`, `item_id`, `item_name`, `subtasks_mm3zthme`, `date4`, `numeric_mm3ry8p5`, `date_mm3rcye8`, `person`, `status`, `formula_mm3rakvr`, `formula_mm3w7cgm`, `customer_open_forecast_total`, `customer_matched_sales_this_month`, `numeric_mm3ry8p5_adjusted`
- **`vw_high_risk`**: `part_number`, `product_name`, `product_class`, `part_type`, `lot_inventory`, `stocking_unit`, `location`, `warehouse`, `lpn`, `vendor_lot_number`, `date_of_expiration`, `shelf_life_remaining`, `days_remaining`, `expiration_bucket`, `sale_by_date`, `cost_ea`, `sale_by_tier`, `sale_by_urgent`, `lot_value`, `total_on_hand`, `average_monthly_usage`, `months_on_hand`, `total_inventory_value`
- **`vw_high_risk_weekly_changes`**: `part_number`, `product_name`, `date_of_expiration`, `expiration_bucket`, `week1_inventory`, `week2_inventory`, `week3_inventory`, `total_change`, `current_value`, `pct_change`
- **`vw_inventory_base`**: `part_number`, `display_name`, `item_stock_type`, `product_class`, `on_hand`, `average_monthly_usage`, `average_daily_usage`, `months_on_hand`, `cost_ea`, `cost_source`, `inventory_value`, `is_overstock`
- **`vw_opportunities_clean`**: `item_name`, `person`, `status`, `amount`, `status_date`, `notes`
- **`vw_overstock_by_bucket`**: `part_number`, `product_name`, `product_class`, `expiration_bucket`, `days_remaining`, `date_of_expiration`, `bucket_inventory`, `bucket_value`, `lot_count`, `months_on_hand`, `inventory_value`, `on_hand`
- **`vw_overstock_with_expiry`**: `part_number`, `display_name`, `product_class`, `item_stock_type`, `on_hand`, `average_monthly_usage`, `months_on_hand`, `inventory_value`, `cost_ea`, `cost_source`, `is_overstock`, `earliest_exp_date`, `min_days_remaining`, `earliest_exp_bucket`, `expiring_lot_value`, `expiring_inventory`, `lots_expiring_0_3mo`, `lots_expiring_4_6mo`, `lots_expiring_7_10mo`, `lots_expiring_11_15mo`, `has_expiring_lots`, `earliest_sale_by_date`
- **`vw_pipeline`**: `sort_order`, `stage`, `probability`, `pipeline_total`
- **`vw_plex_expiring_inventory`**: `part_no`, `part_name`, `product_type`, `exp_bucket`, `exp_bucket_sort`, `earliest_best_by`, `lot_count`, `expiring_qty`, `expiring_value`, `open_demand_qty`, `uncovered_qty`, `uncovered_value`, `part_key`, `earliest_use_by`, `refreshed_at`
- **`vw_plex_expiring_inventory_live`**: `part_no`, `part_name`, `product_type`, `exp_bucket`, `exp_bucket_sort`, `earliest_best_by`, `lot_count`, `expiring_qty`, `expiring_value`, `open_demand_qty`, `uncovered_qty`, `uncovered_value`, `part_key`, `earliest_use_by`
- **`vw_plex_order_header`**: `order_no`, `document_so`, `customer_name`, `sales_rep`, `status`, `next_due_date`
- **`vw_raw_materials_expiring_90`**: `part_number`, `product_name`, `part_type`, `inventory`, `stocking_unit`, `location`, `warehouse`, `shelf_life_remaining`, `date_of_expiration`, `days_remaining`, `cost_ea`, `cost_source`, `lot_value`
- **`vw_rep_pipeline_performance`**: `sales_rep`, `opp_total`, `opp_count`, `won_total`, `lost_total`, `won_count`, `lost_count`, `win_rate`, `loss_rate`, `conversion_rate`, `win_rate_by_count`, `loss_rate_by_count`, `conversion_rate_by_count`
- **`vw_rep_snapshot`**: `sales_rep`, `total_pipeline`, `top_customer_1`, `top_customer_1_total`, `top_customer_2`, `top_customer_2_total`, `top_customer_3`, `top_customer_3_total`, `top_opp_1`, `top_opp_1_total`, `top_opp_2`, `top_opp_2_total`, `top_opp_3`, `top_opp_3_total`
- **`vw_rep_top_customers`**: `sales_rep`, `customer`, `customer_total`, `category`, `rank`
- **`vw_sales`**: `date_approved`, `name`, `sales_rep`, `sales_rep_2`, `amount`
- **`vw_sales_activity_base`**: `rep_name`, `activity_date`, `submitted_at`, `is_pto`, `emails_sent`, `calls_made`, `meetings`, `visits_to_vox`, `social_dms`, `other`, `total_activities`, `leads_assigned`, `leads_contacted`, `notes`, `effective_activities`, `daily_goal`, `goal_status`, `pct_of_goal`
- **`vw_sales_activity_summary`**: `rep_name`, `yesterday_activities`, `yesterday_goal`, `yesterday_pct`, `yesterday_status`, `yesterday_is_pto`, `wtd_activities`, `wtd_goal`, `wtd_pct`, `mtd_activities`, `mtd_goal`, `mtd_pct`, `mtd_leads_assigned`, `mtd_leads_contacted`
- **`vw_sales_by_rep_month`**: `month`, `sales_rep`, `goal`, `actual_total`, `rep_type`, `rep_sort`
- **`vw_sales_daily_detail`**: `rep_name`, `activity_date`, `is_pto`, `emails_sent`, `calls_made`, `meetings`, `visits_to_vox`, `social_dms`, `other`, `total_activities`, `goal`, `pct_of_goal`, `goal_status`, `leads_assigned`, `leads_contacted`, `notes`
- **`vw_sales_daily_pace`**: `yesterday_date`, `monthly_goal`, `workdays_in_month`, `daily_goal`, `sales_yesterday`, `yesterday_pct_to_daily_goal`, `workdays_wtd`, `wtd_goal`, `sales_wtd`, `wtd_pct_to_goal`, `workdays_mtd`, `mtd_pace_goal`, `sales_mtd_thru_yday`, `top_order_10d_customer`, `top_order_10d_rep`, `top_order_10d_amount`, `top_order_10d_date`, `top_rep_10d`, `top_rep_10d_amount`
- **`vw_sales_legacy_sheet`**: `date_approved`, `name`, `sales_rep`, `sales_rep_2`, `amount`
- **`vw_sales_line_status`**: `order_no`, `part_no`, `all_done`, `all_canceled`, `canceled_value`, `release_statuses`
- **`vw_sales_mtd_vs_goal`**: `month`, `goal`, `actual_total`, `goal_progress`, `pct_into_month`
- **`vw_sales_open_order_aging`**: `order_no`, `document_so`, `customer_name`, `sales_rep`, `status`, `date_created`, `days_old`, `age_bucket`, `next_due_date`, `order_value`
- **`vw_sales_orders_over_10k`**: `order_no`, `document_so`, `customer_name`, `sales_rep`, `status`, `date_created`, `next_due_date`, `order_value`, `canceled_value_removed`, `value_rank`
- **`vw_sales_rep_yesterday_wtd`**: `rep_sort`, `sales_rep`, `yesterday_date`, `sales_yesterday`, `orders_yesterday`, `top_customer_yesterday`, `top_order_yesterday`, `sales_wtd`, `sales_mtd`
- **`vw_sales_rush_orders`**: `order_no`, `document_so`, `customer_name`, `sales_rep`, `status`, `memo`, `date_created`, `next_due_date`, `order_value`, `value_rank`
- **`vw_sales_top_wip_orders`**: `order_no`, `document_so`, `customer_name`, `sales_rep`, `next_due_date`, `wip_value`, `value_rank`
- **`vw_sales_wip_by_rep`**: `sales_rep`, `rep_type`, `rep_sort`, `open_orders`, `wip_value`, `orders_past_due`, `wip_value_past_due`
- **`vw_sales_yesterday_detail`**: `rep_name`, `activity_date`, `is_pto`, `emails_sent`, `calls_made`, `meetings`, `visits_to_vox`, `social_dms`, `other`, `total_activities`, `goal`, `pct_of_goal`, `goal_status`, `leads_assigned`, `leads_contacted`, `notes`
- **`vw_sales_ytd_vs_goal`**: `month`, `goal`, `actual_total`
- **`vw_sc_base`**: `month_start`, `metric`, `workcenter`, `value`, `agg_type`, `source_system`
- **`vw_sc_inventory_at_risk`**: `sort_order`, `status`, `lots`, `containers`, `inventory_value`
- **`vw_sc_inventory_split`**: `total_inventory_value`, `customer_inventory_value`, `vox_inventory_value`, `customer_pct`
- **`vw_sc_inventory_split_by_partno`**: `total_inventory_value`, `customer_inventory_value`, `vox_inventory_value`, `customer_pct`
- **`vw_sc_last_month`**: `last_month`, `revenue`, `revenue_goal`, `revenue_pct_to_goal`, `sales`, `sales_goal`, `sales_pct_to_goal`, `encapsulation`, `encapsulation_goal`, `encapsulation_pct_to_goal`, `bottling`, `bottling_goal`, `bottling_pct_to_goal`, `labeling`, `labeling_goal`, `labeling_pct_to_goal`, `wip`, `inventory_value`, `oos_count`
- **`vw_sc_monthly_wide`**: `month_start`, `sales`, `revenue`, `wip`, `inventory_value`, `oos_count`, `encapsulation`, `packaging`, `labeling`, `encapsulation_goal`, `packaging_goal`, `labeling_goal`
- **`vw_sc_production_daily_mtd`**: `sort_order`, `area`, `unit_label`, `yesterday_value`, `today_value`, `mtd_value`, `mtd_goal`, `pct_to_goal`, `pct_of_month`, `open_value`, `open_jobs`, `last_record_at`
- **`vw_sc_production_indexed`**: `month_start`, `encapsulation`, `packaging`, `labeling`, `encapsulation_idx`, `packaging_idx`, `labeling_idx`
- **`vw_sc_rev_ready_to_ship`**: `Order_No`, `PO_No`, `part_no`, `part_name`, `due_date`, `on_hold`, `price_ea`, `open_qty`, `on_hand_qty`, `ready_qty`, `ready_value`, `open_value`
- **`vw_sc_revenue_adjustments`**: `ship_date`, `shipper_no`, `invoice_no`, `account_no`, `description`, `amount`
- **`vw_sc_revenue_mtd_tile`**: `revenue_month`, `revenue_mtd`, `revenue_goal`, `pct_to_goal`, `pct_into_month`, `units_shipped_mtd`, `revenue_prior_months`, `revenue_ytd`, `goal_note`, `revenue_adjustments_mtd`
- **`vw_sc_safe_days`**: `last_recordable_incident`, `safe_days`, `live_incidents_logged`
- **`vw_sc_sales_mtd_tile`**: `sales_month`, `sales_mtd`, `sales_goal`, `pct_to_goal`, `orders_mtd`, `sales_prior_months`, `sales_ytd`
- **`vw_sc_scrap_mtd`**: `sort_order`, `area`, `good_qty_mtd`, `scrap_qty_mtd`, `total_qty_mtd`, `scrap_rate`
- **`vw_sc_wip_status_lines`**: `order_no`, `document_so`, `so_status`, `release_status`, `is_on_hold`, `customer_name`, `sales_rep`, `next_due_date`, `part_no`, `part_name`, `release_key`, `job_nos`, `qty_pending`, `price_ea`, `wip_value`, `ready_qty`, `ready_value`, `remaining_value`, `remaining_sort`, `remaining_status`
- **`vw_sc_wip_status_summary`**: `sort_order`, `status`, `lines`, `orders`, `value`, `pct_of_wip`
- **`vw_sc_wip_where_is_it`**: `order_no`, `document_so`, `customer_name`, `sales_rep`, `next_due_date`, `is_on_hold`, `release_status`, `part_no`, `part_name`, `qty_pending`, `ready_qty`, `wip_value`, `ready_value`, `remaining_value`, `remaining_status`, `fg_job_nos`, `stage`, `partial_note`, `confidence`, `bulk_part_no`, `bulk_part_name`, `bulk_needed`, `bulk_on_hand`, `bulk_open_job_qty`, `bulk_job_nos`, `bulk_lines_needing`, `caps_part_no`, `caps_needed`, `caps_on_hand`, `caps_open_job_qty`, `caps_job_nos`, `caps_lines_needing`, `label_part_no`, `label_needed`, `label_on_hand`, `label_open_job_qty`, `label_job_nos`, `label_status`
- **`vw_sc_ytd_cards`**: `year`, `through_month`, `sales_ytd`, `revenue_ytd`, `encap_ytd`, `packaging_ytd`, `labeling_ytd`, `oos_avg`, `inventory_avg`
- **`vw_shipping_daily_snapshot`**: `report_date`, `week_start`, `total_shipped_revenue`, `shipped_revenue_wtd`, `sales_orders_shipped`, `sales_orders_shipped_wtd`, `shippers_yesterday`, `units_shipped_yesterday`, `packages_shipped`, `new_sales_orders_received`, `sales_orders_in_shipping_dept`, `total_unshipped_revenue`, `unshipped_as_of`, `total_blanket_revenue`
- **`vw_shipping_daily_snapshot_old`**: `report_date`, `total_unshipped_revenue`, `total_blanket_revenue`, `total_shipped_revenue`, `sales_orders_shipped`, `packages_shipped`, `new_sales_orders_received`, `sales_orders_in_shipping_dept`
- **`vw_shoutouts`**: `shoutout`, `person`, `metric_number`, `metric_currency`, `metric_label`
- **`vw_top_opp_by_rep`**: `sales_rep`, `item_name`, `status`, `opp_value`
- **`vw_top_overstock`**: `category`, `rank`, `item`, `metric_value`
- **`vw_win_loss_rates`**: `metric_type`, `won_total`, `lost_total`, `active_total`, `won_count`, `lost_count`, `active_count`, `win_rate`, `loss_rate`, `conversion_rate`
