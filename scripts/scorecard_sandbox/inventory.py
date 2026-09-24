"""
Inventory family: the warehouse as it stands on the build date, the
production / depletion movements behind it since 1 Jan, a year of cycle
counts, and monthly standard-cost snapshots — the rows behind every Inventory
tile (quantity available, out of stock, top quantity, average daily usage,
valuation, cycle count accuracy).

Writes ONLY raw_Part_v_Container, raw_Part_v_Cycle_Inventory,
raw_Part_v_Cell_Production, raw_Part_v_Cell_Depletion, raw_Part_v_Snapshot,
raw_Part_v_Snapshot_Cost_Sub_Type_Breakdown,
raw_Part_v_Cost_Sub_Type_Breakdown_History — plus ONE column of
raw_Part_v_Part, Minimum_Inventory_Quantity, on the 33-prefix capsule parts.

Runs LAST (generators.FAMILIES): it reads the production log the production
module wrote and the open order book the sales module wrote, and sizes itself
against both at run time. Nothing about demand is hard-coded.

HOW IT STAYS REAL
  * Containers are clones of real Part_v_Container rows — the same part's own
    container when one exists, else one of the same part family — with only
    keys, serial, quantity/weights, dates, the (real) part / its operation /
    job op, the (real) location and the status changed. Locations are only
    ever codes the tenant already uses: real container locations, and the
    Default_Production_Location of the work centre that made the part.
  * Cell_Production / Cell_Depletion have NEVER held a real row in PlexTest
    (every row there was the old injector's), so there is no row to clone.
    Each Cell_Production row is instead the projection of a Part_v_Production
    record onto the columns the two tables share (PCN, Part_Key,
    Part_Operation_Key, Quantity, Serial_No, Production_No, Job_Op_Key, date);
    each Cell_Depletion row is that record's level-1 Flat_BOM component
    consumption (quantity x Flat_BOM.Quantity), pointing at a real container
    of the component. Columns no real record can supply are left NULL rather
    than invented.
  * Cycle counts are clones of the one real Part_v_Cycle_Inventory row.
  * Snapshots are clones of the one real Part_v_Snapshot row; cost history
    rows are clones of real Part_v_Cost_Sub_Type_Breakdown_History rows. The
    pointer table Part_v_Snapshot_Cost_Sub_Type_Breakdown is empty in Plex and
    is three keys wide (PCN, Snapshot_Key, Change_Key) — its rows are nothing
    but keys, taken from the snapshot and history rows they join.

THE WAREHOUSE (containers, on the build date)
  Produced parts hold a few weeks of their own recent output: last-30-day good
  production x cover — finished goods (9) 0.25-0.5, blends / bright bottles /
  everything else 0.08-0.3. Purchased parts (raw materials, packaging, labels
  never printed in-house) hold 0.8-2.2 x their last-30-day depletion. The real
  containers stay where they are and count toward the target. A few
  containers sit in Hold (fresh finished goods) or Inspection Required (just
  received, at the Receiving Dock) — both count as on-hand under Vox's rule —
  and ~1% are Defective, which does not.

OUT OF STOCK — sized from the order book at run time
  inventory_out_of_stock_view.sql: part_no LIKE '33%', Minimum_Inventory_
  Quantity > 0, available_vs_total_demand < 0, product type not Custom. Open
  demand (direct + BOM-exploded) is read by running the REAL
  inventory_available_to_sell_view.sql (with part_on_hand_inventory_view.sql
  inlined) against the sandbox. Of the eligible 33-parts that carry demand,
  min(scale.OUT_OF_STOCK_PARTS, how many there are) are held short (on-hand
  0.25-0.8 x demand; where one has no real container, it is left at zero —
  Jennilyn's "zero inventory and we have demand" case), the rest are stocked
  above demand (1.15-1.5 x).
  Minimum_Inventory_Quantity: left at PlexTest's value wherever that is > 0.
  Only an ACTIVE eligible 33-part (open demand or depletion) whose PlexTest
  value is 0 gets one: two weeks (14 days) of its own average daily depletion
  over the last 90 days, rounded to 10,000; if it has never been consumed,
  25% of its open demand. Every 33-part is first reset to PlexTest's value AS
  OF build.SNAPSHOT (the instant the sandbox was copied from), in the same
  UPDATE, so re-runs are idempotent.

STANDARD COSTS — derived, sandbox-only (approved by the user)
  Every cost is per unit, like Plex's (the real rows: $0.0014/capsule,
  $0.039/label, $0.22/finished bottle), split over the two real cost
  sub-types in their real proportion, on the real cost model:
  * Real anchors: for every part that has real cost history, its latest real
    cost. Family anchor = median real cost of the family (part-number prefix).
  * Finished goods (9): F x the part's LOWEST customer price
    (Customer_Part_Price via Customer_Part), where F is the median of
    real-standard-cost / lowest-price over finished goods that have both, if
    that lands in [0.20, 0.80]; otherwise FG_COST_SHARE (0.45, i.e. a 55%
    gross margin, a contract manufacturer's norm). No price -> family anchor.
  * Bright bottles (5): the real 5/9 cost ratio (median over real pairs,
    5-part is a level-1 component of the 9-part) x the cheapest costed
    9-parent's cost. No parent -> family anchor.
  * Capsules (3), blends (2), labels (7): the family's real anchor.
  * Packaging raw materials (1-prefix consumed >= 1 each per parent unit:
    empty capsules, bottles, lids, desiccants): the residual of a real-costed
    parent once its non-packaging components are paid for, shared equally —
    e.g. a real capsule's cost minus its blend content = the empty shell. With
    no real parent: the median residual of the same product type.
  * Every other raw material (ingredients): the real blend anchor per unit —
    a blend is by construction its ingredients in the same unit of measure
    (Flat_BOM ingredient quantities sum to 1.0 per blend unit).
  History: an opening standard dated 29 Dec 2025 (or 3 days before a part's
  first movement, if later) at the rolled cost / (1 + ROLL_UPLIFT), then the
  mid-year roll on the real roll date (the commonest real Change_Date) at the
  derived cost. Snapshots: the 1st of every month through the build month
  (the real snapshot is 1 Sep and is reused), each pointing at the latest
  cost per (part, operation, sub-type) in force on its date.

CYCLE COUNTS
  scale.CYCLE_COUNTS_PER_MONTH location counts a month (the build month
  pro-rated), over real locations, one month left quiet. A count accounts for
  the containers actually in that location; about (1 - scale.CYCLE_ACCURACY)
  of counts find one container unaccounted for, so the per-location hit rate
  averages to scale.CYCLE_ACCURACY. Part_v_Cycle_Inventory.Location is INT64
  on this tenant, so the text code cannot be stored: each real location gets
  one stable key, shared by Location and Location_Key.
"""

