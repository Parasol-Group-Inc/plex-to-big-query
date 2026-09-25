"""
Quality history for the scorecard sandbox: nonconformances (NCs) and
deviations, 1 Jan 2026 -> build day, at the scale of Vox's live scorecard.

Every synthetic row is a CLONE of a real PlexTest row (see common.py):

  * NCs      — the 22 real records Vox Quality entered on the UX Problem
               Control screen (raw_Quality_v_Problem_2, 18-23 Sep) are the
               templates. They are left untouched. Clones keep every column
               of their template — form, category, type, severity, customer,
               supplier, texts — and change only keys, dates, quantities, the
               real part / work centre they point at, and the lifecycle
               fields (status, closure, disposition, cost).
  * Deviations — the one real deviation (+ its part / problem / work-centre
               link rows) is the template for every deviation and link.

What is MODELLED rather than copied, and why:

  * Disposition + Cost. On the real records Final_Disposition is blank and
    Cost is 0.00 with the money typed into Brief_Description instead — an
    open question with Quality (board_data FLAGS). The sandbox models the
    RECOMMENDED answer: material-bearing records get a real Plex disposition
    value (Scrap / Rework / Return / Use as is / Re-introduce) once they are
    far enough through their lifecycle, and Scrap / Rework records carry a
    dollar Cost scaled by quantity. The 22 real records keep their blanks.
    A template whose Brief_Description IS a money figure ("$2305.57", "600",
    "1.5") is cloned with its own real Final_Disposition_Note as the
    description instead, so a clone never shows one dollar figure in the text
    and a different one in Cost.
  * Part_v_Part.Average_Value is 0 on every part on this tenant, so there is
    no Plex unit cost to value material with. A per-part unit cost is drawn
    once (deterministically) in the neighbourhood the real descriptions imply
    — $600 on 890 units, $2,305.57 on a destruction — and reused for every
    record on that part.
  * raw_Quality_v_Deviation_Job has NO real row (0 in PlexTest, all-STRING
    columns). Its four columns are the same junction shape as the real
    Deviation_Part row (PCN, own key, Deviation_Key, Job_Key), so that row
    supplies the PCN; Job_Keys are real jobs from raw_Part_v_Job whose own
    dates bracket the deviation. No real job is dated before 23 Sep, so a
    deviation only links to a job when one existed at the time.
  * raw_Quality_v_Problem (the CLASSIC table) is permanently empty on this
    tenant and has no template row, so nothing is written to it — see the
    report for what that does to quality_deviation_report.problem_nos.

Scale: scale.NC_PER_MONTH, scale.DEVIATIONS_PER_MONTH, scale.TAT_DAYS.
"""

import datetime as dt
import re
import uuid

import random

import scale
from common import KEY_BANDS, PERIOD_START, TAG, month_end, workdays

T_NC = "raw_Quality_v_Problem_2"
T_NC_CLASSIC = "raw_Quality_v_Problem"
T_DEV = "raw_Quality_v_Deviation"
T_DJOB = "raw_Quality_v_Deviation_Job"
T_DPART = "raw_Quality_v_Deviation_Part"
T_DPROB = "raw_Quality_v_Deviation_Problem"
T_DWC = "raw_Quality_v_Deviation_Workcenter"

# Templates are REAL rows only: anything at or above the quality key band is
# a previous build's clone (a generate() without a reset must not clone clones).
REAL = f"SAFE_CAST({{k}} AS INT64) < {KEY_BANDS['quality']}"

# Real records written up from this day on are NOT used as templates (they
# stay in the table untouched). Quality's 24 Sep entries are keyboard tests —
# descriptions "rg[oijaerijg", "test", "Description", a "Copy of 5P" form —
# and cloning them would spread noise through nine months of history. The
# 18-23 Sep records are the deliberate, described test cases.
TEMPLATE_CUTOFF = dt.date(2026, 9, 24)

UTC = dt.timezone.utc
NS = 1_000_000_000

