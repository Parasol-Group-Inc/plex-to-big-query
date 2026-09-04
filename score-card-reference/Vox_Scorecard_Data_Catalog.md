Vox Nutrition Scorecard — Complete Data Catalog 

#### **VOX NUTRITION** 

# **Complete Data Catalog** 

_Every data source, blend, calculated field, and filter behind the Vox Nutrition MTD Scorecard — field by field, with status, aggregation behavior, and known issues. This is the full inventory of the reporting layer, including items that don't currently appear on the visible dashboard._ 

## **How to use this catalog** 

This is a reference document, not something to read cover to cover. Use it to look up any data source, blend, filter, or calculated field by name and see everything known about it: what it connects to, how fresh it is, what fields it exposes, how those fields default to aggregating, and any issue flagged during the audit. 

Four status labels are used throughout: 

**<mark>CLEAN</mark>** no issues found. 

**<mark>FLAGGED</mark>** works today, but has a real risk worth knowing about (e.g. an aggregation default that only happens to be safe given current data shape). 

**<mark>BROKEN</mark>** currently failing, misconfigured, or unreadable as-is. 

**<mark>ORPHAN</mark>** fully valid and working, but not currently wired into any visible chart. 

## **Catalog at a Glance** 

**Data sources:** 26 total  —  10 clean, 10 flagged, 5 broken, 1 orphaned **Blends:** 6 total (4 working production blends, 2 broken) **Calculated fields:** 4 total, all confirmed safe ratio constructions 

**Filters:** 23 total  —  13 active, 6 broken, 4 orphaned 

Page 1 of 14 

Vox Nutrition Scorecard — Complete Data Catalog 

## **Part 1 — Data Sources** 

_Grouped by the dashboard area each source primarily supports. A source's “Charts using it” count reflects the whole reporting ecosystem, not just this scorecard — some sources feed other reports too._ 

### **Revenue & Sales** 

#### **Vox_Looker_DB - Rev_MTD** 

**Connector:** Sheets / ds16 **Freshness:** 15 min **Charts using it:** 3 **<mark>FLAGGED</mark>** 

###### **Fields in this source** 

% Revenue Target Date Goal Inventory Balance 

MTD Revenue 

MTD Run Rate 

REVENUE 

Revenue in Shipping Revenue in WIP Record Count 

**Aggregation notes:** % Revenue Target defaults to Sum 

**Catalog notes:** Revenue in Shipping and Revenue in WIP are typed as TEXT, not Number — likely stored with $ or commas in the sheet, so they cannot be summed/charted numerically. Check the source Sheet formatting. 

#### **Vox_Looker_DB - Rev_MTD (2nd instance)** 

**Connector:** Sheets / ds166 **Freshness:** — **Charts using it:** 1 **<mark>BROKEN</mark>** 

###### **Fields in this source** 

Unknown — blocked by auth 

— **Aggregation notes:** 

**Catalog notes:** BROKEN: requires Sheets reconnect. Duplicate of ds16 under a different alias; unclear if identical. Only feeds 1 chart, so likely low visibility if broken. 

#### **VOX Revenue Targets & Run Rate - Rev_Table** 

**Connector:** Sheets / ds179 **Freshness:** 15 min **Charts using it:** 1 **<mark>BROKEN</mark>** 

###### **Fields in this source** 

A (Sum) Record Count 

**Aggregation notes:** Single unlabeled field 'A' 

**Catalog notes:** Only field is named 'A' — a blank spreadsheet header. Confirmed value (13,173,407.17) exactly matches Flow's 'Ready to Ship' figure — likely a manually copied snapshot that will go stale. Needs a real header and confirmed source of truth. 

#### **vw_sales** 

**Connector:** BigQuery / ds163 **Freshness:** 4 hours **Charts using it:** 3 **<mark>CLEAN</mark>** 

Page 2 of 14 

Vox Nutrition Scorecard — Complete Data Catalog 

**Fields in this source** amount (Sum) date_approved name sales_rep sales_rep_2 Record Count 

##### **Aggregation notes:** Clean 