import datetime as dt
import math
import os
import random
import re
import statistics

import scale
from common import PERIOD_START, PROJECT, TAG

UTC = dt.timezone.utc
HERE = os.path.dirname(os.path.abspath(__file__))
SQL_DIR = os.path.join(os.path.dirname(os.path.dirname(HERE)), "reports", "sql")

T_CONT = "raw_Part_v_Container"
T_CYC = "raw_Part_v_Cycle_Inventory"
T_CP = "raw_Part_v_Cell_Production"
T_CD = "raw_Part_v_Cell_Depletion"
T_SNAP = "raw_Part_v_Snapshot"
T_PTR = "raw_Part_v_Snapshot_Cost_Sub_Type_Breakdown"
T_HIST = "raw_Part_v_Cost_Sub_Type_Breakdown_History"
OWNED = [T_CONT, T_CYC, T_CP, T_CD, T_SNAP, T_PTR, T_HIST]

# Synthetic keys start at KEY_BANDS["inventory"]; anything below is real.
REAL_KEY_MAX = 9_000_000_000

ON_HAND_STATUSES = ("OK", "Hold", "Inspection Required", "HOLD FOR DESIGN ORDER")

COVER_FG = (0.25, 0.50)          # finished goods: weeks of own output on the shelf
COVER_WIP = (0.08, 0.30)         # blends, bright bottles, capsules, printed labels
COVER_PURCHASED = (0.8, 2.2)     # months of depletion held of bought-in stock
MAX_CONTAINERS = 40              # per part, per build
HOLD_P, INSPECT_P, DEFECT_P = 0.05, 0.30, 0.01

OOS_SHORT = (0.25, 0.80)         # on-hand as a share of demand, held-short parts
OOS_HEALTHY = (1.15, 1.50)       # stocked parts
MIN_DAYS = 14                    # Minimum_Inventory_Quantity = 2 weeks of usage

FG_COST_SHARE = 0.45             # fallback standard cost / lowest price
ROLL_UPLIFT = 0.03               # opening standard is 3% below the mid-year roll
OPENING_COST_DATE = dt.date(2025, 12, 29)

MOVED_P = 0.05                   # a count that finds a container moved elsewhere


def generate(sb):
    rng = random.Random(f"{sb.today}-inventory")
    ctx = _context(sb)

    cp_rows, cd_rows, usage = _cell_movements(sb, ctx)
    avail = _availability(sb)
    plan = _plan_containers(sb, rng, ctx, usage, avail)
    mins = _minimums(sb, ctx, usage, avail)

    containers = _container_rows(sb, rng, ctx, plan)
    _attach_depletion_serials(rng, ctx, cd_rows, containers)
    costs = _derive_costs(ctx, usage, containers)
    hist, snaps, ptrs = _valuation_rows(sb, ctx, costs, usage, containers)
    cycles = _cycle_rows(sb, rng, ctx, containers, costs)

    out = {
        T_CP: _append(sb, T_CP, cp_rows),
        T_CD: _append(sb, T_CD, cd_rows),
        T_CONT: _append(sb, T_CONT, containers),
        T_HIST: _append(sb, T_HIST, hist),
        T_SNAP: _append(sb, T_SNAP, snaps),
        T_PTR: _append(sb, T_PTR, ptrs),
        T_CYC: _append(sb, T_CYC, cycles),
    }
    _set_minimums(sb, ctx, mins)
    out["raw_Part_v_Part (Minimum_Inventory_Quantity)"] = len(mins)
    _report(sb, plan)
    return out


# ── reading the tenant ─────────────────────────────────────────────────────

