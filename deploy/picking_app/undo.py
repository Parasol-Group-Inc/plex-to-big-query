"""Undo for picking-app moves, from the Move log page (2026-11-23). Pure functions; app.py wires them.

Why a time limit and a "nothing happened since" rule (evidence, Plex history in the TEST copy, 45 days to 11-21):
after a move, the next Plex change on the same container came within

    moved to              5 min   1 h    24 h   (next action: loaded to work center, job allocation,
    Bottling lines         17%    37%    79%     pallet change, mass update, moved again ...)
    Labeling lines         20%    49%    92%
    Encapsulation / CSR    26%    30%    35%
    PW bins (Pre-Weigh)     2%     8%    50%

Once the floor has loaded, allocated, split or re-palleted a container, moving it back undoes their work
and Plex's records of it. So undo is offered only for UNDO_MINUTES (default 30) after the move, and only
for containers that are exactly as we left them: live record (location, quantity, status, pallet) equal to
the record read right after our move, and no change in Plex's history since other than our own move. For
anything else the page shows the detailed activity since the move instead of a button.

Plex history (Part_v_Container_Change2) is read through the SQL screen. Its times are Plex server time
(US Eastern, PLEX_TZ); in production it is Plex's reporting copy (about 4 h behind), so the LIVE record
check is the one that cannot miss a location, quantity, status or pallet change.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

UNDO_MINUTES = int(os.environ.get("PICKING_UNDO_MINUTES", "30"))
PLEX_TZ = ZoneInfo(os.environ.get("PLEX_TZ", "America/New_York"))
MOVE_ACTIONS = {"Container Move", "Master Unit Move", "Master Unit Moved"}
COMPARE = (("location", "location"), ("quantity", "quantity"), ("containerStatus", "status"), ("masterUnitNo", "pallet"))


def history_sql(serials: list[str], since_utc: dt.datetime) -> str:
    """Every Plex change to these containers since `since_utc` (minus 2 min), with the user's name and the LP."""
    since = since_utc.astimezone(PLEX_TZ).replace(tzinfo=None) - dt.timedelta(minutes=2)
    inl = ",".join("'" + s.replace("'", "''") + "'" for s in serials)
    return f"""
SELECT c.Serial_No, c.Change_Key, CONVERT(varchar(23), c.Change_Date, 121) AS Change_Date, c.Last_Action, c.Location,
       c.Quantity, c.Container_Status, mu.Master_Unit_No, c.Change_By, u.User_ID, u.First_Name, u.Last_Name
FROM Part_v_Container_Change2 AS c
LEFT JOIN Plexus_Control_v_Plexus_User AS u ON u.Plexus_User_No = c.Change_By
LEFT JOIN Part_v_Master_Unit AS mu ON mu.Master_Unit_Key = c.Master_Unit_Key
WHERE c.Serial_No IN ({inl}) AND c.Change_Date >= '{since:%Y-%m-%d %H:%M:%S}'
ORDER BY c.Serial_No, c.Change_Date, c.Change_Key"""


def plex_time_utc(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s[:19]).replace(tzinfo=PLEX_TZ).astimezone(dt.timezone.utc)


def _utc(x) -> dt.datetime:
    if isinstance(x, dt.datetime):
        return x if x.tzinfo else x.replace(tzinfo=dt.timezone.utc)
    return dt.datetime.fromisoformat(str(x).replace("Z", "+00:00").replace(" ", "T", 1)).astimezone(dt.timezone.utc)


def _num(v):
    try:
        return round(float(v), 6)
    except (TypeError, ValueError):
        return v or None


