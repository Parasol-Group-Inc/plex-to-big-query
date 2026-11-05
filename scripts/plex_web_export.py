#!/usr/bin/env python3
"""Pull the revenue/shipping raw tables from the Plex web UI while ODBC is down.

    python scripts/plex_web_export.py            # export + stage + compare, changes nothing live
    python scripts/plex_web_export.py --swap     # also back up and replace PlexProd.raw_<view>

Logs into Plex (PLEX_PORTAL_USERNAME / PLEX_PORTAL_PASSWORD, from the environment
or the repo's .env) with headless Chromium, then, for each view, posts
`SELECT x.* FROM <view> AS x` to the SQL Development Environment's own
"Download Results As CSV" endpoint, the same request the Download button makes.
A `COUNT(*)` through the same endpoint must match the file's row count, or the
view is not loaded.

Loading reuses load_plex_csv_dump.load_file: each file is staged in
Backups.stage_raw_<view>_<tag> (expires in 2 days) and compared with the live
table. With --swap, after every export is checked, each raw table is copied to
Backups.PlexProd__raw_<view>_<tag> (expires in 7 days) and replaced. A view is
not swapped when:
  - its export failed or the row count did not match Plex's COUNT(*);
  - the CSV has under 90% of the current table's rows;
  - the raw table was written after this run started (the ETL is back and won).

Exports land in etl-manual/auto/<tag>/ (gitignored; customer data). Only the
newest 20 runs are kept. Writes use your Application Default Credentials.
The ETL overwrites the raw tables on its next successful run, so nothing here
needs undoing when ODBC returns.
"""
import argparse
import contextlib
import csv
import datetime as dt
import io
import os
import shutil
import sys
from pathlib import Path

from google.cloud import bigquery
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_plex_csv_dump import PROJECT, load_file  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SDE = "https://vox.on.plex.com/BusinessIntelligence/SqlDevelopmentEnvironment"

# Every raw table the revenue, shipping, sales-MTD and AR invoice reports read.
VIEWS = [
    "Sales_v_PO", "Sales_v_PO_Line", "Sales_v_Release", "Sales_v_Price", "Sales_v_PO_Change",
    "Sales_v_PO_Type", "Sales_v_PO_Status", "Sales_v_Order_Salesperson",
    "Sales_v_Shipper", "Sales_v_Shipper_Line", "Sales_v_Shipper_Line_Release",
    "Sales_v_Shipper_AR_Invoice", "Sales_v_Shipper_Status", "Sales_v_Shipper_Container",
    "Accounting_v_AR_Invoice", "Accounting_v_AR_Invoice_Dist",
    "Common_v_Customer", "Part_v_Customer_Part_Price", "Part_v_Part", "Part_v_Part_Group",
    "Plexus_Control_v_Plexus_User",
]
MIN_RATIO = 0.9
KEEP_RUNS = 20


def creds():
    env = {}
    p = REPO / ".env"
    if not p.exists():  # a project worktree has no .env; fall back to the primary folder
        p = REPO.parent / "plex-to-big-query" / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    get = lambda k: os.environ.get(k) or env.get(k)
    u, pw = get("PLEX_PORTAL_USERNAME"), get("PLEX_PORTAL_PASSWORD")
    if not (u and pw):
        sys.exit("PLEX_PORTAL_USERNAME / PLEX_PORTAL_PASSWORD not set (environment or .env)")
    return u, pw


# In the PRIMARY folder when it exists (the hourly task runs from there), so a manual
# run from a project worktree (ptbq-dev, ...) waits for the task and vice versa.
_PRIMARY = REPO.parent / "plex-to-big-query"
LOCK = (_PRIMARY if _PRIMARY.is_dir() else REPO) / "etl-manual" / "plex_web.lock"


