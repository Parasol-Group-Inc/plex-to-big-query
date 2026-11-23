"""One logged-in Plex web session for the picking app: SQL reads and container moves.

Plex's REST API cannot move a container (2026-11-20: scrap and retire exist under
/inventory/v1/inventory-control, every move-like route is a 404) and ODBC is read-only
("Functionality is not supported" on a zero-row UPDATE). The Move Container screen
(Inventory > Inventory Control > Inventory Transactions) can, and on Apply it sends one
JSON request:

    POST /inventory/MoveContainer/ContainerMove?sourceActionKey=11984
    {"SerialNo": "<serial or LP>", "Location": "<location code>", "Putaway": false, "Confirmed": false}
    -> {"ValidationResult": {"Success": true, "Message": "Container X was successfully moved.", ...}}

So this module logs in once with Playwright (plex_web_export.login, the same login every
screen job uses), hands the cookies to a plain `requests` session, and then calls that
request directly: about 0.2-0.5 s per move instead of a page load. An LP number in
SerialNo moves the whole pallet (TEST, 11-20: LP-087265 moved its 4 containers). A lapsed
session answers HTTP 419 (or a login page): the session logs in again once and retries.

SQL reads go through the SQL Development Environment's CSV download with the same
cookies: job sets and per-job BOM are not in the REST API, and this needs no ODBC driver.

The session is SAVED after each login (cookies + user agent) and reused by the next process or
Cloud Run instance until Plex expires it, so a cold start rarely pays the ~10 s login:
PICKING_SESSION_GCS=gs://bucket/path.json (Cloud Run; a private bucket: the cookies ARE a Plex
session), else etl-manual/plex_session_<env>.json (gitignored). A saved session is checked with
`SELECT 1` before use; check() is what the keep-warm ping calls.

Hosts: PLEX_ENV=test (default) -> vox.test.on.plex.com; prod -> vox.on.plex.com.
Credentials: plex_web_export.creds() (env or .env: PLEX_GCP_ODBC_USER / _PASSWORD, else
PLEX_PORTAL_USERNAME / _PASSWORD). Docs: docs/PICKING_STAGING_APP.md.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import threading
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

HOSTS = {"test": "https://vox.test.on.plex.com", "prod": "https://vox.on.plex.com"}
MOVE_PATH = "/inventory/MoveContainer/ContainerMove?sourceActionKey=11984"
SDE_PATH = "/BusinessIntelligence/SqlDevelopmentEnvironment"


class PlexWebError(RuntimeError):
    pass


def parse_move(body: dict) -> tuple[bool, str]:
    """(success, message) from a ContainerMove answer. An LP move nests its result one level
    down ("N Containers of ... were moved to ..."), with Message None at the top."""
    v = (body or {}).get("ValidationResult") or {}
    ok = bool(v.get("Success"))
    msgs = [v.get("Message")] + [c.get("Message") for c in v.get("CollectionValidationResults") or []]
    msgs += [e.get("Message") or str(e) for e in v.get("ValidationErrors") or []]
    for c in v.get("CollectionValidationResults") or []:
        ok = ok and bool(c.get("Success", True))
    return ok, " ".join(m for m in msgs if m) or ("moved" if ok else "Plex refused the move (no message)")


class PlexWeb:
    def __init__(self, env: str | None = None, login_fn=None, creds_fn=None):
        self.env = (env or os.environ.get("PLEX_ENV", "test")).lower()
        if self.env not in HOSTS:
            raise ValueError(f"PLEX_ENV must be test or prod, not {self.env!r}")
        self.host = HOSTS[self.env]
        self._login_fn, self._creds_fn = login_fn, creds_fn
        self._s: requests.Session | None = None
        self._lock = threading.Lock()
        self.logged_in_at: float | None = None
        self.session_source: str | None = None      # "saved" | "login"
        self.store = os.environ.get("PICKING_SESSION_GCS") or str(
            REPO / "etl-manual" / f"plex_session_{self.env}.json")

    # ── saved session ──
    def _store_read(self) -> dict | None:
        try:
            if self.store.startswith("gs://"):
                from google.cloud import storage
                bucket, path = self.store[5:].split("/", 1)
                blob = storage.Client().bucket(bucket).blob(path)
                return json.loads(blob.download_as_text()) if blob.exists() else None
            p = Path(self.store)
            return json.loads(p.read_text()) if p.exists() else None
        except Exception:  # noqa: BLE001 - no saved session is fine: log in
            return None

    def _store_write(self, data: dict) -> None:
        try:
            body = json.dumps(data)
            if self.store.startswith("gs://"):
                from google.cloud import storage
                bucket, path = self.store[5:].split("/", 1)
                storage.Client().bucket(bucket).blob(path).upload_from_string(body, content_type="application/json")
            else:
                p = Path(self.store)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(body)
                os.chmod(p, 0o600)
        except Exception:  # noqa: BLE001 - saving is an optimization
            pass

    @staticmethod
    def _make_session(cookies: list[dict], ua: str) -> requests.Session:
        s = requests.Session()
        s.headers["User-Agent"] = ua
        for c in cookies:
            s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
        return s

    def _try_saved(self) -> bool:
        data = self._store_read()
        if not data or data.get("host") != self.host:
            return False
        s = self._make_session(data["cookies"], data["ua"])
        try:
            r = s.post(self.host + SDE_PATH + "/DownloadAdHocQueryResults", timeout=60, data={
                "PCN": "0", "AdHocQuery": "SELECT 1 AS x", "ExecutionPlanType": "0", "DataSourceExists": "false",
                "SynonymExists": "false", "DataSource": "false", "IntelliPlexSynonym": "false"})
        except requests.RequestException:
            return False
        if r.status_code != 200 or "csv" not in (r.headers.get("content-type") or ""):
            return False
        self._s, self.logged_in_at, self.session_source = s, data.get("at"), "saved"
        return True

    # ── session ──
    def _login(self) -> None:
        import plex_web_export as w
        from playwright.sync_api import sync_playwright
        user, password = (self._creds_fn or w.creds)()
        w.SDE = self.host + SDE_PATH        # login() lands on the SQL Development screen
        with sync_playwright() as p:
            b = p.chromium.launch()
            try:
                ctx = b.new_context()
                pg = ctx.new_page()
                (self._login_fn or w.login)(pg, user, password)
                cookies, ua = ctx.cookies(), pg.evaluate("navigator.userAgent")
            finally:
                b.close()
        self._s, self.logged_in_at, self.session_source = self._make_session(cookies, ua), time.time(), "login"
        self._store_write({"host": self.host, "at": self.logged_in_at, "ua": ua, "cookies": cookies})

    def session(self) -> requests.Session:
        with self._lock:
            if self._s is None and not self._try_saved():
                self._login()
            return self._s

    def check(self) -> bool:
        """Session alive (logs in again if Plex expired it). For the keep-warm ping."""
        self.sql("SELECT 1 AS x")
        return True

    @staticmethod
    def _expired(r: requests.Response) -> bool:
        return r.status_code in (401, 419) or "accounts.plex.com" in r.url or (
            "text/html" in (r.headers.get("content-type") or "") and "iamButton" in r.text[:20000])

    def _post(self, path: str, **kw) -> requests.Response:
        timeout = kw.pop("timeout", 120)
        for attempt in (1, 2):
            s = self.session()
            r = s.post(self.host + path, timeout=timeout, **kw)
            if not self._expired(r):
                return r
            with self._lock:
                if self._s is s:                    # not already replaced by another thread
                    self._login()                   # a fresh login (the saved one just failed)
        raise PlexWebError(f"Plex session refused after a fresh login (HTTP {r.status_code})")

    # ── reads ──
    def sql(self, query: str) -> list[dict]:
        r = self._post(SDE_PATH + "/DownloadAdHocQueryResults", timeout=600, data={
            "PCN": "0", "AdHocQuery": query, "ExecutionPlanType": "0", "DataSourceExists": "false",
            "SynonymExists": "false", "DataSource": "false", "IntelliPlexSynonym": "false"})
        if r.status_code != 200 or "csv" not in (r.headers.get("content-type") or ""):
            raise PlexWebError(f"SQL read failed: HTTP {r.status_code} {r.text[:200]}")
        rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
        # Plex adds a trailing empty column, and writes NULL as the text "NULL"
        return [{k: (None if v == "NULL" else v) for k, v in row.items() if k} for row in rows]

    # ── the move ──
    def move_detail(self, serial_or_lp: str, location: str) -> dict:
        """One move, with everything needed to audit or undo it: {ok, message, request, status, body, ms}.
        `request` is the exact payload sent; `body` Plex's raw answer (first 4000 characters)."""
        payload = {"SerialNo": serial_or_lp, "Location": location, "Putaway": False, "Confirmed": False}
        t0 = time.time()
        try:
            r = self._post(MOVE_PATH, json=payload, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=60)
        except Exception as e:  # noqa: BLE001 - recorded, never raised into a half-done batch
            return {"ok": False, "message": f"request failed: {e}", "request": {"path": MOVE_PATH, **payload},
                    "status": None, "body": None, "ms": round((time.time() - t0) * 1000)}
        out = {"request": {"path": MOVE_PATH, **payload}, "status": r.status_code, "body": r.text[:4000],
               "ms": round((time.time() - t0) * 1000)}
        if r.status_code != 200:
            return {**out, "ok": False, "message": f"HTTP {r.status_code}: {r.text[:200]}"}
        try:
            ok, msg = parse_move(r.json())
        except ValueError:
            ok, msg = False, f"not JSON: {r.text[:200]}"
        return {**out, "ok": ok, "message": msg}

    def move(self, serial_or_lp: str, location: str) -> tuple[bool, str]:
        d = self.move_detail(serial_or_lp, location)
        return d["ok"], d["message"]
