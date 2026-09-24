"""
Sales, shipping and revenue — one order book that every Sales and Revenue tile
reads from, so the tiles agree with each other the way they will for real:
a sale is booked, sits in WIP, goes into shipping, ships and is invoiced, and
the same dollars appear on each tile at the right moment.

WHO SELLS TO WHOM is Plex's own data. Every customer's account rep is its real
`Common_v_Customer.Assigned_To`; customers with no account rep (or one outside
the Inside Sales roster) are shared out to the reps who have none, and the rep
is then written on the ORDER in `Sales_v_PO.Inside_Sales` — which is where Vox
actually records it (label_design_view.sql, 2026-09-24). `Order_Salesperson`
is left as Plex has it: nearly empty. A sales view that reads only that table
therefore shows "(no rep assigned)" here, exactly as it would in production.

WHAT IS SOLD is real customer parts at their real list prices
(`Part_v_Customer_Part` + `Part_v_Customer_Part_Price`). Quantities are the
line value divided by that price.

HOW MUCH is each rep's real goal times an attainment draw (scale.py); months a
rep has no goal use their average share of the company-wide goal; reps with no
goal at all share what is left of the company goal — the "turnover gap"
between $5.04M company-wide and $4.69M across reps. Orders start mid-November
2025 so January's revenue has December's bookings behind it.

LIFECYCLE, all through the real status keys:
  Pending Sales Approval (2585) -> Pending Fulfillment (2073, the SALE date)
  -> shipped in one or two shipments -> Closed (2074).
  Some sit on Hold (2075); a few are Cancelled (2076); the open order book also
  holds Deposit Review orders, fresh Pending Sales Approval orders and Quotes.
"""

import datetime as dt
import math
import random

import scale
from common import TAG, workdays

ST = dict(pending_fulfillment=2073, closed=2074, hold=2075, cancelled=2076,
          pending_approval=2585, deposit_initiate=2587, deposit_bypass=2656,
          quote=2653)
REL = dict(open=3016, closed=3018, scheduled=3020, canceled=3015, hold=3017)
SHIP = dict(shipped=1792, open=1791, pending=1794)
TYPE = dict(blanket=2941, spot=2942)

ORDERS_FROM = dt.date(2025, 11, 17)
AVG_ORDER = 38_000          # ≈ 130 orders a month at Vox's ~$4.9M
UNITS_PER_CONTAINER = 600   # what the real test shipment packed per container


def _one(sb, table, where="TRUE"):
    rows = sb.templates(table, where, limit=1)
    if not rows:
        raise RuntimeError(f"no template row in {table} where {where}")
    return rows[0]


