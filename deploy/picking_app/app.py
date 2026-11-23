"""Vox picking & staging app (2026-11-20). docs/PICKING_STAGING_APP.md.

Pages: / (job sets due in N days), /set/<no> (pick list: opens at once, each ingredient's live
containers load in behind a loader from /set/<no>/line/<part_id>), POST /move
(moves the ticked containers to the staging location), /log (moves done), /health, /warm.

Sources: job sets and per-job BOM from Plex's SQL screen (plex_web.PlexWeb.sql, Plex's
reporting copy, refreshed about every 4 h, which is fine for job sets); containers and lots
live from the REST API (plex_api.PlexApi); moves through the Move Container screen's request
(plex_web.PlexWeb.move).

Speed (2026-11-20, second pass; was 24-36 s to open a job set):
- the pick list opens at once and fills in ingredient by ingredient (third pass, 2026-11-20: live
  data only, so the wait is shown instead of served stale);
- one pooled HTTPS session for the API (no new TLS handshake per call), about 20% faster;
- every ingredient's containers and lots are fetched in parallel (PICKING_WORKERS, default 16);
- caches: job sets 10 min, location groups and lots 1 h, containers 60 s FOR DISPLAY ONLY
  (a move always reads the part's containers fresh first);
- the Plex login is saved (plex_web session store) and reused by the next instance;
- /warm (the keep-warm ping in working hours) checks the Plex session and refreshes the
  default job-set list, so the first person of the morning does not wait;
- a move checks all of a part's ticked containers with ONE live read, moves them (a fully ticked
  pallet as its LP), and verifies with ONE read again: about 0.3-0.5 s per container.

Safety:
- PLEX_ENV=test by default. With PLEX_ENV=prod, moves are refused unless
  PICKING_ALLOW_PROD_MOVES=1 (reads are fine).
- Only status OK, quantity > 0, not already at the target is moved (Plex moves a Hold container
  without asking); a container that is not in the part's live list is read on its own.
- Every attempt goes to the move log (JSON lines, PICKING_LOG; and BigQuery
  PlexOps.picking_move_log when PICKING_BQ_LOG=1), with who asked: the IAP header when
  deployed behind IAP, else PICKING_USER or "local".
- Plex records every move as the company user gcp.odbc.vox, so our log is the only record
  of which person asked for it. Moves are serialized (one at a time per instance).

Run locally (Plex TEST):  PLEX_ENV=test python deploy/picking_app/app.py   -> http://127.0.0.1:8085
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask, flash, has_request_context, redirect, render_template, request, url_for

sys.path.insert(0, str(Path(__file__).resolve().parent))
import picking  # noqa: E402
from plex_api import PlexApi  # noqa: E402
from plex_web import PlexWeb  # noqa: E402

ENV = os.environ.get("PLEX_ENV", "test").lower()
ALLOW_PROD_MOVES = os.environ.get("PICKING_ALLOW_PROD_MOVES") == "1"
LOG = Path(os.environ.get("PICKING_LOG", Path(__file__).resolve().parents[2] / "etl-manual" / "picking_moves.jsonl"))
SETS_TTL = int(os.environ.get("PICKING_SETS_TTL", "600"))
LOTS_TTL = int(os.environ.get("PICKING_LOTS_TTL", "3600"))
CONTAINERS_TTL = int(os.environ.get("PICKING_CONTAINERS_TTL", "60"))
WORKERS = int(os.environ.get("PICKING_WORKERS", "16"))

app = Flask(__name__)
app.secret_key = os.environ.get("PICKING_SECRET", os.urandom(16).hex())
web, api = PlexWeb(ENV), PlexApi(ENV)
_cache: dict = {}
_cache_lock = threading.Lock()
_move_lock = threading.Lock()


def who() -> str:
    h = request.headers.get("X-Goog-Authenticated-User-Email", "")
    return h.split(":", 1)[-1] if h else os.environ.get("PICKING_USER", "local")


def cached(key, ttl: int, fn, refresh: bool = False):
    """(value, fetched_at) from the cache, or fn() when missing, older than ttl or refresh."""
    with _cache_lock:
        hit = _cache.get(key)
    if hit and not refresh and time.time() - hit[0] < ttl:
        return hit[1], hit[0]
    value = fn()
    with _cache_lock:
        _cache[key] = (time.time(), value)
    return value, time.time()


def job_sets(days: int, refresh=False, overdue: int = 14):
    return cached(("sets", days, overdue), SETS_TTL,
                  lambda: picking.build_sets(web.sql(picking.job_sets_sql(days, overdue))), refresh)


def _cached_set(set_no: str):
    """(job set, read_at) from any job-set list still within SETS_TTL, else (None, None)."""
    with _cache_lock:
        hits = [(at, v) for k, (at, v) in _cache.items() if isinstance(k, tuple) and k[0] == "sets"]
    for at, sets in sorted(hits, key=lambda h: -h[0]):
        if time.time() - at < SETS_TTL and set_no in sets:
            return sets[set_no], at
    return None, None


def location_groups() -> dict:
    """Location -> Plex location group, from the SQL screen, cached an hour."""
    return cached("locgroups", 3600,
                  lambda: {r["Location"]: r.get("Location_Group") for r in web.sql(picking.LOCATIONS_SQL)})[0]


def part_containers(part_id: str, fresh=False) -> list[dict]:
    """A part's containers. Cached CONTAINERS_TTL for display; fresh=True for anything that moves."""
    return cached(("containers", part_id), CONTAINERS_TTL, lambda: api.containers_for_part(part_id), fresh)[0]


