"""ETL dispatcher — starts Cloud Run ETL jobs at the times in `etl_schedule`.

Phase 2 of docs/PROBE_BUILD_PLAN.md. Cloud Scheduler cannot read BigQuery, so
this Cloud Function (Gen 2) does: Cloud Scheduler calls it every 5 minutes, and
on each call it

  1. RECONCILES runs it started earlier: a run writes its own outcome onto its
     dispatch row when it finishes (main.py record_dispatch_outcome). A run that
     crashed before getting there is caught here from the Cloud Run execution's
     own status, so a dead run is never mistaken for one still going.
  2. DISPATCHES every enabled `etl_schedule` row whose time (America/Denver) has
     come within the last WINDOW_MINUTES and that has no dispatch row yet for
     that exact slot — the slot (job_name, scheduled_for) is the idempotency
     key, so two overlapping calls, or a call retried by Cloud Scheduler, start
     a job once. A job whose previous dispatch is still running is not started
     twice; the slot is logged as `skipped-busy` instead.
  3. FOLLOWS UP a run that ended `failed` or `partial`: ONE probe-mode run,
     FOLLOWUP_DELAY_MINUTES after it finished. A follow-up never gets a
     follow-up of its own, so a persistent error waits for the next scheduled
     time instead of looping (Emilio, 2026-10-19: "if it failed, probe it after
     15 mins" — and no immediate retry, since right away the error is likely
     the same).

The job learns how it was started from two env overrides on the run request:
RUN_MODE (probe | full) and DISPATCH_ID, plus DISPATCH_LOG_TABLE so it can find
this dataset (the jobs' own BQ_DATASET is PlexProd or PlexTest; the dispatcher's
tables live in OPS_DATASET). Sending overrides needs run.jobs.runWithOverrides,
which the ETL service account holds via the plexEtlRunWithOverrides role
(OPEN_ITEMS D2).

Changing a time is a SQL UPDATE on etl_schedule, never a deploy — see
docs/OPERATIONS.md § "ETL schedule".

Edge cases, by design: a follow-up that finds its job busy is logged
`skipped-busy` and not retried (the job is busy only because it is running
again); a `dispatch-failed` start gets no follow-up (Cloud Run refused it, and
the next scheduled time tries again).

Call with ?dry_run=1 to see what it WOULD do: no writes, no runs.

Planning (which slots are due, which runs need a follow-up, what an execution's
status means) is pure functions at the top of this file, unit-tested in
tests/test_dispatcher.py without BigQuery or Cloud Run.
"""
import datetime as dt
import json
import logging
import os
import uuid
from zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("etl_dispatcher")

GCP_PROJECT = os.environ.get("GCP_PROJECT", "voxdatalake")
REGION = os.environ.get("REGION", "us-central1")
OPS_DATASET = os.environ.get("OPS_DATASET", "PlexOps")
SCHEDULE_TABLE = os.environ.get("SCHEDULE_TABLE", "etl_schedule")
LOG_TABLE = os.environ.get("DISPATCH_LOG_TABLE", "etl_dispatch_log")
TZ = ZoneInfo(os.environ.get("SCHEDULE_TIME_ZONE", "America/Denver"))

# A slot is still dispatched if the dispatcher reaches it up to this late — a
# missed 5-minute tick (or a short outage) must not silently drop a run.
WINDOW_MINUTES = int(os.environ.get("WINDOW_MINUTES", "30"))
FOLLOWUP_DELAY_MINUTES = int(os.environ.get("FOLLOWUP_DELAY_MINUTES", "15"))
# A failed run older than this gets no follow-up (e.g. the dispatcher was down
# for a day); the next scheduled time covers it.
FOLLOWUP_HORIZON_HOURS = int(os.environ.get("FOLLOWUP_HORIZON_HOURS", "6"))
# A dispatched run with no outcome and no finished execution after this long is
# treated as lost (failed). Longer than any job's timeout (max 900 s).
LOST_AFTER_MINUTES = int(os.environ.get("LOST_AFTER_MINUTES", "120"))
# After an execution completes, how long the job's own outcome row may lag
# before the execution's status is used instead.
OUTCOME_GRACE_MINUTES = int(os.environ.get("OUTCOME_GRACE_MINUTES", "5"))

VALID_MODES = ("probe", "full")
FOLLOWUP_OUTCOMES = ("failed", "partial", "lost")


# ── Pure planning ─────────────────────────────────────────────────────────────

def parse_run_time(value):
    """'13:05' -> (13, 5). Raises ValueError on anything else."""
    hh, mm = str(value).strip().split(":")
    h, m = int(hh), int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"run_time out of range: {value!r}")
    return h, m


