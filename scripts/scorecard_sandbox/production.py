"""
Production family: jobs, their operations, and the production log, 1 Jan to
yesterday — the rows behind every production tile (actual vs goal by work
centre group, the Encap / Packaging / Labeling daily reports, FPY by area,
Open Caps and Open Bottles).

Writes ONLY raw_Part_v_Job, raw_Part_v_Job_Op and raw_Part_v_Production.

HOW IT STAYS REAL. Every synthetic row is a clone of a real PlexTest row:
  * A job is a clone of a real job that makes the SAME part, and its op is a
    clone of that job's real op — so Part_Key, Part_Operation_Key,
    Operation_Key, Rate and Setup_Time always form a routing Plex actually
    has. Only keys, dates, quantity, status and the (real) work centre change.
  * Which parts a group makes comes from the part numbering the tenant uses
    (2 BLEND, 3 CAPS, 5 bright bottle, 9 labelled FG, 7 LABEL, 1 raw material
    for pre-weigh) and, within that, only parts a real job already routes.
  * A production record is a clone of a real Part_v_Production row — a good
    row for output, the tenant's real REJECTED row for scrap (its Rejected
    value and Report_Shift included) — and Record_By is a real employee.

THE PLANT. Each work centre runs its jobs back to back. Per group and month,
output = the live scorecard's goal x an attainment draw (scale.py), so some
months hit goal and some miss; it is spread over workdays (no weekends, no
plant holidays) and over the group's lines by a per-line speed, with the odd
line down for a day. When a job's quantity is reached it completes and the
line changes over to the next job the same day. Scrap is logged as its own
rejected rows, sized so each month's FPY sits near the scorecard's FPY for the
group. NOTE: real Plex marks those rows Rejected = 1 and the views count scrap
only at -1 (see SCRAP_FLAG_OBSERVED) — so until the view SQL is corrected,
scrap_qty reads 0 while FPY (good / total) is still right.

TODAY. Whatever a line is running at the end of yesterday is in Production
(op started, not complete). Behind it sits a queue of Scheduled jobs (New if
added in the last two days) sized so Open Caps / Open Bottles land on the
scorecard's figures, plus one Hold job each on Encapsulation and Bottling —
the open views exclude Hold, so they are there to prove the filter works.
"""

import datetime as dt
import random
import uuid

import scale
from common import TAG, month_end

UTC = dt.timezone.utc

# Part-number prefix -> the work centre group that makes it.
PREFIX_GROUP = {"3": "Encapsulating", "5": "Bottling", "9": "Labeling",
                "7": "Printing", "2": "Blending", "1": "Pre-Weigh"}

# The lines that actually run each group's parts (names as Plex has them).
# Encapsulation: the stations the Encap Daily Report sheet itself lists
# (1,2,4,5,7,8,9,10 — see encap_daily_report_view.sql). Bottling / Labeling:
# the numbered lines — the tenant's routed bottling parts are 60ct capsule
# bottles, not Liquid/Powder/Bulk work. Scheduling pseudo-centres, Label
# Design / Label Approval, First 48 and the Testing group never run.
LINES = {
    "Encapsulating": [f"Encapsulation {n}" for n in (1, 2, 4, 5, 7, 8, 9, 10)],
    "Bottling": [f"Bottling Line {n}" for n in range(1, 7)],
    "Labeling": [f"Labeling Line {n}" for n in range(1, 7)],
    "Printing": ["Printing"],
    "Blending": [f"Blend {n}" for n in range(2, 6)],
    "Pre-Weigh": [f"Preweigh {n}" for n in range(1, 4)],
}
# A slow / part-time line in each multi-line group, so the per-line rows
# don't all look identical.
SLOW_LINES = {"Bottling Line 6": 0.45, "Labeling Line 6": 0.4, "Blend 5": 0.5}

# Job size per group (units of the part). Real test jobs: caps 366K-6.4M,
# bottles 3K-14K, labels 3K-14K, blends 500 — the minor groups are scaled
# up because scale.MINOR_GROUPS sets their monthly volume.
JOB_SIZE = {
    "Encapsulating": (1_500_000, 6_500_000, 10_000),
    "Bottling": (6_000, 30_000, 500),
    "Labeling": (4_000, 20_000, 500),
    "Printing": (20_000, 60_000, 500),
    "Blending": (60_000, 160_000, 1_000),
    "Pre-Weigh": (40_000, 120_000, 500),
}

