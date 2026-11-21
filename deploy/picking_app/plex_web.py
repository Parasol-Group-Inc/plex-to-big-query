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

Hosts: PLEX_ENV=test (default) -> vox.test.on.plex.com; prod -> vox.on.plex.com.
Credentials: plex_web_export.creds() (env or .env: PLEX_GCP_ODBC_USER / _PASSWORD, else
PLEX_PORTAL_USERNAME / _PASSWORD). Docs: docs/PICKING_STAGING_APP.md.
"""
from __future__ import annotations

import csv
import io
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
        s = requests.Session()
        s.headers["User-Agent"] = ua
        for c in cookies:
            s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
        self._s, self.logged_in_at = s, time.time()

    def session(self) -> requests.Session:
        with self._lock:
            if self._s is None:
                self._login()
            return self._s

    @staticmethod
    def _expired(r: requests.Response) -> bool:
        return r.status_code in (401, 419) or "accounts.plex.com" in r.url or (
            "text/html" in (r.headers.get("content-type") or "") and "iamButton" in r.text[:20000])

    def _post(self, path: str, **kw) -> requests.Response:
        for attempt in (1, 2):
            r = self.session().post(self.host + path, timeout=kw.pop("timeout", 120), **kw)
            if not self._expired(r):
                return r
            with self._lock:
                self._s = None                      # log in again, once
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
    def move(self, serial_or_lp: str, location: str) -> tuple[bool, str]:
        r = self._post(MOVE_PATH, json={"SerialNo": serial_or_lp, "Location": location,
                                        "Putaway": False, "Confirmed": False},
                       headers={"X-Requested-With": "XMLHttpRequest"}, timeout=60)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        try:
            return parse_move(r.json())
        except ValueError:
            return False, f"not JSON: {r.text[:200]}"