def part_lots(part_id: str) -> list[dict]:
    return cached(("lots", part_id), LOTS_TTL, lambda: api.lots_for_part(part_id))[0]


def fetch_parts(part_ids: list[str], refresh=False) -> dict:
    """{part_id: (containers, lots)}, all parts in parallel."""
    ids = list(dict.fromkeys(part_ids))
    with ThreadPoolExecutor(max_workers=max(1, min(WORKERS, 2 * len(ids) or 1))) as ex:
        conts = {p: ex.submit(part_containers, p, refresh) for p in ids}     # containers and lots together
        lots = {p: ex.submit(part_lots, p) for p in ids}
        return {p: (conts[p].result(), lots[p].result()) for p in ids}


LOG_FIELDS = ("at", "env", "requested_by", "set_no", "job_no", "serial", "moved_as", "from_location", "to_location",
              "ok", "message", "verified_location", "left_pallet",
              # since 2026-11-23: enough to audit and undo any move (restore_moves.py)
              "event", "batch_id", "part_id", "part_no", "lp_before", "status_before", "qty_before",
              "before_json", "after_json", "plan_json", "plex_request", "plex_response", "plex_status", "plex_ms",
              "user_agent", "revision")


def _j(x):
    return None if x is None else json.dumps(x, default=str, separators=(",", ":"))


def log_move(rec: dict) -> None:
    """One row per container per event (preview | cancelled | move | refused | restore). Always to the JSON
    lines file; to BigQuery PlexOps.picking_move_log when PICKING_BQ_LOG=1 (unknown columns are ignored, so
    the app may run before Terraform adds new ones)."""
    rec = {**rec, "revision": rec.get("revision") or os.environ.get("K_REVISION"),
           "user_agent": rec.get("user_agent") or ((request.headers.get("User-Agent") or "")[:300] if has_request_context() else None)}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    if os.environ.get("PICKING_BQ_LOG") == "1":
        try:
            from google.cloud import bigquery
            bq = bigquery.Client(project="voxdatalake")
            row = {k: rec.get(k) for k in LOG_FIELDS}
            errors = bq.insert_rows_json("voxdatalake.PlexOps.picking_move_log", [row], ignore_unknown_values=True)
            if errors:
                app.logger.warning("picking_move_log insert: %s", errors)
        except Exception as e:  # noqa: BLE001 - the JSON log already has it
            app.logger.warning("picking_move_log: %s", e)


