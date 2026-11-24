"""Picking logic: job sets -> pick lines -> suggested containers. Pure functions (tests/test_picking_app.py).

A Plex job set (Part_v_Job_Set) is one blend job plus one Pre-Weigh job per ingredient (2026-11-20:
782 sets since go-live, 1,186 of 1,373 open jobs in one). A pick line is a (job, component) whose
component is NOT made by another job of the same set: for a blend set that leaves the raw materials
the Pre-Weigh jobs weigh out, and drops the weighed WIP the blend job consumes. Required quantity =
job quantity x job BOM quantity (Part_v_Job_Bom, the job's own BOM, not the part's).

Suggested containers: status OK, quantity > 0, not already in a staging or workcenter location,
first-expiring lot first (lot best-by, then oldest container), until the required quantity is covered.
Containers already at the chosen target count as staged; at another of the line's targets, as elsewhere-staged.
"""
from __future__ import annotations

from collections import OrderedDict

# Where picked material goes. Until 2026-11-23 the app sent everything to the four "... Staging"
# locations; Plex's own history (Part_v_Container_Change2) showed the team never stages for production:
# each container used at a work center was last moved to that work center's point of use (Pre-Weigh 1-3:
# the PW bins B7-B10/A3/A4/B6; Encapsulation: the machine or the A*/C* CSR racks; Bottling, Labeling,
# First 48: the line itself). Targets are now those destinations (destinations_sql + destination_options);
# the Staging locations stay at the end of the list for whoever wants them.
STAGING_LOCATIONS = ["Pre-Weigh Staging", "Packaging Staging", "Labeling Staging", "Quality Released Staging"]
DEST_DAYS = int(__import__("os").environ.get("PICKING_DEST_DAYS", "45"))
# Moving into these location groups is putaway or shipping, not picking.
DEST_SKIP_GROUPS = {"Warehouse", "Shipping", "Retains", "Quarantine"}


def destinations_sql(days: int = DEST_DAYS) -> str:
    """For every container used up ('Retired at <work center>') in the last `days` days: where it was last
    moved before that. One row per (work center, group, location) with the number of containers."""
    days = int(days)
    return f"""
WITH ret AS (
  SELECT c.Serial_No, c.Change_Date, REPLACE(c.Last_Action, 'Retired at ', '') AS used_at
  FROM Part_v_Container_Change2 AS c
  WHERE c.Last_Action LIKE 'Retired at %' AND c.Change_Date >= DATEADD(day, -{days}, GETDATE())),
mv AS (
  SELECT r.used_at,
    (SELECT TOP 1 m.Location FROM Part_v_Container_Change2 AS m
     WHERE m.Serial_No = r.Serial_No AND m.Change_Date <= r.Change_Date
       AND m.Last_Action IN ('Container Move', 'Master Unit Move') ORDER BY m.Change_Date DESC) AS to_location
  FROM ret AS r)
SELECT x.used_at AS Workcenter_Code, w.Workcenter_Group, x.to_location AS Location, COUNT(*) AS Containers
FROM mv AS x LEFT JOIN Part_v_Workcenter AS w ON w.Workcenter_Code = x.used_at
WHERE x.to_location IS NOT NULL
GROUP BY x.used_at, w.Workcenter_Group, x.to_location"""


def destination_options(rows: list[dict], workcenter: str, group: str, loc_group: dict | None = None,
                        top: int = 8, min_share: float = 0.01, min_wc: int = 20) -> list[dict]:
    """Target choices for one pick line, most used first: [{location, uses, basis}].

    Uses the line's own work center when it has at least `min_wc` containers of history (a real
    machine), else the whole work center group (jobs often sit on a "SCHED - ..." placeholder).
    Drops putaway/shipping groups and anything under `min_share` of the basis. The Staging locations
    are appended (uses 0) so they can still be chosen."""
    def tally(match):
        out: dict = {}
        for r in rows:
            if match(r):
                out[r["Location"]] = out.get(r["Location"], 0) + int(float(r.get("Containers") or 0))
        return out
    counts = tally(lambda r: workcenter and r.get("Workcenter_Code") == workcenter)
    basis = workcenter
    if sum(counts.values()) < min_wc:
        counts, basis = tally(lambda r: group and r.get("Workcenter_Group") == group), group
    total = sum(counts.values()) or 1
    opts = []
    for loc, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if loc_group is not None and loc_group.get(loc) in DEST_SKIP_GROUPS:
            continue
        if n / total < min_share or len(opts) >= top:
            continue
        opts.append({"location": loc, "uses": n, "basis": basis})
    for loc in STAGING_LOCATIONS:
        if loc not in {o["location"] for o in opts}:
            opts.append({"location": loc, "uses": 0, "basis": "staging (rarely used)"})
    return opts


