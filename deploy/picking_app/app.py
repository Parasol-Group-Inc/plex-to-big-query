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
import hashlib
import json
import os
import secrets
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask, flash, has_request_context, redirect, render_template, request, session, url_for
from markupsafe import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import picking  # noqa: E402
import undo  # noqa: E402
from plex_api import PlexApi  # noqa: E402
from plex_web import PlexWeb  # noqa: E402

ENV = os.environ.get("PLEX_ENV", "test").lower()
ALLOW_PROD_MOVES = os.environ.get("PICKING_ALLOW_PROD_MOVES") == "1"
LOG = Path(os.environ.get("PICKING_LOG", Path(__file__).resolve().parents[2] / "etl-manual" / "picking_moves.jsonl"))
SETS_TTL = int(os.environ.get("PICKING_SETS_TTL", "600"))
LOTS_TTL = int(os.environ.get("PICKING_LOTS_TTL", "3600"))
CONTAINERS_TTL = int(os.environ.get("PICKING_CONTAINERS_TTL", "60"))
WORKERS = int(os.environ.get("PICKING_WORKERS", "16"))
NET_DAYS = int(os.environ.get("PICKING_NET_DAYS", "30"))     # demand netting window (audit 11-23 #6)
IAP_REQUIRED = os.environ.get("PICKING_IAP_REQUIRED") == "1"  # deploy.sh sets it: a request without a valid IAP JWT is "unverified"
APP_PLEX_USER = os.environ.get("PICKING_PLEX_USER", "gcp.odbc.vox")

app = Flask(__name__)
app.secret_key = os.environ.get("PICKING_SECRET", os.urandom(16).hex())
web, api = PlexWeb(ENV), PlexApi(ENV)
_cache: dict = {}
MT = __import__('zoneinfo').ZoneInfo('America/Denver')
_cache_lock = threading.Lock()
_move_lock = threading.Lock()
_plans_lock = threading.Lock()
_jwt_ok: dict = {}                 # sha256(token) -> (email, exp)


def _verify_iap(token: str) -> str | None:
    """Email from a valid IAP JWT (X-Goog-IAP-JWT-Assertion), else None. Audit 11-23 #24: the plain email header is
    unsigned and only safe while IAP fronts the service. Audience checked when PICKING_IAP_AUDIENCE is set."""
    key = hashlib.sha256(token.encode()).hexdigest()
    hit = _jwt_ok.get(key)
    if hit and hit[1] > time.time():
        return hit[0]
    try:
        from google.auth.transport import requests as ga_requests
        from google.oauth2 import id_token
        claims = id_token.verify_token(token, ga_requests.Request(), audience=os.environ.get("PICKING_IAP_AUDIENCE") or None,
                                       certs_url="https://www.gstatic.com/iap/verify/public_key")
        if claims.get("iss") != "https://cloud.google.com/iap" or not claims.get("email"):
            return None
        _jwt_ok[key] = (claims["email"], float(claims.get("exp", time.time() + 300)))
        return claims["email"]
    except Exception as e:  # noqa: BLE001 - invalid, expired or unreachable certs: not verified
        app.logger.warning("IAP JWT not verified: %s", e)
        return None


def who() -> str:
    """The person: the IAP JWT's email when present (verified); without one, the IAP email header unless
    PICKING_IAP_REQUIRED=1 (then "unverified", and nothing can move); locally PICKING_USER."""
    if not has_request_context():
        return os.environ.get("PICKING_USER", "local")
    if getattr(request, "_who", None):
        return request._who
    tok = request.headers.get("X-Goog-IAP-JWT-Assertion")
    hdr = request.headers.get("X-Goog-Authenticated-User-Email", "")
    if tok:
        u = _verify_iap(tok) or "unverified"
    elif IAP_REQUIRED:
        u = "unverified"
    else:
        u = hdr.split(":", 1)[-1] if hdr else os.environ.get("PICKING_USER", "local")
    request._who = u
    return u


def _int_arg(name: str, default: int, lo: int, hi: int) -> int:
    """A bounded integer query parameter (audit 11-23 #26)."""
    try:
        return max(lo, min(hi, int(request.args.get(name, default))))
    except (TypeError, ValueError):
        return default


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