def _context(sb):
    parts = {r["Part_Key"]: r for r in sb.query("""
        SELECT p.Part_Key, p.Part_No, p.Name, pt.Product_Type,
               p.Minimum_Inventory_Quantity AS mi
        FROM `{ds}.raw_Part_v_Part` p
        LEFT JOIN `{ds}.raw_Part_v_Part_Product_Type` pt
          ON SAFE_CAST(p.Product_Type_Key AS FLOAT64) = SAFE_CAST(pt.Product_Type_Key AS FLOAT64)""")}

    bom1 = {}                     # parent -> [(component, qty, parent op)]
    parents = {}                  # component -> [(parent, qty)]
    for r in sb.query("""
        SELECT SAFE_CAST(Part_Key AS INT64) p, SAFE_CAST(Component_Part_Key AS INT64) c,
               SAFE_CAST(Quantity AS FLOAT64) q, SAFE_CAST(Part_Operation_Key AS INT64) op
        FROM `{ds}.raw_Part_v_Flat_BOM` WHERE SAFE_CAST(BOM_Level AS INT64) = 1"""):
        if r["q"] and r["q"] > 0:
            bom1.setdefault(r["p"], []).append((r["c"], round(r["q"], 9), r["op"]))
            parents.setdefault(r["c"], []).append((r["p"], r["q"]))

    prod = sb.query("""
        SELECT Plexus_Customer_No, Production_No, Serial_No, Quantity, Part_Key,
               Part_Operation_Key, Workcenter_Key, Job_Op_Key,
               SAFE_CAST(Rejected AS INT64) AS Rejected,
               COALESCE(
                 DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(Record_Date AS STRING) AS INT64), 0), 1000))),
                 DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(Report_Date AS STRING) AS INT64), 0), 1000)))
               ) AS d
        FROM `{ds}.raw_Part_v_Production`
        WHERE SAFE_CAST(Quantity AS FLOAT64) > 0""")

    wc_loc = {r["Workcenter_Key"]: r["loc"] for r in sb.query("""
        SELECT Workcenter_Key, NULLIF(TRIM(Default_Production_Location), '') loc
        FROM `{ds}.raw_Part_v_Workcenter`""")}

    real_cont = [c for c in sb.templates(T_CONT) if (c["Container_Key"] or 0) < REAL_KEY_MAX]
    if not real_cont:
        raise RuntimeError("raw_Part_v_Container has no real row to clone")

    statuses = {r["s"].upper(): r["s"] for r in sb.query(
        "SELECT DISTINCT Container_Status s FROM `{ds}.raw_Part_v_Container_Status`"
        " WHERE Container_Status IS NOT NULL")} if _exists(sb, "raw_Part_v_Container_Status") else {}

    # A part's own operation: from its real containers, its production, the
    # BOM rows where it is the parent, its real cost history — in that order.
    ops = {}
    for c in real_cont:
        if c["Part_Operation_Key"]:
            ops.setdefault(c["Part_Key"], c["Part_Operation_Key"])
    for r in prod:
        if r["Part_Operation_Key"]:
            ops.setdefault(r["Part_Key"], r["Part_Operation_Key"])
    for p, rows in bom1.items():
        k = max((op for _, _, op in rows if op), default=None)
        if k:
            ops.setdefault(p, k)

    hist = [h for h in sb.templates(T_HIST) if (h["Change_key"] or 0) < REAL_KEY_MAX]
    for h in hist:
        if h["Part_Operation_Key"]:
            ops.setdefault(h["Part_Key"], h["Part_Operation_Key"])

    snaps = [s for s in sb.templates(T_SNAP) if (s["Snapshot_Key"] or 0) < REAL_KEY_MAX]
    cyc = [c for c in sb.templates(T_CYC) if (c["Cycle_Inventory_Key"] or 0) < REAL_KEY_MAX]

    price = {r["Part_Key"]: r["p"] for r in sb.query("""
        SELECT SAFE_CAST(cp.Part_Key AS INT64) Part_Key, MIN(SAFE_CAST(cpp.Price AS FLOAT64)) p
        FROM `{ds}.raw_Part_v_Customer_Part_Price` cpp
        JOIN `{ds}.raw_Part_v_Customer_Part` cp
          ON SAFE_CAST(cp.Customer_Part_Key AS INT64) = SAFE_CAST(cpp.Customer_Part_Key AS INT64)
        WHERE SAFE_CAST(cpp.Price AS FLOAT64) > 0
        GROUP BY 1""")}

    users = sorted({u for c in real_cont for u in (c["Add_By"], c["Update_By"]) if u}
                   | {u for c in cyc for u in (c["Start_By"], c["Complete_By"]) if u})

    return dict(parts=parts, bom1=bom1, parents=parents, prod=prod, wc_loc=wc_loc,
                real_cont=real_cont, statuses=statuses, ops=ops, hist=hist,
                snaps=snaps, cyc=cyc, price=price, users=users)


def _exists(sb, table):
    try:
        sb.client.get_table(f"{PROJECT}.{sb.ds}.{table}")
        return True
    except Exception:
        return False


def _fam(ctx, part_key):
    pn = (ctx["parts"].get(part_key) or {}).get("Part_No") or ""
    return pn[:1]


def _is_33(ctx, part_key):
    p = ctx["parts"].get(part_key) or {}
    return (p.get("Part_No") or "").startswith("33") and \
        not (p.get("Product_Type") or "").startswith("Custom")


# ── movements: Cell_Production / Cell_Depletion from the production log ────

def _cell_movements(sb, ctx):
    """One Cell_Production row per good production record; one Cell_Depletion
    row per (production record, level-1 component). Scrap (Rejected <> 0)
    consumed material too, so it depletes but does not produce."""
    cp_cols = {c: None for c in sb.schema(T_CP)}
    cd_cols = {c: None for c in sb.schema(T_CD)}
    cp_rows, cd_rows = [], []
    usage = {"prod": {}, "dep": {}, "first": {}, "wc": {}}   # part -> {date: qty}

    def add(kind, part, d, q):
        usage[kind].setdefault(part, {}).setdefault(d, 0.0)
        usage[kind][part][d] += q
        f = usage["first"].get(part)
        if f is None or d < f:
            usage["first"][part] = d

    for r in sorted(ctx["prod"], key=lambda r: (r["d"], r["Production_No"])):
        d, part, q = r["d"], r["Part_Key"], float(r["Quantity"])
        if d is None or d < PERIOD_START or d > sb.today:
            continue
        good = not r["Rejected"]
        cp_key = None
        if good:
            cp_key = sb.key("inventory")
            cp_rows.append(sb.clone(
                T_CP, cp_cols,
                PCN=r["Plexus_Customer_No"], Cell_Production_Key=cp_key, Part_Key=part,
                Part_Operation_Key=r["Part_Operation_Key"], Quantity=_num(q),
                Serial_No=r["Serial_No"], Production_No=r["Production_No"],
                Job_Op_Key=r["Job_Op_Key"], Production_Date=sb.when(T_CP, "Production_Date", d)))
            add("prod", part, d, q)
            if r["Workcenter_Key"]:
                usage["wc"].setdefault(part, {}).setdefault(r["Workcenter_Key"], 0.0)
                usage["wc"][part][r["Workcenter_Key"]] += q
        for comp, per, _op in ctx["bom1"].get(part, ()):
            dq = q * per
            if dq <= 0:
                continue
            cd_rows.append(sb.clone(
                T_CD, cd_cols,
                PCN=r["Plexus_Customer_No"], Cell_Depletion_Key=sb.key("inventory"),
                Cell_Production_Key=cp_key, Quantity=_num(dq), Part_Key=comp,
                Part_Operation_Key=r["Part_Operation_Key"], Production_No=r["Production_No"],
                Production_Date=sb.when(T_CD, "Production_Date", d)))
            add("dep", comp, d, dq)
    return cp_rows, cd_rows, usage