**Catalog notes:** Two separate rep columns (sales_rep, sales_rep_2) — confirm what distinguishes them (e.g. split deals). 

#### **Vox_Looker_DB - Revenue** 

###### **Connector:** Sheets / ds130 **Freshness:** 15 min **Charts using it:** 3 **<mark>CLEAN</mark>** 

|**Fields in this source**|
|---|
|Account|
|Date|
|Document Number|
|Period|
|Sum of Amount (Sum)|
|Record Count|



##### **Aggregation notes:** Clean 

**Catalog notes:** Transaction-level detail, distinct from Rev_MTD's summary rows; confirm the two never feed the same tile. 

#### **shipping_revenue_daily** 

###### **Connector:** BigQuery / ds161 **Freshness:** 12 hours **Charts using it:** 1 **<mark>CLEAN</mark>** 

###### **Fields in this source** 

|snapshot_date|
|---|
|total_unshipped_revenue (Sum)|
|Record Count|



##### **Aggregation notes:** Clean 

**Catalog notes:** Genuine dollar total; likely feeds 'Total in Shipping' / WIP tiles. 

#### **vw_shipping_daily_snapshot** 

###### **Connector:** BigQuery / ds164 **Freshness:** — **Charts using it:** 7 **<mark>BROKEN</mark>** 

###### **Fields in this source** 

Unknown — blocked by auth 

##### — **Aggregation notes:** 

**Catalog notes:** BROKEN: requires BigQuery re-authorization (Authorize button, no fields visible). Feeds 7 charts — high-impact if currently failing for viewers. 

Page 3 of 14 

Vox Nutrition Scorecard — Complete Data Catalog 

### **Pipeline & Revenue Flow** 

#### **vw_pipeline** 

###### **Connector:** BigQuery / ds168 **Freshness:** 4 hours **Charts using it:** 1 **<mark>FLAGGED</mark>** 

|**Fields in this source**|
|---|
|pipeline_total (Sum)|
|probability (Sum)|
|stage|
|Record Count|



**Aggregation notes:** probability defaults to Sum 

**Catalog notes:** probability is normally a % per deal; summing across rows isn't meaningful unless a chart re-aggregates it. 

#### **vw_pipeline (duplicate)** 

**Connector:** BigQuery / ds167 **Freshness:** 4 hours **Charts using it:** 1 **<mark>ORPHAN</mark>** 

|**Fields in this source**|
|---|
|pipeline_total (Sum)|
|probability (Sum)|
|stage|
|Record Count|



##### **Aggregation notes:** Identical to ds168 

**Catalog notes:** Confirmed identical fields/aggregations/freshness to ds168 — a duplicate copy of the same view, likely created by duplicating a chart. Safe to consolidate to one source. 

#### **Vox_Looker_DB - Flow** 

**Connector:** Sheets / ds32 **Freshness:** 15 min **Charts using it:** 1 **<mark>CLEAN</mark>** 

|**Fields in this source**|
|---|
|Amount (Sum)|
|Order (Sum)|
|Phase|
|Record Count|



**Aggregation notes:** Order is a sort key, not a quantity — confirmed via data preview 

**Catalog notes:** 5 phases: Quotes, Pending SOs, WIP, Ready to Ship, Inventory Val. Order = 1-5 display sequence, not summable data — resolved, not an issue. 

### **Production** 

#### **Vox_Looker_DB - Production_Daily** 

**Connector:** Sheets / ds15 **Freshness:** 15 min **Charts using it:** 21 **<mark>CLEAN</mark>** 

|**Fields in this source**|
|---|
|Blending/Botling/Encap/Labeling: Date|
|Total (Sum)|
|Yesterday (Sum) x4 stages|



Page 4 of 14 

Vox Nutrition Scorecard — Complete Data Catalog 

###### **Fields in this source** 

Record Count 

##### **Aggregation notes:** Clean 

**Catalog notes:** Highest-usage source (21 charts). Wide layout (4 near-identical stage column groups) — adding a new stage later requires a schema change plus chart updates. 

#### **Vox_Looker_DB - Production_Goals** 