# Actors (who closes an NC, who approves a deviation) are read from the real
# rows at generate() time — see _Q.load_reference — never invented or
# hard-coded, since keys differ between PlexTest snapshots.

# Real Plex value lists (quality_disposition_cost_view.sql:18-20).
FINAL = ["Scrap", "Rework", "Return", "Use as is", "Re-introduce"]
INITIAL_FOR = {                      # a plausible first call for each outcome
    "Scrap": (["Scrap", "Sort & Scrap", "Hold"], [5, 2, 3]),
    "Rework": (["Rework", "Sort & Rework", "Hold"], [5, 3, 2]),
    "Return": (["Return", "Hold"], [7, 3]),
    "Use as is": (["Use as is", "Hold"], [5, 5]),
    "Re-introduce": (["Hold"], [1]),
}
# What each real form ends in. A Material Destruction record is, by
# definition, scrapped material; audits and safety findings carry none.
DISPOSITION_BY_FORM = {
    "Material Destruction": ([1, 0, 0, 0, 0]),
    "Non-Conformance Form": ([25, 40, 10, 20, 5]),
    "Complaint Form": ([40, 25, 30, 5, 0]),
    "8D": ([30, 40, 20, 10, 0]),
    "5P": ([15, 45, 10, 25, 5]),
    "Risk Assessment": ([10, 20, 0, 45, 25]),
    "Initial Problem Report": ([30, 35, 5, 25, 5]),
}
# Plex due date offset (calendar days after the problem) per form.
DUE_DAYS = {"Material Destruction": 7, "Non-Conformance Form": 7,
            "Complaint Form": 14, "8D": 30, "5P": 14, "Risk Assessment": 14,
            "System Audit CAR": 30, "Initial Problem Report": 7}
# Mean closure time in WORK days by stock type (Part_Type), inside
# scale.TAT_DAYS. The live scorecard reads 4 -> 10.7 work days by stock type.
TAT_MEAN = {"Raw Materials": 4.5, "Semi-Finished Goods": 7.0,
            "Finished Goods": 10.5, None: 7.5}
# Unit cost ($/each) neighbourhood per stock type, lognormal median.
UNIT_COST = {"Raw Materials": 0.55, "Semi-Finished Goods": 0.9,
             "Finished Goods": 1.8, "Components": 0.25}
# Open statuses seen on the real records, by how far along they are.
EARLY_OPEN = ["Open / In-Process", "In Process", "Hold"]
LATE_OPEN = ["Pending Verification", "Submitted for Closure", "Verification Pending"]

# Deviation type NAME (raw_Quality_v_Deviation_Type) by what the deviation
# covers; keys are looked up by name at generate() time.
DEV_TYPE = {"Raw Materials": "Raw Material", "Components": "Component",
            "Finished Goods": "Finished Good", "Semi-Finished Goods": "Process",
            "Process": "Process", "Other": "Other"}
# Work-centre groups each kind of deviation happens in (raw_Part_v_Workcenter).
DEV_WC_GROUPS = {"Raw Materials": ["Pre-Weigh", "Blending", "Testing"],
                 "Components": ["Labeling", "Bottling"],
                 "Finished Goods": ["Bottling", "Labeling"],
                 "Semi-Finished Goods": ["Encapsulating", "Blending"],
                 "Process": ["Encapsulating", "Blending", "Bottling"],
                 "Other": ["Testing", "Preparation", "Rework"]}
NC_WC_GROUPS = {"Raw Materials": ["Encapsulating", "Blending", "Pre-Weigh"],
                "Semi-Finished Goods": ["Encapsulating", "Bottling"],
                "Finished Goods": ["Labeling", "Bottling"],
                None: ["Bottling", "Encapsulating", "Labeling"]}

MONEY_ONLY = re.compile(r"^\s*(<p>)?\s*\$?\s*[\d,]+(\.\d+)?\s*(</p>)?\s*$")


# ── small date helpers ─────────────────────────────────────────────────────

def _dt(ns):
    return None if ns in (None, 0) else dt.datetime.fromtimestamp(ns / NS, UTC)


