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
  4. HOLDS everything while Plex refuses connections (2026-10-22, see
     OUTAGE_SIGNATURE below): scheduled slots are logged `held-outage`, a quiet
     `canary` run tests the connection every CANARY_INTERVAL_MINUTES, and once
     one connects every held job gets one `recovery` run, mailed as one batch.

The job learns how it was started from two env overrides on the run request:
RUN_MODE (probe | full) and DISPATCH_ID, plus DISPATCH_LOG_TABLE so it can find
this dataset (the jobs' own BQ_DATASET is PlexProd or PlexTest; the dispatcher's
tables live in OPS_DATASET). Since 2026-10-21 it also sends EMAIL_ROLE,
BATCH_ID and BATCH_KIND (batch_for), so only the first and last job of each
hour's batch email, the last one a digest of all of them. Sending overrides needs run.jobs.runWithOverrides,
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
# The Functions Framework configures the root logger before this module loads,
# so basicConfig above is a no-op there and INFO lines were dropped (seen on
# the first deploy, 2026-10-19). Set the level explicitly; the tick summary is
# also printed as one JSON line, which Cloud Logging stores as jsonPayload.
log.setLevel(logging.INFO)

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
# treated as lost (failed). Longer than any job's timeout (max 2400 s).
LOST_AFTER_MINUTES = int(os.environ.get("LOST_AFTER_MINUTES", "120"))
# After an execution completes, how long the job's own outcome row may lag
# before the execution's status is used instead.
OUTCOME_GRACE_MINUTES = int(os.environ.get("OUTCOME_GRACE_MINUTES", "5"))

VALID_MODES = ("probe", "full")
FOLLOWUP_OUTCOMES = ("failed", "partial", "lost")

# Plex outage breaker (2026-10-22). On 2026-10-21, from 11 PM to 4:30 AM, Plex
# prod refused every ODBC connection: every scheduled run failed, each failure
# earned a follow-up that failed too, and each mailed. Now, once
# OUTAGE_THRESHOLD runs in a row (any jobs, by finish time) fail to connect,
# the breaker is open:
#   - scheduled slots are logged `held-outage` instead of started;
#   - follow-ups wait;
#   - every CANARY_INTERVAL_MINUTES one light job (CANARY_JOBS, first that is
#     free) is started as a `canary`. The first canary of an outage mails its
#     failure ("outage-alert"), the rest are silent.
# Any run that connects — a canary that succeeds, partial or skipped — closes
# it. Then each job with a held slot gets ONE `recovery` run (full if any held
# slot was full), RECOVERY_PER_TICK per tick, mailing as one batch whose last
# job sends the digest. Stateless: everything is read back from the log.
OUTAGE_SIGNATURE = "ODBC connection failed"   # main.py's prefix on a failed connect
OUTAGE_THRESHOLD = int(os.environ.get("OUTAGE_THRESHOLD", "2"))
CANARY_INTERVAL_MINUTES = int(os.environ.get("CANARY_INTERVAL_MINUTES", "10"))
# The quickest probes in PlexProd.job_run_log (about 20-30 s), in order of
# preference. An empty or stale list falls back to any scheduled job.
CANARY_JOBS = os.environ.get(
    "CANARY_JOBS",
    "plex-etl-sales-quotes plex-etl-quality-supplier-returns plex-etl-part-obsolescence").split()
RECOVERY_HORIZON_HOURS = int(os.environ.get("RECOVERY_HORIZON_HOURS", "24"))
RECOVERY_PER_TICK = int(os.environ.get("RECOVERY_PER_TICK", "4"))
HEALTHY_OUTCOMES = ("success", "partial", "skipped", "succeeded-unrecorded")
# Outcomes of a dispatch row that never started a run.
NOT_STARTED = ("held-outage", "skipped-busy", "dispatch-failed")
# Runs that never earn a follow-up: a follow-up, and the breaker's own runs
# (a failed canary is the next canary's job; a failed recovery waits for the
# next scheduled time like any follow-up would).
NO_FOLLOWUP_REASONS = ("follow-up", "canary", "recovery")


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
            out.append({"job_name": job, "mode": mode, "scheduled_for": slot, "action": action,
                        "run_time": row.get("run_time")})
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
        if r.get("reason") in NO_FOLLOWUP_REASONS or r.get("outcome") not in FOLLOWUP_OUTCOMES:
            continue
        if r["dispatch_id"] in already or not r.get("finished_at"):
            continue
        # The job has run again since (a scheduled slot, a recovery run): that
        # run is the follow-up.
        if _covered(r, log_rows):
            continue
        age = now_utc - r["finished_at"]
        if dt.timedelta(minutes=delay_minutes) <= age <= dt.timedelta(hours=horizon_hours):
            out.append(r)
    return out


