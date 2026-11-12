"""Is Plex's ODBC copy behind? One measure for every alert (since 2026-11-12).

The old measure was the age of ODBC's newest change. That age also grows when nobody works
in Plex (nights, weekends), so it raised false alarms on 11-12 02:11 (watchdog, 6.1 h) and
07:21 (screens digest, "554 min behind" for lines under an hour old). Plex's REST API
(connect.plex.com) returns every sales order with its modifiedDate in about a second. The
question every check now asks is: "is there a change in Plex, older than X, that ODBC does
not have?" A quiet night gives 0; a frozen ODBC (11-10) grows minute by minute.

Used by watchdog.py (odbc_vs_plex), main.py (the stale-data email) and
scripts/screen_recon.py (the "behind" verdict). Docs: docs/ODBC_VS_SCREENS.md.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.request
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
DEN = ZoneInfo("America/Denver")
PROJECT = os.environ.get("GCP_PROJECT", "voxdatalake")
PLEX_API_BASE = os.environ.get("PLEX_API_BASE", "https://connect.plex.com")
PLEX_API_SECRETS = (os.environ.get("SECRET_PLEX_API_CONSUMER_KEY", "plex-api-consumer-key"),
                    os.environ.get("SECRET_PLEX_API_CONSUMER_SECRET", "plex-api-consumer-secret"))
SLACK_MIN = 5   # clock skew and same-minute saves between Plex's API and its ODBC copy


def plex_order_changes(timeout: int = 60) -> list[dt.datetime]:
    """Every sales order's modifiedDate (UTC) from Plex's REST API. GET only. Raises on failure."""
    from google.cloud import secretmanager
    sm = secretmanager.SecretManagerServiceClient()
    key, sec = (sm.access_secret_version(request={"name": f"projects/{PROJECT}/secrets/{n}/versions/latest"})
                .payload.data.decode("utf-8").strip() for n in PLEX_API_SECRETS)
    req = urllib.request.Request(f"{PLEX_API_BASE}/sales/v1/orders", method="GET", headers={
        "X-Plex-Connect-Api-Key": key, "X-Plex-Connect-Api-Secret": sec, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        orders = json.loads(r.read())
    out = []
    for o in orders:
        m = o.get("modifiedDate")
        if m:
            try:
                out.append(dt.datetime.fromisoformat(m.replace("Z", "+00:00")).astimezone(UTC))
            except ValueError:
                pass
    return out


def mt_to_utc(v):
    """ODBC returns naive Mountain-time datetimes; make them aware UTC (None stays None)."""
    if v is None:
        return None
    if isinstance(v, str):
        v = dt.datetime.fromisoformat(v)
    if v.tzinfo is None:
        v = v.replace(tzinfo=DEN)
    return v.astimezone(UTC)


def odbc_plex_lag(changes, odbc_newest, as_of, slack_min: int = SLACK_MIN):
    """Pure. changes: Plex API modification times (aware). odbc_newest: the newest order change
    the ODBC side holds (aware). as_of: when that ODBC side was read (now for a live query; the
    load time for our BigQuery copy, so the hours between our own loads never count).

    Returns (lag_min, unseen_count, oldest_unseen): how long the oldest Plex change made before
    as_of, that ODBC lacked at as_of, had been waiting at as_of. (None, 0, None) when there is
    no ODBC reference."""
    if odbc_newest is None or as_of is None:
        return None, 0, None
    edge = odbc_newest + dt.timedelta(minutes=slack_min)
    unseen = sorted(t for t in changes if edge < t <= as_of)
    if not unseen:
        return 0.0, 0, None
    return round((as_of - unseen[0]).total_seconds() / 60, 1), len(unseen), unseen[0]