def _num(q):
    q = round(q, 6)
    return int(q) if q == int(q) else q


def _window(series, today, days):
    lo = today - dt.timedelta(days=days)
    return sum(q for d, q in (series or {}).items() if lo < d <= today)


# ── demand, from the tile's own SQL ────────────────────────────────────────

def _availability(sb):
    """inventory_available_to_sell_view.sql, run as a query with
    part_on_hand_inventory_view.sql inlined, so demand here is exactly the
    demand the tile will compute — including the Include_In_MRP gate and the
    BOM explosion."""
    def load(name):
        return (open(os.path.join(SQL_DIR, name), encoding="utf-8").read()
                .replace("{gcp_project}", PROJECT).replace("{dataset}", sb.ds))
    ats, oh = load("inventory_available_to_sell_view.sql"), load("part_on_hand_inventory_view.sql")
    ref = f"`{PROJECT}.{sb.ds}.part_on_hand_inventory_report`"
    if ref not in ats:
        raise RuntimeError("available-to-sell SQL no longer reads part_on_hand_inventory_report")
    ats = ats.replace(ref, "(\n" + oh + "\n)")
    rows = sb.client.query(
        "SELECT part_key, part_no, on_hand_qty, total_demand_qty, available_vs_total_demand,"
        " minimum_inventory_quantity, part_product_type FROM (\n" + ats + "\n)").result()
    return {r["part_key"]: dict(r.items()) for r in rows}


# ── the warehouse ──────────────────────────────────────────────────────────

def _plan_containers(sb, rng, ctx, usage, avail):
    """part -> dict(add=qty to put on the shelf, why=...)."""
    today = sb.today
    plan = {}
    real_oh = {k: (v["on_hand_qty"] or 0) for k, v in avail.items()}
    active = set(usage["prod"]) | set(usage["dep"])

    for part in sorted(active):
        if part not in ctx["parts"] or _is_33(ctx, part):
            continue
        p30 = _window(usage["prod"].get(part), today, 30)
        d30 = _window(usage["dep"].get(part), today, 30)
        if p30 > 0:
            cover = COVER_FG if _fam(ctx, part) == "9" else COVER_WIP
            target = p30 * rng.uniform(*cover)
            why = "produced"
        elif d30 > 0:
            target = d30 * rng.uniform(*COVER_PURCHASED)
            why = "purchased"
        else:
            continue
        add = target - real_oh.get(part, 0)
        if add > 0:
            plan[part] = dict(add=add, why=why)

    # The 33-parts: sized against open demand so the out-of-stock tile lands
    # on the scorecard's figure (or as close as the tenant's 33-parts allow).
    elig = sorted(k for k in ctx["parts"] if _is_33(ctx, k))
    demand = {k: (avail.get(k) or {}).get("total_demand_qty") or 0 for k in elig}
    with_demand = [k for k in elig if demand[k] > 0 and real_oh.get(k, 0) < demand[k]]
    rng.shuffle(with_demand)
    n_short = min(scale.OUT_OF_STOCK_PARTS, len(with_demand))
    short = set(with_demand[:n_short])
    zero_left = n_short < 3             # leave one short part with nothing, if >= 3
    for k in elig:
        p30 = _window(usage["prod"].get(k), today, 30)
        oh = real_oh.get(k, 0)
        if k in short:
            if not zero_left and oh == 0:
                zero_left = True
                plan[k] = dict(add=0, why="short-zero", demand=demand[k])
                continue
            target = demand[k] * rng.uniform(*OOS_SHORT)
            why = "short"
        elif demand[k] > 0:
            target = demand[k] * rng.uniform(*OOS_HEALTHY)
            why = "stocked"
        elif p30 > 0:
            target = p30 * rng.uniform(*COVER_WIP)
            why = "produced"
        else:
            continue
        plan[k] = dict(add=max(0.0, target - oh), why=why, demand=demand[k])
    plan["_summary"] = dict(eligible=len(elig), with_demand=len(with_demand) + sum(
        1 for k in elig if demand[k] > 0 and real_oh.get(k, 0) >= demand[k]),
        short=n_short, target=scale.OUT_OF_STOCK_PARTS)
    return plan