def _covered(row, log_rows):
    """Whether a run of the same job started after `row` and does its work: any
    started run covers a probe; only a full run covers a full one. A canary
    that could not connect covers nothing."""
    for r in log_rows:
        if (r.get("job_name") == row.get("job_name") and r.get("dispatch_id") != row.get("dispatch_id")
                and r.get("dispatched_at") and row.get("dispatched_at")
                and r["dispatched_at"] > row["dispatched_at"]
                and r.get("outcome") not in NOT_STARTED
                and not (r.get("reason") == "canary" and r.get("outcome") in ("failed", "lost"))
                and (r.get("mode") == "full" or row.get("mode") != "full")):
            return True
    return False


def connect_evidence(row):
    """'up' if this run reached Plex, 'down' if it could not connect, else
    None (a failure of some other kind says nothing about Plex)."""
    outcome = row.get("outcome")
    if outcome in HEALTHY_OUTCOMES:
        return "up"
    if outcome == "failed" and str(row.get("detail") or "").startswith(OUTAGE_SIGNATURE):
        return "down"
    return None


def outage_state(log_rows, threshold=OUTAGE_THRESHOLD):
    """None while Plex answers. Else {since, failures}: the newest `failures`
    finished runs that tell anything about Plex all failed to connect, and the
    first of them finished at `since`."""
    evidence = sorted((r for r in log_rows if r.get("finished_at") and connect_evidence(r)),
                      key=lambda r: r["finished_at"], reverse=True)
    streak = []
    for r in evidence:
        if connect_evidence(r) == "up":
            break
        streak.append(r)
    if len(streak) < threshold:
        return None
    return {"since": streak[-1]["finished_at"], "failures": len(streak)}


def canary_due(log_rows, now_utc, outage, schedule, busy_jobs,
               interval_minutes=CANARY_INTERVAL_MINUTES, preferred=CANARY_JOBS):
    """The canary to start now during an outage, or None: {job_name, role}.

    One at a time, interval_minutes after the last one started (or after the
    outage opened). The first canary of an outage has role 'outage-alert' —
    its failure is the outage's one email — and the rest 'canary'."""
    canaries = [r for r in log_rows if r.get("reason") == "canary"
                and r.get("dispatched_at") and r["dispatched_at"] >= outage["since"]]
    if any(r.get("outcome") is None for r in canaries):
        return None
    last = max([r["dispatched_at"] for r in canaries] + [outage["since"]])
    if now_utc - last < dt.timedelta(minutes=interval_minutes):
        return None
    enabled = sorted({r["job_name"] for r in schedule if r.get("enabled") and r.get("job_name")})
    for job in [j for j in preferred if j in enabled] + enabled:
        if job not in busy_jobs:
            return {"job_name": job, "role": "canary" if canaries else "outage-alert"}
    return None