**Connector:** Sheets / ds13 **Freshness:** 15 min **Charts using it:** 18 **<mark>CLEAN</mark>** 

###### **Fields in this source** 

Blending Bottling Encapsulation 

GOALS (Date) Labeling Record Count 

**Aggregation notes:** Clean (once understood) 

**Catalog notes:** GOALS holds month-start dates — it's a join key to Production_Daily via the production blends, not a data error. Confirmed via the 'encap goals + totals' blend. 

### **Quality** 

#### **Quality_Looker_DB - YTD FPYs** 

**Connector:** Sheets / ds160 **Freshness:** 15 min **Charts using it:** 9 **<mark>FLAGGED</mark>** 

|**Fields in this source**|
|---|
|Area|
|DPMO|
|FPY|
|Month|
|Opps|
|Sigma|
|Total NCs+ Reworks|
|Total Produced|
|Record Count|



**Aggregation notes:** FPY, DPMO, Sigma default to Sum 

**Catalog notes:** HIGH PRIORITY: FPY/DPMO/Sigma are rates, not additive. Feeds the dashboard's FPY tiles (Encap/Bottling/Labeling). If any chart sums across Areas/Months, the displayed % is likely wrong. 

#### **Vox_Looker_DB - Quality_Rework** 

**Connector:** Sheets / ds17 **Freshness:** 15 min **Charts using it:** 5 **<mark>CLEAN</mark>** 

###### **Fields in this source** 

RW and Incoming Report Number(s) Date 

Page 5 of 14 

Vox Nutrition Scorecard — Complete Data Catalog 

**Fields in this source** Status Total Cost (COG + Labor) (Sum) Record Count 

##### **Aggregation notes:** Clean 

**Catalog notes:** Genuine additive dollar total; feeds the Reworks tile. 

#### **Vox_Looker_DB - Quality_Deviation** 

###### **Connector:** Sheets / ds18 **Freshness:** 15 min **Charts using it:** 3 **<mark>CLEAN</mark>** 

###### **Fields in this source** 

Date Deviation was Initiated Deviation No. Status Record Count 

##### **Aggregation notes:** Clean 

**Catalog notes:** Simple log/register; feeds the Deviations tile via Record Count. 

#### **Vox_Looker_DB - Quality_FGTAT** 

###### **Connector:** Sheets / ds124 **Freshness:** 15 min **Charts using it:** 2 **<mark>FLAGGED</mark>** 

|**Fields in this source**|
|---|
|Date of Result|
|Date Shipped|
|Days (Sum)|
|Lot #|
|Product Descripton|
|Record Count|



##### **Aggregation notes:** Days defaults to Sum 

**Catalog notes:** Days = finished-goods turnaround time per lot; summing across lots is meaningless (should be Average). Raw sheet also has a 'WITHIN GOAL' column not exposed here. 

#### **Vox_Looker_DB - Quality_RawTAT** 

###### **Connector:** Sheets / ds123 **Freshness:** 15 min **Charts using it:** 2 **<mark>FLAGGED</mark>** 

|**Fields in this source**|
|---|
|Date of Result|
|Date Sent|
|Days (Sum)|
|Part # (Sum)|
|Received Date|
|Record Count|



##### **Aggregation notes:** Days AND Part # default to Sum 

**Catalog notes:** Days = raw-material TAT, same issue as FGTAT. Part # is an identifier (e.g. 12057) — summing part numbers is meaningless, more clear-cut than the other aggregation flags. Raw sheet's 'WITHIN GOAL' flag not exposed here either. 

Page 6 of 14 

Vox Nutrition Scorecard — Complete Data Catalog 

#### **Vox_Looker_DB - Quality_MatDestr** 

**Connector:** Sheets / ds19 **Freshness:** 15 min **Charts using it:** 5 **<mark>CLEAN</mark>** 

###### **Fields in this source** 

|Material Destructon Report Number(s)|
|---|
|Report Date|
|Status|
|Value (Sum)|
|Record Count|



##### **Aggregation notes:** Clean 

**Catalog notes:** Genuine additive dollar total. Original dashboard tile showed 'No data' for Destruction $ — check whether this source has rows for the current period. 

