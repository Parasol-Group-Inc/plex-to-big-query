"""Minimal Plex ODBC probe for the D20 outage, runnable from anywhere the ETL image runs.

One round per host per pass: DNS lookup, a bare TCP handshake to the ODBC port,
the ODBC connect (IAM token), then two tiny reads. Each step has its own wall-clock
deadline, so a hang is reported as a hang instead of blocking the script. The
output is one markdown table plus the machine's public IP, ready to paste into the
Plex case: it separates "the network can't reach Plex" (DNS/TCP fail) from "Plex's
ODBC service doesn't answer" (TCP fine, ODBC connect or read hangs).

Read-only: nothing is written to BigQuery or anywhere else. Needs the Plex driver,
so run it inside the ETL image, e.g. from the repo root:

    docker run --rm --platform linux/amd64 --env-file .env \
      -e PROBE_SOURCE="Mac, office network" \
      -v "$PWD/scripts:/scripts:ro" --entrypoint python \
      plex-to-big-query-etl /scripts/plex_odbc_probe.py --passes 3

Env: PLEX_ACCESS_TOKEN, PLEX_ODBC_USER (from .env), optional PROBE_SOURCE label.
"""
import argparse
import os
import socket
import threading
import time
import urllib.request
from datetime import datetime, timezone

import pyodbc

HOSTS = {"prod": "vox.odbc.plex.com", "test": "vox.test.odbc.plex.com"}
PORT = int(os.environ.get("PLEX_PORT", "19995"))
QUERIES = [
    ("8-row lookup", "SELECT COUNT(*) FROM Sales_v_PO_Status"),
    ("TOP 10 orders", "SELECT TOP 10 PO_Key FROM Sales_v_PO ORDER BY PO_Key DESC"),
]


def with_deadline(fn, seconds):
    """Run fn() on a daemon thread. Returns (status, value, elapsed): status is
    'ok', 'error' or 'hung'. A hung call is abandoned, not cancelled: the driver
    ignores query timeouts (D28), so nothing else would stop it."""
    box = {}

    def run():
        try:
            box["value"] = fn()
        except Exception as exc:  # noqa: BLE001 - reported, not handled
            box["error"] = exc

    start = time.monotonic()
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(seconds)
    elapsed = time.monotonic() - start
    if t.is_alive():
        return "hung", None, elapsed
    if "error" in box:
        return "error", box["error"], elapsed
    return "ok", box.get("value"), elapsed


def conn_str(host):
    return (
        "DRIVER={" + os.environ.get("PLEX_DRIVER", "/usr/oaodbc81/lib64/ivoa27.so") + "};"
        f"HOST={host};PORT={PORT};"
        f"ServerDataSource={os.environ.get('PLEX_SERVER_DATASOURCE', 'ReportDataSource')};"
        "Encrypted=1;UseLDAP=0;"
        f"UID={os.environ['PLEX_ODBC_USER']};PWD=;"
        f"CustomProperties=authmethod=iam; accesstoken={os.environ['PLEX_ACCESS_TOKEN']}"
    )


def short(exc):
    return str(exc).replace("\n", " ").replace("|", "/")[:140]


def probe(env, host, args):
    row = {"utc": datetime.now(timezone.utc).strftime("%m-%d %H:%M:%S"), "env": env}
    st, ips, el = with_deadline(lambda: sorted({a[4][0] for a in socket.getaddrinfo(host, PORT, proto=socket.IPPROTO_TCP)}), 15)
    row["dns"] = f"{','.join(ips)} ({el:.1f}s)" if st == "ok" else f"{st} {el:.0f}s"
    st, _, el = with_deadline(lambda: socket.create_connection((host, PORT), timeout=args.tcp).close(), args.tcp + 5)
    row["tcp"] = f"{el:.2f}s" if st == "ok" else f"{st} {el:.0f}s"
    st, conn, el = with_deadline(lambda: pyodbc.connect(conn_str(host), timeout=30), args.connect)
    connected = st == "ok"
    row["connect"] = f"{el:.1f}s" if st == "ok" else (f"no answer in {el:.0f}s" if st == "hung" else f"error {el:.0f}s: {short(conn)}")
    for name, sql in QUERIES:
        if st != "ok":
            row[name] = "-"
            continue

        def read(sql=sql):
            cur = conn.cursor()
            cur.execute(sql)
            return len(cur.fetchall())

        qst, n, qel = with_deadline(read, args.query)
        row[name] = f"{n} rows, {qel:.1f}s" if qst == "ok" else (f"no answer in {qel:.0f}s" if qst == "hung" else f"error: {short(n)}")
        if qst == "hung":
            st = "hung"  # the session is stuck; don't send more on it
    if connected and st == "ok":
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    return row


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--passes", type=int, default=3, help="rounds per host (default 3)")
    p.add_argument("--hosts", default="prod,test", help="comma list of prod,test")
    p.add_argument("--tcp", type=int, default=10, help="TCP handshake deadline, s")
    p.add_argument("--connect", type=int, default=90, help="ODBC connect deadline, s")
    p.add_argument("--query", type=int, default=120, help="per-query deadline, s")
    p.add_argument("--pause", type=int, default=20, help="seconds between passes")
    args = p.parse_args()

    try:
        ip = urllib.request.urlopen("https://checkip.amazonaws.com", timeout=10).read().decode().strip()
    except Exception as exc:  # noqa: BLE001
        ip = f"unknown ({short(exc)})"
    source = os.environ.get("PROBE_SOURCE", socket.gethostname())
    print(f"Source: {source}; public IP {ip}; user {os.environ.get('PLEX_ODBC_USER')}; port {PORT}\n", flush=True)
    cols = ["utc", "env", "dns", "tcp", "connect"] + [q[0] for q in QUERIES]
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols), flush=True)
    for i in range(args.passes):
        for env in args.hosts.split(","):
            row = probe(env, HOSTS[env], args)
            print("| " + " | ".join(row[c] for c in cols) + " |", flush=True)
        if i < args.passes - 1:
            time.sleep(args.pause)
    os._exit(0)  # abandoned driver threads would otherwise keep the process alive


if __name__ == "__main__":
    main()