MOVABLE_STATUSES = {"OK"}   # Plex itself moves Hold containers without asking (TEST 11-20): we refuse
# Only these Plex location groups are picked from. On 11-20 the first TEST pick lists suggested
# dozens of ~0.05 retain samples in R5-3, "R and D", Ship and "z**DO NOT USE**": those sit in other
# groups (Retains, Sample Room, Shipping, Quality Holding, Quarantine, ...). Env PICKING_FROM_GROUPS.
import os as _os
PICK_FROM_GROUPS = {g.strip() for g in _os.environ.get("PICKING_FROM_GROUPS", "Warehouse").split(",") if g.strip()}
# "R and D" is in the Warehouse group but holds 0.1-unit samples (TEST 11-20). Env PICKING_EXCLUDE_LOCATIONS.
EXCLUDE_LOCATIONS = {g.strip() for g in _os.environ.get("PICKING_EXCLUDE_LOCATIONS", "R and D").split(",") if g.strip()}

LOCATIONS_SQL = """
SELECT l.Location, g.Location_Group, l.Location_Type
FROM Common_v_Location l LEFT JOIN Common_v_Location_Group g ON g.Location_Group_Key = l.Location_Group_Key
WHERE l.Active = 1"""

OPEN_STATUSES = ("Scheduled", "Production")


def job_sets_sql(days: int, overdue: int = 14) -> str:
    """Every row of every job set with an open member job due within `days` days, or overdue by at
    most `overdue` days (TEST and prod still carry October jobs marked Scheduled)."""
    days, overdue = int(days), int(overdue)
    return f"""
SELECT s.Job_Set_No, CONVERT(varchar(10), s.Due_Date, 120) AS Set_Due,
       j.Job_No, LOWER(CAST(j.Resource_ID AS varchar(40))) AS Job_Id, js.Job_Status,
       CONVERT(varchar(10), j.Due_Date, 120) AS Job_Due, j.Quantity AS Job_Qty,
       p.Part_No, LOWER(CAST(p.Resource_ID AS varchar(40))) AS Part_Id,
       w.Workcenter_Code, w.Workcenter_Group, o.Op_No,
       cp.Part_No AS Component_Part_No, LOWER(CAST(cp.Resource_ID AS varchar(40))) AS Component_Part_Id,
       cp.Part_Type AS Component_Type, b.Quantity AS Bom_Qty
FROM Part_v_Job_Set s
JOIN Part_v_Job_Set_Member m ON m.Job_Set_Key = s.Job_Set_Key
JOIN Part_v_Job j ON j.Job_Key = m.Job_Key
JOIN Part_v_Job_Status js ON js.Job_Status_Key = j.Job_Status_Key
JOIN Part_v_Part p ON p.Part_Key = j.Part_Key
LEFT JOIN Part_v_Job_Op o ON o.Job_Key = j.Job_Key
LEFT JOIN Part_v_Workcenter w ON w.Workcenter_Key = o.Workcenter_Key
LEFT JOIN Part_v_Job_Bom b ON b.Job_Op_Key = o.Job_Op_Key AND b.Active = 1
LEFT JOIN Part_v_Part cp ON cp.Part_Key = b.Component_Part_Key
WHERE s.Job_Set_Key IN (
  SELECT m2.Job_Set_Key FROM Part_v_Job_Set_Member m2
  JOIN Part_v_Job j2 ON j2.Job_Key = m2.Job_Key
  JOIN Part_v_Job_Status js2 ON js2.Job_Status_Key = j2.Job_Status_Key
  WHERE js2.Job_Status IN ('Scheduled', 'Production') AND j2.Due_Date < DATEADD(day, {days}, GETDATE())
    AND j2.Due_Date >= DATEADD(day, -{overdue}, CAST(GETDATE() AS date)))
ORDER BY s.Job_Set_No, j.Job_No, o.Op_No"""