@app.context_processor
def common():
    return {"env": ENV, "moves_enabled": ENV == "test" or ALLOW_PROD_MOVES, "user": who()}


@app.get("/health")
def health():
    return {"ok": True, "env": ENV, "logged_in_at": web.logged_in_at, "session_source": web.session_source}


@app.get("/warm")
def warm():
    """The keep-warm ping (Cloud Scheduler, working hours): Plex session alive, default list cached."""
    t = time.time()
    alive = web.check()
    sets, at = job_sets(3)
    location_groups()
    destinations()
    return {"ok": True, "plex_session": alive, "job_sets": len(sets), "sets_read_at": at,
            "seconds": round(time.time() - t, 2), "session_source": web.session_source}


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


def _find_set(set_no: str, days: int):
    """(set, read_at) from any fresh cached list, else the window of `days`, else a year back / 60 days ahead."""
    s, at = _cached_set(set_no)                     # any fresh cached list that holds it (the /warm one, ...)
    if not s:
        sets, at = job_sets(days)
        s = sets.get(set_no)
    if not s:
        sets, at = job_sets(60, overdue=365)
        s = sets.get(set_no)
    return s, at


def destinations() -> list[dict]:
    """Plex history: where containers used at each work center were last moved (SQL screen, cached 6 h).
    In production this reads Plex's reporting copy (about 4 h behind): fine for a 45-day statistic."""
    def read():
        try:
            return web.sql(picking.destinations_sql())
        except Exception as e:  # noqa: BLE001 - the Staging locations remain as targets
            app.logger.warning("destinations: %s", e)
            return []
    return cached("destinations", int(os.environ.get("PICKING_DEST_TTL", "21600")), read)[0]


def line_options(ln: dict) -> list[dict]:
    return picking.destination_options(destinations(), ln.get("workcenter") or "", ln.get("group") or "", location_groups())


def _line(s: dict, ln: dict, target: str, data, groups: dict) -> dict:
    conts, lots = data
    opts = line_options(ln)
    target = target if target in {o["location"] for o in opts} else opts[0]["location"]
    return {**ln, "target": target, "options": opts,
            **picking.suggest(conts, lots, ln["required"], target, staging=[o["location"] for o in opts], loc_group=groups)}


def _page_args(s, days) -> dict:
    return {"s": s, "days": days, "pick_from": sorted(picking.PICK_FROM_GROUPS), "dest_days": picking.DEST_DAYS}


@app.get("/set/<set_no>")
def job_set(set_no):
    """The pick list. Opens at once with a loader per ingredient; each ingredient's live containers
    arrive from /set/<no>/line/<part_id> as soon as Plex answers (2026-11-20: Plex's API takes
    about 2 s per ingredient on its side, and data older than live is not acceptable).
    ?all=1 renders everything on the server in one go (the old way, and the no-JavaScript fallback)."""
    t0 = time.time()
    days = int(request.args.get("days", 3))
    refresh = "1" if request.args.get("refresh") == "1" else None
    s, at = _find_set(set_no, days)
    if not s:
        flash(f"Job set {set_no} has no open jobs due between a year ago and 60 days from now.", "error")
        return redirect(url_for("index"))
    targets = {ln["part_id"]: request.args.get("target_" + ln["part_id"], "") for ln in s["lines"]}
    read_at = dt.datetime.fromtimestamp(at).strftime("%H:%M")
    if request.args.get("all") != "1":
        location_groups()                           # cached 1 h; warm it once instead of in every fragment
        destinations()                              # cached 6 h (Plex history of where material goes)
        lines = [{**ln, "target": targets[ln["part_id"]]} for ln in s["lines"]]
        return render_template("set.html", lines=lines, loading=True, refresh=refresh, read_at=read_at,
                               load_seconds=None, **_page_args(s, days))
    groups = location_groups()
    data = fetch_parts([ln["part_id"] for ln in s["lines"]], refresh=bool(refresh))
    lines = [_line(s, ln, targets[ln["part_id"]], data[ln["part_id"]], groups) for ln in s["lines"]]
    return render_template("set.html", lines=lines, loading=False, refresh=refresh, read_at=read_at,
                           load_seconds=round(time.time() - t0, 1), **_page_args(s, days))