@app.before_request
def _csrf_check():
    """Every POST carries the session's token (audit 11-23 #4: a forged cross-site POST, or a script injected
    through any page, must not be able to move)."""
    if request.method == "POST":
        tok = request.form.get("csrf") or request.headers.get("X-CSRF-Token")
        if not tok or not secrets.compare_digest(str(tok), str(session.get("csrf", ""))):
            if request.path.startswith(("/move/preview", "/log/undo/review", "/move/cancel")):
                return {"ok": False, "error": "This page is out of date (form token). Reload it and try again."}, 400
            return "This page is out of date (form token). Go back, reload it and try again.", 400


@app.after_request
def _security_headers(resp):
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; "
                            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    return resp


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


def part_alloc(part_id: str, fresh=False) -> dict:
    """{serial: [job_no]} for a part (audit 11-23 #5: the floor stages through job allocations). SQL screen;
    in production Plex's copy (about 4 h behind), so a container whose live status is Allocated but has no
    row here is treated as allocated to an unknown job (picking.allocation_why)."""
    def read():
        try:
            return picking.alloc_map(web.sql(picking.allocations_sql(part_id)))
        except Exception as e:  # noqa: BLE001 - Allocated containers then stay blocked
            app.logger.warning("allocations %s: %s", part_id, e)
            return {}
    return cached(("alloc", part_id), CONTAINERS_TTL, read, fresh)[0]


def fetch_parts(part_ids: list[str], refresh=False) -> dict:
    """{part_id: (containers, lots, allocations)}, all parts in parallel."""
    ids = list(dict.fromkeys(part_ids))
    with ThreadPoolExecutor(max_workers=max(1, min(WORKERS, 3 * len(ids) or 1))) as ex:
        conts = {p: ex.submit(part_containers, p, refresh) for p in ids}
        lots = {p: ex.submit(part_lots, p) for p in ids}
        alloc = {p: ex.submit(part_alloc, p, refresh) for p in ids}
        return {p: (conts[p].result(), lots[p].result(), alloc[p].result()) for p in ids}


LOG_FIELDS = ("at", "env", "requested_by", "set_no", "job_no", "serial", "moved_as", "from_location", "to_location",
              "ok", "message", "verified_location", "left_pallet",
              # since 2026-11-23: enough to audit and undo any move (restore_moves.py)
              "event", "batch_id", "part_id", "part_no", "lp_before", "status_before", "qty_before",
              "before_json", "after_json", "plan_json", "plex_request", "plex_response", "plex_status", "plex_ms",
              "user_agent", "revision")


def _j(x):
    return None if x is None else json.dumps(x, default=str, separators=(",", ":"))


def log_move(rec: dict) -> None:
    """One row per container per event (preview | cancelled | sent | move | refused | refused-gate |
    undo-review | restore). Always to the JSON
    lines file; to BigQuery PlexOps.picking_move_log when PICKING_BQ_LOG=1 (unknown columns are ignored, so
    the app may run before Terraform adds new ones)."""
    rec = {**rec, "revision": rec.get("revision") or os.environ.get("K_REVISION"),
           "user_agent": rec.get("user_agent") or ((request.headers.get("User-Agent") or "")[:300] if has_request_context() else None)}
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except OSError as e:                 # audit 11-23 #3: never cut a batch's logging short
        app.logger.error("move log file: %s; row: %s", e, json.dumps(rec, default=str)[:2000])
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


@app.template_filter("mt")
def mt_filter(at) -> str:
    """A UTC timestamp (log) shown in Mountain time."""
    try:
        return undo._utc(at).astimezone(MT).strftime("%m-%d %H:%M:%S")
    except Exception:  # noqa: BLE001
        return str(at)[:19]


@app.context_processor
def common():
    return {"env": ENV, "moves_enabled": ENV == "test" or ALLOW_PROD_MOVES, "user": who(), "csrf": csrf_token()}


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
    days = _int_arg("days", 3, 1, 60)
    group = request.args.get("group", "")
    overdue = _int_arg("overdue", 14, 0, 365)
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