def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def build_sets(rows: list[dict]) -> "OrderedDict[str, dict]":
    """Rows of job_sets_sql -> {set_no: {set_no, due, jobs: {job_no: {...}}, lines: [...], main}}."""
    sets: "OrderedDict[str, dict]" = OrderedDict()
    for r in rows:
        s = sets.setdefault(r["Job_Set_No"], {"set_no": r["Job_Set_No"], "due": r.get("Set_Due") or "",
                                              "jobs": OrderedDict(), "bom": []})
        j = s["jobs"].setdefault(r["Job_No"], {
            "job_no": r["Job_No"], "job_id": r.get("Job_Id"), "status": r.get("Job_Status"), "due": r.get("Job_Due") or "",
            "qty": _f(r.get("Job_Qty")), "part_no": r.get("Part_No"), "part_id": r.get("Part_Id"),
            "workcenter": r.get("Workcenter_Code") or "", "group": r.get("Workcenter_Group") or ""})
        if not j["workcenter"] and r.get("Workcenter_Code"):
            j["workcenter"], j["group"] = r["Workcenter_Code"], r.get("Workcenter_Group") or ""
        if r.get("Component_Part_Id"):
            s["bom"].append((r["Job_No"], r["Component_Part_No"], r["Component_Part_Id"],
                             r.get("Component_Type") or "", _f(r.get("Bom_Qty"))))
    for s in sets.values():
        made_here = {j["part_id"] for j in s["jobs"].values()}
        seen, lines = set(), []
        for job_no, comp_no, comp_id, comp_type, bom_qty in s["bom"]:
            j = s["jobs"][job_no]
            if comp_id in made_here and comp_id != j["part_id"]:
                continue                       # weighed WIP made by a sibling job: not picked from stock
            if (job_no, comp_id) in seen or j["status"] not in OPEN_STATUSES:
                continue
            seen.add((job_no, comp_id))
            lines.append({"job_no": job_no, "part_no": comp_no, "part_id": comp_id, "type": comp_type,
                          "required": round(j["qty"] * bom_qty, 4), "group": j["group"],
                          "workcenter": j["workcenter"], "due": j["due"], "target": ""})
        s["lines"] = lines
        main = max(s["jobs"].values(), key=lambda j: (j["group"] != "Pre-Weigh", j["due"] or ""))
        s["main"] = main
        s["open_jobs"] = sum(j["status"] in OPEN_STATUSES for j in s["jobs"].values())
        del s["bom"]
    return sets


def pickable_from(location: str, loc_group: dict | None) -> str | None:
    """Why stock in `location` is not picked from (None = pickable). loc_group None = no filter."""
    if "DO NOT USE" in (location or "").upper():
        return "location marked DO NOT USE"
    if location in EXCLUDE_LOCATIONS:
        return "excluded location (samples)"
    if loc_group is None:
        return None
    g = loc_group.get(location)
    if g not in PICK_FROM_GROUPS:
        return f"location group {g or 'none'}"
    return None


ALLOCATED = "Allocated"


def allocations_sql(part_id: str) -> str:
    """Which job each active container of a part is allocated to (Part_v_Job_Allocation). The REST API has
    no allocation endpoint (tested 11-23): it only shows containerStatus "Allocated", live. In production this
    reads Plex's reporting copy (about 4 h behind), so a new allocation can be missing: see check_movable."""
    pid = str(part_id).replace("'", "''").lower()
    return f"""
SELECT a.Container_Serial_No AS Serial_No, j.Job_No, a.Quantity
FROM Part_v_Job_Allocation AS a
JOIN Part_v_Job AS j ON j.Job_Key = a.Job_Key
JOIN Part_v_Container AS c ON c.Serial_No = a.Container_Serial_No
JOIN Part_v_Part AS p ON p.Part_Key = c.Part_Key
WHERE c.Active = 1 AND LOWER(CAST(p.Resource_ID AS varchar(40))) = '{pid}'"""


def alloc_map(rows: list[dict]) -> dict:
    """allocations_sql rows -> {serial: [job_no, ...]}."""
    out: dict = {}
    for r in rows:
        out.setdefault(r["Serial_No"], [])
        if r.get("Job_No") and r["Job_No"] not in out[r["Serial_No"]]:
            out[r["Serial_No"]].append(r["Job_No"])
    return out