def recovery_plan(log_rows, now_utc, busy_jobs, horizon_hours=RECOVERY_HORIZON_HOURS,
                  per_tick=RECOVERY_PER_TICK):
    """The recovery runs to start now, once an outage is over.

    Each job with a `held-outage` slot in the last horizon_hours that no later
    run has covered owes ONE run: full if any held slot was full. The
    outage's recovery is one batch named after its newest held slot, so it
    keeps its name across the ticks it takes (per_tick runs each); roles
    first/middle/last count the recovery runs already started for it.
    Returns {batch_id, batch_kind, expected, runs: [{job_name, mode,
    followup_of, role}]}, or None when nothing is owed."""
    horizon = dt.timedelta(hours=horizon_hours)
    held = [r for r in log_rows if r.get("outcome") == "held-outage"
            and r.get("dispatched_at") and now_utc - r["dispatched_at"] <= horizon]
    if not held:
        return None
    newest = max(held, key=lambda r: r["dispatched_at"])
    started = sorted({r["job_name"] for r in log_rows if r.get("reason") == "recovery"
                      and r.get("dispatched_at") and r["dispatched_at"] > newest["dispatched_at"]})
    owed = {}
    for r in sorted(held, key=lambda r: r["dispatched_at"]):
        # A job's recovery run is its one try, whatever its outcome: a failed
        # one waits for the next scheduled time, never a loop.
        if r["job_name"] in started or _covered(r, log_rows):
            continue
        entry = owed.setdefault(r["job_name"], {"job_name": r["job_name"], "mode": "probe"})
        if r.get("mode") == "full":
            entry["mode"] = "full"
        entry["followup_of"] = r["dispatch_id"]   # the newest owed slot
    if not owed:
        return None
    names = sorted(owed)
    total = len(started) + len(names)
    runs = []
    for job in names:
        if job in busy_jobs:
            continue
        if len(runs) >= per_tick:
            break
        pos = len(started) + names.index(job)
        role = ("only" if total == 1 else "first" if pos == 0
                else "last" if pos == total - 1 else "middle")
        runs.append({**owed[job], "role": role})
    return {"batch_id": f"recovery-{newest['dispatch_id']}", "batch_kind": "recovery",
            "expected": sorted(set(started) | set(names)), "runs": runs}


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


def batch_for(schedule, job_name, mode, scheduled_for):
    """Which batch a scheduled run belongs to, and its place in it (2026-10-21).

    A batch is every enabled row with the same mode whose run_time falls in the
    same hour: the 1 PM probes, the 4 AM full run. Ordered by run_time, the
    first job emails its own report, the last one sends the digest of the whole
    batch, and the rest stay silent unless they fail (main.py email_plan).
    Returns {"role": first|middle|last|only, "batch_id", "batch_kind"}, or None
    when the row is not in the schedule (e.g. disabled since)."""
    local = scheduled_for.astimezone(TZ)
    group = []
    for row in schedule:
        if not row.get("enabled") or row.get("mode") != mode or not row.get("job_name"):
            continue
        try:
            h, m = parse_run_time(row.get("run_time"))
        except (ValueError, TypeError):
            continue
        if h == local.hour:
            group.append(((h, m), row["job_name"]))
    names = [name for _, name in sorted(group)]
    if job_name not in names:
        return None
    i = names.index(job_name)
    role = "only" if len(names) == 1 else "first" if i == 0 else "last" if i == len(names) - 1 else "middle"
    kind = f"{mode}-{local.hour:02d}00"
    return {"role": role, "batch_id": f"{kind}-{local.date().isoformat()}", "batch_kind": kind}


def run_body(mode, dispatch_id, batch=None):
    """The jobs.run request body: env overrides on the job's only container.
    batch (from batch_for, role possibly replaced) adds EMAIL_ROLE, BATCH_ID
    and BATCH_KIND; without it the job keeps its own email rules."""
    env = [
        {"name": "RUN_MODE", "value": mode},
        {"name": "DISPATCH_ID", "value": dispatch_id},
        {"name": "DISPATCH_LOG_TABLE", "value": f"{OPS_DATASET}.{LOG_TABLE}"},
    ]
    if batch:
        env += [
            {"name": "EMAIL_ROLE", "value": batch["role"]},
            {"name": "BATCH_ID", "value": batch["batch_id"]},
            {"name": "BATCH_KIND", "value": batch["batch_kind"]},
        ]
        if batch.get("expected"):
            # A recovery batch has no history to read its members from.
            env.append({"name": "BATCH_EXPECTED", "value": " ".join(batch["expected"])})
    return {"overrides": {"containerOverrides": [{"env": env}]}}


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