# Open-order backlog at build time, in units. Encap and Bottling are the
# scorecard's own Open Caps / Open Bottles figures; the others (no scorecard
# tile) carry roughly two weeks of work so their open-WO lists aren't empty.
OPEN_TARGET = {
    "Encapsulating": scale.OPEN_CAPS_TARGET,
    "Bottling": scale.OPEN_BOTTLES_TARGET,
    "Labeling": 350_000, "Printing": 420_000,
    "Blending": 900_000, "Pre-Weigh": 600_000,
}

# Month-to-month wobble on FPY around scale.FPY. Groups the scorecard shows
# no FPY for get a plain 99% (none of the live figures cover them).
FPY_SD = {"Encapsulating": 0.008, "Bottling": 0.0004, "Labeling": 0.0015}
MINOR_FPY, MINOR_FPY_SD = 0.99, 0.003
SCRAP_DAY_P = {"Encapsulating": 0.45}          # share of job-days logging scrap
DEFAULT_SCRAP_DAY_P = 0.2

# The Rejected value a real scrap record carries. The production views test
# Rejected = -1 (a convention assumed on 2026-08-23, CHANGELOG), but the first
# real rejected record on this tenant (PlexTest, 2026-09-24, Bottling Line 1,
# 500 units) carries Rejected = 1. Used only when a snapshot has no real
# rejected row to clone; otherwise the real row's own value is used.
SCRAP_FLAG_OBSERVED = 1

LINE_DOWN_P = 0.07          # a line idle for the day (PM, no crew, no job)
SPLIT_P = 0.3               # a job-day logged as two containers by two people
SPLIT_GROUPS = {"Encapsulating", "Bottling", "Labeling"}   # crewed lines
SHIFT_UTC = (11.0, 21.5)    # 1st shift, as UTC hours (real rows: 13:11-14:28)

# Plant holidays (weekday closures) in the simulated year.
HOLIDAYS = {dt.date(2026, 1, 1), dt.date(2026, 5, 25), dt.date(2026, 7, 3),
            dt.date(2026, 9, 7), dt.date(2026, 11, 26), dt.date(2026, 12, 25)}

# Tenant status keys, resolved by name at run time.
JOB_STATUS = ("New", "Scheduled", "Production", "Completed", "Hold", "Cancelled")


def generate(sb):
    rng = random.Random(f"{sb.today}-production")
    ref = _reference(sb)
    plant = _Plant(sb, rng, ref)

    for g in LINES:
        plant.run_history(g)
    for g in LINES:
        plant.fill_backlog(g)
    plant.extras()
    jobs, ops, prod = plant.rows()

    return {
        "raw_Part_v_Job": sb.append("raw_Part_v_Job", jobs),
        "raw_Part_v_Job_Op": sb.append("raw_Part_v_Job_Op", ops),
        "raw_Part_v_Production": sb.append("raw_Part_v_Production", prod),
    }


# ── what the tenant really has ─────────────────────────────────────────────