@app.get("/set/<set_no>/line/<part_id>")
def job_set_line(set_no, part_id):
    """One ingredient's card (HTML fragment) with its live containers and suggestions."""
    days = int(request.args.get("days", 3))
    s, _ = _find_set(set_no, days)
    ln = next((x for x in (s or {}).get("lines", []) if x["part_id"] == part_id), None)
    if not ln:
        return f"<div class='card muted'>This ingredient is no longer in job set {set_no}.</div>", 404
    data = fetch_parts([part_id], refresh=request.args.get("refresh") == "1")[part_id]
    line = _line(s, ln, request.args.get("target") or "", data, location_groups())
    return render_template("_line.html", ln=line, **_page_args(s, days))


def _live_lookup(serials: list[str], part_list: list[dict]) -> dict:
    """{serial: live record or None}: from the part's fresh list, else one read per missing serial."""
    by = {c.get("serialNo"): c for c in part_list}
    missing = [s for s in serials if s not in by]
    if missing:
        with ThreadPoolExecutor(max_workers=min(WORKERS, len(missing))) as ex:
            by.update(dict(zip(missing, ex.map(api.container, missing))))
    return {s: by.get(s) for s in serials}


PLAN_TTL = int(os.environ.get("PICKING_PLAN_TTL", "600"))
_plans: dict = {}


def _summary(c: dict | None, serial: str) -> dict:
    c = c or {}
    return {"serial": serial, "lp": c.get("masterUnitNo") or "", "lot": c.get("lotNo") or "", "part_no": c.get("partNo") or "",
            "qty": c.get("quantity"), "status": c.get("containerStatus") or "", "location": c.get("location") or ""}


def _line_for(set_no: str, part_id: str, job_no: str):
    s, _ = _find_set(set_no, 60) if set_no else (None, None)
    for ln in (s or {}).get("lines", []):
        if ln["part_id"] == part_id and (not job_no or ln["job_no"] == job_no):
            return ln
    return None


def _check_request(form) -> tuple[dict | None, str | None]:
    """Common checks for preview and approve: moves allowed here, a known line, an allowed target."""
    if not (ENV == "test" or ALLOW_PROD_MOVES):
        return None, "Moves are turned off in production (PICKING_ALLOW_PROD_MOVES is not 1)."
    set_no, job_no, part_id = form.get("set_no", ""), form.get("job_no", ""), form.get("part_id", "")
    target, serials = form.get("target", ""), list(dict.fromkeys(form.getlist("serial")))
    if not serials:
        return None, "Nothing ticked."
    ln = _line_for(set_no, part_id, job_no)
    allowed = {o["location"] for o in line_options(ln)} if ln else set(picking.STAGING_LOCATIONS)
    if target not in allowed:
        return None, f"{target!r} is not one of this line's targets."
    return {"set_no": set_no, "job_no": job_no, "part_id": part_id, "target": target, "serials": serials,
            "part_no": (ln or {}).get("part_no")}, None


def build_plan(req: dict) -> dict:
    """What a move would do, from a fresh live read: one item per Plex call (a container, or a whole pallet)."""
    part_list = part_containers(req["part_id"], fresh=True) if req["part_id"] else []
    lives = _live_lookup(req["serials"], part_list)
    items = []
    for what, members in picking.plan_moves(req["serials"], part_list):
        whys = {s: picking.check_movable(lives[s], req["target"]) for s in members}
        if what in members:
            todo = [(what, [what])]
        elif any(whys.values()):
            todo = [(s, [s]) for s in members]
        else:
            todo = [(what, members)]
        for item, covered in todo:
            why = next((whys[s] or "its pallet has a container that may not move" for s in covered if whys[s]), None)
            items.append({"send": None if why else item, "covered": covered, "why": why,
                          "pallet": item if item not in covered else None,
                          "left_pallet": picking.breaks_pallet(item, req["serials"], part_list) if item in covered else None,
                          "containers": [_summary(lives[s], s) for s in covered]})
    return {**req, "items": items, "lives": {s: lives[s] for s in req["serials"]}}