def allocation_why(serial: str, status: str, job_no: str | None, alloc: dict | None) -> tuple[bool, str | None]:
    """(for_this_job, why_not) for a container. Allocated to this job -> (True, None). Allocated elsewhere or to a
    job the copy does not show yet -> (False, reason). Not allocated -> (False, None)."""
    jobs = (alloc or {}).get(serial) or []
    if status != ALLOCATED and not jobs:
        return False, None
    if job_no and job_no in jobs:
        return True, None
    if jobs:
        return False, f"allocated to job {', '.join(jobs)}"
    return False, "allocated to a job Plex's copy does not show yet (up to 4 h behind)"


def suggest(containers: list[dict], lots: list[dict], required: float, target: str,
            staging=STAGING_LOCATIONS, loc_group: dict | None = None, job_no: str | None = None,
            alloc: dict | None = None, claimed: dict | None = None) -> dict:
    """Classify a part's live containers for one pick line (2026-11-23 audit fixes: allocations + netting).

    The floor stages per job through Plex job allocations (71% of containers moved into PW bins were status
    Allocated at the move). So, in order:
      1. containers allocated to THIS line's job: "staged" if at the target, else "pick" (from any location
         that is not DO NOT USE), first;
      2. OK, unallocated, unclaimed containers already at the target: "staged" until the need is covered,
         then "there-spare";
      3. OK, unallocated, unclaimed containers in pickable locations, first-expiring first: "pick" until covered,
         then "spare".
    `claimed` = {serial: "set 757 job 3806 (due 11-16)"} for containers earlier-due lines of the same part use
    (app.net_claims): shown as "reserved", never counted twice. Allocated to another job: "reserved".
    Returns {rows, staged_qty, picked_qty, short_qty, claims (serials this line uses), ...}."""
    claimed = claimed or {}
    best_by = {l.get("id"): (l.get("bestByDateTime") or l.get("useByDateTime") or "") for l in lots}
    rows = []
    for c in containers:
        if _f(c.get("quantity")) <= 0:
            continue
        rows.append({
            "serial": c.get("serialNo"), "lp": c.get("masterUnitNo") or "", "lot": c.get("lotNo") or "",
            "best_by": (best_by.get(c.get("lotId")) or "")[:10], "location": c.get("location") or "",
            "status": c.get("containerStatus") or "", "qty": _f(c.get("quantity")),
            "added": (c.get("addDateTime") or "")[:19], "updated": (c.get("updateDateTime") or "")[:19]})
    fefo = lambda r: (r["best_by"] or "9999", r["added"] or "9999", -r["qty"])
    rows.sort(key=fefo)
    covered = picked = 0.0
    claims = []
    for r in rows:                                    # 1. allocated to this job
        mine, why = allocation_why(r["serial"], r["status"], job_no, alloc)
        r["alloc_why"] = why
        if mine:
            r["why"] = f"allocated to this job ({job_no})"
            if "DO NOT USE" in r["location"].upper():
                r["role"] = "blocked"; r["why"] += "; location DO NOT USE"
            elif r["location"] == target or r["location"] in staging:
                # already where the floor stages for this work center (a PW bin ...): there, whichever bin
                r["role"] = "staged"; covered += r["qty"]; claims.append(r["serial"])
                if r["location"] != target:
                    r["why"] += f", already at {r['location']}"
            else:
                r["role"] = "pick"; picked += r["qty"]; claims.append(r["serial"])
    for r in rows:                                    # 2. already at the target
        if r.get("role") or r["location"] != target:
            continue
        if r["serial"] in claimed:
            r["role"], r["why"] = "reserved", f"for {claimed[r['serial']]}"
        elif r["alloc_why"]:
            r["role"], r["why"] = "reserved", r["alloc_why"]
        elif r["status"] not in MOVABLE_STATUSES:
            r["role"], r["why"] = "blocked", f"status {r['status']}"
        elif covered + picked < required - 1e-9:
            r["role"] = "staged"; covered += r["qty"]; claims.append(r["serial"])
        else:
            r["role"], r["why"] = "there-spare", "at the target, not needed for this line"
    for r in rows:                                    # 3. pick from stock
        if r.get("role"):
            continue
        if r["serial"] in claimed:
            r["role"], r["why"] = "reserved", f"for {claimed[r['serial']]}"
        elif r["alloc_why"]:
            r["role"], r["why"] = ("reserved" if r["alloc_why"].startswith("allocated to job") else "blocked"), r["alloc_why"]
        elif r["status"] not in MOVABLE_STATUSES:
            r["role"], r["why"] = "blocked", f"status {r['status']}"
        elif r["location"] in staging:
            r["role"], r["why"] = "elsewhere-staged", f"at {r['location']}"
        elif pickable_from(r["location"], loc_group):
            r["role"], r["why"] = "not-here", pickable_from(r["location"], loc_group)
        elif covered + picked < required - 1e-9:
            r["role"] = "pick"; picked += r["qty"]; claims.append(r["serial"])
        else:
            r["role"] = "spare"
    order = {"staged": 0, "pick": 1, "spare": 2, "there-spare": 3, "elsewhere-staged": 4, "reserved": 5, "not-here": 6, "blocked": 7}
    rows.sort(key=lambda r: (order[r["role"]], *fefo(r)))
    need = max(0.0, required - covered)
    return {"rows": rows, "staged_qty": round(covered, 4), "picked_qty": round(picked, 4),
            "short_qty": round(max(0.0, need - picked), 4), "required": required, "target": target, "claims": claims,
            "reserved_n": sum(r["role"] == "reserved" for r in rows)}