def net_claims(s: dict, ln: dict, conts, lots, groups: dict, alloc: dict) -> dict:
    """Containers that earlier-due lines of the same part (any job set due within NET_DAYS) would use, each at its
    own default target: {serial: "set 757 job 3806 (due 11-16)"}. Audit 11-23 #6: eight sets each saw the same
    1,225 in PW - B9 as "all there"."""
    try:
        sets, _ = job_sets(NET_DAYS)
    except Exception as e:  # noqa: BLE001 - without netting the line still shows; say so in the log
        app.logger.warning("net_claims: %s", e)
        return {}
    mine = (ln.get("due") or "9999", s["set_no"], ln["job_no"])
    earlier = sorted(((l.get("due") or "9999", ss["set_no"], l["job_no"]), ss, l) for ss in sets.values()
                     for l in ss["lines"] if l["part_id"] == ln["part_id"])
    claimed: dict = {}
    for key, ss, l in earlier:
        if key >= mine:
            break
        opts = line_options(l)
        res = picking.suggest(conts, lots, l["required"], picking.default_target(opts, conts, l["job_no"], alloc),
                              staging=[o["location"] for o in opts],
                              loc_group=groups, job_no=l["job_no"], alloc=alloc, claimed=claimed)
        for sn in res["claims"]:
            claimed.setdefault(sn, f"set {ss['set_no']} job {l['job_no']} (due {l.get('due')})")
    return claimed


def _line(s: dict, ln: dict, target: str, data, groups: dict) -> dict:
    conts, lots, alloc = data
    opts = line_options(ln)
    target = target if target in {o["location"] for o in opts} else picking.default_target(opts, conts, ln["job_no"], alloc)
    claimed = net_claims(s, ln, conts, lots, groups, alloc)
    return {**ln, "target": target, "options": opts,
            **picking.suggest(conts, lots, ln["required"], target, staging=[o["location"] for o in opts], loc_group=groups,
                              job_no=ln["job_no"], alloc=alloc, claimed=claimed)}


def _page_args(s, days) -> dict:
    return {"s": s, "days": days, "pick_from": sorted(picking.PICK_FROM_GROUPS), "dest_days": picking.DEST_DAYS}


@app.get("/set/<set_no>")
def job_set(set_no):
    """The pick list. Opens at once with a loader per ingredient; each ingredient's live containers
    arrive from /set/<no>/line/<part_id> as soon as Plex answers (2026-11-20: Plex's API takes
    about 2 s per ingredient on its side, and data older than live is not acceptable).
    ?all=1 renders everything on the server in one go (the old way, and the no-JavaScript fallback)."""
    t0 = time.time()
    days = _int_arg("days", 3, 1, 60)
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
    days = _int_arg("days", 3, 1, 60)
    s, _ = _find_set(set_no, days)
    ln = next((x for x in (s or {}).get("lines", []) if x["part_id"] == part_id), None)
    if not ln:                                       # escaped: audit 11-23 #4 (reflected XSS)
        return f"<div class='card muted'>This ingredient is no longer in job set {escape(set_no)}.</div>", 404
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


def plan_put(plan: dict) -> str:
    pid = (plan.get("kind") == "undo" and "u" or "") + uuid.uuid4().hex[:12]
    now = time.time()
    with _plans_lock:                                   # audit 11-23 #20: no unlocked iteration
        for k in [k for k, v in _plans.items() if now - v["created"] > PLAN_TTL]:
            _plans.pop(k, None)
        _plans[pid] = {**plan, "created": now}
    return pid


def plan_pop(pid: str) -> dict | None:
    with _plans_lock:
        p = _plans.pop(pid or "", None)
    return p if p and time.time() - p["created"] <= PLAN_TTL else None


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