def start_job(session, job_name, mode, dispatch_id, batch=None):
    url = (f"https://run.googleapis.com/v2/projects/{GCP_PROJECT}/locations/{REGION}"
           f"/jobs/{job_name}:run")
    resp = session.post(url, json=run_body(mode, dispatch_id, batch), timeout=60)
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
               "dispatched": [], "skipped": [], "followups": [], "canary": [], "recovery": [],
               "outage": None, "errors": []}

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
            try:
                _query(bq, f"""
                    UPDATE {_fq(LOG_TABLE)}
                    SET outcome = @outcome, finished_at = @finished, detail = @detail
                    WHERE dispatch_id = @id AND outcome IS NULL""",
                       [_param("outcome", outcome), _param("finished", finished, "TIMESTAMP"),
                        _param("detail", detail), _param("id", row["dispatch_id"])])
            except Exception as exc:
                # The row stays open and is settled on the next tick. The job
                # counts as busy meanwhile, so it is not started twice.
                summary["errors"].append(f"settle {row['dispatch_id']}: {exc}")
                busy.add(row["job_name"])

    # The last day of the log, as settled by step 1: the outage breaker, the
    # canary, recovery and follow-ups all read it.
    recent = _query(bq, f"""
        SELECT dispatch_id, job_name, mode, reason, scheduled_for, dispatched_at, outcome,
               finished_at, followup_of, detail
        FROM {_fq(LOG_TABLE)}
        WHERE dispatched_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)""")
    outage = outage_state(recent)
    summary["outage"] = outage

    # 2. Scheduled slots — held, not started, while Plex is refusing connections.
    schedule = _query(bq, f"SELECT job_name, run_time, mode, enabled FROM {_fq(SCHEDULE_TABLE)}")
    logged = {(r["job_name"], r["scheduled_for"]) for r in _query(bq, f"""
        SELECT job_name, scheduled_for FROM {_fq(LOG_TABLE)}
        WHERE scheduled_for > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 DAY)""")}
    for slot in due_slots(schedule, now, logged, busy):
        if slot["action"] == "invalid":
            summary["errors"].append(f"schedule row for {slot['job_name']}: {slot['detail']}")
            continue
        action = "held-outage" if outage and slot["action"] == "dispatch" else slot["action"]
        batch = batch_for(schedule, slot["job_name"], slot["mode"], slot["scheduled_for"])
        _dispatch(bq, session, slot["job_name"], slot["mode"], "schedule",
                  slot["scheduled_for"], None, action, summary, dry_run, batch)
        if action == "dispatch":
            busy.add(slot["job_name"])

    if outage:
        # 3a. During an outage: no follow-ups, one canary at a time.
        canary = canary_due(recent, now, outage, schedule, busy)
        if canary:
            day = now.astimezone(TZ).date().isoformat()
            _dispatch(bq, session, canary["job_name"], "probe", "canary", None, None, "dispatch",
                      summary, dry_run, {"role": canary["role"], "batch_id": f"canary-{day}",
                                         "batch_kind": "canary"})
        print(json.dumps({"message": "etl-dispatcher tick", "severity": "WARNING" if not summary["errors"]
                          else "ERROR", **summary}, default=str), flush=True)
        return summary

    # 3b. After an outage: one recovery run per job with a held slot.
    started_now = set()
    plan = recovery_plan(recent, now, busy)
    for run in (plan or {}).get("runs", []):
        _dispatch(bq, session, run["job_name"], run["mode"], "recovery", None, run["followup_of"],
                  "dispatch", summary, dry_run,
                  {"role": run["role"], "batch_id": plan["batch_id"], "batch_kind": plan["batch_kind"],
                   "expected": plan["expected"]})
        busy.add(run["job_name"])
        started_now.add(run["job_name"])

    # 4. One follow-up probe per failed run. It logs under the failed run's
    # batch for the audit, but mails as itself: the digest has gone by then.
    for row in followups_due(recent, now):
        if row["job_name"] in started_now:
            continue   # a recovery run just started covers it
        action = "skipped-busy" if row["job_name"] in busy else "dispatch"
        batch = (batch_for(schedule, row["job_name"], row["mode"], row["scheduled_for"])
                 if row.get("scheduled_for") else None)
        _dispatch(bq, session, row["job_name"], "probe", "follow-up", None,
                  row["dispatch_id"], action, summary, dry_run,
                  {**batch, "role": "followup"} if batch else None)
        if action == "dispatch":
            busy.add(row["job_name"])

    print(json.dumps({"message": "etl-dispatcher tick", "severity":
                      "ERROR" if summary["errors"] else "INFO", **summary}, default=str), flush=True)
    return summary