def activity_since(row: dict, history: list[dict]) -> list[dict]:
    """Plex changes to this container after our move, without our move itself."""
    moved_at = _utc(row["at"])
    out = []
    for h in history:
        if h.get("Serial_No") != row["serial"]:
            continue
        t = plex_time_utc(h["Change_Date"])
        ours = (h.get("Last_Action") in MOVE_ACTIONS and h.get("Location") == row.get("to_location")
                and abs((t - moved_at).total_seconds()) <= 120)
        if t < moved_at - dt.timedelta(seconds=120) or ours:
            continue
        who = " ".join(x for x in (h.get("First_Name"), h.get("Last_Name")) if x) or f"user {h.get('Change_By')}"
        out.append({"at_utc": t.isoformat(), "action": h.get("Last_Action"), "location": h.get("Location"),
                    "quantity": _num(h.get("Quantity")), "status": h.get("Container_Status"), "pallet": h.get("Master_Unit_No"),
                    "by": who + (f" ({h['User_ID']})" if h.get("User_ID") else "")})
    return out


def check(row: dict, live: dict | None, history: list[dict], now: dt.datetime, minutes: int = UNDO_MINUTES) -> dict:
    """Can this moved container be put back? {serial, ok, back, reasons, activity, now, was}."""
    age = (now - _utc(row["at"])).total_seconds() / 60
    after = json.loads(row["after_json"]) if row.get("after_json") else {"location": row.get("to_location")}
    reasons, activity = [], activity_since(row, history)
    back = bool(live) and live.get("location") == row.get("from_location")
    if age > minutes:
        reasons.append(f"moved {age:.0f} min ago; undo is offered for {minutes} min after a move")
    if not live:
        reasons.append("not found in Plex now")
    elif not back:
        for k, label in COMPARE:
            if k in after and _num(after.get(k)) != _num(live.get(k)):
                reasons.append(f"{label} is now {live.get(k) or 'none'} (was {after.get(k) or 'none'} right after our move)")
    if activity and not back:
        reasons.append(f"{len(activity)} change(s) in Plex since our move")
    return {"serial": row["serial"], "ok": not reasons and not back, "back": back, "reasons": reasons, "activity": activity,
            "age_min": round(age, 1), "moved_as": row.get("moved_as"), "from": row.get("from_location"), "to": row.get("to_location"),
            "now": (live or {}).get("location"), "qty": (live or {}).get("quantity"), "left_pallet": row.get("left_pallet")}


def batches(rows: list[dict], now: dt.datetime, minutes: int = UNDO_MINUTES) -> list[dict]:
    """Log rows -> one summary per batch (newest first) for the Move log page."""
    out: dict = {}
    for r in rows:
        if (r.get("event") or "move") not in ("move", "refused", "restore"):
            continue
        key = r.get("batch_id") or f"{r.get('at')}|{r.get('serial')}"
        b = out.setdefault(key, {"batch_id": r.get("batch_id"), "at": r.get("at"), "by": r.get("requested_by"), "env": r.get("env"),
                                 "set_no": r.get("set_no"), "job_no": r.get("job_no"), "part_no": r.get("part_no"),
                                 "to": r.get("to_location"), "moved": 0, "failed": 0, "refused": 0, "restored": 0, "rows": []})
        b["rows"].append(r)
        ev = r.get("event") or "move"
        if ev == "move":
            b["moved" if r.get("ok") in (True, "true", "True") else "failed"] += 1
        elif ev == "refused":
            b["refused"] += 1
        else:
            b["restored"] += r.get("ok") in (True, "true", "True")
        if str(r.get("at")) < str(b["at"]):
            b["at"] = r.get("at")
    for k, b in out.items():                            # restore batches count back on the batch they undid
        if b["batch_id"] and b["batch_id"].startswith("restore-") and b["batch_id"][8:] in out:
            out[b["batch_id"][8:]]["restored"] += b["restored"]
    res = sorted(out.values(), key=lambda b: str(b["at"]), reverse=True)
    for b in res:
        age = (now - _utc(b["at"])).total_seconds() / 60
        b["age_min"] = round(age)
        b["undo_open"] = bool(b["batch_id"]) and not b["batch_id"].startswith("restore-") and b["moved"] > 0 and age <= minutes
        b["undo_left_min"] = max(0, round(minutes - age))
    return res