def default_target(options: list[dict], containers: list[dict], job_no: str | None, alloc: dict | None) -> str:
    """The line's default target: the destination where this job's allocated containers already are (the floor
    already chose it), else the most used destination. Found 11-23 on set 544: job 2305's containers were in
    PW - B8 while the most used bin is PW - B9, so the app suggested moving them bin to bin."""
    locs = {o["location"] for o in options}
    here: dict = {}
    for c in containers:
        if job_no and job_no in ((alloc or {}).get(c.get("serialNo")) or []) and c.get("location") in locs:
            here[c["location"]] = here.get(c["location"], 0) + 1
    if here:
        return max(here.items(), key=lambda kv: kv[1])[0]
    return options[0]["location"]


def check_movable(live: dict | None, target: str, allow_status=MOVABLE_STATUSES, job_no: str | None = None,
                  alloc: dict | None = None) -> str | None:
    """Why a container must not be moved right now (live API record), or None. Status OK moves; status
    Allocated moves only when it is allocated to this line's job (`alloc` from allocations_sql)."""
    if not live:
        return "not found in Plex (consumed or wrong serial)"
    st = live.get("containerStatus") or ""
    mine, why = allocation_why(live.get("serialNo"), st, job_no, alloc)
    if why:
        return why
    if st not in allow_status and not (mine and st == ALLOCATED):
        return f"status is {st}, only {', '.join(sorted(allow_status))} (or allocated to this job) is moved"
    if (live.get("location") or "") == target:
        return f"already at {target}"
    if _f(live.get("quantity")) <= 0:
        return "quantity is 0"
    return None


def plan_moves(selected: list[str], part_containers: list[dict]) -> list[tuple[str, list[str]]]:
    """Group ticked serials into moves: a pallet (LP) whose containers of this part are ALL ticked
    moves as the LP, in one call, and stays a pallet; any other serial moves alone. Plex takes a
    container moved alone off its LP (TEST 11-20: LP-087265's 4 containers, moved back one by one,
    all lost the LP and the LP went inactive). Returns [(what_to_move, [serials covered])]."""
    by_serial = {c.get("serialNo"): c for c in part_containers}
    lp_members: dict[str, set] = {}
    for c in part_containers:
        if c.get("masterUnitNo") and _f(c.get("quantity")) > 0:
            lp_members.setdefault(c["masterUnitNo"], set()).add(c["serialNo"])
    chosen, moves, done = set(selected), [], set()
    for s in selected:
        if s in done:
            continue
        lp = (by_serial.get(s) or {}).get("masterUnitNo")
        if lp and lp_members.get(lp) and lp_members[lp] <= chosen:
            members = sorted(lp_members[lp])
            moves.append((lp, members))
            done.update(members)
        else:
            moves.append((s, [s]))
            done.add(s)
    return moves


def breaks_pallet(serial: str, selected: list[str], part_containers: list[dict]) -> str | None:
    """The LP a serial leaves if moved alone (some of its pallet mates are not ticked), else None."""
    lp = next((c.get("masterUnitNo") for c in part_containers if c.get("serialNo") == serial), None)
    if not lp:
        return None
    mates = {c["serialNo"] for c in part_containers if c.get("masterUnitNo") == lp and _f(c.get("quantity")) > 0}
    return None if mates <= set(selected) else lp