### **Operations (TAT & Jobs)** 

#### **Weekly Rolling TAT Analysis - Analysis** 

**Connector:** Sheets / ds165 **Freshness:** 15 min **Charts using it:** 1 **<mark>FLAGGED</mark>** 

|**Fields in this source**|
|---|
|Average Work Days (Sum)|
|Bonus Standard (Sum)|
|Item Stock Type|
|Performance Standard (Sum)|
|Record Count|



##### **Aggregation notes:** Average Work Days defaults to Sum 

**Catalog notes:** A field literally named 'Average' is being summed — clearest example of the aggregation issue in the whole report. Should be Average. 

#### **Monthly TAT Analysis - Analysis** 

**Connector:** Sheets / ds177 **Freshness:** 15 min **Charts using it:** 1 **<mark>FLAGGED</mark>** 

###### **Fields in this source** 

|Average Work Days (Sum)|
|---|
|Bonus Standard (Sum)|
|Item Stock Type|
|Performance Standard (Sum)|
|Record Count|



**Aggregation notes:** Average Work Days defaults to Sum 

**Catalog notes:** Identical field structure to Weekly Rolling TAT Analysis — likely a copied sheet template (weekly vs monthly rollup). Same aggregation issue. 

#### **Vox_Looker_DB - MFG_Job** 

**Connector:** Sheets / ds174 **Freshness:** 15 min **Charts using it:** 1 **<mark>FLAGGED</mark>** 

###### **Fields in this source** 

Cap Specs 

Page 7 of 14 

Vox Nutrition Scorecard — Complete Data Catalog 

###### **Fields in this source** 

Caps Pending Customer Date Entered Days in WIP Description Qty Ordered SKU Yield Record Count 

**Aggregation notes:** Yield, Days in WIP default to Sum **Catalog notes:** Yield is typically a % per job; Days in WIP summed across jobs is not meaningful. Consider Average. 

#### **Vox_Looker_DB - Bottling_Job** 

**Connector:** Sheets / ds173 **Freshness:** 15 min **Charts using it:** 1 **<mark>CLEAN</mark>** 

**Fields in this source** Bottle Company DATE Pill Count (Sum) Product QTY (Sum) WO# Record Count 

##### **Aggregation notes:** Clean 

**Catalog notes:** Genuine additive quantities; no issues. 

### **Inventory & Safety** 

#### **Vox_Looker_DB - Inventory** 

###### **Connector:** Sheets / ds36 **Freshness:** 15 min **Charts using it:** 1 **<mark>FLAGGED</mark>** 

|**Fields in this source**|
|---|
|Avg. Daily|
|Current Qty|
|Item Name|
|On Order|
|Record Count|



**Aggregation notes:** Avg. Daily defaults to Sum 

**Catalog notes:** Raw sheet has ~23 columns incl. a full reorder-point analysis table; Looker Studio only pulls a smaller secondary set (Item Name/Current Qty/Avg. Daily/On Order). The detailed table isn't used at all — confirm intentional. 

Page 8 of 14 

Vox Nutrition Scorecard — Complete Data Catalog 

#### **vw_top_overstock** 

**Connector:** BigQuery / ds189 **Freshness:** 12 hours **Charts using it:** 2 **<mark>FLAGGED</mark>** 

###### **Fields in this source** 

category item metric_value (Sum) rank (Sum) Record Count 

**Aggregation notes:** rank defaults to Sum 

**Catalog notes:** rank is an ordinal (1st, 2nd...); summing it is not meaningful. Check if the consuming chart re-aggregates. 

#### **Cycle count - Dashboard** 

###### **Connector:** Sheets / ds181 **Freshness:** 15 min **Charts using it:** 3 **<mark>BROKEN</mark>** 

###### **Fields in this source** 

H (Sum) I (Text all null) J (Text) K (Sum) L (Sum) Record Count 

**Aggregation notes:** Fields named after raw column letters 

**Catalog notes:** No real header row — Looker Studio reads column letters as field names. Data preview suggests J = cycle-count Class (A-E), K = items counted, L = inventory value, H = possibly accuracy % (one row shows 0.987). Row 4 looks column-shifted; row 7 is a stray header row ('Class') bleeding into the data range. Needs real headers and a cleaned source range. 