def _container_rows(sb, rng, ctx, plan):
    real = ctx["real_cont"]
    ok_real = [c for c in real if c["Active"] == 1 and c["Container_Status"] == "OK"] or real
    by_part, by_fam = {}, {}
    for c in ok_real:
        by_part.setdefault(c["Part_Key"], []).append(c)
        by_fam.setdefault(_fam(ctx, c["Part_Key"]), []).append(c)
    fam_locs = {}
    for c in real:
        if c["Location"]:
            fam_locs.setdefault(_fam(ctx, c["Part_Key"]), set()).add(c["Location"])
    bins = sorted({c["Location"] for c in real if c["Location"] and re.match(r"^\d{3}-", c["Location"])})
    fg_bins = sorted(l for l in fam_locs.get("9", ()) if re.match(r"^\d{3}-", l)) or bins
    dock = next((c["Location"] for c in real if (c["Location"] or "").lower() == "receiving dock"), None)
    st = ctx["statuses"]
    hold, insp, defect = st.get("HOLD", "Hold"), st.get("INSPECTION REQUIRED", "Inspection Required"), st.get("DEFECTIVE", "Defective")
    today = sb.today
    rows = []

    def med_size(part):
        own = [c["Quantity"] for c in by_part.get(part, ()) if (c["Quantity"] or 0) > 1]
        fam = [c["Quantity"] for c in by_fam.get(_fam(ctx, part), ()) if (c["Quantity"] or 0) > 1]
        allq = [c["Quantity"] for c in ok_real if (c["Quantity"] or 0) > 1]
        return statistics.median(own or fam or allq or [1000])

    for part, pl in sorted((k, v) for k, v in plan.items() if k != "_summary"):
        qty = pl["add"]
        if qty <= 0:
            continue
        fam = _fam(ctx, part)
        tmpl_pool = by_part.get(part) or by_fam.get(fam) or ok_real
        size = med_size(part)
        n = max(1, math.ceil(qty / size))
        if n > MAX_CONTAINERS:
            n, size = MAX_CONTAINERS, qty / MAX_CONTAINERS
        split = [size * rng.uniform(0.85, 1.15) for _ in range(n)]
        scale_ = qty / sum(split)
        prod_days = _prod_days(ctx, part)
        produced = bool(prod_days) and pl["why"] != "purchased"
        for i, q in enumerate(split):
            q = q * scale_
            q = round(q) if q >= 50 else round(q, 2)
            if q <= 0:
                continue
            t = rng.choice(tmpl_pool)
            if produced:
                d = rng.choice(prod_days[-25:])
                wloc = _wc_location(ctx, part)
                if wloc and rng.random() < 0.45:
                    loc = wloc
                else:
                    loc = rng.choice(fg_bins if fam == "9" else sorted(fam_locs.get(fam, ())) or bins)
                status = hold if fam == "9" and rng.random() < HOLD_P else "OK"
            else:
                d = today - dt.timedelta(days=rng.randint(0, 45))
                while d.weekday() >= 5:
                    d -= dt.timedelta(days=1)
                if dock and (today - d).days <= 7:
                    loc = dock
                    status = insp if rng.random() < INSPECT_P else "OK"
                else:
                    loc = rng.choice(sorted(fam_locs.get(fam, ())) or bins)
                    status = "OK"
            if rng.random() < DEFECT_P:
                status = defect
            when = dt.datetime(d.year, d.month, d.day, tzinfo=UTC) + dt.timedelta(
                hours=rng.uniform(12, 21))
            key = sb.key("inventory")
            ratio = (t["Net_Weight"] / t["Quantity"]) if t["Quantity"] and t["Net_Weight"] else 1.0
            tare = t["Tare_Weight"] or 0.0
            rows.append(sb.clone(
                T_CONT, t,
                Container_Key=key, Serial_No=f"S{TAG}{key % 10_000_000:07d}",
                Part_Key=part, Part_Operation_Key=ctx["ops"].get(part),
                Location=loc, Container_Status=status, Active=1,
                Quantity=float(q), Net_Weight=float(q) * ratio, Gross_Weight=float(q) * ratio + tare,
                Add_Date=sb.when(T_CONT, "Add_Date", when),
                Update_Date=sb.when(T_CONT, "Update_Date", when),
                Moved_To_Workcenter=sb.when(T_CONT, "Moved_To_Workcenter", when),
                Lot_Key=float(sb.key("inventory")),
                Job_Key=None, Job_Op_Key=None))
    return rows


def _prod_days(ctx, part):
    cache = ctx.setdefault("_pdays", {})
    if part not in cache:
        cache[part] = sorted({r["d"] for r in ctx["prod"]
                              if r["Part_Key"] == part and not r["Rejected"] and r["d"]})
    return cache[part]


def _wc_location(ctx, part):
    cache = ctx.setdefault("_wcloc", {})
    if part not in cache:
        tot = {}
        for r in ctx["prod"]:
            if r["Part_Key"] == part and r["Workcenter_Key"]:
                tot[r["Workcenter_Key"]] = tot.get(r["Workcenter_Key"], 0) + 1
        locs = [ctx["wc_loc"].get(w) for w in sorted(tot, key=tot.get, reverse=True)]
        cache[part] = next((l for l in locs if l), None)
    return cache[part]


def _attach_depletion_serials(rng, ctx, cd_rows, containers):
    """A depletion consumes a container of the component: point each row at
    a real or sandbox container of that part, where one exists."""
    serials = {}
    for c in list(ctx["real_cont"]) + containers:
        if c["Serial_No"]:
            serials.setdefault(str(c["Part_Key"]), []).append(c["Serial_No"])
    for r in cd_rows:
        pool = serials.get(str(r["Part_Key"]))
        if pool:
            r["Serial_No"] = rng.choice(pool)


# ── minimum inventory quantity on the 33-parts ─────────────────────────────