def generate(sb):
    rng = random.Random(f"{sb.today}-sales")
    today = sb.today

    # ── master data ────────────────────────────────────────────────────
    reps = {r["plexus_user_no"]: r["sales_rep"] for r in sb.query(
        "SELECT plexus_user_no, sales_rep FROM `voxdatalake.PlexTest.sales_reps_report`")}
    customers = sb.query(
        "SELECT Customer_No, Name, SAFE_CAST(Assigned_To AS INT64) AS rep "
        "FROM `{ds}.raw_Common_v_Customer` ORDER BY Customer_No")
    cparts = sb.query("""
        WITH bp AS (
          SELECT Customer_Part_Key, Price,
                 ROW_NUMBER() OVER (PARTITION BY Customer_Part_Key
                                    ORDER BY SAFE_CAST(Breakpoint_Quantity AS FLOAT64)) rn
          FROM `{ds}.raw_Part_v_Customer_Part_Price`)
        SELECT cp.Customer_No, cp.Customer_Part_Key, cp.Part_Key,
               SAFE_CAST(bp.Price AS FLOAT64) AS price
        FROM `{ds}.raw_Part_v_Customer_Part` cp
        JOIN bp ON SAFE_CAST(bp.Customer_Part_Key AS INT64) = SAFE_CAST(cp.Customer_Part_Key AS INT64)
               AND bp.rn = 1
        JOIN `{ds}.raw_Part_v_Part` p ON SAFE_CAST(p.Part_Key AS INT64) = SAFE_CAST(cp.Part_Key AS INT64)
        WHERE SAFE_CAST(bp.Price AS FLOAT64) > 0 AND COALESCE(SAFE_CAST(cp.Active AS INT64), 1) = 1
    """)
    if not cparts:
        raise RuntimeError("no priced customer parts that join to a real part — "
                           "the raw tables are out of step; re-extract PlexTest first")
    parts_of = {}
    for cp in cparts:
        parts_of.setdefault(cp["Customer_No"], []).append(cp)
    customers = [c for c in customers if c["Customer_No"] in parts_of]

    # ── rep books ──────────────────────────────────────────────────────
    book = {r: [] for r in reps}
    pool = []
    for c in customers:
        (book[c["rep"]] if c["rep"] in book else pool).append(c)
    unassigned_customer = pool[-1] if pool else None   # orders with no rep at all
    bookless = [r for r in reps if not book[r]]
    for i, c in enumerate(pool[:-1] if len(pool) > 1 else pool):
        if bookless:
            book[bookless[i % len(bookless)]].append(c)
    book = {r: cs for r, cs in book.items() if cs}

    # ── targets per rep-month ──────────────────────────────────────────
    company = {r["period_month"]: float(r["goal_value"]) for r in sb.query(
        "SELECT period_month, goal_value FROM `{ds}.scorecard_goals_resolved` "
        "WHERE metric = 'sales' AND (scope IS NULL OR scope = '')")}
    rep_goal = {}
    for r in sb.query("SELECT scope, period_month, goal_value FROM `{ds}.scorecard_goals_resolved` "
                      "WHERE metric = 'sales' AND scope IS NOT NULL AND scope != ''"):
        rep_goal[(r["scope"], r["period_month"])] = float(r["goal_value"])
    share = {}
    for name in {s for s, _ in rep_goal}:
        ratios = [v / company[m] for (s, m), v in rep_goal.items() if s == name and company.get(m)]
        share[name] = sum(ratios) / len(ratios) if ratios else 0

    def months():
        m = ORDERS_FROM.replace(day=1)
        while m <= today:
            yield m
            m = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)

    first_goal_month = min(company)
    targets = []   # (month, rep_no or None, dollars)
    for m in months():
        G = company.get(m) or company[first_goal_month]
        month_factor = rng.uniform(0.92, 1.06)
        # The month in progress only gets the days that have happened — a
        # full month's bookings crammed into 17 days read as 126% to goal.
        if m.year == today.year and m.month == today.month:
            elapsed = len([d for d in workdays(sb, m) if d < today])
            month_factor *= elapsed / max(len([d for d in sb.days(m, (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)) if d.weekday() < 5]), 1)
        # November 2025 starts mid-month.
        if m == ORDERS_FROM.replace(day=1):
            month_factor *= 0.45
        goal_reps = {}
        for rep_no, name in reps.items():
            if rep_no in book and name in share:
                goal_reps[rep_no] = rep_goal.get((name, m), share[name] * G)
        rest = max(G * (1 - scale.UNASSIGNED_SHARE) - sum(goal_reps.values()), 0.04 * G)
        others = [r for r in book if r not in goal_reps]
        for rep_no, base in goal_reps.items():
            targets.append((m, rep_no, base * month_factor * rng.uniform(*scale.REP_ATTAINMENT)))
        for rep_no in others:
            targets.append((m, rep_no, rest / max(len(others), 1) * month_factor * rng.uniform(0.7, 1.3)))
        if unassigned_customer:
            targets.append((m, None, G * scale.UNASSIGNED_SHARE * month_factor))

    # ── templates ──────────────────────────────────────────────────────
    t_po = _one(sb, "raw_Sales_v_PO", "SAFE_CAST(PO_Status_Key AS INT64) = 2073")
    t_ch = _one(sb, "raw_Sales_v_PO_Change")
    t_pl = _one(sb, "raw_Sales_v_PO_Line")
    t_rel = _one(sb, "raw_Sales_v_Release")
    t_pr = _one(sb, "raw_Sales_v_Price")
    t_sh = _one(sb, "raw_Sales_v_Shipper")
    t_sl = _one(sb, "raw_Sales_v_Shipper_Line")
    t_slr = _one(sb, "raw_Sales_v_Shipper_Line_Release")
    t_sc = _one(sb, "raw_Sales_v_Shipper_Container")
    t_inv = _one(sb, "raw_Sales_v_Shipper_AR_Invoice")

    out = {k: [] for k in ("raw_Sales_v_PO", "raw_Sales_v_PO_Change", "raw_Sales_v_PO_Line",
                           "raw_Sales_v_Release", "raw_Sales_v_Price", "raw_Sales_v_Shipper",
                           "raw_Sales_v_Shipper_Line", "raw_Sales_v_Shipper_Line_Release",
                           "raw_Sales_v_Shipper_Container", "raw_Sales_v_Shipper_AR_Invoice")}
    W = lambda t, c, d, h=12: sb.when(t, c, d, h)
    n_order = [0]
    n_ship = [0]

    def workday(d):
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        return d

    def change(po_key, po_no, cust, status, when, po_date):
        out["raw_Sales_v_PO_Change"].append(sb.clone("raw_Sales_v_PO_Change", t_ch,
            PO_Key=po_key, Change_Key=sb.key("sales"), Change_Date=W("raw_Sales_v_PO_Change", "Change_Date", when, 15),
            PO_No=po_no, Customer_No=cust, PO_Status_Key=status,
            PO_Date=W("raw_Sales_v_PO_Change", "PO_Date", po_date),
            Add_Date=W("raw_Sales_v_PO_Change", "Add_Date", po_date)))

    def shipment(cust_no, lines, ship_date, status):
        """lines: [(customer_part, qty, price, release_key, price_key)]"""
        n_ship[0] += 1
        sk = sb.key("shipping")
        shipped = status == SHIP["shipped"]
        out["raw_Sales_v_Shipper"].append(sb.clone("raw_Sales_v_Shipper", t_sh,
            Shipper_Key=sk, Shipper_No=f"{TAG}-SH{n_ship[0]:05d}", Master_BOL_No=f"{TAG}-SH{n_ship[0]:05d}",
            Customer_No=cust_no, Shipper_Status_Key=status,
            Ship_Date=W("raw_Sales_v_Shipper", "Ship_Date", ship_date, 16) if shipped else None,
            Scheduled_Ship_Date=W("raw_Sales_v_Shipper", "Scheduled_Ship_Date", ship_date),
            Add_Date=W("raw_Sales_v_Shipper", "Add_Date", ship_date - dt.timedelta(days=2)),
            Updated_Date=W("raw_Sales_v_Shipper", "Updated_Date", ship_date),
            Delivery_Date=W("raw_Sales_v_Shipper", "Delivery_Date", ship_date + dt.timedelta(days=5)),
            Note=f"{TAG} sandbox shipment"))
        for cp, qty, price, rel_key, price_key in lines:
            lk = sb.key("shipping")
            out["raw_Sales_v_Shipper_Line"].append(sb.clone("raw_Sales_v_Shipper_Line", t_sl,
                Shipper_Line_Key=lk, Shipper_Key=sk, Part_Key=cp["Part_Key"], Quantity=qty,
                Release_Key=rel_key, Price=price, Shipment_Price=0.0,
                Customer_Part_Key=cp["Customer_Part_Key"], Price_Key=price_key))
            out["raw_Sales_v_Shipper_Line_Release"].append(sb.clone(
                "raw_Sales_v_Shipper_Line_Release", t_slr, Shipper_Line_Key=lk, Release_Key=rel_key))
            loaded = dt.datetime(ship_date.year, ship_date.month, ship_date.day, 10)
            for c in range(max(1, math.ceil(qty / UNITS_PER_CONTAINER))):
                out["raw_Sales_v_Shipper_Container"].append(sb.clone(
                    "raw_Sales_v_Shipper_Container", t_sc,
                    Shipper_Line_Key=lk, Serial_No=f"{TAG}{lk % 10_000_000:07d}{c:03d}",
                    Release_Key=rel_key, Quantity=min(UNITS_PER_CONTAINER, qty),
                    Loaded_Date=loaded.isoformat(sep=" "), Shipper_Container_Key=sb.key("shipping")))
            if shipped:
                inv_day = ship_date + dt.timedelta(days=rng.choice([0, 0, 1, 2]))
                out["raw_Sales_v_Shipper_AR_Invoice"].append(sb.clone(
                    "raw_Sales_v_Shipper_AR_Invoice", t_inv, Shipper_Key=sk, Shipper_Line_Key=lk,
                    Invoice_Line_Item_No=sb.key("shipping"), Release_Key=rel_key,
                    Add_Date=W("raw_Sales_v_Shipper_AR_Invoice", "Add_Date", inv_day, 18)))

    def order(customer, rep_no, value, po_date, fate, sale_date=None):
        """fate: 'sold' | 'pending_approval' | 'deposit' | 'quote' | 'cancelled_early'"""
        n_order[0] += 1
        po_key = sb.key("sales")
        po_no = f"{TAG}-{n_order[0]:05d}"
        cust = customer["Customer_No"]
        cps = parts_of[cust]
        n_lines = rng.randint(*scale.LINES_PER_ORDER)
        picks = rng.sample(cps, min(n_lines, len(cps)))
        weights = [rng.uniform(0.5, 1.5) for _ in picks]
        lines = []
        for cp, w in zip(picks, weights):
            qty = max(500.0, round(value * w / sum(weights) / cp["price"] / 250) * 250)
            lines.append(dict(cp=cp, qty=qty, pl=sb.key("sales"), rel=sb.key("sales"), pk=sb.key("sales")))

        status = {"pending_approval": ST["pending_approval"], "quote": ST["quote"],
                  "cancelled_early": ST["cancelled"],
                  "deposit": rng.choice([ST["deposit_initiate"], ST["deposit_bypass"]])}.get(fate)
        change(po_key, po_no, cust, ST["quote"] if fate == "quote" else ST["pending_approval"], po_date, po_date)

        rel_state = {}
        if fate == "sold":
            change(po_key, po_no, cust, ST["pending_fulfillment"], sale_date, po_date)
            lag = rng.triangular(*scale.SHIP_LAG_DAYS)
            first = workday(sale_date + dt.timedelta(days=round(lag)))
            split = rng.random() < 0.18
            second = workday(first + dt.timedelta(days=rng.randint(5, 15))) if split else None
            hold = rng.random() < 0.05 and first > today
            cancel_late = rng.random() < 0.004
            shipped_all = True
            for ln in lines:
                parts = [(first, ln["qty"] * (0.6 if split else 1.0))]
                if split:
                    parts.append((second, ln["qty"] * 0.4))
                done = 0.0
                for d, q in parts:
                    q = round(q)
                    if cancel_late or hold:
                        continue
                    if d < today:
                        shipment(cust, [(ln["cp"], q, ln["cp"]["price"], ln["rel"], ln["pk"])], d, SHIP["shipped"])
                        done += q
                    elif d <= today + dt.timedelta(days=scale.IN_SHIPPING_DAYS):
                        # Packed and on the dock, not yet gone: "Total in Shipping".
                        shipment(cust, [(ln["cp"], q, ln["cp"]["price"], ln["rel"], ln["pk"])], d,
                                 rng.choice([SHIP["open"], SHIP["pending"]]))
                rel_state[ln["rel"]] = (done, parts[-1][0])
                if done < ln["qty"] - 1:
                    shipped_all = False
            if cancel_late:
                status = ST["cancelled"]
                change(po_key, po_no, cust, status, sale_date + dt.timedelta(days=3), po_date)
            elif hold:
                status = ST["hold"]
                change(po_key, po_no, cust, status, sale_date + dt.timedelta(days=2), po_date)
            elif shipped_all:
                status = ST["closed"]
                change(po_key, po_no, cust, status, max(d for _, d in rel_state.values()), po_date)
            else:
                status = ST["pending_fulfillment"]
        elif fate == "deposit":
            change(po_key, po_no, cust, status, po_date + dt.timedelta(days=1), po_date)
        elif fate == "cancelled_early":
            change(po_key, po_no, cust, status, po_date + dt.timedelta(days=4), po_date)

        out["raw_Sales_v_PO"].append(sb.clone("raw_Sales_v_PO", t_po,
            PO_Key=po_key, PO_No=po_no, Order_No=po_no, Customer_No=cust, PO_Status_Key=status,
            PO_Type_Key=TYPE["blanket"] if rng.random() < 0.2 else TYPE["spot"],
            PO_Date=W("raw_Sales_v_PO", "PO_Date", po_date, 0),
            Add_Date=W("raw_Sales_v_PO", "Add_Date", po_date, 9),
            Update_Date=W("raw_Sales_v_PO", "Update_Date", min(today, po_date + dt.timedelta(days=30))),
            Inside_Sales=rep_no or 0, Note=f"{TAG} sandbox order"))
        for i, ln in enumerate(lines, 1):
            cp = ln["cp"]
            out["raw_Sales_v_PO_Line"].append(sb.clone("raw_Sales_v_PO_Line", t_pl,
                PO_Line_Key=ln["pl"], PO_Key=po_key, Part_Key=cp["Part_Key"],
                Customer_Part_Key=cp["Customer_Part_Key"], Line_No=str(i), Active=1,
                Add_Date=W("raw_Sales_v_PO_Line", "Add_Date", po_date, 9),
                Update_Date=W("raw_Sales_v_PO_Line", "Update_Date", po_date, 9), Note=""))
            done, due = rel_state.get(ln["rel"], (0.0, workday(po_date + dt.timedelta(days=30))))
            rstat = (REL["canceled"] if status == ST["cancelled"] else
                     REL["hold"] if status == ST["hold"] else
                     REL["closed"] if done >= ln["qty"] - 1 else
                     REL["scheduled"] if fate == "sold" else REL["open"])
            out["raw_Sales_v_Release"].append(sb.clone("raw_Sales_v_Release", t_rel,
                Release_Key=ln["rel"], Release_No="1", PO_Line_Key=ln["pl"], Quantity=ln["qty"],
                Quantity_Shipped=round(done), Release_Status_Key=rstat,
                Ship_Date=W("raw_Sales_v_Release", "Ship_Date", due),
                Due_Date=W("raw_Sales_v_Release", "Due_Date", due),
                Customer_Due_Date=W("raw_Sales_v_Release", "Customer_Due_Date", due),
                Preliminary_Due_Date=W("raw_Sales_v_Release", "Preliminary_Due_Date", due),
                Add_Date=W("raw_Sales_v_Release", "Add_Date", po_date, 9),
                Update_Date=W("raw_Sales_v_Release", "Update_Date", po_date, 9), Note=""))
            # Most lines carry their own price, as a real order entry does; the
            # rest fall back to the customer's list, which the views flag.
            if rng.random() < 0.9:
                out["raw_Sales_v_Price"].append(sb.clone("raw_Sales_v_Price", t_pr,
                    Price_Key=ln["pk"], PO_Line_Key=ln["pl"], Price=cp["price"], Active=1,
                    Primary_Price=1, Breakpoint_Quantity=0.0, Note="",
                    Effective_Date=W("raw_Sales_v_Price", "Effective_Date", po_date, 0),
                    Add_Date=W("raw_Sales_v_Price", "Add_Date", po_date, 9),
                    Update_Date=W("raw_Sales_v_Price", "Update_Date", po_date, 9)))
        return sum(ln["qty"] * ln["cp"]["price"] for ln in lines)

    # ── booked orders, month by month ──────────────────────────────────
    for m, rep_no, dollars in targets:
        days = [d for d in workdays(sb, m) if d >= ORDERS_FROM and d < today]
        if not days:
            continue
        cs = book[rep_no] if rep_no else [unassigned_customer]
        booked = 0.0
        while booked < dollars * 0.97:
            size = min(rng.lognormvariate(math.log(AVG_ORDER), 0.6), max(dollars - booked, 8_000))
            sale = rng.choice(days)
            po_date = sale - dt.timedelta(days=rng.randint(0, 4))
            booked += order(rng.choice(cs), rep_no, size, po_date, "sold", sale)
            if rng.random() < 0.02:
                order(rng.choice(cs), rep_no, size, po_date, "cancelled_early")

    # ── the open front of the order book, as of today ──────────────────
    rep_list = [r for r in book]
    recent = [d for d in sb.days(today - dt.timedelta(days=14), today - dt.timedelta(days=1))
              if d.weekday() < 5]

    def fill(fate, target, avg, days, count=None):
        total, n = 0.0, 0
        while (count is None and total < target) or (count is not None and n < count):
            r = rng.choice(rep_list)
            total += order(rng.choice(book[r]), r, rng.lognormvariate(math.log(avg), 0.5),
                           rng.choice(days), fate)
            n += 1
        return total

    fill("pending_approval", scale.PENDING_APPROVAL_TARGET, AVG_ORDER, recent)
    fill("deposit", None, AVG_ORDER, recent, count=scale.DEPOSIT_REVIEW_ORDERS)
    fill("quote", scale.QUOTES_TARGET, 9_000,
         [d for d in sb.days(today - dt.timedelta(days=45), today) if d.weekday() < 5])

    return {t: sb.append(t, rows) for t, rows in out.items()}
