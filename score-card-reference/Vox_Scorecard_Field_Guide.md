A Field Guide to Your Scorecard 

#### **VOX NUTRITION** 

# **A Field Guide to Your Scorecard: Jargon, KPIs, and How Nutrition Companies Forecast** 

_You don't need to be a data analyst to understand your own dashboard. This is a plain-English tour of the terms we've been using, and the bigger picture of how supplement and nutrition manufacturers plan, forecast, and report on their business._ 

## **1. The Building Blocks: Jargon, Translated** 

Every dashboard is really just a set of numbers with a story behind them — where they came from, how they were combined, and what math was applied. Four ideas explain almost everything technical about how the Vox Scorecard is built: 

**Where a number lives —** Most companies your size run on a mix of spreadsheets (fast, flexible, but fragile — anyone can accidentally break a header row) and purpose-built systems like ERPs and MES platforms (slower to change, but far more trustworthy at scale). Your scorecard today pulls from both. 

**How numbers get combined —** “Aggregation” is just the math applied when many rows of data become one number on a dashboard — usually Sum, Average, or Count. The wrong choice here (say, summing a percentage instead of averaging it) is the single most common way a dashboard quietly lies to you. 

**Row grain —** This is the detail behind “how many rows am I actually adding together?” If a number is supposed to represent “one row per month,” but the underlying data secretly has three rows for June, summing it triples June by accident. This was the single biggest technical question we had to run down in your audit — good news, it checked out clean. 

**Calculated fields & blends —** A calculated field is a formula built inside the reporting tool (like “revenue ÷ goal”). A blend is joining two separate data sources together inside that same tool, the way a spreadsheet VLOOKUP joins two tabs. Both are powerful, but they're invisible unless someone opens the report and looks — which is exactly what this audit did. 

## **2. What Nutrition & Supplement Companies Actually Track** 

Your scorecard's six sections aren't arbitrary — they mirror the standard categories every supplement or nutrition manufacturer tracks, because the industry has a few things in common: physical production lines, FDA-regulated quality requirements, and inventory that expires. 

### **Sales & demand** 

Bookings, revenue, and pipeline — usually tracked Month-to-Date and Year-to-Date against a goal set during annual or quarterly planning. The goal itself typically comes from a demand forecast (see Section 3), not just a number picked out of thin air. 

Page 1 of 4 

A Field Guide to Your Scorecard 

### **Production throughput** 

For a manufacturer, “how much did we actually make” is as important as “how much did we sell.” Companies track output by production stage (in your case: Encapsulation, Bottling, Labeling) against a daily or monthly goal, plus a same-day “yesterday” number as a pulse check that the line is running. 

### **Quality & compliance** 

Supplements are regulated under cGMP (Current Good Manufacturing Practice), the FDA's rulebook for how these products must be made, tested, and documented. That's why First Pass Yield, defect rates (DPMO), reworks, deviations, and even destroyed/scrapped material all get tracked religiously — not just for efficiency, but because a regulator can ask for this history at any time. 

### **Inventory & supply chain** 

Work-in-progress, out-of-stock counts, and turnaround time all exist because raw materials and finished goods have lead times and, often, expiration dates. A stock-out on a key ingredient can halt a production line for weeks, so these numbers function as an early-warning system, not just bookkeeping. 

### **Financial roll-ups** 

MTD, QTD, and YTD views against goal are the standard cadence almost every manufacturer reports on, because it matches how budgets and targets are set — monthly and annually — and lets leadership see whether the business is pacing ahead or behind partway through a period. 

Page 2 of 4 

A Field Guide to Your Scorecard 

## **3. How Forecasting Actually Works in This Industry** 

Forecasting in a manufacturing business isn't one number — it's a recurring negotiation between sales expectations and production capacity, usually called S&OP (Sales & Operations Planning). A simplified version of the cycle: 

- Sales/demand planning estimates what customers will order next, usually a blend of historical trend, known contracts, and market judgment. 

- Operations checks that estimate against real production capacity — can the lines actually make that much, given raw material lead times and labor? 

- The two sides reconcile into a single agreed plan, which becomes the “goal” figures your dashboard measures actuals against every month. 

- Actuals get tracked continuously (this is what your scorecard is doing), and meaningful gaps between plan and actual feed back into the next planning cycle. 

Forecast accuracy matters more in this industry than in many others because of two things specific to nutrition/supplement manufacturing: raw material lead times can run months (especially for specialty or imported ingredients), and finished goods carry expiration dates — so overforecasting ties up cash in inventory that can go stale, while underforecasting means stock-outs and missed sales. 

This is also exactly why goal figures shouldn't live as one-off hardcoded numbers in a spreadsheet or a SQL query (as this audit found in one place) — they're the output of a real planning process and deserve the same rigor and audit trail as the actuals they're compared against. 

## **4. The Systems Behind the Curtain** 

Companies at your stage typically sit somewhere on a spectrum: 

- Early stage: everything in spreadsheets, maintained by whoever built them. Fast and flexible, but fragile — exactly the pattern this audit found repeatedly (scrambled headers, hardcoded values, duplicate copies of the same source). 

- Mid stage (where Vox sits today): a mix of spreadsheets and purpose-built views (BigQuery), joined together in a reporting tool. More powerful, but the seams between systems are where most of the issues in this audit were found. 

- Mature stage: a unified ERP/MES platform (like Plex, NetSuite, SAP Business One, or similar manufacturingfocused systems) that becomes the single source of truth for production, quality, and inventory, with the dashboard simply reading from it — no blends, no hardcoded goals, no scrambled headers possible. 

The migration plan in your companion Study Guide describes the move from the middle of that spectrum to the mature end — not because the current setup is unusual (it's a very normal stage for a growing manufacturer to be in), but because every issue this audit found traces back to that middle stage's inherent fragility. 

Page 3 of 4 

A Field Guide to Your Scorecard 

## **Quick-Reference Cheat Sheet** 

_Keep this page open the next time a term in one of the other documents doesn't ring a bell._ 

|**Term**|**What it means**|
|---|---|
|**MTD / YTD**|Month-to-date / year-to-date — running totals that reset each month or each January.|
|**FPY**|First Pass Yield — % of units that pass quality inspecton without needing rework.|
|**DPMO / Sigma**|Defects Per Million Opportunites, and the Sigma level derived from it — Six Sigma's way of<br>comparing quality across processes of diferent sizes.|
|**WIP**|Work In Progress — inventory that's started producton but isn't fnished yet.|
|**OOS**|Out of Stock.|
|**TAT**|Turnaround Time — how long a job takes start to fnish.|
|**cGMP**|Current Good Manufacturing Practce — the FDA's quality rulebook for supplement and food<br>manufacturers.|
|**Lot / Batch**|A specifc producton run, tracked as a unit for quality and recall purposes.|
|**S&OP**|Sales & Operatons Planning — the recurring meetng/process where sales forecasts and<br>producton capacity get reconciled.|
|**ERP**|Enterprise Resource Planning — the company-wide system of record for fnance, orders, and<br>inventory.|
|**MES**|Manufacturing Executon System — tracks what's happening on the plant foor in real tme.|
|**Source of truth**|The one place a number is authoritatvely calculated — everything else should just be reading<br>from it, not recalculatng it diferently.|
|**Row grain**|How much detail one row of data represents (e.g. one row per month, vs. one row per order)<br>— maters a lot for whether “adding up” a column makes sense.|
|**Calculated feld / Blend**|A formula built inside a reportng tool (like “revenue ÷ goal”), and a join of two data sources<br>inside that same tool — both live only in the dashboard, not in the original data.|



Page 4 of 4 