@app.post("/move/preview")
def move_preview():
    """The review step: what would move, from where to where, and what will not move and why.
    Nothing is sent to Plex. The page shows it in a dialog with Approve / Cancel."""
    req, err = _check_request(request.form)
    if err:
        return {"ok": False, "error": err}, 400
    plan = build_plan(req)
    plan_id = uuid.uuid4().hex[:12]
    now = time.time()
    for k in [k for k, v in _plans.items() if now - v["created"] > PLAN_TTL]:
        _plans.pop(k, None)
    _plans[plan_id] = {**plan, "created": now, "by": who()}
    at = dt.datetime.now(dt.timezone.utc).isoformat()
    for it in plan["items"]:
        for c in it["containers"]:
            log_move({"at": at, "event": "preview", "batch_id": plan_id, "env": ENV, "requested_by": who(),
                      "set_no": req["set_no"], "job_no": req["job_no"], "part_id": req["part_id"], "part_no": req["part_no"],
                      "serial": c["serial"], "moved_as": it["send"], "from_location": c["location"], "to_location": req["target"],
                      "lp_before": c["lp"], "status_before": c["status"], "qty_before": c["qty"], "message": it["why"],
                      "left_pallet": it["left_pallet"], "before_json": _j(plan["lives"].get(c["serial"])), "plan_json": _j(it)})
    return {"ok": True, "plan_id": plan_id, "target": req["target"], "part_no": req["part_no"], "set_no": req["set_no"],
            "job_no": req["job_no"], "env": ENV, "items": plan["items"], "expires_s": PLAN_TTL,
            "to_send": sum(1 for it in plan["items"] if it["send"]),
            "containers_moving": sum(len(it["covered"]) for it in plan["items"] if it["send"])}


@app.post("/move/cancel")
def move_cancel():
    plan = _plans.pop(request.form.get("plan_id", ""), None)
    if plan:
        at = dt.datetime.now(dt.timezone.utc).isoformat()
        for s in plan["serials"]:
            log_move({"at": at, "event": "cancelled", "batch_id": request.form.get("plan_id"), "env": ENV, "requested_by": who(),
                      "set_no": plan["set_no"], "job_no": plan["job_no"], "part_id": plan["part_id"], "serial": s,
                      "to_location": plan["target"], "message": "cancelled in the review dialog"})
    return {"ok": True}


def _changed(before: dict | None, now: dict | None) -> str | None:
    """Why a container no longer matches what the person approved (None = same)."""
    if before is None or now is None:
        return "not found in Plex" if now is None else None
    for k, label in (("location", "location"), ("containerStatus", "status"), ("quantity", "quantity"), ("masterUnitNo", "pallet")):
        if (before.get(k) or None) != (now.get(k) or None):
            return f"{label} changed since you reviewed it ({before.get(k)} -> {now.get(k)})"
    return None


