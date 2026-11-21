"""Vox picking & staging app (draft, 2026-11-20). docs/PICKING_STAGING_APP.md.

Pages: / (job sets due in N days), /set/<no> (pick list with live containers), POST /move
(moves the ticked containers to the staging location), /log (moves done), /health.

Sources: job sets and per-job BOM from Plex's SQL screen (plex_web.PlexWeb.sql, Plex's
reporting copy, refreshed about every 4 h, which is fine for job sets); containers, lots and
jobs live from the REST API (plex_api.PlexApi); moves through the Move Container screen's
request (plex_web.PlexWeb.move).

Safety:
- PLEX_ENV=test by default. With PLEX_ENV=prod, moves are refused unless
  PICKING_ALLOW_PROD_MOVES=1 (reads are fine).
- Before each move the container is read live from the API: only status OK, quantity > 0 and
  not already at the target is moved (Plex moves a Hold container without asking).
- After each move the API is read again and the new location recorded.
- Every attempt goes to the move log (JSON lines, PICKING_LOG; and BigQuery
  PlexOps.picking_move_log when PICKING_BQ_LOG=1), with who asked: the IAP header when
  deployed behind IAP, else PICKING_USER or "local".
- Plex records every move as the company user gcp.odbc.vox, so our log is the only record
  of which person asked for it.

Run locally (Plex TEST):  PLEX_ENV=test python deploy/picking_app/app.py   -> http://127.0.0.1:8085
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import threading
import time
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

sys.path.insert(0, str(Path(__file__).resolve().parent))
import picking  # noqa: E402
from plex_api import PlexApi  # noqa: E402
from plex_web import PlexWeb  # noqa: E402

ENV = os.environ.get("PLEX_ENV", "test").lower()
ALLOW_PROD_MOVES = os.environ.get("PICKING_ALLOW_PROD_MOVES") == "1"
LOG = Path(os.environ.get("PICKING_LOG", Path(__file__).resolve().parents[2] / "etl-manual" / "picking_moves.jsonl"))
SETS_TTL = int(os.environ.get("PICKING_SETS_TTL", "600"))

app = Flask(__name__)
app.secret_key = os.environ.get("PICKING_SECRET", os.urandom(16).hex())
web, api = PlexWeb(ENV), PlexApi(ENV)
_cache: dict = {}
_cache_lock = threading.Lock()


def who() -> str:
    h = request.headers.get("X-Goog-Authenticated-User-Email", "")
    return h.split(":", 1)[-1] if h else os.environ.get("PICKING_USER", "local")


def job_sets(days: int, refresh=False, overdue: int = 14):
    key = ("sets", days, overdue)
    with _cache_lock:
        hit = _cache.get(key)
        if hit and not refresh and time.time() - hit[0] < SETS_TTL:
            return hit[1], hit[0]
    sets = picking.build_sets(web.sql(picking.job_sets_sql(days, overdue)))
    with _cache_lock:
        _cache[key] = (time.time(), sets)
    return sets, time.time()


def location_groups() -> dict:
    """Location -> Plex location group, from the SQL screen, cached an hour."""
    with _cache_lock:
        hit = _cache.get("locgroups")
        if hit and time.time() - hit[0] < 3600:
            return hit[1]
    groups = {r["Location"]: r.get("Location_Group") for r in web.sql(picking.LOCATIONS_SQL)}
    with _cache_lock:
        _cache["locgroups"] = (time.time(), groups)
    return groups


def log_move(rec: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    if os.environ.get("PICKING_BQ_LOG") == "1":
        try:
            from google.cloud import bigquery
            bq = bigquery.Client(project="voxdatalake")
            bq.query("""CREATE TABLE IF NOT EXISTS `voxdatalake.PlexOps.picking_move_log` (
                at TIMESTAMP, env STRING, requested_by STRING, set_no STRING, job_no STRING, serial STRING,
                from_location STRING, to_location STRING, ok BOOL, message STRING, verified_location STRING)""").result()
            errors = bq.insert_rows_json("voxdatalake.PlexOps.picking_move_log", [rec])
            if errors:
                app.logger.warning("picking_move_log insert: %s", errors)
        except Exception as e:  # noqa: BLE001 - the JSON log already has it
            app.logger.warning("picking_move_log: %s", e)


@app.context_processor
def common():
    return {"env": ENV, "moves_enabled": ENV == "test" or ALLOW_PROD_MOVES, "user": who()}


@app.get("/health")
def health():
    return {"ok": True, "env": ENV, "logged_in_at": web.logged_in_at}


@app.get("/")
def index():
    days = int(request.args.get("days", 3))
    group = request.args.get("group", "")
    overdue = int(request.args.get("overdue", 14))
    sets, at = job_sets(days, refresh=request.args.get("refresh") == "1", overdue=overdue)
    rows = [s for s in sets.values() if s["lines"] and (not group or s["main"]["group"] == group
                                                         or any(l["group"] == group for l in s["lines"]))]
    rows.sort(key=lambda s: (min((l["due"] for l in s["lines"]), default="9999"), s["set_no"]))
    groups = sorted({l["group"] for s in sets.values() for l in s["lines"] if l["group"]})
    return render_template("index.html", sets=rows, days=days, group=group, groups=groups, overdue=overdue,
                           read_at=dt.datetime.fromtimestamp(at).strftime("%H:%M"))


@app.get("/set/<set_no>")
def job_set(set_no):
    days = int(request.args.get("days", 3))
    sets, at = job_sets(days)
    s = sets.get(set_no)
    if not s:
        sets, at = job_sets(60, overdue=365)
        s = sets.get(set_no)
    if not s:
        flash(f"Job set {set_no} has no open jobs due between a year ago and 60 days from now.", "error")
        return redirect(url_for("index"))
    lines, groups = [], location_groups()
    for ln in s["lines"]:
        target = request.args.get("target_" + ln["part_id"], ln["target"])
        lines.append({**ln, "target": target,
                      **picking.suggest(api.containers_for_part(ln["part_id"]), api.lots_for_part(ln["part_id"]),
                                        ln["required"], target, loc_group=groups)})
    return render_template("set.html", s=s, lines=lines, days=days, staging=picking.STAGING_LOCATIONS,
                           pick_from=sorted(picking.PICK_FROM_GROUPS),
                           read_at=dt.datetime.fromtimestamp(at).strftime("%H:%M"))


@app.post("/move")
def move():
    set_no, job_no = request.form.get("set_no", ""), request.form.get("job_no", "")
    target = request.form.get("target", "")
    serials = request.form.getlist("serial")
    back = redirect(url_for("job_set", set_no=set_no) if set_no else url_for("index"))
    if not (ENV == "test" or ALLOW_PROD_MOVES):
        flash("Moves are turned off in production (PICKING_ALLOW_PROD_MOVES is not 1).", "error")
        return back
    if target not in picking.STAGING_LOCATIONS:
        flash(f"{target!r} is not a staging location.", "error")
        return back
    part_id = request.form.get("part_id", "")
    part_containers = api.containers_for_part(part_id) if part_id else []
    done = failed = 0
    for what, members in picking.plan_moves(serials, part_containers):
        lives = {s: api.container(s) for s in members}
        whys = {s: picking.check_movable(lives[s], target) for s in members}
        base = {"env": ENV, "requested_by": who(), "set_no": set_no, "job_no": job_no, "to_location": target}
        if what in members:                       # a single container
            todo = [(what, [what])]
        elif any(whys.values()):                  # a pallet with a container that may not move: one by one
            todo = [(s, [s]) for s in members]
        else:                                     # a whole pallet, one call
            todo = [(what, members)]
        for item, covered in todo:
            why = next((whys[s] for s in covered if whys[s]), None)
            if why:
                for s in covered:
                    rec = {**base, "at": dt.datetime.now(dt.timezone.utc).isoformat(), "serial": s,
                           "from_location": (lives[s] or {}).get("location"), "ok": False,
                           "message": f"not moved: {whys[s] or 'its pallet has a container that may not move'}",
                           "verified_location": (lives[s] or {}).get("location")}
                    log_move(rec); failed += 1
                    flash(f"{s}: {rec['message']}", "error")
                continue
            ok, msg = web.move(item, target)
            for s in covered:
                after = api.container(s) if ok else lives[s]
                rec = {**base, "at": dt.datetime.now(dt.timezone.utc).isoformat(), "serial": s,
                       "moved_as": item, "from_location": (lives[s] or {}).get("location"),
                       "ok": ok and (after or {}).get("location") == target, "message": msg,
                       "verified_location": (after or {}).get("location"),
                       "left_pallet": picking.breaks_pallet(s, serials, part_containers) if item == s else None}
                log_move(rec)
                done += rec["ok"]; failed += not rec["ok"]
                note = f" (left pallet {rec['left_pallet']})" if rec["left_pallet"] else (f" (as pallet {item})" if item != s else "")
                flash(f"{s}: {rec['message']}{note} (now at {rec['verified_location']})", "ok" if rec["ok"] else "error")
    flash(f"{done} moved to {target}, {failed} not moved.", "ok" if not failed else "error")
    return back


@app.get("/log")
def move_log():
    rows = []
    if LOG.exists():
        rows = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()][-300:][::-1]
    return render_template("log.html", rows=rows)


if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 8085)), threaded=False)
