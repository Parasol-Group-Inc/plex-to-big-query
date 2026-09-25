"""
Shared plumbing for the scorecard sandbox build.

The one rule every generator follows: a synthetic record is a CLONE OF A REAL
PlexTest RECORD. The template row is copied column for column and only the
keys, dates, quantities and the (real) customer / part / rep / work centre it
points at are changed. Nothing is invented column by column, so every column a
view might read arrives exactly as Plex shapes it — including the ones nobody
realised a view reads.
"""

import datetime as dt
import decimal
import json
import random
import sys

from google.cloud import bigquery

# The Windows console defaults to cp1252, which cannot print the ✗/── used in
# progress output and kills the build mid-run on the first one.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT = "voxdatalake"
SOURCE = "PlexTest"
SANDBOX = "ScorecardSandbox"

# Refuse anything but the sandbox. A generator that could be pointed at a
# dataset reports read would be a way to corrupt a scorecard.
WRITABLE = {SANDBOX}

# The simulated year runs from 1 Jan to the day of the build, so "yesterday",
# MTD, YTD and % into month all have something real to compute from.
PERIOD_START = dt.date(2026, 1, 1)

# Synthetic key space: one billion-sized band per family. Real Plex keys in
# this tenant are 8-digit (e.g. Plexus_User_No 18453010), so none of these can
# collide, and a key's band says which generator wrote it.
KEY_BANDS = {
    "sales": 9_100_000_000,
    "shipping": 9_200_000_000,
    "production": 9_300_000_000,
    "quality": 9_400_000_000,
    "inventory": 9_500_000_000,
}

# Text marker on document numbers the tiles display (SO / shipper / job
# numbers), so a sandbox figure can never be mistaken for a live one in a
# screenshot.
TAG = "SBX"


class Sandbox:
    def __init__(self, today=None, seed=20260924):
        self.client = bigquery.Client(project=PROJECT)
        self.ds = SANDBOX
        self.today = today or dt.date.today()
        # Seeded: two builds on the same day produce the same numbers, so a
        # tile that changes between builds changed because the SQL did.
        self.rng = random.Random(seed)
        self._schemas = {}
        self._next = dict(KEY_BANDS)

    # ── keys and dates ──────────────────────────────────────────────────
    def key(self, family):
        self._next[family] += 1
        return self._next[family]

    def days(self, start=None, end=None):
        d, end = start or PERIOD_START, end or self.today
        while d <= end:
            yield d
            d += dt.timedelta(days=1)

    def months(self):
        m = PERIOD_START.replace(day=1)
        while m <= self.today:
            yield m
            m = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)

    # ── schema-aware values ─────────────────────────────────────────────
    def schema(self, table):
        if table not in self._schemas:
            t = self.client.get_table(f"{PROJECT}.{self.ds}.{table}")
            self._schemas[table] = {f.name: f.field_type for f in t.schema}
        return self._schemas[table]

    def when(self, table, col, d, hour=12):
        """A date in whatever shape this table stores dates in. Plex dates
        land as INT64 NANOSECONDS (UTC) in typed tables and as ISO text in
        tables that were autodetected while empty; every view's COALESCE
        handles both, but only if the value is in the column's own shape."""
        ty = self.schema(table).get(col)
        if isinstance(d, dt.date) and not isinstance(d, dt.datetime):
            d = dt.datetime(d.year, d.month, d.day, hour, tzinfo=dt.timezone.utc)
        if ty in ("INTEGER", "INT64"):
            return int(d.timestamp()) * 1_000_000_000
        if ty == "DATE":
            return d.date().isoformat()
        if ty in ("TIMESTAMP", "DATETIME"):
            return d.strftime("%Y-%m-%d %H:%M:%S")
        return d.strftime("%Y-%m-%d")

    def val(self, table, col, v):
        """Coerce v to the column's type (ALL-STRING tables need text)."""
        if v is None:
            return None
        ty = self.schema(table).get(col)
        if ty == "STRING":
            return str(v)
        if ty in ("INTEGER", "INT64"):
            return int(v)
        if ty in ("FLOAT", "FLOAT64", "NUMERIC"):
            return float(v)
        if ty in ("BOOLEAN", "BOOL"):
            return bool(v)
        return v

    # ── read ────────────────────────────────────────────────────────────
    def query(self, sql):
        sql = sql.replace("{ds}", f"{PROJECT}.{self.ds}")
        return [dict(r.items()) for r in self.client.query(sql).result()]

    def templates(self, table, where="TRUE", limit=None):
        lim = f" LIMIT {limit}" if limit else ""
        return self.query(f"SELECT * FROM `{{ds}}.{table}` WHERE {where}{lim}")

    # ── write ───────────────────────────────────────────────────────────
    def clone(self, table, template, **changes):
        """Copy a real row and apply changes, coercing each change to the
        column's type. Columns the table does not have are an error — a typo
        here would otherwise silently leave the template's value in place."""
        schema = self.schema(table)
        unknown = [k for k in changes if k not in schema]
        if unknown:
            raise KeyError(f"{table} has no column(s): {', '.join(unknown)}")
        row = dict(template)
        for k, v in changes.items():
            row[k] = self.val(table, k, v)
        return row

    def append(self, table, rows):
        if self.ds not in WRITABLE:
            raise RuntimeError(f"refusing to write to {self.ds}")
        if not rows:
            return 0
        t = self.client.get_table(f"{PROJECT}.{self.ds}.{table}")
        job = self.client.load_table_from_json(
            [_jsonable(r) for r in rows], t,
            job_config=bigquery.LoadJobConfig(
                schema=t.schema,
                write_disposition="WRITE_APPEND",
                source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            ))
        job.result()
        return len(rows)

    def exec(self, sql):
        if self.ds not in WRITABLE:
            raise RuntimeError(f"refusing to write to {self.ds}")
        self.client.query(sql.replace("{ds}", f"{PROJECT}.{self.ds}")).result()


def _jsonable(row):
    out = {}
    for k, v in row.items():
        if isinstance(v, (dt.datetime, dt.date)):
            v = v.isoformat()
        elif isinstance(v, decimal.Decimal):
            v = float(v)
        elif isinstance(v, bytes):
            v = v.decode("utf-8", "replace")
        out[k] = v
    return out


def weighted(rng, items, weights):
    return rng.choices(items, weights=weights, k=1)[0]


def month_end(m):
    return (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)


def workdays(sb, month):
    """Mon-Fri days of a month that are on or before the build date."""
    return [d for d in sb.days(month, min(month_end(month), sb.today)) if d.weekday() < 5]


def dump(obj):
    return json.dumps(obj, default=str, indent=1)