def _reference(sb):
    wc = sb.query("SELECT Workcenter_Key, Name, Workcenter_Group "
                  "FROM `{ds}.raw_Part_v_Workcenter`")
    lines = {}
    for g, names in LINES.items():
        found = {r["Name"]: r["Workcenter_Key"] for r in wc if r["Workcenter_Group"] == g}
        missing = [n for n in names if n not in found]
        if missing:
            raise RuntimeError(f"{g}: work centre(s) not in Plex: {missing}")
        lines[g] = [(n, found[n]) for n in names]

    status = {r["Job_Status"]: r["Job_Status_Key"] for r in sb.query(
        "SELECT Job_Status, Job_Status_Key FROM `{ds}.raw_Part_v_Job_Status`")}
    missing = [s for s in JOB_STATUS if s not in status]
    if missing:
        raise RuntimeError(f"Job_Status missing: {missing}")

    # Op status keys by what the real ops show: not started / running / done
    # (the commonest Job_Op_Status_Key among ops in each state).
    ops = {}
    for r in sb.query("""
        SELECT CASE WHEN Complete_Date IS NOT NULL THEN 'done'
                    WHEN Start_Date IS NOT NULL THEN 'running'
                    ELSE 'open' END state,
               Job_Op_Status_Key k, COUNT(*) n
        FROM `{ds}.raw_Part_v_Job_Op`
        GROUP BY 1, 2 ORDER BY n"""):
        ops[r["state"]] = r["k"]
    if not ops:
        raise RuntimeError("raw_Part_v_Job_Op is empty — nothing to clone")
    for state in ("open", "running", "done"):
        if state not in ops:
            # Only work_orders_report passes this key through (no view
            # filters on it), so a thin snapshot degrades to a label, not a
            # wrong tile.
            fallback = ops.get("open") or next(iter(ops.values()))
            print(f"  ! no real Job_Op is {state}; reusing status key {fallback}")
            ops[state] = fallback

    # Every real (job, op) pair, keyed by the group that makes its part.
    jobs = {j["Job_Key"]: j for j in sb.templates("raw_Part_v_Job")}
    part_nos = {r["Part_Key"]: r["Part_No"] for r in sb.query(
        "SELECT Part_Key, Part_No FROM `{ds}.raw_Part_v_Part`")}
    by_group, all_pairs = {}, []
    for op in sb.templates("raw_Part_v_Job_Op"):
        job = jobs.get(op["Job_Key"])
        if not job:
            continue
        all_pairs.append((job, op))
        pn = part_nos.get(job["Part_Key"])
        g = PREFIX_GROUP.get((pn or "")[:1])
        if g:
            by_group.setdefault(g, []).append((op["Operation_Key"], pn, job, op))
    if not all_pairs:
        raise RuntimeError("no real job/op pair to clone")

    # Per group: the operation most of its real jobs route through (drops
    # e.g. the label design/approval steps on 7-parts), then one template
    # pair per part — preferring a job without a job-specific note.
    parts = {}
    for g in LINES:
        rows = by_group.get(g) or []
        if not rows:
            parts[g] = _fallback_parts(sb, g, all_pairs)
            continue
        counts = {}
        for op_key, *_ in rows:
            counts[op_key] = counts.get(op_key, 0) + 1
        main_op = max(counts, key=counts.get)
        best = {}
        for op_key, pn, job, op in sorted(rows, key=lambda x: (x[1], x[2]["Job_Key"])):
            if op_key != main_op:
                continue
            cur = best.get(pn)
            if cur is None or (cur[1]["Note"] and not job["Note"]):
                best[pn] = (pn, job, op)
        parts[g] = sorted(best.values(), key=lambda x: x[0])

    emp = [r["Plexus_User_No"] for r in sb.query(
        "SELECT Plexus_User_No FROM `{ds}.raw_Personnel_v_Employee` "
        "WHERE Employee_Status = 'Active' AND Shift_Key > 0 ORDER BY 1")]
    planners = sorted({r["Add_By"] for r in sb.query(
        "SELECT DISTINCT Add_By FROM `{ds}.raw_Part_v_Job` WHERE Add_By > 0")})

    tmpl = sb.templates("raw_Part_v_Production", "Rejected = 0")
    if not tmpl:
        raise RuntimeError("no real Part_v_Production row to clone")
    # Scrap rows are clones of a REAL rejected record when the snapshot has
    # one, flag value and all — see SCRAP_FLAG_OBSERVED for why that matters.
    rejected = sb.templates("raw_Part_v_Production", "COALESCE(Rejected, 0) != 0", limit=1)
    if rejected:
        scrap_tmpl, scrap_flag = rejected[0], rejected[0]["Rejected"]
    else:
        scrap_tmpl, scrap_flag = tmpl[0], SCRAP_FLAG_OBSERVED
    by_wc = {t["Workcenter_Key"]: t for t in tmpl}
    wc_group = {r["Workcenter_Key"]: r["Workcenter_Group"] for r in wc}
    prod_tmpl = {}
    for g in LINES:
        same = [t for k, t in by_wc.items() if wc_group.get(k) == g]
        prod_tmpl[g] = same[0] if same else tmpl[0]

    # Report_Date sits at a fixed offset from the record's UTC midnight in
    # the real rows (the report day boundary) — mirror it.
    t0 = tmpl[0]
    rec = dt.datetime.fromtimestamp(t0["Record_Date"] / 1e9, UTC)
    midnight = dt.datetime(rec.year, rec.month, rec.day, tzinfo=UTC)
    report_offset = dt.timedelta(seconds=t0["Report_Date"] / 1e9 - midnight.timestamp())

    # Open jobs already in the copy (real ones) count toward the backlog.
    # Each open view has its own work-centre filter (Encap and Labeling
    # match on Name, Bottling on the group), so count real open jobs the way
    # each view will.
    real_open = {r["g"]: r["q"] or 0 for r in sb.query("""
        SELECT CASE WHEN wc.Name LIKE 'Encapsulation%' THEN 'Encapsulating'
                    WHEN wc.Name LIKE 'Labeling Line%' THEN 'Labeling'
                    WHEN wc.Name LIKE 'Printing%' THEN 'Printing'
                    WHEN wc.Workcenter_Group IN ('Bottling', 'Blending', 'Pre-Weigh')
                      THEN wc.Workcenter_Group END g, SUM(q) q FROM (
          SELECT DISTINCT j.Job_Key, SAFE_CAST(jo.Workcenter_Key AS INT64) wk,
                 SAFE_CAST(j.Quantity AS FLOAT64) q
          FROM `{ds}.raw_Part_v_Job_Op` jo
          JOIN `{ds}.raw_Part_v_Job` j USING (Job_Key)
          JOIN `{ds}.raw_Part_v_Job_Status` js USING (Job_Status_Key)
          WHERE js.Completed_Status = 0 AND js.Cancelled_Status = 0
            AND js.Hold_Status = 0)
        JOIN `{ds}.raw_Part_v_Workcenter` wc ON wc.Workcenter_Key = wk
        GROUP BY 1""")}

    return dict(lines=lines, status=status, ops=ops, parts=parts, emp=emp,
                planners=planners, prod_tmpl=prod_tmpl,
                scrap_tmpl=scrap_tmpl, scrap_flag=scrap_flag,
                report_offset=report_offset, real_open=real_open)


