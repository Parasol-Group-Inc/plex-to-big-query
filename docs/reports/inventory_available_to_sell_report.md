# Inventory | Available to Sell (On-Hand less Demand)

> **Status:** ✅ Built and verified 2026-09-09; demand rules confirmed by Jennilyn the same day · **Category:** Supply Chain · **Runs:** rides the Sales Orders pipeline

## What this tells you

**Quantity Available** for every part in one place: what is physically on hand, minus what is already owed to customers. This is the number Jennilyn asked for directly (email, 2026-09-04):

> *"We're wondering where to best see the Quantity Available of parts. Traditionally, we use Quantity on Hand − Quantity (Sold, Demand, Allocated, etc) to get this. Sales uses as they sell things, but we also using for reporting OOS."*

Amber's answer named Plex's **Sales Order Line Inventory Check** screen, with the caveat that it is *"a single part view at a time."* This report is that same calculation for every part at once, which is the reason to have it in BigQuery at all: Sales can filter it, and the out-of-stock report is built on top of it rather than duplicating the maths.

## Where it fits

- Answers the open "where do we pull Quantity Available from" question for both Sales and OOS reporting.
- Becomes the single source for [`inventory_out_of_stock_report`](inventory_out_of_stock_report.md), which is now just this report filtered to Vox's three OOS conditions.
- Sits alongside [`mfg_job_schedule_inventory_availability_report`](mfg_job_schedule_inventory_availability_report.md), which pairs on-hand with **on order** (inbound POs) rather than with demand.

## How it's built (high level)

On-hand comes from [`part_on_hand_inventory_report`](part_on_hand_inventory_report.md) — read from that report rather than recalculated, so there is exactly one definition of "on hand" in the pipeline.

Demand comes from **sales order releases**, mirroring how Plex's own screen splits it:

- **Order demand** — the part is itself on a sales order line. Quantity comes from the release (the schedule line), with anything already shipped netted off.
- **Component demand ("Order Reqd")** — a *parent* finished good is on a sales order, and this part is a component of it. Plex pushes that requirement down the bill of materials, so a 5,000-unit order on a finished good creates 5,000 units of demand against the blend and bottle that go into it. This report does the same, using Plex's pre-flattened BOM.
- **Job demand ("Job Reqd")** is deliberately **not** included — see flags.

Which order statuses count as demand is **Plex's own answer, not ours**: the `Include_In_MRP` flag on the order status. As of 2026-09-09 that means **Pending Fulfillment and Hold**, and excludes Quote, Pending Sales Approval, Deposit Review, Closed and Cancelled. Reading the flag rather than hand-writing that list is what let the report absorb a same-day change to Vox's Plex configuration — Jennilyn switched demand off for the two approval stages, and Vox cut the status list from 10 to 7, with no edit needed here.

Two availability columns are published — with and without BOM-exploded component demand. It was four until 2026-09-09; the two "firm" variants became meaningless once Plex's own flag encoded Vox's demand rule.

- **Pipeline:** `reports/sales_orders.yaml` → `inventory_available_to_sell_report`
- **SQL:** `reports/sql/inventory_available_to_sell_view.sql`

## Flags and open questions

- **✅ The "do unapproved orders count as demand" question is answered — and Jennilyn fixed it in Plex, not here.** *"I did change it in Plex because I saw that it was showing demand for deposit review and pending sales approval. We don't count those as demand until they're pending fulfillment."* (2026-09-09.) Because this report gates on Plex's own `Include_In_MRP` flag rather than a hand-written status list, **it needed no code change** — order demand dropped from **508,807 units to 5,000** on its own once her change reached the extract. `Include_In_MRP = 1` now means exactly Pending Fulfillment + Hold.
- **The `_firm_` columns were removed, not kept for the record.** They were defined as "Include_In_MRP and not on hold", which after her change would wrongly exclude the **Hold** status she explicitly wants counted (*"hold as well... it was sold but it hasn't shipped yet"*). A stale second reading is worse than none. `order_demand_from_held_orders_qty` keeps the Hold portion visible without pretending it's excluded.
- **One real choice remains:** `available_vs_orders` (the part's own order lines) vs `available_vs_total_demand` (plus BOM-exploded component demand). For `33` blend parts it has to be the second — they are almost never ordered directly, so without the explosion they show no demand at all.
- **"Job Reqd" is the next thing to add, and it is now possible.** Open-job component requirements were left out because `Part_v_Job`/`Part_v_Job_Op` had been 0 rows on every previous check — a column there would have been a confidently-wrong zero. **As of 2026-09-09 they hold real rows** (25 jobs, 28 job operations), and Jennilyn pointed at Plex's **Job Allocations** screen as the better source for "required" (*"the job allocations might work better... you can see how much is required and the inventory amount"*). `Part_v_Job_Bom` is the requirement table. Not built yet: it needs care to avoid double-counting against the BOM explosion, since a job is created *from* an order at Pending Fulfillment, so the same demand can appear twice.
- **The flat BOM's quantity meaning is now partly proven.** The report treats `Part_v_Flat_BOM.Quantity` as the component quantity per *one* unit of the top-level part. Checked 2026-09-09 against the single-level `Part_v_BOM`: the quantities are **identical on all 81 (parent, component) pairs present in both**, and the deepest BOM at Vox is **one level**. So the two agree wherever they can be compared — but at one level, per-unit and extended quantities are the same number anyway, so **the multi-level case is still untested**. Re-run that comparison the first time a two-level BOM exists.
- **No time dimension.** This is availability *now*. Plex's PRP/MRP screens (Amber's other suggestion) project it forward by date; doing that here needs demand at a due-date grain and the inventory snapshot table, which is empty.
- **Inbound purchase orders are not netted in.** "Available to sell" is what exists minus what is owed, not what is on its way. On-order is covered separately by [`purchasing_open_orders_report`](purchasing_open_orders_report.md).
- **Finished goods have no shelf stock at Vox, and that is expected.** In both the live Plex screens and this data, finished-goods on-hand is zero — everything sits as components and WIP, because Vox builds to order. So finished goods will show negative availability whenever they have an open order. That is the business reality, not a data fault, and it is why the OOS report is scoped to `33` parts with a minimum stock level rather than run across everything.

## More detail

Full demand rules, the confirmed `Include_In_MRP` status table and every deliberate exclusion are in the SQL file's header. The requirements conversations are in [`meetings-reference/Sep-1/`](../../meetings-reference/Sep-1/), [`meetings-reference/Sep-4/`](../../meetings-reference/Sep-4/) and [`meetings-reference/sep-9/`](../../meetings-reference/sep-9/).
