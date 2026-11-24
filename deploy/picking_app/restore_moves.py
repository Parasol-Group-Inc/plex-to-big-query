"""Put picking-app moves back where they were (2026-11-23). Dry run unless --apply.

    python deploy/picking_app/restore_moves.py --batch 3f9c0a1b2c4d            # what it would do
    python deploy/picking_app/restore_moves.py --batch 3f9c0a1b2c4d --apply    # do it (Plex TEST)
    python deploy/picking_app/restore_moves.py --batch ... --apply --prod      # production: asks you to type RESTORE
    python deploy/picking_app/restore_moves.py --serial S029901 --since 2026-11-23   # by container instead of batch
    python deploy/picking_app/restore_moves.py --log etl-manual/picking_moves.jsonl --batch ...   # from a JSON lines log

Reads the app's move log (BigQuery PlexOps.picking_move_log, event = 'move', ok; or a JSON lines file),
reads every container live from Plex's REST API, and decides per container:
- already back at its old location: nothing to do;
- moved again since (no longer at the location we moved it to): skipped, unless --force;
- moved as a whole pallet and the pallet is still together at the target: the pallet is moved back in one call;
- otherwise the container is moved back on its own.
Moves go through Plex's Move Container screen request with a Playwright login (plex_web.PlexWeb), the
same way the app moves them, and each is read back. A container that LEFT its pallet when it was moved
is not put back on the pallet by moving it (Plex's Add to Master Unit screen does that): the tool says so.
Every action is written to the JSON lines log (PICKING_LOG, default etl-manual/picking_moves.jsonl) and to
BigQuery when it can (event = 'restore', batch_id = 'restore-<batch>').
docs/PICKING_STAGING_APP.md, "Restoring moves".
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "scripts")]
LOG = Path(os.environ.get("PICKING_LOG", HERE.parents[1] / "etl-manual" / "picking_moves.jsonl"))


def load_rows(batch: str | None, serials: list[str], since: str | None, log: str | None) -> list[dict]:
    """The log's successful 'move' rows (oldest first) for a batch and/or serials."""
    if log:
        rows = [json.loads(l) for l in Path(log).read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        from google.cloud import bigquery
        where, params = ["event IN ('move', 'sent')"], []
        if batch:
            where.append("batch_id = @batch"); params.append(bigquery.ScalarQueryParameter("batch", "STRING", batch))
        if serials:
            where.append("serial IN UNNEST(@serials)"); params.append(bigquery.ArrayQueryParameter("serials", "STRING", serials))
        if since:
            where.append("`at` >= TIMESTAMP(@since)"); params.append(bigquery.ScalarQueryParameter("since", "STRING", since))
        q = f"SELECT * FROM `voxdatalake.PlexOps.picking_move_log` WHERE {' AND '.join(where)} ORDER BY `at`"
        rows = [dict(r) for r in bigquery.Client(project="voxdatalake").query(
            q, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()]
    import undo
    keep = [r for r in rows if (not serials or r.get("serial") in serials) and (not since or str(r.get("at")) >= since)]
    out = []
    for b in dict.fromkeys(r.get("batch_id") for r in keep if not batch or r.get("batch_id") == batch):
        out += undo.moved_rows(keep, b)                 # verified 'move' rows, else Plex-confirmed 'sent' rows
    return sorted(out, key=lambda r: str(r.get("at")))


def plan_restore(rows: list[dict], live: dict, all_rows: list[dict] | None = None, lp_members=None) -> list[dict]:
    """Pure: log rows + {serial: live API record or None} -> actions.

    Each action: {kind: 'pallet' | 'container' | 'skip' | 'done', send, to, serials, why, note}.
    The LAST logged move of a container wins (restore to where it was before that move).
    A pallet is sent back whole only when (audit 11-23 #1) every container we moved on it is in `rows` (all_rows =
    the whole batch; rows = those that passed the checks) and lp_members(lp, serial) -> the pallet's live members
    equals exactly those containers. Otherwise the containers in `rows` go back one by one (leaving the pallet)."""
    last: "OrderedDict[str, dict]" = OrderedDict()
    for r in rows:
        last.pop(r["serial"], None)
        last[r["serial"]] = r
    by_item: "OrderedDict[str, list]" = OrderedDict()
    for s, r in last.items():
        by_item.setdefault(r.get("moved_as") or s, []).append(r)
    actions = []
    for item, rs in by_item.items():
        pallet = item not in {r["serial"] for r in rs}
        ready, rest = [], []
        for r in rs:
            now = (live.get(r["serial"]) or {})
            loc = now.get("location")
            note = (f"left pallet {r['left_pallet']} when moved: moving it back does not put it back on the pallet "
                    f"(Plex screen Add to Master Unit)") if r.get("left_pallet") else None
            if not now:
                actions.append({"kind": "skip", "serials": [r["serial"]], "why": "not found in Plex now", "note": note})
            elif loc == r.get("from_location"):
                actions.append({"kind": "done", "serials": [r["serial"]], "why": f"already back at {loc}", "note": note})
            elif loc != r.get("to_location"):
                actions.append({"kind": "skip", "serials": [r["serial"]], "to": r.get("from_location"),
                                "why": f"moved again since: now at {loc}, not {r.get('to_location')}", "note": note,
                                "send": r["serial"]})
            else:
                (ready if pallet and now.get("masterUnitNo") == item else rest).append((r, note))
        froms = {r.get("from_location") for r, _ in ready}
        whole = {r["serial"] for r in (all_rows or rs) if (r.get("moved_as") or r["serial"]) == item}
        on_lp = sorted(lp_members(item, ready[0][0]["serial"]) or []) if (pallet and ready and lp_members) else None
        same_lp = on_lp is None or set(on_lp) == whole
        if ready and len(froms) == 1 and len(ready) == len(rs) and {r["serial"] for r, _ in ready} == whole and same_lp:
            actions.append({"kind": "pallet", "send": item, "to": froms.pop(), "serials": [r["serial"] for r, _ in ready],
                            "why": f"whole pallet {item} back in one call", "note": None})
        else:
            if pallet and ready:
                why_split = (f"pallet {item} now holds {', '.join(sorted(set(on_lp or []) ^ whole)) or 'other containers'}"
                             if not same_lp else f"not every container moved on pallet {item} can go back")
                ready = [(r, f"{why_split}: goes back on its own and leaves the pallet") for r, _ in ready]
            rest = ready + rest
        for r, note in rest:
            actions.append({"kind": "container", "send": r["serial"], "to": r.get("from_location"), "serials": [r["serial"]],
                            "why": "container back on its own", "note": note})
    return actions


def write_log(rec: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    try:
        from google.cloud import bigquery
        errs = bigquery.Client(project="voxdatalake").insert_rows_json(
            "voxdatalake.PlexOps.picking_move_log", [rec], ignore_unknown_values=True)
        if errs:
            print("  (BigQuery log refused:", errs, ")")
    except Exception as e:  # noqa: BLE001 - the file log has it
        print(f"  (BigQuery log not written: {str(e)[:120]}; the file log has it)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--batch")
    ap.add_argument("--serial", action="append", default=[])
    ap.add_argument("--since", help="only moves at or after this time (UTC, e.g. 2026-11-23 or 2026-11-23T16:00)")
    ap.add_argument("--log", help="read a JSON lines log instead of BigQuery")
    ap.add_argument("--apply", action="store_true", help="really move (default: dry run)")
    ap.add_argument("--force", action="store_true", help="also move back containers moved again since")
    ap.add_argument("--prod", action="store_true")
    a = ap.parse_args()
    if not (a.batch or a.serial):
        ap.error("give --batch or --serial")
    env = "prod" if a.prod else "test"
    from plex_api import PlexApi
    api = PlexApi(env)
    rows = load_rows(a.batch, a.serial, a.since, a.log)
    envs = {r.get("env") for r in rows}
    if rows and envs != {env}:
        sys.exit(f"the log rows are for {sorted(envs)}, not {env}: pass --prod for production rows")
    print(f"{len(rows)} logged move(s); reading {len({r['serial'] for r in rows})} container(s) live from Plex {env.upper()}")
    live = {s: api.container(s) for s in dict.fromkeys(r["serial"] for r in rows)}
    def members(lp, serial):
        loc = (live.get(serial) or {}).get("locationId")
        return [c.get("serialNo") for c in api.containers_at(loc) if c.get("masterUnitNo") == lp] if loc else None
    actions = plan_restore(rows, live, all_rows=rows, lp_members=members)
    for x in actions:
        if x["kind"] == "skip" and a.force and x.get("send"):
            x.update(kind="container", why=x["why"] + " (forced)")
    for x in actions:
        tgt = f" -> {x['to']}" if x.get("to") else ""
        print(f"  {x['kind']:9} {x.get('send') or ', '.join(x['serials'])}{tgt}: {x['why']}" + (f" [{x['note']}]" if x.get("note") else ""))
    todo = [x for x in actions if x["kind"] in ("pallet", "container")]
    if not a.apply:
        print(f"dry run: {len(todo)} Plex move(s) would be made. Add --apply to do it.")
        return 0
    if env == "prod" and input("Production. Type RESTORE to move these back: ").strip() != "RESTORE":
        print("not confirmed; nothing moved")
        return 1
    from plex_web import PlexWeb
    web = PlexWeb(env)
    bad = good = 0
    for x in todo:
        d = web.move_detail(x["send"], x["to"])
        for s in x["serials"]:
            now = (api.container(s) or {}).get("location")
            ok = d["ok"] and now == x["to"]
            bad += not ok
            good += ok
            print(f"  {s}: {d['message']} (now at {now}){'' if ok else '  <-- CHECK'}")
            write_log({"at": dt.datetime.now(dt.timezone.utc).isoformat(), "event": "restore", "env": env,
                       "batch_id": f"restore-{a.batch or 'serials'}", "requested_by": f"restore_moves.py (laptop user {os.environ.get('USER', '?')})",
                       "serial": s, "moved_as": x["send"], "from_location": (live.get(s) or {}).get("location"),
                       "to_location": x["to"], "ok": ok, "message": d["message"], "verified_location": now,
                       "plex_request": json.dumps(d["request"]), "plex_response": d["body"], "plex_status": d["status"],
                       "plex_ms": d["ms"], "before_json": json.dumps(live.get(s), default=str), "left_pallet": None})
    print(f"{good} container(s) back where they were, {bad} to check")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