@contextlib.contextmanager
def run_lock():
    """One Plex web run at a time, shared by plex_web_export.py and plex_live_screens.py.

    Both log in as the same Plex user and the hourly task must not start a second
    browser while the previous run is still going. The lock is an operating-system
    lock on the file (msvcrt on Windows, flock on macOS/Linux), not the file's
    existence, so a run that is killed (the task's 50-minute limit, a reboot)
    releases it with its process and the next run starts normally. The file is
    left in place and holds the last holder's pid and start time, for the log.
    Exits 75 (temporary failure) if another run holds it.
    """
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    f = open(LOCK, "a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(1 << 20)  # lock a byte past the text, so a waiting run can still read who holds it
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        try:  # Windows locks are mandatory: the locked byte may not be readable
            f.seek(0)
            held = f.read().strip()
        except OSError:
            held = ""
        f.close()
        print(f"another Plex web run holds {LOCK.name} ({held or 'holder unknown'}); not starting")
        sys.exit(75)
    try:
        f.seek(0)
        f.truncate()
        f.write(f"pid {os.getpid()} {Path(sys.argv[0]).name} since {dt.datetime.now():%Y-%m-%d %H:%M:%S}")
        f.flush()
        yield
    finally:
        f.close()  # closing the handle releases the lock


def login(pg, user, password):
    pg.goto(SDE, wait_until="networkidle", timeout=90000)
    if "accounts.plex.com" in pg.url or pg.locator("#iamButton").count():
        pg.click("#iamButton")
        pg.wait_for_selector("#inputUsername3", state="visible", timeout=60000)
        pg.fill("#inputUsername3", user)
        pg.click("#usernameNextButton")
        pg.wait_for_selector("#inputPassword3", state="visible", timeout=60000)
        pg.fill("#inputPassword3", password)
        pg.click("#loginButton")
        pg.wait_for_url("**/SqlDevelopmentEnvironment**", timeout=120000)
        pg.wait_for_load_state("networkidle", timeout=90000)
    if "SqlDevelopmentEnvironment" not in pg.url:
        raise RuntimeError(f"login did not reach the SQL Development Environment (at {pg.url.split('?')[0]})")


def download(pg, query):
    """The SQL Development Environment's "Download Results As CSV" request. HTTP 400 = bad query."""
    r = pg.request.post(f"{SDE}/DownloadAdHocQueryResults", timeout=600000, form={
        "PCN": "0", "AdHocQuery": query, "ExecutionPlanType": "0", "DataSourceExists": "false",
        "SynonymExists": "false", "DataSource": "false", "IntelliPlexSynonym": "false"})
    if r.status != 200 or "csv" not in (r.headers.get("content-type") or ""):
        raise RuntimeError(f"HTTP {r.status} {r.headers.get('content-type')}")
    return r.body()


def export(views, out, user, password):
    """Returns {view: error or None}; writes out/<view>.csv for each success."""
    result = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context().new_page()
        login(pg, user, password)
        for v in views:
            try:
                n = list(csv.reader(io.StringIO(download(pg, f"SELECT COUNT(*) AS n FROM {v} AS x")
                                                .decode("utf-8-sig"))))[1][0]
                body = download(pg, f"SELECT x.* FROM {v} AS x")
                rows = sum(1 for _ in csv.reader(io.StringIO(body.decode("utf-8-sig")))) - 1
                if rows != int(n):
                    raise RuntimeError(f"file has {rows} rows, Plex COUNT(*) says {n}")
                (out / f"{v}.csv").write_bytes(body)
                result[v] = None
                print(f"{v}: exported {rows} rows")
            except Exception as e:  # one bad view must not stop the rest
                result[v] = str(e).splitlines()[0][:200]
                print(f"{v}: EXPORT FAILED: {result[v]}")
        b.close()
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--swap", action="store_true", help="back up and replace PlexProd.raw_<view>")
    ap.add_argument("--views", help="comma-separated subset of the default list")
    args = ap.parse_args()
    views = args.views.split(",") if args.views else VIEWS
    started = dt.datetime.now(dt.timezone.utc)
    tag = started.strftime("%Y%m%d_%H%M")
    base = REPO / "etl-manual" / "auto"
    out = base / tag
    out.mkdir(parents=True, exist_ok=True)
    for old in sorted(x for x in base.iterdir() if x.is_dir())[:-KEEP_RUNS]:
        shutil.rmtree(old, ignore_errors=True)

    user, password = creds()
    with run_lock():
        exported = export(views, out, user, password)

    c = bigquery.Client(project=PROJECT)
    failed = [v for v, e in exported.items() if e]
    for v in views:
        if exported[v]:
            continue
        raw = c.get_table(f"{PROJECT}.PlexProd.raw_{v}")
        swap = args.swap
        if swap and raw.modified > started:
            print(f"{v}: raw table written at {raw.modified:%H:%M} UTC, after this run started; not swapped")
            swap = False
            fresh = True
        else:
            fresh = False
        if swap:
            bak = f"{PROJECT}.Backups.PlexProd__raw_{v}_{tag}"
            c.copy_table(raw, bak).result()
            t = c.get_table(bak)
            t.expires = started + dt.timedelta(days=7)
            c.update_table(t, ["expires"])
        res = load_file(c, out / f"{v}.csv", tag, swap=swap, min_ratio=MIN_RATIO, stage_expiry_days=2)
        print(res["message"])
        if args.swap and res["status"] != "swapped" and not fresh:
            failed.append(v)
    print(f"done {tag}: {len(views) - len(failed)}/{len(views)} ok" + (f"; FAILED {failed}" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
