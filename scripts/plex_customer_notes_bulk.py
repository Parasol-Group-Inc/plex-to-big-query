"""Set customer Notes in Plex from a CSV, in verified batches, through the Customer Details screen.

Built 2026-11-09 for docs/reference/CustomerNotesResults9.csv (an export with ID, Name, ...,
Comments, Plex Customer Code). Each row's Comments becomes the Plex customer's Note (the
multi-line "Note" in the NOTES section; not the Brief Note, not the Contact Information note).
Runbook: docs/CUSTOMER_NOTES_BULK.md. Hub tab: "Customer notes" (scripts/hub/customer_notes_tab.py).

    python scripts/plex_customer_notes_bulk.py plan --csv docs/reference/CustomerNotesResults9.csv
    python scripts/plex_customer_notes_bulk.py run --batch-size 5      # one batch, then stops
    python scripts/plex_customer_notes_bulk.py verify                  # API check of that batch
    python scripts/plex_customer_notes_bulk.py log --actor claude --event review "batch 1 looks right"
    python scripts/plex_customer_notes_bulk.py status
    python scripts/plex_customer_notes_bulk.py resume --reason "..."  # clear a stop after review

Categories (decided 2026-11-09):
  write               code AND name match Plex exactly, customer Active, Plex note empty
  append              same, but the customer already has a note: new = old + newline + comment
  flag-inactive       matched exactly but the customer is Inactive (not written for now)
  flag-name-mismatch  the code matches but the name in the file is not identical to Plex's
  flag-not-in-plex    the code is not a Plex customer code
  flag-no-code        the row has a comment but no Plex code
  flag-no-customer-no matched, but no Customer_No for the screen (customer newer than ODBC)

Checks: (1-3) before running, three independent plans agreed row for row (Claude, a Sonnet
agent, and an ODBC-based cross-check; docs/CUSTOMER_NOTES_BULK.md). (4) during the run:
  - before each write: the page title must be the planned customer, and the Note on screen must
    equal the note in the plan's backup (else someone changed it since: stop);
  - after Apply: the screen is reloaded and the saved Note must equal the planned text;
  - after each batch, `verify` reads every customer through the API: each batch customer must
    hold its planned note, earlier ones must still hold theirs, and no other customer's note may
    differ from the backup. A batch must be verified before the next one runs.
Anything odd writes BULK_STOPPED.txt with the reason and exits non-zero; nothing runs until
`resume --reason` records why it is safe to continue. Every step is appended to
bulk_actions.jsonl (who, what, when). All files live in etl-manual/customer_note/ (gitignored:
customer data).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import subprocess
import sys
import traceback
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plex_web_export import LOCK, creds, login, run_lock  # noqa: E402

DIR = LOCK.parent / "customer_note"
PLAN = DIR / "bulk_plan.csv"
LOG = DIR / "bulk_actions.jsonl"
STOP = DIR / "BULK_STOPPED.txt"
API = "https://connect.plex.com/mdm/v1/customers"
SCREEN = "https://vox.on.plex.com/SalesAndCRM/customeraddresses?__sk=3&__sak=23&CustomerNo={no}"
WRITE_CATEGORIES = ("write", "append")
FIELDS = ["seq", "csv_line", "file_id", "code", "customer_no", "plex_id", "file_name", "plex_name",
          "plex_status", "category", "before_note", "comment", "new_note"]


# ── small helpers ─────────────────────────────────────────────────────────────

def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def norm(s) -> str:
    """Compare notes the way Plex stores them: \\r\\n and \\n are the same, ends trimmed."""
    return (s or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def log(event: str, actor: str = "script", **kw) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now(), "actor": actor, "event": event, **kw}, ensure_ascii=False) + "\n")


def entries() -> list[dict]:
    if not LOG.exists():
        return []
    return [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines() if line.strip()]


def stop(reason: str, **kw) -> None:
    STOP.write_text(f"{now()}\n{reason}\n{json.dumps(kw, ensure_ascii=False, default=str)}\n", encoding="utf-8")
    log("abort", reason=reason, **kw)
    print(f"STOPPED: {reason}")
    sys.exit(3)


def env_file() -> dict:
    env = {}
    for p in (Path(__file__).resolve().parents[1] / ".env", LOCK.parents[1] / ".env"):
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


def api_customers() -> list[dict]:
    env = env_file()
    req = urllib.request.Request(API, headers={
        "X-Plex-Connect-Api-Key": env["PLEX_API_CONSUMER_KEY"],
        "X-Plex-Connect-Api-Secret": env["PLEX_API_CONSUMER_SECRET"], "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode())
    if not isinstance(data, list) or len(data) < 1000:
        raise RuntimeError(f"unexpected customers answer ({type(data).__name__}, {len(data) if isinstance(data, list) else '?'})")
    return data


def plan_rows() -> list[dict]:
    with PLAN.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def done_seqs(log_entries) -> set[str]:
    return {e["seq"] for e in log_entries if e["event"] in ("saved", "already-set")}


# ── plan ──────────────────────────────────────────────────────────────────────

def cmd_plan(args) -> None:
    if PLAN.exists() and any(e["event"] == "saved" for e in entries()):
        sys.exit(f"{PLAN.name} already has writes against it; refusing to rebuild it")
    rows = list(csv.DictReader(open(args.csv, encoding="utf-8-sig", newline="")))
    customers = api_customers()
    backup = DIR / f"customers_backup_prod_{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}.json"
    backup.write_text(json.dumps(customers, indent=1, ensure_ascii=False), encoding="utf-8")
    by_code = {c["code"]: c for c in customers}
    out = subprocess.run(["bq", "query", "--use_legacy_sql=false", "--project_id=voxdatalake", "--format=csv",
                          "--quiet", "--max_rows=100000",
                          "SELECT Customer_Code, Customer_No FROM `voxdatalake.PlexProd.raw_Common_v_Customer`"],
                         capture_output=True, text=True, check=True).stdout
    numbers = {r["Customer_Code"]: r["Customer_No"] for r in csv.DictReader(out.splitlines())}
    plan, seq = [], 0
    for line, r in enumerate(rows, start=2):
        code, comment = (r.get("Plex Customer Code") or "").strip(), (r.get("Comments") or "").strip()
        if not comment:
            continue
        c = by_code.get(code) if code else None
        before = (c or {}).get("note") or ""
        if not code:
            cat = "flag-no-code"
        elif not c:
            cat = "flag-not-in-plex"
        elif r["Name"] != c["name"]:
            cat = "flag-name-mismatch"
        elif c["status"] != "Active":
            cat = "flag-inactive"
        elif not numbers.get(code):
            cat = "flag-no-customer-no"
        else:
            cat = "append" if norm(before) else "write"
        new = (norm(before) + "\n" + comment) if cat == "append" else comment if cat == "write" else ""
        seq += 1
        plan.append({"seq": str(seq), "csv_line": str(line), "file_id": r.get("ID", ""), "code": code,
                     "customer_no": numbers.get(code, "") if c else "", "plex_id": (c or {}).get("id", ""),
                     "file_name": r.get("Name", ""), "plex_name": (c or {}).get("name", ""),
                     "plex_status": (c or {}).get("status", ""), "category": cat, "before_note": before,
                     "comment": comment, "new_note": new})
    # writes first (simple ones before appends), each group in file order
    order = {"write": 0, "append": 1}
    plan.sort(key=lambda p: (order.get(p["category"], 2), int(p["csv_line"])))
    for i, p in enumerate(plan, 1):
        p["seq"] = str(i)
    with PLAN.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(plan)
    counts = {}
    for p in plan:
        counts[p["category"]] = counts.get(p["category"], 0) + 1
    log("plan", csv=str(args.csv), backup=backup.name, customers=len(customers), counts=counts)
    print(f"{PLAN}: {len(plan)} rows {counts}\nbackup: {backup}")


# ── run one batch ─────────────────────────────────────────────────────────────

def open_details(pg, customer_no):
    pg.goto(SCREEN.format(no=customer_no), wait_until="networkidle", timeout=90000)
    pg.locator("p.plex-sidetabs-menu-item-title", has_text="Customer Details").first.click()
    note = pg.locator('textarea[name="Note"]').first
    note.wait_for(state="visible", timeout=60000)
    pg.wait_for_load_state("networkidle", timeout=60000)
    return note


def page_customer(pg) -> tuple[str, str]:
    """(Name, Customer Code) as the screen's own fields hold them. Until 2026-11-09 this parsed the
    page title and cut names at " - ", which stopped the pilot on "Adriana Castagno - rotulo-hgcg"."""
    name = pg.locator('input[name="Name"]').first.input_value()
    code = pg.locator('input[name="CustomerCode"], input[name="Code"]').first.input_value()
    return name, code


def cmd_run(args) -> None:
    if STOP.exists():
        sys.exit(f"{STOP.name} exists; read it, then `resume --reason ...` once it is safe:\n{STOP.read_text()}")
    log_entries = entries()
    batches = [e for e in log_entries if e["event"] == "batch-start"]
    verified = {e["batch"] for e in log_entries if e["event"] == "verified"}
    if batches and batches[-1]["batch"] not in verified:
        sys.exit(f"batch {batches[-1]['batch']} is not verified yet; run `verify` first")
    done = done_seqs(log_entries)
    todo = [p for p in plan_rows() if p["category"] in WRITE_CATEGORIES and p["seq"] not in done][:args.batch_size]
    if not todo:
        print("nothing left to write")
        return
    batch = (batches[-1]["batch"] + 1) if batches else 1
    user, password = creds()
    from playwright.sync_api import sync_playwright
    with run_lock(), sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        log("batch-start", batch=batch, size=len(todo), seqs=[t["seq"] for t in todo])
        try:
            login(pg, user, password)
            for t in todo:
                ctx = {"batch": batch, "seq": t["seq"], "code": t["code"], "customer_no": t["customer_no"]}
                note = open_details(pg, t["customer_no"])
                shown = page_customer(pg)
                if shown != (t["plex_name"], t["code"]):
                    stop(f"screen shows customer {shown!r}, plan expects {(t['plex_name'], t['code'])!r}", **ctx)
                current = norm(note.input_value())
                if current == norm(t["new_note"]):
                    log("already-set", **ctx)
                    continue
                if current != norm(t["before_note"]):
                    stop("the Note on screen differs from the backup taken for the plan (changed since?)",
                         screen=current[:300], plan=norm(t["before_note"])[:300], **ctx)
                note.fill(t["new_note"])
                note.press("Tab")
                pg.locator("button", has_text="Apply").first.click()
                pg.wait_for_load_state("networkidle", timeout=60000)
                pg.wait_for_timeout(1500)
                errs = [e.strip() for e in pg.locator(".plex-error, .plex-banner-error, .validation-summary-errors,"
                                                      " .plex-dialog .plex-error-message").all_inner_texts() if e.strip()]
                if errs:
                    stop("Plex showed an error after Apply", errors=errs[:3], **ctx)
                saved = norm(open_details(pg, t["customer_no"]).input_value())
                if saved != norm(t["new_note"]):
                    stop("after reload the Note is not the planned text", saved=saved[:300], **ctx)
                log("saved", category=t["category"], **ctx)
                print(f"  {t['seq']:>5} {t['code']:8} {t['category']:6} saved")
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 - any surprise stops the run
            stop(f"unexpected error: {type(exc).__name__}: {str(exc)[:300]}", trace=traceback.format_exc()[-1500:],
                 batch=batch)
        finally:
            browser.close()
    log("batch-end", batch=batch)
    print(f"batch {batch} written ({len(todo)}); now run `verify`")


# ── verify the last batch through the API ─────────────────────────────────────

def cmd_verify(args) -> None:
    log_entries = entries()
    batches = [e for e in log_entries if e["event"] == "batch-start"]
    if not batches:
        sys.exit("no batch to verify")
    batch = batches[-1]["batch"]
    if not any(e["event"] == "batch-end" and e["batch"] == batch for e in log_entries) and not STOP.exists():
        sys.exit(f"batch {batch} did not finish; nothing to verify")
    plan = {p["seq"]: p for p in plan_rows()}
    done = done_seqs(log_entries)
    backup_name = next(e["backup"] for e in log_entries if e["event"] == "plan")
    backup = {c["id"]: c for c in json.loads((DIR / backup_name).read_text(encoding="utf-8"))}
    live = {c["id"]: c for c in api_customers()}
    expected = {plan[s]["plex_id"]: plan[s] for s in done}
    problems = []
    for cid, p in expected.items():
        got = norm((live.get(cid) or {}).get("note"))
        if got != norm(p["new_note"]):
            problems.append(f"{p['code']} (seq {p['seq']}): API note {got[:80]!r} != planned {norm(p['new_note'])[:80]!r}")
    for cid, c in backup.items():
        if cid in expected:
            continue
        if cid not in live:
            problems.append(f"{c['code']}: missing from the API answer")
        elif norm(live[cid].get("note")) != norm(c.get("note")):
            problems.append(f"{c['code']}: note changed outside the plan: {norm(c.get('note'))[:60]!r} -> "
                            f"{norm(live[cid].get('note'))[:60]!r}")
    batch_seqs = set(batches[-1]["seqs"])
    in_batch = len(batch_seqs & done)
    if problems:
        stop(f"API verification of batch {batch} failed ({len(problems)} problem(s))", problems=problems[:20])
    log("verified", batch=batch, batch_saved=in_batch, total_done=len(done), customers_checked=len(live))
    print(f"batch {batch} verified: {in_batch} written in this batch, {len(done)} in total; "
          f"all {len(live)} customers match the plan or the backup")


def cmd_log(args) -> None:
    log(args.event, actor=args.actor, text=args.text)
    print("logged")


def cmd_resume(args) -> None:
    if not STOP.exists():
        sys.exit("not stopped")
    reason = STOP.read_text(encoding="utf-8")
    STOP.unlink()
    log("resume", actor=args.actor, text=args.reason, stopped_for=reason[:500])
    print("stop cleared")


def cmd_status(args) -> None:
    rows, log_entries = plan_rows(), entries()
    done = done_seqs(log_entries)
    counts = {}
    for p in rows:
        k = p["category"] if p["category"] not in WRITE_CATEGORIES else (p["category"] + (" done" if p["seq"] in done else " pending"))
        counts[k] = counts.get(k, 0) + 1
    print(json.dumps(counts, indent=1))
    print("stopped:", STOP.read_text(encoding="utf-8") if STOP.exists() else "no")
    for e in log_entries[-5:]:
        print(" ", e["ts"], e["actor"], e["event"], {k: v for k, v in e.items() if k not in ("ts", "actor", "event")})


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("plan"); s.add_argument("--csv", required=True); s.set_defaults(fn=cmd_plan)
    s = sub.add_parser("run"); s.add_argument("--batch-size", type=int, required=True); s.set_defaults(fn=cmd_run)
    s = sub.add_parser("verify"); s.set_defaults(fn=cmd_verify)
    s = sub.add_parser("log"); s.add_argument("--actor", default="claude"); s.add_argument("--event", default="review")
    s.add_argument("text"); s.set_defaults(fn=cmd_log)
    s = sub.add_parser("resume"); s.add_argument("--actor", default="claude"); s.add_argument("--reason", required=True)
    s.set_defaults(fn=cmd_resume)
    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