#### **Vox_Looker_DB - Safety** 

**Connector:** Sheets / ds22 **Freshness:** 15 min **Charts using it:** 1 **<mark>BROKEN</mark>** 

###### **Fields in this source** 

|'7/23/2026' (Sum) = actually holds the Safe Days value (8); 'Last OSHA' (Text) = actually holds the label 'Safe Days'; Record Count|
|---|



**Aggregation notes:** Field names and values are swapped 

**Catalog notes:** Source sheet has no header row — it's a 2-row label/value table (Last OSHA: 7/23/2026 / Safe Days: 8). Looker Studio read row 1 as headers, so field names and values are backwards. Underlying numbers are correct; only the labels are broken. Needs a real Metric/Value header structure. 

Page 9 of 14 

Vox Nutrition Scorecard — Complete Data Catalog 

## **Part 2 — Blends** 

_Joins of two Sheets sources performed inside Looker Studio itself — the reporting-layer equivalent of a SQL JOIN._ 

#### **encap goals + totals** 

**Connector:** Blend (Merge type: Left outer) **Freshness:** — **Charts using it:** 6 **<mark>CLEAN</mark>** 

Table 1: Vox_Looker_DB - Production_Daily (Encap Date, Encap Total) Table 2: Vox_Looker_DB - Production_Goals (GOALS, Encapsulation) Join key: Encap Date = GOALS 

Working. No calculated field in the blend itself — the % to Goal math must live at chart level. 

#### **bottling daily+ goals** 

**Connector:** Blend (Merge type: Left outer) **Freshness:** — **Charts using it:** 6 **<mark>CLEAN</mark>** 

Table 1: Vox_Looker_DB - Production_Daily (Bottling Date, Bottling Total) Table 2: Vox_Looker_DB - Production_Goals (GOALS, Bottling) Join key: Bottling Date = GOALS 

Working. Identical structure to the Encap blend. 

#### **labeling daily + goals** 

**Connector:** Blend (Merge type: Left outer) **Freshness:** — **Charts using it:** 6 **<mark>CLEAN</mark>** 

Table 1: Vox_Looker_DB - Production_Daily (Labeling Date, Labeling Total) Table 2: Vox_Looker_DB - Production_Goals (GOALS, Labeling) Join key: Labeling Date = GOALS 

Working. Identical structure to the Encap/Bottling blends. 

#### **blending goals + to date** 

**Connector:** Blend (Merge type: Left outer) **Freshness:** — **Charts using it:** 0 **<mark>ORPHAN</mark>** 

Table 1: Vox_Looker_DB - Production_Daily (Blending Date, Blending Total) Table 2: Vox_Looker_DB - Production_Goals (GOALS, Blending) Join key: Blending Date = GOALS 

Fully valid and correctly built — identical to the other 3 production blends — but no chart on the dashboard uses it. The Blending production stage simply never got a chart added. 

#### **mtd to goal** 

**Connector:** Blend (Merge type: Left outer) **Freshness:** — **Charts using it:** 0 **<mark>BROKEN</mark>** 

<mark>Table 1: (no data source selected) Table 2: (no data source selected) Join key: Invalid dimension on both sides</mark> 

BROKEN: both tables are missing their data source; Save is disabled in Looker Studio. Cascades into at least 3 broken filters (mtd, this month, last month) that reference this blend's missing fields. 

#### **Goal + SalesDB** 

**Connector:** Blend (Merge type: Left outer) **Freshness:** — **Charts using it:** 0 **<mark>BROKEN</mark>** 

Table 1: "Monthly Goal" (no data source selected) Table 2: "MTD Sales" (no data source selected) Join key: Invalid dimension on both sides 

BROKEN: same failure as mtd to goal. Table names ("Monthly Goal", "MTD Sales") suggest it was meant to join the Monthly Goal tab (LookerStudio_DB.xlsx) to sales data, but the underlying sources have since been removed or disconnected. 

Page 10 of 14 