def slot_for(run_time, local_date):
    """The UTC instant of run_time (America/Denver wall clock) on local_date.
    DST-safe: the wall-clock time is placed in the zone, then converted."""
    h, m = parse_run_time(run_time)
    local = dt.datetime(local_date.year, local_date.month, local_date.day, h, m, tzinfo=TZ)
    return local.astimezone(dt.timezone.utc)


def due_slots(schedule, now_utc, logged_slots, busy_jobs, window_minutes=WINDOW_MINUTES):
    """Which schedule rows should act now.

    schedule      list of dicts: job_name, run_time, mode, enabled
    logged_slots  set of (job_name, scheduled_for_utc) already in the dispatch log
    busy_jobs     set of job_names with a dispatch still running
    Returns a list of dicts: job_name, mode, scheduled_for (UTC), action
    ('dispatch' or 'skipped-busy'), and 'invalid' rows are reported with
    action 'invalid' so a typo in the table is visible rather than ignored.
    """
    out = []
    local_now = now_utc.astimezone(TZ)
    # Today and yesterday: a slot at 23:55 is still due at 00:10.
    dates = {local_now.date(), (local_now - dt.timedelta(days=1)).date()}
    window = dt.timedelta(minutes=window_minutes)
    planned = set()
    for row in schedule:
        if not row.get("enabled"):
            continue
        job, mode = row.get("job_name"), row.get("mode")
        try:
            slots = [slot_for(row.get("run_time"), d) for d in dates]
        except (ValueError, TypeError) as exc:
            out.append({"job_name": job, "mode": mode, "scheduled_for": None,
                        "action": "invalid", "detail": f"bad run_time {row.get('run_time')!r}: {exc}"})
            continue
        if mode not in VALID_MODES or not job:
            out.append({"job_name": job, "mode": mode, "scheduled_for": None,
                        "action": "invalid", "detail": f"mode must be one of {VALID_MODES}"})
            continue
        for slot in slots:
            if not (now_utc - window < slot <= now_utc):
                continue
            key = (job, slot)
            if key in logged_slots or key in planned:
                continue
            planned.add(key)
            action = "skipped-busy" if job in busy_jobs else "dispatch"
            out.append({"job_name": job, "mode": mode, "scheduled_for": slot, "action": action})
            busy_jobs = busy_jobs | {job} if action == "dispatch" else busy_jobs
    return out


def followups_due(log_rows, now_utc, delay_minutes=FOLLOWUP_DELAY_MINUTES,
                  horizon_hours=FOLLOWUP_HORIZON_HOURS):
    """Dispatch rows that have earned their ONE follow-up probe.

    log_rows: dicts with dispatch_id, job_name, reason, outcome, finished_at,
    followup_of. A follow-up is owed when the run ended failed/partial/lost, it
    was not itself a follow-up, none has been sent for it yet, and it finished
    at least delay_minutes ago (but not longer ago than horizon_hours)."""
    already = {r.get("followup_of") for r in log_rows if r.get("followup_of")}
    out = []
    for r in log_rows:
        if r.get("reason") == "follow-up" or r.get("outcome") not in FOLLOWUP_OUTCOMES:
            continue
        if r["dispatch_id"] in already or not r.get("finished_at"):
            continue
        age = now_utc - r["finished_at"]
        if dt.timedelta(minutes=delay_minutes) <= age <= dt.timedelta(hours=horizon_hours):
            out.append(r)
    return out


def reconcile(row, execution, now_utc, lost_after=LOST_AFTER_MINUTES,
              grace=OUTCOME_GRACE_MINUTES):
    """The outcome to write for a dispatch row that has none yet, or None to
    leave it for the job (or a later tick) to settle.

    execution: dict from the Cloud Run API (completionTime, succeededCount,
    failedCount) or None when it could not be read."""
    if execution and execution.get("completionTime"):
        finished = _ts(execution["completionTime"])
        tasks = int(execution.get("taskCount") or 1)
        if (int(execution.get("failedCount") or 0) > 0
                or int(execution.get("cancelledCount") or 0) > 0
                or int(execution.get("succeededCount") or 0) < tasks):
            # Failed, or cancelled by hand (cancelledCount, failedCount 0):
            # either way it did not finish its work, so it earns a follow-up.
            return "failed", finished, "execution failed or was cancelled before the job wrote its outcome"
        if now_utc - finished >= dt.timedelta(minutes=grace):
            # Succeeded at the Cloud Run level but never wrote an outcome — e.g.
            # its BigQuery write failed. Treat as success: the job's own
            # job_run_log / email still carry the detail.
            return "succeeded-unrecorded", finished, "execution succeeded; job did not record an outcome"
        return None
    if now_utc - row["dispatched_at"] >= dt.timedelta(minutes=lost_after):
        return "lost", now_utc, f"no outcome and no finished execution after {lost_after} min"
    return None