def _gate_refused(form, what: str) -> str | None:
    """Prod gate and identity. Refusals are logged (audit 11-23 #13)."""
    msg = None
    if not (ENV == "test" or ALLOW_PROD_MOVES):
        msg = "Moves are turned off in production (PICKING_ALLOW_PROD_MOVES is not 1)."
    elif who() == "unverified":
        msg = "Your sign-in could not be verified (IAP), so nothing can move. Reload the page; if it persists, tell Emilio."
    if msg:
        log_move({"at": dt.datetime.now(dt.timezone.utc).isoformat(), "event": "refused-gate", "env": ENV, "requested_by": who(),
                  "set_no": form.get("set_no"), "job_no": form.get("job_no"), "part_id": form.get("part_id"),
                  "batch_id": form.get("plan_id") or form.get("batch_id"), "serial": ",".join(form.getlist("serial"))[:1000] or None,
                  "to_location": form.get("target"), "message": f"{what}: {msg}"})
    return msg


def _check_request(form) -> tuple[dict | None, str | None]:
    """Common checks for preview: moves allowed here, a known line, an allowed target."""
    err = _gate_refused(form, "preview")
    if err:
        return None, err
    set_no, job_no, part_id = form.get("set_no", ""), form.get("job_no", ""), form.get("part_id", "")
    target, serials = form.get("target", ""), list(dict.fromkeys(form.getlist("serial")))
    if not serials:
        return None, "Nothing ticked."
    if not part_id:
        return None, "No part given."
    ln = _line_for(set_no, part_id, job_no)
    allowed = {o["location"] for o in line_options(ln)} if ln else set(picking.STAGING_LOCATIONS)
    if target not in allowed:
        return None, f"{target!r} is not one of this line's targets."
    return {"set_no": set_no, "job_no": job_no, "part_id": part_id, "target": target, "serials": serials,
            "part_no": (ln or {}).get("part_no")}, None


def lp_members(lp: str, any_live: dict | None) -> list[str] | None:
    """Every container on pallet `lp` right now, any part, any quantity (audit 11-23 #2), read live from the
    pallet's location. None when it cannot be read."""
    loc_id = (any_live or {}).get("locationId")
    if not lp or not loc_id:
        return None
    try:
        return sorted(c.get("serialNo") for c in api.containers_at(loc_id) if c.get("masterUnitNo") == lp)
    except Exception as e:  # noqa: BLE001
        app.logger.warning("lp_members %s: %s", lp, e)
        return None


def build_plan(req: dict) -> dict:
    """What a move would do, from a fresh live read: one item per Plex call (a container, or a whole pallet).
    A pallet is sent whole only when exactly the ticked containers are on it right now; otherwise its ticked
    containers go one by one, each flagged as leaving the pallet."""
    part_list = part_containers(req["part_id"], fresh=True)
    alloc = part_alloc(req["part_id"], fresh=True)
    by = {c.get("serialNo"): c for c in part_list}
    lives = {s: by.get(s) for s in req["serials"]}
    items, lp_cache = [], {}
    not_part = [s for s in req["serials"] if s not in by]              # audit 11-23 #23
    for s in not_part:
        items.append({"send": None, "covered": [s], "why": "not a container of this part in Plex now", "pallet": None,
                      "left_pallet": None, "lp_snapshot": None, "containers": [_summary(None, s)]})
    serials = [s for s in req["serials"] if s in by]

    def members(lp, live):
        if lp not in lp_cache:
            lp_cache[lp] = lp_members(lp, live)
        return lp_cache[lp]

    def single(s, why, note=None):
        lp = (lives[s] or {}).get("masterUnitNo")
        mates = members(lp, lives[s]) if lp and not why else None
        left = lp if lp and not why and (mates is None or set(mates) - {s}) else None
        return {"send": None if why else s, "covered": [s], "why": why, "pallet": None, "left_pallet": left, "lp_snapshot": None,
                "note": note, "containers": [_summary(lives[s], s)]}

    for what, covered in picking.plan_moves(serials, part_list):
        whys = {s: picking.check_movable(lives[s], req["target"], job_no=req["job_no"], alloc=alloc) for s in covered}
        if what in covered:
            items.append(single(what, whys[what]))
            continue
        on_lp = members(what, lives[covered[0]])
        if any(whys.values()):
            items += [single(s, whys[s]) for s in covered]
        elif on_lp is None or set(on_lp) != set(covered):
            extra = sorted(set(on_lp or []) - set(covered))
            note = (f"pallet {what} also holds {', '.join(extra)} (other parts or empty containers, not in this review), so these "
                    f"go one by one and leave it" if on_lp is not None else f"pallet {what} could not be read whole, so these go one by one")
            items += [single(s, None, note) for s in covered]
        else:
            items.append({"send": what, "covered": covered, "why": None, "pallet": what, "left_pallet": None,
                          "lp_snapshot": on_lp, "note": None, "containers": [_summary(lives[s], s) for s in covered]})
    return {**req, "items": items, "lives": lives}