Vox Nutrition Scorecard — Complete Data Catalog 

## **Part 3 — Calculated Fields** 

_Formulas built inside Looker Studio itself, computed live from other fields — not stored anywhere in the source data._ 

|**Field**|**Built on**|**Formula**|**Type**|**Comparison**|**Notes**|
|---|---|---|---|---|---|
|**% to rev goal**|Vox_Looker_DB -<br>Rev_MTD|MAX(MTD Revenue)<br>/ MAX(Goal)|Percent|None|Confrmed clean —<br>safe MAX/MAX rato<br>constructon.|
|**encap %**|encap goals + totals<br>(blend)|SUM(Encap Total) /<br>SUM(Encapsulaton)|Percent|Period|Confrmed clean —<br>safe SUM/SUM<br>rato. Field ID<br>qt_stxthsll2d.|
|**botling %**|botling daily+ goals<br>(blend)|SUM(Botling<br>Total) /<br>SUM(Botling)|Percent|Period|Confrmed clean —<br>safe SUM/SUM<br>rato. Field ID<br>qt_ae8tyyll2d.|
|**New Field (=**<br>**labeling %)**|labeling daily +<br>goals (blend)|SUM(Labeling Total)<br>/ SUM(Labeling)|Percent|Period|Confrmed clean,<br>but never renamed<br>from Looker<br>Studio's default —<br>cosmetc gap. Field<br>ID qt_b68tyyll2d.|



Page 11 of 14 

Vox Nutrition Scorecard — Complete Data Catalog 

## **Part 4 — Filters** 

_Every filter defined anywhere in the report's data sources and blends, including ones not currently attached to any visible chart._ 