SKIP_DETAILS = {
    "skipped-busy": "previous dispatch of this job still running",
    "held-outage":  "Plex is refusing ODBC connections: held, to re-run once a canary connects",
}


def _dispatch(bq, session, job, mode, reason, scheduled_for, followup_of, action, summary, dry_run,
              batch=None):
    dispatch_id = uuid.uuid4().hex[:16]
    entry = {"dispatch_id": dispatch_id, "job_name": job, "mode": mode, "reason": reason,
             "scheduled_for": scheduled_for, "followup_of": followup_of,
             "email_role": (batch or {}).get("role")}
    bucket = {"follow-up": "followups", "canary": "canary", "recovery": "recovery"}.get(
        reason, "dispatched" if action == "dispatch" else "skipped")
    record = {**entry, "action": action}
    if dry_run:
        summary[bucket].append(record)
        return
    # The row goes in BEFORE the run starts: a crash between the two leaves a
    # row the next tick reconciles as lost, never a run with no row (which
    # would be started again).
    try:
        _query(bq, f"""
        INSERT INTO {_fq(LOG_TABLE)}
          (dispatch_id, job_name, mode, reason, scheduled_for, followup_of, dispatched_at, outcome, finished_at, detail)
        VALUES (@id, @job, @mode, @reason, @slot, @followup_of, CURRENT_TIMESTAMP(),
                @outcome, IF(@outcome IS NULL, NULL, CURRENT_TIMESTAMP()), @detail)""",
           [_param("id", dispatch_id), _param("job", job), _param("mode", mode),
            _param("reason", reason), _param("slot", scheduled_for, "TIMESTAMP"),
            _param("followup_of", followup_of),
            _param("outcome", None if action == "dispatch" else action),
            _param("detail", SKIP_DETAILS.get(action))])
    except Exception as exc:
        # No row, so no run: the slot is still unlogged and the next tick, five
        # minutes later, tries it again. One failed insert must not end the pass
        # for every other job.
        summary["errors"].append(f"log {job}: {exc} — not started, retried next tick")
        return
    # Listed only once its row exists, so the summary never reports a run that
    # was not logged.
    summary[bucket].append(record)
    if action != "dispatch":
        return
    import requests
    try:
        execution = start_job(session, job, mode, dispatch_id, batch)
    except requests.exceptions.Timeout as exc:
        # Cloud Run may well have created the execution before the POST timed
        # out. Leave the row OPEN: the job writes its own outcome if it runs,
        # and the next ticks reconcile it as `lost` after LOST_AFTER_MINUTES if
        # it never did. Marking it dispatch-failed here could hide a live run.
        summary["errors"].append(f"start {job}: timed out, left open for reconcile: {exc}")
        return
    except Exception as exc:
        # jobs.run itself refused (HTTP error): no execution exists.
        record["action"] = "dispatch-failed"
        summary["errors"].append(f"start {job}: {exc}")
        try:
            _query(bq, f"""
                UPDATE {_fq(LOG_TABLE)}
                SET outcome = 'dispatch-failed', finished_at = CURRENT_TIMESTAMP(), detail = @d
                WHERE dispatch_id = @id AND outcome IS NULL""", [_param("d", str(exc)[:1000]), _param("id", dispatch_id)])
        except Exception as exc2:
            # Left open, the row is reconciled as lost after LOST_AFTER_MINUTES.
            summary["errors"].append(f"could not mark {job} dispatch-failed: {exc2}")
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