def _ts(value):
    """RFC3339 from the Run API -> aware datetime."""
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def run_body(mode, dispatch_id):
    """The jobs.run request body: env overrides on the job's only container."""
    return {"overrides": {"containerOverrides": [{"env": [
        {"name": "RUN_MODE", "value": mode},
        {"name": "DISPATCH_ID", "value": dispatch_id},
        {"name": "DISPATCH_LOG_TABLE", "value": f"{OPS_DATASET}.{LOG_TABLE}"},
    ]}]}}


# ── IO: BigQuery and Cloud Run ────────────────────────────────────────────────

def _bq():
    from google.cloud import bigquery
    return bigquery.Client(project=GCP_PROJECT)


def _fq(table):
    return f"`{GCP_PROJECT}.{OPS_DATASET}.{table}`"


def _query(bq, sql, params=None):
    from google.cloud import bigquery
    cfg = bigquery.QueryJobConfig(query_parameters=params or [])
    return [dict(r) for r in bq.query(sql, job_config=cfg).result()]


def _param(name, value, kind="STRING"):
    from google.cloud import bigquery
    return bigquery.ScalarQueryParameter(name, kind, value)


def _session():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return AuthorizedSession(creds)


def start_job(session, job_name, mode, dispatch_id):
    url = (f"https://run.googleapis.com/v2/projects/{GCP_PROJECT}/locations/{REGION}"
           f"/jobs/{job_name}:run")
    resp = session.post(url, json=run_body(mode, dispatch_id), timeout=60)
    if resp.status_code >= 300:
        raise RuntimeError(f"jobs.run {job_name} -> HTTP {resp.status_code}: {resp.text[:400]}")
    meta = (resp.json() or {}).get("metadata") or {}
    return meta.get("name", "")   # projects/…/jobs/<job>/executions/<execution>


def get_execution(session, job_name, execution_name):
    """Accepts the full resource name or the short one the job writes back."""
    if not execution_name:
        return None
    name = execution_name if execution_name.startswith("projects/") else (
        f"projects/{GCP_PROJECT}/locations/{REGION}/jobs/{job_name}/executions/{execution_name}")
    resp = session.get(f"https://run.googleapis.com/v2/{name}", timeout=30)
    if resp.status_code >= 300:
        log.warning("executions.get %s -> HTTP %s", name, resp.status_code)
        return None
    return resp.json()


def tick(now_utc=None, dry_run=False):
    """One dispatcher pass. Returns a JSON-able summary of what it did."""
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    bq, session = _bq(), _session()
    summary = {"now_utc": now.isoformat(), "dry_run": dry_run, "reconciled": [],
               "dispatched": [], "skipped": [], "followups": [], "errors": []}

    # 1. Settle runs still open.
    open_rows = _query(bq, f"""
        SELECT dispatch_id, job_name, execution_name, dispatched_at
        FROM {_fq(LOG_TABLE)}
        WHERE outcome IS NULL
          AND dispatched_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 DAY)""")
    busy = set()
    for row in open_rows:
        try:
            execution = get_execution(session, row["job_name"], row.get("execution_name"))
            verdict = reconcile(row, execution, now)
        except Exception as exc:   # one unreadable execution must not stop the pass
            summary["errors"].append(f"reconcile {row['dispatch_id']}: {exc}")
            busy.add(row["job_name"])
            continue
        if verdict is None:
            busy.add(row["job_name"])
            continue
        outcome, finished, detail = verdict
        summary["reconciled"].append({"dispatch_id": row["dispatch_id"], "job_name": row["job_name"],
                                      "outcome": outcome})
        if not dry_run:
            _query(bq, f"""
                UPDATE {_fq(LOG_TABLE)}
                SET outcome = @outcome, finished_at = @finished, detail = @detail
                WHERE dispatch_id = @id AND outcome IS NULL""",
                   [_param("outcome", outcome), _param("finished", finished, "TIMESTAMP"),
                    _param("detail", detail), _param("id", row["dispatch_id"])])

    # 2. Scheduled slots.
    schedule = _query(bq, f"SELECT job_name, run_time, mode, enabled FROM {_fq(SCHEDULE_TABLE)}")
    logged = {(r["job_name"], r["scheduled_for"]) for r in _query(bq, f"""
        SELECT job_name, scheduled_for FROM {_fq(LOG_TABLE)}
        WHERE scheduled_for > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 DAY)""")}
    for slot in due_slots(schedule, now, logged, busy):
        if slot["action"] == "invalid":
            summary["errors"].append(f"schedule row for {slot['job_name']}: {slot['detail']}")
            continue
        _dispatch(bq, session, slot["job_name"], slot["mode"], "schedule",
                  slot["scheduled_for"], None, slot["action"], summary, dry_run)
        if slot["action"] == "dispatch":
            busy.add(slot["job_name"])

    # 3. One follow-up probe per failed run.
    recent = _query(bq, f"""
        SELECT dispatch_id, job_name, reason, outcome, finished_at, followup_of
        FROM {_fq(LOG_TABLE)}
        WHERE dispatched_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)""")
    for row in followups_due(recent, now):
        action = "skipped-busy" if row["job_name"] in busy else "dispatch"
        _dispatch(bq, session, row["job_name"], "probe", "follow-up", None,
                  row["dispatch_id"], action, summary, dry_run)
        if action == "dispatch":
            busy.add(row["job_name"])

    log.info("tick: %s", json.dumps(summary, default=str))
    return summary