@app.post("/move/preview")
def move_preview():
    """The review step: what would move, from where to where, and what will not move and why.
    Nothing is sent to Plex. The page shows it in a dialog with Approve / Cancel."""
    req, err = _check_request(request.form)
    if err:
        return {"ok": False, "error": err}, 400
    plan = build_plan(req)
    plan_id = plan_put({**plan, "by": who()})
    at = dt.datetime.now(dt.timezone.utc).isoformat()
    for it in plan["items"]:
        for c in it["containers"]:
            log_move({"at": at, "event": "preview", "batch_id": plan_id, "env": ENV, "requested_by": who(),
                      "set_no": req["set_no"], "job_no": req["job_no"], "part_id": req["part_id"], "part_no": req["part_no"],
                      "serial": c["serial"], "moved_as": it["send"], "from_location": c["location"], "to_location": req["target"],
                      "lp_before": c["lp"], "status_before": c["status"], "qty_before": c["qty"], "message": it["why"] or it.get("note"),
                      "left_pallet": it["left_pallet"], "before_json": _j(plan["lives"].get(c["serial"])), "plan_json": _j(it)})
    return {"ok": True, "plan_id": plan_id, "target": req["target"], "part_no": req["part_no"], "set_no": req["set_no"],
            "job_no": req["job_no"], "env": ENV, "items": plan["items"], "expires_s": PLAN_TTL,
            "to_send": sum(1 for it in plan["items"] if it["send"]),
            "containers_moving": sum(len(it["covered"]) for it in plan["items"] if it["send"])}


@app.post("/move/cancel")
def move_cancel():
    pid = request.form.get("plan_id", "")
    plan = plan_pop(pid)
    if plan:
        at = dt.datetime.now(dt.timezone.utc).isoformat()
        serials = plan.get("serials") or [r["serial"] for r in plan.get("rows", [])]     # audit 11-23 #20: undo plans too
        for s in serials:
            log_move({"at": at, "event": "cancelled", "batch_id": pid, "env": ENV, "requested_by": who(),
                      "set_no": plan.get("set_no"), "job_no": plan.get("job_no"), "part_id": plan.get("part_id"), "serial": s,
                      "to_location": plan.get("target"), "message": f"{plan.get('kind') or 'move'} review cancelled"})
    return {"ok": True}


def _changed(before: dict | None, now: dict | None) -> str | None:
    """Why a container no longer matches what the person approved (None = same)."""
    if before is None or now is None:
        return "not found in Plex" if now is None else None
    for k, label in (("location", "location"), ("containerStatus", "status"), ("quantity", "quantity"), ("masterUnitNo", "pallet")):
        if (before.get(k) or None) != (now.get(k) or None):
            return f"{label} changed since you reviewed it ({before.get(k)} -> {now.get(k)})"
    return None


def _flash_results(lines: list[tuple[str, str]], summary: str, ok: bool) -> None:
    """Per-container lines, capped (audit 11-23 #21: a big batch overflowed the flash cookie)."""
    for msg, cat in lines[:12]:
        flash(msg, cat)
    if len(lines) > 12:
        flash(f"... and {len(lines) - 12} more: every line is in the Move log.", "ok" if ok else "error")
    flash(summary, "ok" if ok else "error")