def _fallback_parts(sb, g, all_pairs):
    """PlexTest is rebuilt nightly, so some snapshots hold no job for a
    group at all. Then: real parts of the group's prefix, each on a real
    job/op clone, with Part_Operation_Key cleared — the template's belongs to
    another part's routing, and no production view reads it."""
    prefix = next(k for k, v in PREFIX_GROUP.items() if v == g)
    rows = sb.query(f"""
        SELECT Part_Key, Part_No FROM `{{ds}}.raw_Part_v_Part`
        WHERE STARTS_WITH(Part_No, '{prefix}') AND Part_Status = 'Production'
        ORDER BY Part_No""") or sb.query(f"""
        SELECT Part_Key, Part_No FROM `{{ds}}.raw_Part_v_Part`
        WHERE STARTS_WITH(Part_No, '{prefix}') ORDER BY Part_No""")
    if not rows:
        raise RuntimeError(f"no {g} part (prefix {prefix}) in raw_Part_v_Part")
    rows = rows[:: max(1, len(rows) // 8)][:8]
    job, op = sorted(all_pairs, key=lambda x: (bool(x[0]["Note"]), x[0]["Job_Key"]))[0]
    print(f"  ! no real job routes a {g} part; cloning job {job['Job_No']} for "
          f"{len(rows)} real {prefix}-parts (Part_Operation_Key cleared)")
    out = []
    for r in rows:
        j = dict(job, Part_Key=r["Part_Key"])
        o = dict(op, Part_Key=r["Part_Key"], Part_Operation_Key=None)
        out.append((r["Part_No"], j, o))
    return out


# ── the simulation ─────────────────────────────────────────────────────────

class _Job:
    __slots__ = ("group", "part", "tjob", "top", "wc", "qty", "made", "status",
                 "add", "due", "start", "end", "starter", "finisher", "key",
                 "op_key", "setup_key", "records")

    def __init__(self, group, part, wc, qty):
        self.group, self.wc, self.qty = group, wc, qty
        self.part, self.tjob, self.top = part
        self.made = 0
        self.status = "Scheduled"
        self.add = self.due = self.start = self.end = None
        self.starter = self.finisher = None
        self.records = []          # (datetime, qty, is_scrap, employee)


class _Plant:
    def __init__(self, sb, rng, ref):
        self.sb, self.rng, self.ref = sb, rng, ref
        self.jobs = []
        self.crew = {}             # wc key -> list of employees
        pool = list(ref["emp"])
        rng.shuffle(pool)
        planners = set(ref["planners"])
        pool = [e for e in pool if e not in planners] or list(ref["emp"])
        i = 0
        for g in LINES:
            for _, wk in ref["lines"][g]:
                n = 3 if g in ("Encapsulating", "Bottling", "Labeling") else 2
                self.crew[wk] = [pool[(i + k) % len(pool)] for k in range(n)]
                i += n
        self.current = {}          # wc key -> running _Job

    # helpers
    def _size(self, g):
        lo, hi, step = JOB_SIZE[g]
        return int(round(self.rng.uniform(lo, hi) / step) * step)

    def _new_job(self, g, wk, prev=None):
        parts = self.ref["parts"][g]
        part = ((prev.part, prev.tjob, prev.top)
                if prev and len(parts) > 1 and self.rng.random() < 0.35 else None)
        if part is None:
            part = self.rng.choice(parts)
        j = _Job(g, part, wk, self._size(g))
        self.jobs.append(j)
        return j

    def _at(self, d, lo=None, hi=None):
        lo, hi = lo or SHIFT_UTC[0], hi or SHIFT_UTC[1]
        h = self.rng.uniform(lo, hi)
        return dt.datetime(d.year, d.month, d.day, tzinfo=UTC) + dt.timedelta(
            hours=h, seconds=self.rng.randint(0, 59))

    def _workdays(self, m):
        return [d for d in _days(m, month_end(m)) if d.weekday() < 5 and d not in HOLIDAYS]

    def _goal(self, g):
        return scale.PRODUCTION_GOALS.get(g) or scale.MINOR_GROUPS[g]

    # history
    def run_history(self, g):
        rng, lines = self.rng, self.ref["lines"][g]
        speed = {wk: SLOW_LINES.get(name, 1.0) * rng.uniform(0.85, 1.15) for name, wk in lines}
        m = dt.date(2026, 1, 1)
        yesterday = self.sb.today - dt.timedelta(days=1)
        while m <= yesterday:
            days = self._workdays(m)
            target = self._goal(g) * rng.uniform(*scale.PRODUCTION_ATTAINMENT)
            cells = []
            for d in days:
                for _, wk in lines:
                    if rng.random() < LINE_DOWN_P:
                        continue
                    cells.append((d, wk, speed[wk] * rng.uniform(0.8, 1.2)))
            total_w = sum(w for *_, w in cells) or 1
            month_jobdays = []
            for d, wk, w in cells:
                if d > yesterday:
                    continue
                qty = int(round(target * w / total_w))
                month_jobdays += self._run_day(g, wk, d, qty)
            self._scrap(g, month_jobdays)
            m = month_end(m) + dt.timedelta(days=1)

    def _run_day(self, g, wk, d, qty):
        """Run a line for a day; returns [(job, day, good_qty)] per job touched."""
        out = []
        while qty > 0:
            j = self.current.get(wk)
            if j is None:
                j = self._new_job(g, wk)
                self.current[wk] = j
            if j.start is None:
                j.start = d
                j.status = "Production"
            take = min(qty, j.qty - j.made)
            self._log(j, d, take)
            out.append((j, d, take))
            qty -= take
            if j.made >= j.qty:
                j.status = "Completed"
                j.end = d
                nxt = self._new_job(g, wk, prev=j)
                self.current[wk] = nxt
        return out

    def _log(self, j, d, qty):
        crew = self.crew[j.wc]
        if qty > 1 and j.group in SPLIT_GROUPS and self.rng.random() < SPLIT_P:
            a = int(qty * self.rng.uniform(0.35, 0.65))
            e1, e2 = self.rng.sample(crew, 2)
            j.records.append((self._at(d, SHIFT_UTC[0], 16), a, False, e1))
            j.records.append((self._at(d, 16, SHIFT_UTC[1]), qty - a, False, e2))
        else:
            j.records.append((self._at(d), qty, False, self.rng.choice(crew)))
        j.made += qty

    def _scrap(self, g, jobdays):
        if not jobdays:
            return
        rng = self.rng
        if g in scale.FPY:
            fpy = rng.gauss(scale.FPY[g], FPY_SD[g])
        else:
            fpy = rng.gauss(MINOR_FPY, MINOR_FPY_SD)
        fpy = min(max(fpy, 0.5), 0.99995)
        good = sum(q for *_, q in jobdays)
        scrap_total = good * (1 - fpy) / fpy
        p = SCRAP_DAY_P.get(g, DEFAULT_SCRAP_DAY_P)
        picked = [(j, d, q * rng.uniform(0.3, 1.7)) for j, d, q in jobdays
                  if q > 0 and rng.random() < p] or [max(jobdays, key=lambda x: x[2])]
        w = sum(x for *_, x in picked) or 1
        for j, d, x in picked:
            q = int(round(scrap_total * x / w))
            if q > 0:
                j.records.append((self._at(d), q, True, rng.choice(self.crew[j.wc])))

    # backlog at build time
    def fill_backlog(self, g):
        rng, today, lines = self.rng, self.sb.today, self.ref["lines"][g]
        # Lines whose job has not started yet are just the head of the queue.
        running = [j for j in self.current.values() if j.group == g]
        for j in running:
            if j.start is None:
                j.status = "Scheduled"
        have = sum(j.qty for j in running) + self.ref["real_open"].get(g, 0)
        target = OPEN_TARGET[g]
        k = 0
        while have < target:
            _, wk = lines[k % len(lines)]
            k += 1
            j = self._new_job(g, wk)
            step = JOB_SIZE[g][2]
            j.qty = min(j.qty, max(int(round((target - have) / step) * step), step))
            j.status = "Scheduled"
            have += j.qty

    def extras(self):
        """One Hold job on each of Encap and Bottling (excluded by the open
        views), and a few cancellations through the year."""
        rng, today = self.rng, self.sb.today
        for g in ("Encapsulating", "Bottling"):
            _, wk = rng.choice(self.ref["lines"][g])
            j = self._new_job(g, wk)
            j.status = "Hold"
            j.add = today - dt.timedelta(days=rng.randint(18, 40))
            for _ in range(2):
                _, wk = rng.choice(self.ref["lines"][g])
                c = self._new_job(g, wk)
                c.status = "Cancelled"
                c.add = dt.date(2026, 1, 1) + dt.timedelta(days=rng.randint(10, 230))

    # dates, keys, rows
    def rows(self):
        sb, rng, ref = self.sb, self.rng, self.ref
        today = sb.today
        for j in self.jobs:
            if j.add is None:
                if j.start is not None:
                    j.add = j.start - dt.timedelta(days=rng.randint(3, 21))
                elif j.status == "Scheduled":
                    j.add = today - dt.timedelta(days=rng.randint(0, 40))
                else:
                    j.add = today - dt.timedelta(days=rng.randint(1, 30))
            if j.status == "Scheduled" and j.start is None and (today - j.add).days <= 2:
                j.status = "New"
            base = j.add if j.status != "Scheduled" or j.start else max(j.add, today)
            j.due = base + dt.timedelta(days=rng.randint(10, 35))
            if j.records:
                j.records.sort(key=lambda r: r[0])
                j.starter = j.records[0][3]
                j.finisher = j.records[-1][3]
        # Keys and job numbers in the order the jobs were entered.
        self.jobs.sort(key=lambda j: (j.add, j.group, j.wc))
        for n, j in enumerate(self.jobs, 1):
            j.key = sb.key("production")
            j.op_key = sb.key("production")
            j.setup_key = sb.key("production")
        jobs, ops, prod = [], [], []
        for n, j in enumerate(self.jobs, 1):
            jobs.append(self._job_row(j, f"{TAG}-{n:05d}"))
            ops.append(self._op_row(j))
            prod += self._prod_rows(j)
        return jobs, ops, prod

    def _uuid(self):
        return str(uuid.UUID(int=self.rng.getrandbits(128), version=4))

    def _job_row(self, j, job_no):
        sb, T = self.sb, "raw_Part_v_Job"
        planner = self.rng.choice(self.ref["planners"]) if self.ref["planners"] else j.tjob["Add_By"]
        added = self._at(j.add, 13, 20)
        done = j.status == "Completed"
        last = j.records[-1][0] if j.records else added
        return sb.clone(
            T, j.tjob,
            Job_Key=j.key, Job_No=job_no, Quantity=float(j.qty),
            Job_Status_Key=self.ref["status"][j.status],
            Note="", Add_By=planner, Add_Date=sb.when(T, "Add_Date", added),
            Due_Date=sb.when(T, "Due_Date", dt.datetime(j.due.year, j.due.month, j.due.day, tzinfo=UTC)),
            Earliest_Start_Date=sb.when(T, "Earliest_Start_Date", added),
            Update_By=(j.finisher if j.records else planner),
            Update_Date=sb.when(T, "Update_Date", last + dt.timedelta(minutes=1) if j.records else added),
            Completed_By=(float(j.finisher) if done else None),
            Completed_Date=(sb.when(T, "Completed_Date", last + dt.timedelta(minutes=1)) if done else None),
            Resource_ID=self._uuid(),
        )

    def _op_row(self, j):
        sb, T, ops = self.sb, "raw_Part_v_Job_Op", self.ref["ops"]
        started = bool(j.records)
        done = j.status == "Completed"
        first = j.records[0][0] - dt.timedelta(minutes=15) if started else None
        last = j.records[-1][0] if started else None
        state = "done" if done else "running" if started else "open"
        return sb.clone(
            T, j.top,
            Job_Op_Key=j.op_key, Job_Key=j.key, Production_Job_Op_Key=j.op_key,
            Workcenter_Key=float(j.wc), Job_Op_Status_Key=ops[state],
            Started_By=(j.starter if started else 0),
            Start_Date=(sb.when(T, "Start_Date", first) if started else None),
            Completed_By=(j.finisher if done else 0),
            Complete_Date=(sb.when(T, "Complete_Date", last) if done else None),
            Update_By=(j.finisher if started else 0),
            Update_Date=(sb.when(T, "Update_Date", last) if started else None),
            Resource_ID=self._uuid(),
        )

    def _prod_rows(self, j):
        sb, T = self.sb, "raw_Part_v_Production"
        good_tmpl, scrap_tmpl = self.ref["prod_tmpl"][j.group], self.ref["scrap_tmpl"]
        out = []
        for when, qty, is_scrap, emp in j.records:
            tmpl = scrap_tmpl if is_scrap else good_tmpl
            midnight = dt.datetime(when.year, when.month, when.day, tzinfo=UTC)
            key = sb.key("production")
            out.append(sb.clone(
                T, tmpl,
                Production_No=key, Serial_No=f"{TAG}{key % 10_000_000:07d}",
                Report_Date=sb.when(T, "Report_Date", midnight + self.ref["report_offset"]),
                Quantity=float(qty),
                Record_Date=sb.when(T, "Record_Date", when), Record_By=emp,
                Part_Key=j.tjob["Part_Key"], Part_Operation_Key=j.top["Part_Operation_Key"],
                Workcenter_Key=j.wc, Job_Op_Key=j.op_key,
                Rejected=(self.ref["scrap_flag"] if is_scrap else 0),
                Gross_Weight=float(qty) * (tmpl.get("Piece_Weight") or 1.0),
                Net_Weight=float(qty) * (tmpl.get("Piece_Weight") or 1.0),
                Log_Key=sb.key("production"), Setup_Key=j.setup_key,
            ))
        return out


def _days(a, b):
    while a <= b:
        yield a
        a += dt.timedelta(days=1)
