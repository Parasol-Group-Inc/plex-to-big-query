"""Picking logic: job sets -> pick lines -> suggested containers. Pure functions (tests/test_picking_app.py).

A Plex job set (Part_v_Job_Set) is one blend job plus one Pre-Weigh job per ingredient (2026-11-20:
782 sets since go-live, 1,186 of 1,373 open jobs in one). A pick line is a (job, component) whose
component is NOT made by another job of the same set: for a blend set that leaves the raw materials
the Pre-Weigh jobs weigh out, and drops the weighed WIP the blend job consumes. Required quantity =
job quantity x job BOM quantity (Part_v_Job_Bom, the job's own BOM, not the part's).

Suggested containers: status OK, quantity > 0, not already in a staging or workcenter location,
first-expiring lot first (lot best-by, then oldest container), until the required quantity is covered.
Containers already in the target staging location count as staged.
"""
from __future__ import annotations

from collections import OrderedDict

# Where each workcenter group's picks are staged. The four staging locations exist in Plex
# (typed Storage; Plex's own "Staging" location type is unused). TO CONFIRM with the team.
STAGING_FOR_GROUP = {
    "Pre-Weigh": "Pre-Weigh Staging",
    "Blending": "Pre-Weigh Staging",
    "Encapsulating": "Packaging Staging",
    "Bottling": "Packaging Staging",
    "Packaging": "Packaging Staging",
    "Labeling": "Labeling Staging",
}
STAGING_LOCATIONS = ["Pre-Weigh Staging", "Packaging Staging", "Labeling Staging", "Quality Released Staging"]
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
                          "workcenter": j["workcenter"], "due": j["due"],
                          "target": STAGING_FOR_GROUP.get(j["group"], STAGING_LOCATIONS[0])})
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


def suggest(containers: list[dict], lots: list[dict], required: float, target: str,
            staging=STAGING_LOCATIONS, loc_group: dict | None = None) -> dict:
    """Classify a part's live containers for one pick line.

    Returns {rows: [...], staged_qty, picked_qty, short_qty}; each row has `role`:
    staged (already at target), pick (suggested), spare (OK, not needed), elsewhere-staged
    (in another staging location), not-here (location group not picked from, e.g. Retains),
    blocked (status not OK; reason in `why`). loc_group maps location -> Plex location group.
    """
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
    staged = [r for r in rows if r["location"] == target]
    for r in staged:
        r["role"] = "staged"
    need = max(0.0, required - sum(r["qty"] for r in staged if r["status"] in MOVABLE_STATUSES))
    rest = [r for r in rows if r["location"] != target]
    rest.sort(key=lambda r: (r["best_by"] or "9999", r["added"] or "9999", -r["qty"]))
    picked = 0.0
    for r in rest:
        if r["status"] not in MOVABLE_STATUSES:
            r["role"], r["why"] = "blocked", f"status {r['status']}"
        elif r["location"] in staging:
            r["role"], r["why"] = "elsewhere-staged", f"already staged at {r['location']}"
        elif pickable_from(r["location"], loc_group):
            r["role"], r["why"] = "not-here", pickable_from(r["location"], loc_group)
        elif picked < need - 1e-9:
            r["role"] = "pick"
            picked += r["qty"]
        else:
            r["role"] = "spare"
    order = {"staged": 0, "pick": 1, "spare": 2, "elsewhere-staged": 3, "not-here": 4, "blocked": 5}
    rows.sort(key=lambda r: (order[r["role"]], r["best_by"] or "9999", r["added"]))
    staged_qty = sum(r["qty"] for r in staged)
    return {"rows": rows, "staged_qty": round(staged_qty, 4), "picked_qty": round(picked, 4),
            "short_qty": round(max(0.0, need - picked), 4), "required": required, "target": target}


def check_movable(live: dict | None, target: str, allow_status=MOVABLE_STATUSES) -> str | None:
    """Why a container must not be moved right now (live API record), or None."""
    if not live:
        return "not found in Plex (consumed or wrong serial)"
    if (live.get("containerStatus") or "") not in allow_status:
        return f"status is {live.get('containerStatus')}, only {', '.join(sorted(allow_status))} is moved"
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