@app.post("/move")
def move():
    """Approve: carries out a reviewed plan (plan_id from /move/preview), re-checking every container live first.
    Each Plex call is logged the moment Plex answers (event 'sent'), then again once read back ('move')."""
    set_no = request.form.get("set_no", "")
    back = redirect(url_for("job_set", set_no=set_no) if set_no else url_for("index"))
    err = _gate_refused(request.form, "approve")
    if err:
        flash(err, "error")
        return back
    plan_id = request.form.get("plan_id", "")
    plan = plan_pop(plan_id)
    if not plan:
        flash("That review has expired or was already used. Press the move button again to review it.", "error")
        return back
    if plan.get("by") != who():                                   # audit 11-23 #16
        flash(f"Only the person who opened that review ({plan.get('by')}) can approve it. Open your own review.", "error")
        return back
    target = plan["target"]
    base = {"env": ENV, "requested_by": who(), "set_no": plan["set_no"], "job_no": plan["job_no"], "to_location": target,
            "batch_id": plan_id, "part_id": plan["part_id"], "part_no": plan["part_no"]}
    now_iso = lambda: dt.datetime.now(dt.timezone.utc).isoformat()

    def row(s, **kw):
        b = plan["lives"].get(s) or {}
        return {**base, "at": now_iso(), "serial": s, "from_location": b.get("location"), "lp_before": b.get("masterUnitNo"),
                "status_before": b.get("containerStatus"), "qty_before": b.get("quantity"), "before_json": _j(plan["lives"].get(s)), **kw}

    results = []                                        # (serial, item, plex detail or None, message, left_pallet)
    with _move_lock:
        part_list = part_containers(plan["part_id"], fresh=True)
        alloc = part_alloc(plan["part_id"], fresh=True)
        lives = _live_lookup(plan["serials"], part_list)
        for it in plan["items"]:
            if not it["send"]:
                for s in it["covered"]:
                    log_move(row(s, event="refused", ok=False, message=f"not moved: {it['why']}"))
                    results.append((s, None, None, f"not moved: {it['why']}", None))
                continue
            whys = {s: _changed(plan["lives"].get(s), lives[s])
                    or picking.check_movable(lives[s], target, job_no=plan["job_no"], alloc=alloc) for s in it["covered"]}
            if it["pallet"] and not any(whys.values()):
                now_lp = lp_members(it["pallet"], lives[it["covered"][0]])
                if now_lp != it["lp_snapshot"]:
                    whys = {s: f"pallet {it['pallet']} changed since you reviewed it ({len(it['lp_snapshot'] or [])} -> "
                               f"{'?' if now_lp is None else len(now_lp)} containers)" for s in it["covered"]}
            if any(whys.values()):
                for s in it["covered"]:
                    m = f"not moved: {whys[s] or 'a container on its pallet changed or may not move'}"
                    log_move(row(s, event="refused", ok=False, message=m))
                    results.append((s, None, None, m, None))
                continue
            d = web.move_detail(it["send"], target)
            for s in it["covered"]:                   # audit 11-23 #3: logged before anything else can fail
                log_move(row(s, event="sent", moved_as=it["send"], ok=bool(d["ok"]), message=d["message"],
                             left_pallet=it["left_pallet"], plex_request=_j(d["request"]), plex_response=d["body"],
                             plex_status=d["status"], plex_ms=d["ms"], plan_json=_j(it)))
                results.append((s, it["send"], d, d["message"], it["left_pallet"]))
        moved = [s for s, item, d, _, _ in results if item]
        after, read_note = {}, None
        if moved:
            try:
                after = _live_lookup(moved, part_containers(plan["part_id"], fresh=True))
            except Exception as e:  # noqa: BLE001 - the 'sent' rows already record the moves
                read_note = f"read-back failed ({str(e)[:80]}); Plex's answer is logged"
    done = failed = 0
    lines = []
    for s, item, d, msg, left in results:
        if not item:
            failed += 1
            lines.append((f"{s}: {msg}", "error"))
            continue
        now = (after.get(s) or {}).get("location")
        ok = bool(d["ok"]) and now == target
        log_move(row(s, event="move", moved_as=item, ok=ok, message=msg + (f" [{read_note}]" if read_note else ""),
                     verified_location=now, left_pallet=left, after_json=_j(after.get(s)), plex_request=_j(d["request"]),
                     plex_response=d["body"], plex_status=d["status"], plex_ms=d["ms"]))
        done += ok
        failed += not ok
        note = f" (left pallet {left})" if left else (f" (as pallet {item})" if item != s else "")
        lines.append((f"{s}: {msg}{note} (now at {now or '?'})", "ok" if ok else "error"))
    _flash_results(lines, f"{done} moved to {target}, {failed} not moved. Batch {plan_id}: undo it from the Move log within "
                          f"{undo.UNDO_MINUTES} min if nothing touches the containers meanwhile.", not failed)
    return back