def _dispatch(bq, session, job, mode, reason, scheduled_for, followup_of, action, summary, dry_run):
    dispatch_id = uuid.uuid4().hex[:16]
    entry = {"dispatch_id": dispatch_id, "job_name": job, "mode": mode, "reason": reason,
             "scheduled_for": scheduled_for, "followup_of": followup_of}
    bucket = "followups" if reason == "follow-up" else ("dispatched" if action == "dispatch" else "skipped")
    summary[bucket].append({**entry, "action": action})
    if dry_run:
        return
    # The row goes in BEFORE the run starts: a crash between the two leaves a
    # row the next tick reconciles as lost, never a run with no row (which
    # would be started again).
    _query(bq, f"""
        INSERT INTO {_fq(LOG_TABLE)}
          (dispatch_id, job_name, mode, reason, scheduled_for, followup_of, dispatched_at, outcome, finished_at, detail)
        VALUES (@id, @job, @mode, @reason, @slot, @followup_of, CURRENT_TIMESTAMP(),
                @outcome, IF(@outcome IS NULL, NULL, CURRENT_TIMESTAMP()), @detail)""",
           [_param("id", dispatch_id), _param("job", job), _param("mode", mode),
            _param("reason", reason), _param("slot", scheduled_for, "TIMESTAMP"),
            _param("followup_of", followup_of),
            _param("outcome", None if action == "dispatch" else action),
            _param("detail", None if action == "dispatch" else "previous dispatch of this job still running")])
    if action != "dispatch":
        return
    import requests
    try:
        execution = start_job(session, job, mode, dispatch_id)
    except requests.exceptions.Timeout as exc:
        # Cloud Run may well have created the execution before the POST timed
        # out. Leave the row OPEN: the job writes its own outcome if it runs,
        # and the next ticks reconcile it as `lost` after LOST_AFTER_MINUTES if
        # it never did. Marking it dispatch-failed here could hide a live run.
        summary["errors"].append(f"start {job}: timed out, left open for reconcile: {exc}")
        return
    except Exception as exc:
        # jobs.run itself refused (HTTP error): no execution exists.
        summary["errors"].append(f"start {job}: {exc}")
        _query(bq, f"""
            UPDATE {_fq(LOG_TABLE)}
            SET outcome = 'dispatch-failed', finished_at = CURRENT_TIMESTAMP(), detail = @d
            WHERE dispatch_id = @id AND outcome IS NULL""", [_param("d", str(exc)[:1000]), _param("id", dispatch_id)])
        return
    try:
        # Bookkeeping only. If it fails the run still stands: the job writes its
        # own short execution name back, which reconcile() also accepts.
        _query(bq, f"UPDATE {_fq(LOG_TABLE)} SET execution_name = @ex WHERE dispatch_id = @id",
               [_param("ex", execution), _param("id", dispatch_id)])
    except Exception as exc:
        summary["errors"].append(f"started {job}, but could not record its execution name: {exc}")


# ── Cloud Functions entry point ───────────────────────────────────────────────

def dispatch(request):
    """HTTP entry point (Cloud Scheduler, every 5 minutes)."""
    dry = str((request.args or {}).get("dry_run", "")).lower() in ("1", "true", "yes")
    summary = tick(dry_run=dry)
    return (json.dumps(summary, default=str), 200, {"Content-Type": "application/json"})