def _source_part_table():
    """PlexTest's part master at the instant the sandbox was copied from
    (build.SNAPSHOT), so a reset restores exactly what the copy brought in."""
    try:
        from build import SNAPSHOT
        return f"`{PROJECT}.PlexTest.raw_Part_v_Part` FOR SYSTEM_TIME AS OF TIMESTAMP '{SNAPSHOT}'"
    except Exception:
        return f"`{PROJECT}.PlexTest.raw_Part_v_Part`"


def _minimums(sb, ctx, usage, avail):
    src = {r["Part_Key"]: r["mi"] for r in sb.query(
        f"SELECT Part_Key, Minimum_Inventory_Quantity mi FROM {_source_part_table()} "
        "WHERE STARTS_WITH(Part_No, '33')")}
    lo = sb.today - dt.timedelta(days=90)
    first = max(lo, PERIOD_START)
    days = max(1, (sb.today - first).days)
    out = {}
    for k in sorted(ctx["parts"]):
        if not _is_33(ctx, k):
            continue
        real = src.get(k, ctx["parts"][k]["mi"]) or 0
        if real > 0:
            continue                       # Plex already has one: leave it
        dep = _window(usage["dep"].get(k), sb.today, 90)
        dem = (avail.get(k) or {}).get("total_demand_qty") or 0
        if dep > 0:
            out[k] = max(10_000, round(dep / days * MIN_DAYS, -4))
        elif dem > 0:
            out[k] = max(10_000, round(dem * 0.25, -4))
    return out


def _set_minimums(sb, ctx, mins):
    """Idempotent: every 33-part's value is first put back to PlexTest's,
    then the derived one written, in one statement."""
    keys = sorted(k for k in ctx["parts"] if (ctx["parts"][k]["Part_No"] or "").startswith("33"))
    if not keys:
        return
    cases = " ".join(f"WHEN {int(k)} THEN {float(v)!r}" for k, v in mins.items())
    sb.exec(f"""
        UPDATE `{{ds}}.raw_Part_v_Part` p
        SET Minimum_Inventory_Quantity = CASE p.Part_Key {cases or 'WHEN -1 THEN NULL'}
                                         ELSE src.Minimum_Inventory_Quantity END
        FROM (SELECT Part_Key, Minimum_Inventory_Quantity FROM {_source_part_table()}) src
        WHERE p.Part_Key = src.Part_Key AND p.Part_Key IN ({", ".join(str(int(k)) for k in keys)})""")


# ── standard costs ─────────────────────────────────────────────────────────

def _latest_real_costs(ctx):
    """part -> {sub_type: cost}: the latest real cost per (part, sub-type)."""
    best = {}
    for h in ctx["hist"]:
        k = (h["Part_Key"], h["Cost_Sub_Type_Key"])
        if k not in best or str(h["Change_Date"]) > str(best[k]["Change_Date"]):
            best[k] = h
    out = {}
    for (p, s), h in best.items():
        out.setdefault(p, {})[s] = float(h["Cost"] or 0)
    return out


def _derive_costs(ctx, usage, containers):
    real = _latest_real_costs(ctx)
    real_tot = {p: sum(v.values()) for p, v in real.items() if sum(v.values()) > 0}
    subs = sorted({s for v in real.values() for s in v})
    share = {s: statistics.median([v.get(s, 0) / sum(v.values()) for v in real.values()
                                   if sum(v.values()) > 0]) for s in subs}
    norm = sum(share.values()) or 1
    share = {s: x / norm for s, x in share.items()}

    fam_anchor = {}
    for p, c in real_tot.items():
        fam_anchor.setdefault(_fam(ctx, p), []).append(c)
    fam_anchor = {f: statistics.median(v) for f, v in fam_anchor.items()}

    ratios = [real_tot[p] / ctx["price"][p] for p in real_tot
              if _fam(ctx, p) == "9" and ctx["price"].get(p)]
    f_real = statistics.median(ratios) if ratios else None
    F = f_real if f_real and 0.20 <= f_real <= 0.80 else FG_COST_SHARE

    pairs = []
    for p9, c9 in real_tot.items():
        if _fam(ctx, p9) != "9":
            continue
        for comp, _q, _op in ctx["bom1"].get(p9, ()):
            if _fam(ctx, comp) == "5" and comp in real_tot:
                pairs.append(real_tot[comp] / c9)
    r59 = statistics.median(pairs) if pairs else None

    # Costed: what physically exists or moves — real and sandbox containers,
    # produced and consumed parts — plus every part Plex has really costed.
    costed = set(ctx["parts"]) & (
        {c["Part_Key"] for c in ctx["real_cont"]} | {c["Part_Key"] for c in containers}
        | set(usage["prod"]) | set(usage["dep"]) | set(real_tot))
    cost = dict(real_tot)
    for p in sorted(costed):
        if p in cost:
            continue
        f = _fam(ctx, p)
        if f == "9":
            pr = ctx["price"].get(p)
            v = F * pr if pr else fam_anchor.get("9")
            if v:
                cost[p] = v
    for p in sorted(costed):
        if p in cost or _fam(ctx, p) != "5":
            continue
        par = [cost[q] for q, _ in ctx["parents"].get(p, ()) if q in cost and _fam(ctx, q) == "9"]
        v = (r59 * min(par)) if (r59 and par) else fam_anchor.get("5")
        if v:
            cost[p] = v
    for p in sorted(costed):
        if p not in cost and _fam(ctx, p) in ("3", "2", "7") and fam_anchor.get(_fam(ctx, p)):
            cost[p] = fam_anchor[_fam(ctx, p)]

    # Packaging: residual of real-costed parents over their non-packaging parts.
    def is_pack(comp, qty):
        return _fam(ctx, comp) == "1" and qty >= 0.999
    pack = {}
    for par, c in real_tot.items():
        comps = ctx["bom1"].get(par, ())
        packs = [comp for comp, q, _ in comps if is_pack(comp, q)]
        if not packs:
            continue
        other = [(comp, q) for comp, q, _ in comps if not is_pack(comp, q)]
        if any(comp not in cost for comp, _ in other):
            continue
        resid = c - sum(q * cost[comp] for comp, q in other)
        if resid > 0:
            for comp in packs:
                pack.setdefault(comp, []).append(resid / len(packs))
    pack = {k: statistics.median(v) for k, v in pack.items()}
    by_type = {}
    for k, v in pack.items():
        by_type.setdefault(ctx["parts"][k]["Product_Type"], []).append(v)
    by_type = {t: statistics.median(v) for t, v in by_type.items()}
    pack_all = statistics.median(pack.values()) if pack else None
    pack_parts = {comp for rows in ctx["bom1"].values() for comp, q, _ in rows if is_pack(comp, q)}
    blend = fam_anchor.get("2")
    for p in sorted(costed):
        if p in cost or _fam(ctx, p) != "1":
            continue
        if p in pack_parts:
            v = pack.get(p) or by_type.get(ctx["parts"][p]["Product_Type"]) or pack_all
        else:
            v = blend
        if v:
            cost[p] = v
    ctx["_cost_meta"] = dict(F=F, f_real=f_real, r59=r59, share=share, anchors=fam_anchor,
                             packaging=pack_all, blend=blend)
    return dict(unit=cost, share=share, real=set(real_tot))