# `at` is a reserved word in BigQuery: unquoted, this query failed and /log silently showed only the
# instance's own file (lost on every restart). Found in the live audit, 2026-11-23.
LOG_SQL = "SELECT * FROM `voxdatalake.PlexOps.picking_move_log` ORDER BY `at` DESC LIMIT 300"


@app.get("/favicon.ico")
def favicon():
    return "", 204


def load_log_rows(limit: int = 2000) -> list[dict]:
    """The move log, newest first: BigQuery when PICKING_BQ_LOG=1, else (or if that fails) the instance's file."""
    rows = []
    if os.environ.get("PICKING_BQ_LOG") == "1":
        try:
            from google.cloud import bigquery
            rows = [dict(r) for r in bigquery.Client(project="voxdatalake").query(LOG_SQL.replace("300", str(limit))).result()]
            for r in rows:
                r["at"] = r["at"].isoformat() if hasattr(r["at"], "isoformat") else str(r["at"])
        except Exception as e:  # noqa: BLE001 - fall back to the local file
            app.logger.warning("reading picking_move_log: %s", e)
    if not rows and LOG.exists():
        rows = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()][-limit:][::-1]
    return rows


@app.get("/log")
def move_log():
    rows = load_log_rows()
    now = dt.datetime.now(dt.timezone.utc)
    return render_template("log.html", batches=undo.batches(rows, now)[:150], rows=rows[:300], undo_minutes=undo.UNDO_MINUTES,
                           can_move=ENV == "test" or ALLOW_PROD_MOVES)


def _history(serials: list[str], since) -> tuple[list, str | None]:
    try:
        return web.sql(undo.history_sql(serials, since)), None
    except Exception as e:  # noqa: BLE001 - the live check still decides
        return [], f"Plex history could not be read ({str(e)[:80]}); only the live check was made."


def _undo_review(batch_id: str) -> dict:
    """Per moved container of a batch: can it be put back, and everything Plex recorded since."""
    rows = undo.moved_rows(load_log_rows(), batch_id)                  # audit 11-23 #11: 'sent' rows count
    if not rows:
        return {"ok": False, "error": f"No moves found for batch {batch_id}."}
    if {r.get("env") for r in rows} != {ENV}:
        return {"ok": False, "error": f"Batch {batch_id} was in Plex {rows[0].get('env')}; this app is on Plex {ENV}."}
    serials = list(dict.fromkeys(r["serial"] for r in rows))
    with ThreadPoolExecutor(max_workers=min(WORKERS, len(serials))) as ex:
        live = dict(zip(serials, ex.map(api.container, serials)))
    history, hist_note = _history(serials, min(undo._utc(r["at"]) for r in rows))
    now = dt.datetime.now(dt.timezone.utc)
    checks = [undo.check(r, live.get(r["serial"]), history, now, app_user=APP_PLEX_USER) for r in rows]
    return {"ok": True, "batch_id": batch_id, "rows": rows, "live": live, "history": history, "checks": checks,
            "history_note": hist_note or ("Plex history in production is Plex's reporting copy (about 4 h behind); "
                                          "the live check (location, quantity, status, pallet) is current." if ENV == "prod" else None)}


@app.post("/log/undo/review")
def undo_review():
    """What undoing a batch would do, and the detailed Plex activity since the move. Nothing is moved."""
    r = _undo_review(request.form.get("batch_id", ""))
    if not r["ok"]:
        return r, 400
    can = [c for c in r["checks"] if c["ok"]]
    plan_id = None
    if can and (ENV == "test" or ALLOW_PROD_MOVES) and who() != "unverified":
        plan_id = plan_put({"kind": "undo", "batch_id": r["batch_id"], "rows": r["rows"], "by": who()})
    for c in r["checks"]:
        log_move({"at": dt.datetime.now(dt.timezone.utc).isoformat(), "event": "undo-review", "batch_id": f"restore-{r['batch_id']}",
                  "env": ENV, "requested_by": who(), "serial": c["serial"], "from_location": c["now"], "to_location": c["from"],
                  "message": "can undo" if c["ok"] else ("already back" if c["back"] else "; ".join(c["reasons"])),
                  "plan_json": _j({"activity": c["activity"], "age_min": c["age_min"]})})
    return {"ok": True, "batch_id": r["batch_id"], "plan_id": plan_id, "env": ENV, "undo_minutes": undo.UNDO_MINUTES,
            "checks": r["checks"], "history_note": r["history_note"],
            "moves_enabled": ENV == "test" or ALLOW_PROD_MOVES, "can": len(can)}