|**Filter**|**Applies to**|**Conditon**|**Charts**|**Status**|**Notes**|
|---|---|---|---|---|---|
|**Encap Date flter**|encap goals + totals<br>(blend)|Encap Date Is This<br>Month|2|**ACTIVE**|Restricts blend to<br>the current month;<br>sidesteps the daily-<br>vs-monthly join<br>granularity concern.|
|**botling mtd**|botling daily+ goals<br>(blend)|Botling Date Is This<br>Month|2|**ACTIVE**|Same patern as<br>Encap Date flter.|
|**Labeling Date flter**|labeling daily +<br>goals (blend)|Labeling Date Is This<br>Month|2|**ACTIVE**|Same patern as<br>Encap Date flter.|
|**encap last month**|encap goals + totals<br>(blend)|Encap Date Is<br>Previous Month|3|**ACTIVE**|Pairs with Encap<br>Date flter for<br>month-over-month<br>comparison.|
|**labeling last month**|labeling daily +<br>goals (blend)|Labeling Date Is<br>Previous Month|3|**ACTIVE**|Pairs with Labeling<br>Date flter.|
|**botling last month**|botling daily+ goals<br>(blend)|Botling Date Is<br>Previous Month|3|**ACTIVE**|Pairs with botling<br>mtd.|
|**Period flter**|(unconfrmed<br>source)|Period Is in the Year|2|**ACTIVE**|Conditon<br>confrmed from the<br>sources list screen;<br>underlying data<br>source not opened<br>directly.|
|**wip**|Vox_Looker_DB -<br>Flow|Phase Equal to (=)<br>WIP|1|**ACTIVE**|Only one of Flow's 5<br>phases with a live<br>chart.|
|**value**|vw_top_overstock|category Equal to<br>(=) Top Value|1|**ACTIVE**|Confrms real<br>category values<br>inside<br>vw_top_overstock.|
|**qty**|vw_top_overstock|category Equal to<br>(=) Top Quantty|1|**ACTIVE**|Confrms real<br>category values<br>inside<br>vw_top_overstock.|
|**botling only**|Quality_Looker_DB<br>- YTD FPYs|Area Equal to (=)<br>Botling/Packaging|3|**ACTIVE**|Confrms real Area<br>values inside YTD<br>FPYs.|
|**labeling only**|Quality_Looker_DB<br>- YTD FPYs|Area Equal to (=)<br>Labeling|3|**ACTIVE**|Confrms real Area<br>values inside YTD<br>FPYs.|
|**encap only**|Quality_Looker_DB<br>- YTD FPYs|Area Equal to (=)<br>Encapsulaton|3|**ACTIVE**|Confrms real Area<br>values inside YTD<br>FPYs.|
|**blending goals + to**<br>**date flter (Blending**|blending goals + to<br>date (blend)|Blending Date Is<br>This Month|0|**ORPHAN**|Fully valid, identcal<br>structure to the|



Page 12 of 14 

Vox Nutrition Scorecard — Complete Data Catalog 

|**Filter**|**Applies to**|**Conditon**|**Charts**|**Status**|**Notes**|
|---|---|---|---|---|---|
|**Date flter)**|||||other 3 stages —<br>just never atached<br>to a chart. Part of<br>the 'Blending never<br>shipped' fnding.|
|**blending last month**|blending goals + to<br>date (blend)|Blending Date Is<br>Previous Month|0|**ORPHAN**|Fully valid — same<br>story as Blending<br>Date flter.|
|**Phase flter**|Vox_Looker_DB -<br>Flow|Phase Equal to (=)<br>Ready to Ship|0|**ORPHAN**|Valid and correctly<br>built, but no chart<br>uses it. One of 3<br>unused Flow-phase<br>flters.|
|**inv val**|Vox_Looker_DB -<br>Flow|Phase Equal to (=)<br>Inventory Val|0|**ORPHAN**|Valid and correctly<br>built, but no chart<br>uses it.|
|**this month**|mtd to goal (blend)|Field "Missing";<br>conditon<br>incomplete|0|**BROKEN**|Broken because the<br>mtd to goal blend<br>has no data source.<br>Cascading failure,<br>not independent.|
|**GOALS flter**|encap goals + totals<br>(blend)|Field "Missing"<br>(references GOALS,<br>which isn't exposed<br>in the blend's<br>output)|0|**BROKEN**|Diferent root cause<br>than the others: the<br>blend itself is valid,<br>but this flter<br>references a raw<br>join-key feld name<br>that the blend<br>doesn't expose<br>downstream.|
|**mtd**|mtd to goal (blend)|Field "Missing"; Is<br>This (incomplete)|0|**BROKEN**|Cascading failure<br>from the broken<br>mtd to goal blend.|
|**last month**|mtd to goal (blend)|Field "Missing"; Is<br>Previous<br>(incomplete)|0|**BROKEN**|Cascading failure<br>from the broken<br>mtd to goal blend.|
|**no total**|Vox_Looker_DB -<br>Safety|No conditon clause<br>confgured at all;<br>flter name did not<br>save|0|**BROKEN**|Abandoned mid-<br>creaton — a data<br>source was picked<br>but no conditon<br>was ever added.<br>Diferent failure<br>mode than the<br>'Missing feld' cases.|
|**total only**|Vox_Looker_DB -<br>Safety|No conditon clause<br>confgured at all;<br>flter name did not<br>save|0|**BROKEN**|Same<br>abandoned/incompl<br>ete state as 'no<br>total' — likely a<br>second atempt at<br>the same unfnished<br>idea.|



Page 13 of 14 

Vox Nutrition Scorecard — Complete Data Catalog 

## **Appendix: Related Documents** 

This catalog is the field-level reference companion to three other deliverables from this audit: 

- Vox_Scorecard_Data_Mapping.xlsx — the working audit tracker, including the chart-by-chart map of all 32 visible dashboard tiles with confidence ratings. 

- vox_scorecard_navigator.html — an interactive, clickable replica of the live dashboard for tracing any number back to its source visually. 

- Vox_Scorecard_Study_Guide.docx — the narrative explanation of the dashboard's logic, risk register, and the Plex migration plan. 

- Vox_Scorecard_Field_Guide.docx — a plain-English primer on the jargon and how nutrition/supplement companies forecast and report more broadly. 

This catalog goes one layer deeper than any of those: it documents every field in every source, whether or not that field currently appears on a chart — useful both for auditing today's dashboard and for scoping a future migration (see the Study Guide's Section 6). 

Page 14 of 14 