def _valuation_rows(sb, ctx, costs, usage, containers):
    if not ctx["hist"] or not ctx["snaps"]:
        print("  ! no real cost history / snapshot row to clone — valuation skipped")
        return [], [], []
    tmpl_h = sorted(ctx["hist"], key=lambda h: h["Change_key"])[0]
    tmpl_s = ctx["snaps"][0]
    roll_dates = {}
    for h in ctx["hist"]:
        d = _as_date(h["Change_Date"])
        roll_dates[d] = roll_dates.get(d, 0) + 1
    roll = max(roll_dates, key=lambda d: (roll_dates[d], -d.toordinal()))

    first = dict(usage["first"])
    for c in containers:
        d = _ns_date(c["Add_Date"])
        if d and (c["Part_Key"] not in first or d < first[c["Part_Key"]]):
            first[c["Part_Key"]] = d

    hist = []
    for p in sorted(costs["unit"]):
        op = ctx["ops"].get(p)
        if not op:
            continue
        unit = costs["unit"][p]
        f = first.get(p)
        opening = OPENING_COST_DATE if (f is None or f <= PERIOD_START + dt.timedelta(days=14)) \
            else f - dt.timedelta(days=3)
        steps = []
        if opening < roll:
            steps.append((opening, unit / (1 + ROLL_UPLIFT)))
        if p not in costs["real"]:
            steps.append((max(roll, opening), unit))
        for d, u in steps:
            at = dt.datetime(d.year, d.month, d.day, 6, 32, 44, tzinfo=UTC)
            for s, sh in sorted(costs["share"].items()):
                hist.append(sb.clone(
                    T_HIST, tmpl_h, Change_key=sb.key("inventory"), Part_Key=p,
                    Part_Operation_Key=op, Cost_Sub_Type_Key=s,
                    Change_Date=sb.when(T_HIST, "Change_Date", at), Cost=round(u * sh, 7)))

    everything = [dict(h, _d=_as_date(h["Change_Date"])) for h in ctx["hist"]] + \
                 [dict(h, _d=_as_date(h["Change_Date"])) for h in hist]
    real_snap_date = _ns_date(tmpl_s["Snapshot_Date"])
    snaps, ptrs = [], []
    m = PERIOD_START.replace(day=1)
    while m <= sb.today:
        if m == real_snap_date:
            s_key = tmpl_s["Snapshot_Key"]
        else:
            s_key = sb.key("inventory")
            at = dt.datetime(m.year, m.month, m.day, tzinfo=UTC)
            snaps.append(sb.clone(
                T_SNAP, tmpl_s, Snapshot_Key=s_key,
                Snapshot_Date=sb.when(T_SNAP, "Snapshot_Date", at),
                Insert_Date=sb.when(T_SNAP, "Insert_Date", at + dt.timedelta(hours=2)),
                Completed_Date=sb.when(T_SNAP, "Completed_Date", at + dt.timedelta(hours=2, seconds=1)),
                Last_Hit_Date=sb.when(T_SNAP, "Last_Hit_Date", at + dt.timedelta(hours=2))))
        latest = {}
        for h in everything:
            if h["_d"] and h["_d"] <= m:
                k = (h["Part_Key"], h["Part_Operation_Key"], h["Cost_Sub_Type_Key"])
                if k not in latest or (h["_d"], h["Change_key"]) > (latest[k]["_d"], latest[k]["Change_key"]):
                    latest[k] = h
        for h in sorted(latest.values(), key=lambda h: h["Change_key"]):
            ptrs.append({"PCN": sb.val(T_PTR, "PCN", tmpl_s["PCN"]),
                         "Snapshot_Key": sb.val(T_PTR, "Snapshot_Key", s_key),
                         "Change_Key": sb.val(T_PTR, "Change_Key", h["Change_key"])})
        m = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return hist, snaps, ptrs


def _as_date(v):
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, int):
        return _ns_date(v)
    return dt.date.fromisoformat(str(v)[:10])