@app.post("/log/undo")
def undo_apply():
    """Put back the containers of a reviewed undo that are STILL exactly as we left them (live record and a fresh
    read of Plex's history). A pallet goes back whole only if every container we moved on it qualifies and the
    pallet holds exactly those containers (audit 11-23 #1); otherwise the qualifying ones go back one by one."""
    back = redirect(url_for("move_log"))
    err = _gate_refused(request.form, "undo")
    if err:
        flash(err, "error")
        return back
    plan = plan_pop(request.form.get("plan_id", ""))
    if not plan or plan.get("kind") != "undo":
        flash("That undo review has expired or was already used. Open it again from the log.", "error")
        return back
    if plan.get("by") != who():
        flash(f"Only the person who opened that undo review ({plan.get('by')}) can approve it.", "error")
        return back
    import restore_moves
    rows = plan["rows"]
    done = bad = 0
    lines = []
    with _move_lock:
        serials = list(dict.fromkeys(r["serial"] for r in rows))
        live = {s: api.container(s) for s in serials}
        history, _ = _history(serials, min(undo._utc(r["at"]) for r in rows))       # audit 11-23 #19: fresh history
        now = dt.datetime.now(dt.timezone.utc)
        checks = {r["serial"]: undo.check(r, live.get(r["serial"]), history, now, app_user=APP_PLEX_USER) for r in rows}
        ok_rows = [r for r in rows if checks[r["serial"]]["ok"]]
        actions = restore_moves.plan_restore(ok_rows, live, all_rows=rows,
                                             lp_members=lambda lp, s: lp_members(lp, live.get(s)))
        for c in checks.values():
            if not c["ok"]:
                lines.append((f"{c['serial']}: not put back: {'already back' if c['back'] else '; '.join(c['reasons'])}",
                              "ok" if c["back"] else "error"))
        for x in [x for x in actions if x["kind"] in ("pallet", "container")]:
            d = web.move_detail(x["send"], x["to"])
            for s in x["serials"]:
                try:
                    now_loc = (api.container(s) or {}).get("location")
                except Exception:  # noqa: BLE001 - logged with Plex's answer regardless
                    now_loc = None
                ok = bool(d["ok"]) and now_loc == x["to"]
                done += ok
                bad += not ok
                left = next((r.get("left_pallet") for r in rows if r["serial"] == s), None)
                log_move({"at": dt.datetime.now(dt.timezone.utc).isoformat(), "event": "restore", "batch_id": f"restore-{plan['batch_id']}",
                          "env": ENV, "requested_by": who(), "serial": s, "moved_as": x["send"], "from_location": (live.get(s) or {}).get("location"),
                          "to_location": x["to"], "ok": ok, "message": d["message"] + (f" [{x['note']}]" if x.get("note") else ""),
                          "verified_location": now_loc, "before_json": _j(live.get(s)), "plex_request": _j(d["request"]),
                          "plex_response": d["body"], "plex_status": d["status"], "plex_ms": d["ms"], "left_pallet": left})
                note = (f" (it had left pallet {left}: re-add it in Plex's Add to Master Unit screen)" if left else "") + \
                       (f" ({x['note']})" if x.get("note") else "")
                lines.append((f"{s}: {d['message']} (now at {now_loc or '?'}){note}", "ok" if ok else "error"))
    _flash_results(lines, f"Undo of batch {plan['batch_id']}: {done} put back, {bad} to check.", not bad)
    return back


if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 8085)), threaded=True)