@app.post("/move")
def move():
    """Approve: carries out a reviewed plan (plan_id from /move/preview), re-checking every container live
    first. A container that changed since the review, or may not move, is not sent."""
    set_no = request.form.get("set_no", "")
    back = redirect(url_for("job_set", set_no=set_no) if set_no else url_for("index"))
    if not (ENV == "test" or ALLOW_PROD_MOVES):
        flash("Moves are turned off in production (PICKING_ALLOW_PROD_MOVES is not 1).", "error")
        return back
    plan_id = request.form.get("plan_id", "")
    plan = _plans.pop(plan_id, None)
    if not plan or time.time() - plan["created"] > PLAN_TTL:
        flash("That review has expired or was already used. Press the move button again to review it.", "error")
        return back
    target = plan["target"]
    base = {"env": ENV, "requested_by": who(), "set_no": plan["set_no"], "job_no": plan["job_no"], "to_location": target,
            "batch_id": plan_id, "part_id": plan["part_id"], "part_no": plan["part_no"]}
    results = []                                        # (serial, item or None, plex detail or None, message)
    with _move_lock:
        part_list = part_containers(plan["part_id"], fresh=True) if plan["part_id"] else []
        lives = _live_lookup(plan["serials"], part_list)
        for it in plan["items"]:
            if not it["send"]:
                results += [(s, None, None, f"not moved: {it['why']}") for s in it["covered"]]
                continue
            whys = {s: _changed(plan["lives"].get(s), lives[s]) or picking.check_movable(lives[s], target) for s in it["covered"]}
            if any(whys.values()):
                results += [(s, None, None, f"not moved: {whys[s] or 'a container on its pallet changed or may not move'}")
                            for s in it["covered"]]
                continue
            d = web.move_detail(it["send"], target)
            results += [(s, it["send"], d, d["message"]) for s in it["covered"]]
        moved = [s for s, item, d, _ in results if item]
        after = _live_lookup(moved, part_containers(plan["part_id"], fresh=True) if plan["part_id"] and moved else []) if moved else {}
    done = failed = 0
    for s, item, d, msg in results:
        now = (after.get(s) or {}).get("location") if item else (lives[s] or {}).get("location")
        b = plan["lives"].get(s) or {}
        rec = {**base, "at": dt.datetime.now(dt.timezone.utc).isoformat(), "event": "move" if item else "refused",
               "serial": s, "moved_as": item, "from_location": b.get("location"), "ok": bool(item) and bool(d and d["ok"]) and now == target,
               "message": msg, "verified_location": now, "lp_before": b.get("masterUnitNo"), "status_before": b.get("containerStatus"),
               "qty_before": b.get("quantity"), "left_pallet": picking.breaks_pallet(s, plan["serials"], part_list) if item == s else None,
               "before_json": _j(plan["lives"].get(s)), "after_json": _j(after.get(s)) if item else None,
               "plex_request": _j(d and d["request"]), "plex_response": d and d["body"], "plex_status": d and d["status"],
               "plex_ms": d and d["ms"]}
        log_move(rec)
        done += rec["ok"]
        failed += not rec["ok"]
        note = f" (left pallet {rec['left_pallet']})" if rec["left_pallet"] else (f" (as pallet {item})" if item and item != s else "")
        flash(f"{s}: {msg}{note} (now at {now})", "ok" if rec["ok"] else "error")
    flash(f"{done} moved to {target}, {failed} not moved. Batch {plan_id} (undo: restore_moves.py --batch {plan_id}).",
          "ok" if not failed else "error")
    return back


# `at` is a reserved word in BigQuery: unquoted, this query failed and /log silently showed only the
# instance's own file (lost on every restart). Found in the live audit, 2026-11-23.
LOG_SQL = "SELECT * FROM `voxdatalake.PlexOps.picking_move_log` ORDER BY `at` DESC LIMIT 300"


@app.get("/favicon.ico")
def favicon():
    return "", 204


@app.get("/log")
def move_log():
    rows = []
    if os.environ.get("PICKING_BQ_LOG") == "1":
        try:
            from google.cloud import bigquery
            rows = [dict(r) for r in bigquery.Client(project="voxdatalake").query(
                LOG_SQL).result()]
            for r in rows:
                r["at"] = r["at"].isoformat() if hasattr(r["at"], "isoformat") else str(r["at"])
        except Exception as e:  # noqa: BLE001 - fall back to the local file
            app.logger.warning("reading picking_move_log: %s", e)
    if not rows and LOG.exists():
        rows = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()][-300:][::-1]
    return render_template("log.html", rows=rows)


if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 8085)), threaded=True)