def _ns_date(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return dt.datetime.fromtimestamp(v / 1e9, UTC).date()
    return dt.date.fromisoformat(str(v)[:10])


# ── cycle counts ───────────────────────────────────────────────────────────

def _cycle_rows(sb, rng, ctx, containers, costs):
    if not ctx["cyc"]:
        print("  ! no real Part_v_Cycle_Inventory row to clone — cycle counts skipped")
        return []
    tmpl = ctx["cyc"][0]
    on_hand = [c for c in list(ctx["real_cont"]) + containers
               if c["Active"] == 1 and (c["Container_Status"] or "").upper()
               in {s.upper() for s in ON_HAND_STATUSES} and c["Location"]]
    at_loc = {}
    for c in on_hand:
        at_loc.setdefault(c["Location"], []).append(c)
    locs = sorted(at_loc)
    if not locs:
        return []
    # One stable key per real location code (the column is INT64 here).
    loc_key = {l: sb.key("inventory") for l in locs}
    weight = [3 if re.match(r"^\d{3}-", l) or l.lower().startswith("rack") else 1 for l in locs]
    counters = ctx["users"] or [tmpl["Start_By"]]

    months = []
    m = PERIOD_START.replace(day=1)
    while m <= sb.today:
        months.append(m)
        m = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    quiet = rng.choice(months[1:-1]) if len(months) > 2 else None

    events = []
    for m in months:
        end = min((m.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1),
                  sb.today - dt.timedelta(days=1))
        days = [m + dt.timedelta(days=i) for i in range((end - m).days + 1)]
        days = [d for d in days if d.weekday() < 5]
        if not days or m == quiet:
            continue
        n = rng.randint(*scale.CYCLE_COUNTS_PER_MONTH)
        if m.year == sb.today.year and m.month == sb.today.month:
            n = round(n * (sb.today.day - 1) / 30)
        # Counting is lumpy: a few blitz days carry most of the month.
        blitz = rng.sample(days, min(len(days), rng.randint(2, 5)))
        month_counters = rng.sample(counters, min(len(counters), rng.randint(1, 3)))
        for _ in range(n):
            d = rng.choice(blitz) if rng.random() < 0.75 else rng.choice(days)
            events.append((d, rng.choices(locs, weights=weight, k=1)[0], rng.choice(month_counters)))
    events.sort()
    misses = set(rng.sample(range(len(events)), round(len(events) * (1 - scale.CYCLE_ACCURACY))))

    unit = costs["unit"]
    rows = []
    for i, (d, loc, who) in enumerate(events):
        here = at_loc[loc]
        acc = max(1, round(len(here) * rng.uniform(0.8, 1.2)))
        per_qty = sum(c["Quantity"] or 0 for c in here) / len(here)
        per_cost = sum((c["Quantity"] or 0) * unit.get(c["Part_Key"], 0) for c in here) / len(here)
        un = 1 if i in misses else 0
        mv = 1 if rng.random() < MOVED_P else 0
        acc_q, un_q, mv_q = acc * per_qty, un * per_qty, mv * per_qty
        acc_c, un_c, mv_c = acc * per_cost, un * per_cost, mv * per_cost
        start = dt.datetime(d.year, d.month, d.day, tzinfo=UTC) + dt.timedelta(hours=rng.uniform(12.5, 20))
        done = start + dt.timedelta(minutes=rng.randint(6, 55))
        added = start - dt.timedelta(days=rng.randint(1, 6))
        key = sb.key("inventory")
        rows.append(sb.clone(
            T_CYC, tmpl, Cycle_Inventory_Key=key, Location=loc_key[loc], Location_Key=loc_key[loc],
            Accuracy=_pct(acc, un), Accounted_For=acc, Moved=mv, Unaccounted_For=un,
            Cycle_Inventory_Date=sb.when(T_CYC, "Cycle_Inventory_Date", done),
            Cycle_Inventory_By=who, Start_By=who, Complete_By=who, Complete=1,
            Accuracy_Quantity=_pct(acc_q, un_q), Accounted_For_Quantity=round(acc_q, 4),
            Moved_Quantity=round(mv_q, 4), Unaccounted_For_Quantity=round(un_q, 4),
            Accuracy_Cost=_pct(acc_c, un_c), Accounted_For_Cost=round(acc_c, 4),
            Moved_Cost=round(mv_c, 4), Unaccounted_For_Cost=round(un_c, 4),
            Accounted_For_Cycle_Quantity=round(acc_q, 4), Accounted_For_Cycle_Cost=round(acc_c, 4),
            Cycle_Variance_Quantity=round(-un_q, 4), Cycle_Variance_Cost=round(-un_c, 4),
            Start_Date=sb.when(T_CYC, "Start_Date", start),
            Complete_Date=sb.when(T_CYC, "Complete_Date", done),
            Add_Date=sb.when(T_CYC, "Add_Date", added),
            Cycle_Inventory_No=f"{TAG}{i + 1:05d}"))
    return rows


def _pct(ok, bad):
    return 100.0 if ok + bad == 0 else round(100.0 * ok / (ok + bad), 4)


# ── write / report ─────────────────────────────────────────────────────────

def _append(sb, table, rows, chunk=40_000):
    n = 0
    for i in range(0, len(rows), chunk):
        n += sb.append(table, rows[i:i + chunk])
    return n


def _report(sb, plan):
    """Re-read availability through the tile's own SQL, after the writes, and
    apply inventory_out_of_stock_view.sql's rule — the count the tile shows."""
    s = plan.get("_summary", {})
    oos = [r for r in _availability(sb).values()
           if (r["part_no"] or "").startswith("33")
           and (r["minimum_inventory_quantity"] or 0) > 0
           and (r["available_vs_total_demand"] or 0) < 0
           and not (r["part_product_type"] or "").startswith("Custom")]
    print(f"  33-parts eligible {s.get('eligible')}, with demand {s.get('with_demand')}, "
          f"held short {s.get('short')}; out of stock now {len(oos)} "
          f"(scorecard: {s.get('target')})")
    return len(oos)