def _ns(d):
    return int(round(d.timestamp() * 1000)) * 1_000_000


def _midnight(d):
    return dt.datetime(d.year, d.month, d.day, tzinfo=UTC)


def _add_workdays(d, n):
    while n > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _is_date_col(v):
    """Plex dates in typed tables are INT64 nanoseconds; nothing else in
    these tables is anywhere near 1e17."""
    return isinstance(v, int) and not isinstance(v, bool) and v > 10 ** 17


class _Q:
    def __init__(self, sb):
        self.sb = sb
        self.rng = random.Random(f"{sb.today}-quality")
        self.now = dt.datetime(sb.today.year, sb.today.month, sb.today.day, 23, 59, tzinfo=UTC)
        self._unit_cost = {}

    # ── typed writes ────────────────────────────────────────────────────
    def ts(self, table, col, d):
        """A timestamp in the column's own shape, keeping the time of day
        (Recorded_Date is a precise timestamp on the real records)."""
        if d is None:
            return None
        if self.sb.schema(table).get(col) in ("INTEGER", "INT64"):
            return _ns(d)
        return self.sb.when(table, col, d)

    def shift_dates(self, table, row, delta):
        """Move every date on a cloned row by the same amount, so the
        intervals the real record had between its own dates survive."""
        out = {}
        for c, v in row.items():
            if _is_date_col(v) and self.sb.schema(table).get(c) in ("INTEGER", "INT64"):
                out[c] = _ns(_dt(v) + delta)
        return out

    # ── reference data ──────────────────────────────────────────────────
    def load_reference(self):
        sb = self.sb
        self.forms = {r["Problem_Form_Key"]: r["Name"] for r in sb.query(
            "SELECT SAFE_CAST(Problem_Form_Key AS INT64) Problem_Form_Key, Name "
            "FROM `{ds}.raw_Quality_v_Problem_Form`")}
        parts = sb.query(
            "SELECT SAFE_CAST(Part_Key AS INT64) Part_Key, Part_No, Name, Part_Type "
            "FROM `{ds}.raw_Part_v_Part` WHERE Part_Status = 'Active' "
            "AND Part_Type IN ('Raw Materials','Finished Goods','Semi-Finished Goods','Components')")
        self.part_type = {p["Part_Key"]: p["Part_Type"] for p in parts}
        self.part_family = {p["Part_Key"]: (p["Name"] or "").split(" | ")[0].strip()
                            for p in parts}
        self.parts_by_type = {}
        self.parts_by_family = {}
        for p in parts:
            self.parts_by_type.setdefault(p["Part_Type"], []).append(p["Part_Key"])
            fam = (p["Part_Type"], self.part_family[p["Part_Key"]])
            self.parts_by_family.setdefault(fam, []).append(p["Part_Key"])
        # Deterministic pools, independent of query row order.
        for d in (self.parts_by_type, self.parts_by_family):
            for k in d:
                d[k].sort()
        wcs = sb.query(
            "SELECT SAFE_CAST(Workcenter_Key AS INT64) Workcenter_Key, Workcenter_Code, "
            "Workcenter_Group FROM `{ds}.raw_Part_v_Workcenter` WHERE SAFE_CAST(Active AS INT64) = 1")
        self.wc_by_group = {}
        for w in wcs:
            code = w["Workcenter_Code"] or ""
            # Scheduling placeholders and design/approval desks are not where
            # material goes wrong.
            if code.startswith("SCHED") or code in ("Label Design", "Label Approval"):
                continue
            self.wc_by_group.setdefault(w["Workcenter_Group"], []).append(w["Workcenter_Key"])
        for k in self.wc_by_group:
            self.wc_by_group[k].sort()
        # Jobs with the window they were live in, whatever shape the dates are in.
        conv = ("COALESCE(DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST({c} AS STRING) AS INT64), 0), 1000))),"
                " SAFE_CAST(CAST({c} AS STRING) AS DATE), DATE(SAFE_CAST(CAST({c} AS STRING) AS TIMESTAMP)))")
        self.jobs = sb.query(f"""
            SELECT SAFE_CAST(Job_Key AS INT64) Job_Key, SAFE_CAST(Part_Key AS INT64) Part_Key,
                   {conv.format(c='Add_Date')} lo,
                   GREATEST(IFNULL({conv.format(c='Due_Date')}, DATE '1970-01-01'),
                            IFNULL({conv.format(c='Completed_Date')}, DATE '1970-01-01'),
                            IFNULL({conv.format(c='Add_Date')}, DATE '1970-01-01')) hi
            FROM `{{ds}}.raw_Part_v_Job`
            WHERE SAFE_CAST(Job_Key AS INT64) IS NOT NULL
            ORDER BY Job_Key""")

        # Lookups by NAME, keys read from this snapshot.
        self.dev_type = {r["n"]: r["k"] for r in sb.query(
            "SELECT Deviation_Type n, SAFE_CAST(Deviation_Type_Key AS INT64) k "
            "FROM `{ds}.raw_Quality_v_Deviation_Type`")}
        self.dev_status = {r["n"]: r["k"] for r in sb.query(
            "SELECT Deviation_Status n, SAFE_CAST(Deviation_Status_Key AS INT64) k "
            "FROM `{ds}.raw_Quality_v_Deviation_Status`")}
        # The Quality user who records the real NCs closes the clones; the
        # deviation's own reviewer plus the real NC reporters approve.
        users = sb.query(
            "SELECT SAFE_CAST(Recorded_By AS INT64) u, COUNT(*) n "
            "FROM `{ds}.raw_Quality_v_Problem_2` WHERE " + REAL.format(k="Problem_Key") +
            " GROUP BY 1 ORDER BY n DESC, u LIMIT 1")
        self.quality_user = users[0]["u"] if users else 0
        appr = sb.query(
            "SELECT DISTINCT u FROM ("
            " SELECT SAFE_CAST(FMEA_Review_By AS INT64) u FROM `{ds}.raw_Quality_v_Deviation`"
            " WHERE " + REAL.format(k="Deviation_Key") +
            " UNION ALL SELECT SAFE_CAST(Reported_By AS INT64) FROM `{ds}.raw_Quality_v_Problem_2`"
            " WHERE " + REAL.format(k="Problem_Key") + ")"
            " WHERE u > 0 ORDER BY u")
        self.approvers = [r["u"] for r in appr] or [self.quality_user]

    def pick_part(self, ptype, family=None):
        pool = self.parts_by_family.get((ptype, family)) if family else None
        if not pool or self.rng.random() < 0.25:     # stay mostly in the family
            pool = self.parts_by_type.get(ptype) or []
        return self.rng.choice(pool) if pool else -1

    def pick_wc(self, groups):
        pool = [w for g in groups for w in self.wc_by_group.get(g, [])]
        return self.rng.choice(pool) if pool else 0

    def unit_cost(self, part_key):
        if part_key not in self._unit_cost:
            base = UNIT_COST.get(self.part_type.get(part_key), 0.6)
            r = random.Random(f"{self.sb.today}-quality-cost-{part_key}")
            self._unit_cost[part_key] = round(base * r.lognormvariate(0, 0.55), 4)
        return self._unit_cost[part_key]

    # ── nonconformances ─────────────────────────────────────────────────
    def nc_plan(self, real):
        """(month, record-dates) per month. September's synthetic records
        stop the day before the first real one: the real week of entry is
        kept exactly as Quality left it."""
        first_real = min(_dt(r["Recorded_Date"]) for r in real).date()
        plan = []
        for m in self.sb.months():
            days = workdays(self.sb, m)
            n = self.rng.randint(*scale.NC_PER_MONTH)
            full = len([d for d in self.sb.days(m, month_end(m)) if d.weekday() < 5])
            if m.year == first_real.year and m.month == first_real.month:
                days = [d for d in days if d < first_real]
                n = round(n * len(days) / full)
            else:
                n = round(n * len(days) / full)
            plan.append((m, sorted(self.rng.choice(days) for _ in range(n)) if days else []))
        return plan

    def template_weights(self, real):
        # The one Finished Goods template (labels tearing on a labelling line)
        # is weighted up so finished-goods turnaround has more than a handful
        # of records; every other real record counts once.
        return [3 if self.part_type.get(r["Part_Key"]) == "Finished Goods" else 1 for r in real]

    def make_nc(self, t, rec_day):
        rng, sb = self.rng, self.sb
        form = self.forms.get(t["Problem_Form_Key"])
        t_part = t["Part_Key"] if t["Part_Key"] not in (None, 0) else -1
        t_type = self.part_type.get(t_part)
        if t_part > 0 and t_type is None:
            # A real record whose Part_Key does not resolve in this snapshot of
            # raw_Part_v_Part (about half do not, on any given instant). The
            # clone still points at a part, one that does resolve; Raw
            # Materials is what every resolvable real NC part but one is.
            t_type = "Raw Materials"

        # ── what it is about (the real part it points at) ──
        if form == "Material Destruction":
            ptype = t_type or "Raw Materials"        # destruction is of material
        elif form == "Complaint Form" and t_part == -1 and rng.random() < 0.6:
            ptype = "Finished Goods"                 # a customer complains about product
        elif form == "Non-Conformance Form" and rng.random() < 0.3:
            ptype = "Finished Goods"
        else:
            ptype = t_type
        if ptype:
            fam = self.part_family.get(t_part) if ptype == t_type else None
            part = self.pick_part(ptype, fam)
            if part == -1:
                ptype = None
        else:
            part = -1
        wc = t["Workcenter_Key"] or 0
        if wc:
            wc = self.pick_wc(NC_WC_GROUPS.get(ptype, NC_WC_GROUPS[None]))

        material = part != -1 or (t["Quantity"] or 0) > 0
        disp_weights = DISPOSITION_BY_FORM.get(form)
        if not disp_weights:
            material = False                           # audit / system CAR: no material

        # ── when: written up on a work day, happened a little earlier ──
        t_rec, t_prob = _dt(t["Recorded_Date"]), _dt(t["Problem_Date"])
        rec = dt.datetime(rec_day.year, rec_day.month, rec_day.day,
                          rng.randint(7, 15), rng.randint(0, 59), rng.randint(0, 59),
                          rng.randint(0, 999) * 1000, tzinfo=UTC)
        timed = t_prob is not None and (t_prob.hour or t_prob.minute)
        if timed:        # the template logged the time it happened, minutes earlier
            prob = rec - dt.timedelta(minutes=rng.randint(1, 5))
            prob = prob.replace(second=0, microsecond=0)
        else:            # date-only problem date, with a small reporting lag
            lag = rng.choices([0, 1, 2, 3, 4, 5], weights=[55, 25, 9, 5, 3, 3])[0]
            prob = _midnight(rec - dt.timedelta(days=lag))
        if prob.date() < PERIOD_START:
            prob = _midnight(dt.datetime.combine(PERIOD_START, dt.time(), UTC))

        # ── lifecycle ──
        mean = TAT_MEAN.get(ptype if ptype in TAT_MEAN else None)
        lo, hi = scale.TAT_DAYS
        tat_wd = min(hi, lo + round(rng.gammavariate(3, (mean - lo) / 3)))
        close = _midnight(_add_workdays(rec, tat_wd))
        straggler = rng.random() < 0.04                  # the odd one nobody closes
        closed = close <= self.now and not straggler
        if closed:
            status = "Closed"
            progress = 1.0
        else:
            elapsed = max(0, (self.now - rec).days)
            progress = elapsed / max(1, (close - rec).days)
            if straggler:
                status = "Hold"
            elif progress < 0.6:
                status = t["Problem_Status"] if t["Problem_Status"] in EARLY_OPEN else rng.choice(EARLY_OPEN)
            else:
                status = rng.choice(LATE_OPEN)

        # ── quantities, disposition, cost ──
        qty = t["Quantity"] or 0
        rejected = returned = scrapped = 0
        final = initial = ""
        cost = 0.0
        if material:
            if qty <= 0:
                qty = rng.choice([20, 480, 485, 840, 890, 900, 1458])   # real quantities
            qty = max(1, round(qty * rng.uniform(0.3, 2.5)))
            final = rng.choices(FINAL, weights=disp_weights)[0]
            vals, w = INITIAL_FOR[final]
            initial = rng.choices(vals, weights=w)[0]
            share = 1.0 if final == "Scrap" else rng.uniform(0.05, 0.6)
            rejected = max(1, round(qty * share))
            if final == "Scrap":
                scrapped = rejected
            if final == "Return":
                returned = rejected
            uc = self.unit_cost(part) if part != -1 else 0.6
            if final == "Scrap":
                cost = rejected * uc
            elif final == "Rework":
                cost = rejected * uc * rng.uniform(0.15, 0.4) + rng.uniform(40, 180)
            cost = round(min(max(cost, 12.0), 4800.0), 2) if cost else 0.0
            # A disposition is decided before closure: open records only carry
            # one once they are most of the way there.
            if not closed and progress < 0.6:
                final = ""
                cost = 0.0
                if progress < 0.25:
                    initial = ""

        brief = t["Brief_Description"]
        if brief and MONEY_ONLY.match(brief) and t["Final_Disposition_Note"]:
            brief = t["Final_Disposition_Note"]

        delta = rec - t_rec
        ch = self.shift_dates(T_NC, t, delta)
        due = None
        if t["Problem_Due_Date"]:
            due = _midnight(prob + dt.timedelta(days=DUE_DAYS.get(form, 14)))
        ch.update(
            Part_Key=part,
            Workcenter_Key=wc,
            Recorded_Date=self.ts(T_NC, "Recorded_Date", rec),
            Problem_Date=self.ts(T_NC, "Problem_Date", prob),
            Problem_Due_Date=self.ts(T_NC, "Problem_Due_Date", due),
            Closed_Date=self.ts(T_NC, "Closed_Date", close) if closed else None,
            Closed_By=self.quality_user if closed else 0,
            Status_Change_Date=self.ts(T_NC, "Status_Change_Date",
                                       close + dt.timedelta(hours=rng.randint(8, 16)))
            if closed else ch.get("Status_Change_Date", t["Status_Change_Date"]),
            Updated_Date=self.ts(T_NC, "Updated_Date",
                                 close + dt.timedelta(hours=rng.randint(8, 16), minutes=rng.randint(0, 59)))
            if closed else ch.get("Updated_Date", t["Updated_Date"]),
            Updated_By=self.quality_user if closed else t["Updated_By"],
            Problem_Status=status,
            Quantity=qty,
            Quantity_Rejected=rejected,
            Quantity_Returned=returned,
            Quantity_Scrapped=scrapped,
            Initial_Disposition=initial,
            Final_Disposition=final,
            Cost=cost,
            Brief_Description=brief,
            Internal_Problem_No=f"{TAG}-NC",
        )
        return ch, dict(rec=rec, part=part, wc=wc, ptype=ptype, qty=qty,
                        rejected=rejected, material=material)

    def nonconformances(self):
        sb, rng = self.sb, self.rng
        real = sorted((r for r in sb.templates(T_NC, REAL.format(k="Problem_Key"))
                       if _dt(r["Recorded_Date"]).date() < TEMPLATE_CUTOFF),
                      key=lambda r: r["Problem_No"])
        weights = self.template_weights(real)
        drafts = []
        for _m, days in self.nc_plan(real):
            for d in days:
                t = rng.choices(real, weights=weights)[0]
                ch, meta = self.make_nc(t, d)
                drafts.append((meta["rec"], t, ch, meta))
        # Keys and numbers in the order the records were written up, the way
        # Plex hands them out. Numbers sit in their own range (90001+) so a
        # sandbox NC is never confused with Vox's real 1-22.
        drafts.sort(key=lambda x: x[0])
        rows, metas = [], []
        for i, (_rec, t, ch, meta) in enumerate(drafts, start=1):
            key = sb.key("quality")
            ch.update(Problem_Key=key, Problem_No=90000 + i,
                      Internal_Problem_No=f"{TAG}-NC-{90000 + i}")
            rows.append(sb.clone(T_NC, t, **ch))
            meta.update(key=key)
            metas.append(meta)
        return rows, metas

    # ── deviations ──────────────────────────────────────────────────────
    def deviations(self, ncs):
        sb, rng = self.sb, self.rng
        real_devs = sb.templates(T_DEV, REAL.format(k="Deviation_Key"))
        t_dev = sorted(real_devs, key=lambda r: r["Deviation_Key"])[0]
        t_part = sb.templates(T_DPART, REAL.format(k="Deviation_Part_Key"), 1)[0]
        t_prob = sb.templates(T_DPROB, REAL.format(k="Deviation_Problem_Key"), 1)[0]
        t_wc = sb.templates(T_DWC, REAL.format(k="Deviation_Workcenter_Key"), 1)[0]
        real_add = min(_dt(r["Add_Date"]) for r in real_devs).date()
        # No real junction row for jobs: the sibling Deviation_Part row has the
        # identical shape and supplies the PCN (see module docstring).
        t_job = {c: None for c in sb.schema(T_DJOB)}
        t_job["PCN"] = sb.val(T_DJOB, "PCN", t_part["PCN"])

        linkable = [m for m in ncs if m["material"] and m["part"] != -1]
        devs, parts, probs, wcs, jobs = [], [], [], [], []
        drafts = []
        for m in sb.months():
            days = workdays(sb, m)
            full = len([d for d in sb.days(m, month_end(m)) if d.weekday() < 5])
            n = round(rng.randint(*scale.DEVIATIONS_PER_MONTH) * len(days) / full)
            if m.year == real_add.year and m.month == real_add.month:
                n -= 1                                   # the real one counts
            for _ in range(max(0, n)):
                drafts.append(rng.choice(days))
        drafts.sort()

        for i, day in enumerate(drafts, start=1):
            add = dt.datetime(day.year, day.month, day.day, rng.randint(7, 15),
                              rng.randint(0, 59), rng.randint(0, 59),
                              rng.randint(0, 999) * 1000, tzinfo=UTC)
            # Some deviations are raised for a recent nonconformance, and then
            # cover that NC's part (and line, if it had one).
            nc = None
            recent = [x for x in linkable
                      if dt.timedelta(0) <= add - x["rec"] <= dt.timedelta(days=10)]
            if recent and rng.random() < 0.35:
                nc = rng.choice(recent)
            if nc:
                kind = nc["ptype"]
                dparts = [nc["part"]]
                pieces = nc["rejected"] or nc["qty"]
            else:
                kind = rng.choices(["Raw Materials", "Components", "Finished Goods",
                                    "Semi-Finished Goods", "Process", "Other"],
                                   weights=[35, 20, 15, 5, 20, 5])[0]
                ptype = kind if kind in self.parts_by_type else rng.choice(
                    ["Semi-Finished Goods", "Finished Goods"])
                dparts = [self.pick_part(ptype)]
                if rng.random() < 0.2:
                    dparts.append(self.pick_part(ptype))
                pieces = rng.randint(2, 100) * 50
            dparts = sorted({p for p in dparts if p != -1})
            type_key = self.dev_type.get(DEV_TYPE.get(kind), t_dev["Deviation_Type_Key"])
            wc_key = nc["wc"] if nc and nc["wc"] else self.pick_wc(
                DEV_WC_GROUPS.get(kind, DEV_WC_GROUPS["Process"]))

            eff = _midnight(add + dt.timedelta(days=rng.choice([0, 0, 1, 2])))
            exp = eff + dt.timedelta(days=rng.choice([9, 14, 30, 60, 90, 90, 180]))
            age = (self.now - add).days
            approved = None
            if age < 5:
                status = rng.choices(["Draft", "Submitted", "Checked Out"], weights=[4, 4, 2])[0]
            elif rng.random() < 0.05:
                status = "Cancelled"
            else:
                approved = _add_workdays(add, rng.randint(1, 4)).replace(
                    hour=rng.randint(8, 16), minute=rng.randint(0, 59))
                if approved > self.now:
                    approved, status = None, "Submitted"
                elif exp < self.now:
                    status = rng.choices(["Expired", "Superseded", "Approved"], weights=[50, 15, 35])[0]
                else:
                    status = rng.choices(["Approved", "Submitted", "Checked Out"], weights=[85, 10, 5])[0]
                    if status != "Approved":
                        approved = None
            key = sb.key("quality")
            upd = approved or add + dt.timedelta(minutes=rng.randint(1, 40))
            devs.append(sb.clone(
                T_DEV, t_dev,
                Deviation_Key=key,
                Deviation_No=f"{TAG}-{i:04d}",
                Deviation_Type_Key=type_key,
                Deviation_Status_Key=self.dev_status.get(status, t_dev["Deviation_Status_Key"]),
                Effective_Date=self.ts(T_DEV, "Effective_Date", eff),
                Expiration_Date=self.ts(T_DEV, "Expiration_Date", exp),
                Pieces_Affected=max(1, int(pieces)),
                Add_Date=self.ts(T_DEV, "Add_Date", add),
                Update_Date=self.ts(T_DEV, "Update_Date", upd),
                FMEA_Review_Date=self.ts(T_DEV, "FMEA_Review_Date", add),
                Approved_By=rng.choice(self.approvers) if approved else 0,
                Approved_Date=self.ts(T_DEV, "Approved_Date", approved),
                Supplier_No=t_dev["Supplier_No"] if kind in ("Raw Materials", "Components") else 0,
                Resource_ID=str(uuid.UUID(int=rng.getrandbits(128), version=4)),
            ))
            for p in dparts:
                parts.append(sb.clone(T_DPART, t_part, Deviation_Part_Key=sb.key("quality"),
                                      Deviation_Key=key, Part_Key=p))
            if wc_key:
                wcs.append(sb.clone(T_DWC, t_wc, Deviation_Workcenter_Key=sb.key("quality"),
                                    Deviation_Key=key, Workcenter_Key=wc_key))
            if nc:
                probs.append(sb.clone(
                    T_DPROB, t_prob, Deviation_Problem_Key=sb.key("quality"),
                    Deviation_Key=key, Problem_Key=nc["key"],
                    Add_Date=self.ts(T_DPROB, "Add_Date", add + dt.timedelta(minutes=2))))
            # A job, only if one was actually live then — same part first,
            # else any job live that day, for half the deviations.
            live = [j for j in self.jobs if j["lo"] and j["lo"] - dt.timedelta(days=3) <= add.date() <= j["hi"]]
            same = [j for j in live if j["Part_Key"] in dparts]
            job = rng.choice(same) if same else (rng.choice(live) if live and rng.random() < 0.5 else None)
            if job:
                jobs.append(sb.clone(T_DJOB, t_job, Deviation_Job_Key=sb.key("quality"),
                                     Deviation_Key=key, Job_Key=job["Job_Key"]))
        return devs, parts, probs, wcs, jobs


def generate(sb):
    q = _Q(sb)
    q.load_reference()
    nc_rows, nc_meta = q.nonconformances()
    devs, dparts, dprobs, dwcs, djobs = q.deviations(nc_meta)
    return {
        T_NC: sb.append(T_NC, nc_rows),
        T_NC_CLASSIC: 0,
        T_DEV: sb.append(T_DEV, devs),
        T_DPART: sb.append(T_DPART, dparts),
        T_DPROB: sb.append(T_DPROB, dprobs),
        T_DWC: sb.append(T_DWC, dwcs),
        T_DJOB: sb.append(T_DJOB, djobs),
    }
