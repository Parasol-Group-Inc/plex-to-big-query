# Plex ODBC probe: is it our side or Plex's?

`scripts/plex_odbc_probe.py` is a small, read-only check of Plex's ODBC service.
It was built on 2026-11-06 for the D20 outage
([PLEX_PROD_ODBC_INCIDENT_2026-11-04.md](PLEX_PROD_ODBC_INCIDENT_2026-11-04.md)),
to give Plex support evidence they could not put down to our network. Use it whenever
prod ODBC misbehaves and someone asks "is it us?".

Not to be confused with the ETL's **change probe** (a cheap "has anything changed?"
query at the start of a run, which ends a run `skipped` when nothing has). That one is
described in [OPERATIONS.md](OPERATIONS.md#change-probe).

## Contents

- [What it measures](#what-it-measures)
- [How it works](#how-it-works)
- [Reading the result](#reading-the-result)
- [Running it](#running-it)
- [Options](#options)
- [SQL Development Environment checks](#sql-development-environment-checks)
- [What it found in November 2026](#what-it-found-in-november-2026)

## What it measures

For each host, on each pass, the probe runs five steps in order, each under its own
deadline:

| Step | What it does | Deadline | Shows |
|---|---|---|---|
| DNS | resolves the host name | 15 s | the address we are actually reaching |
| TCP | opens and closes a bare TCP connection to port 19995 | 10 s (`--tcp`) | whether the network path works at all |
| connect | ODBC login with the IAM token (`pyodbc.connect`) | 90 s (`--connect`) | whether Plex's ODBC service answers a login |
| 8-row lookup | `SELECT COUNT(*) FROM Sales_v_PO_Status` | 120 s (`--query`) | a read that should take well under a second |
| TOP 10 orders | `SELECT TOP 10 PO_Key FROM Sales_v_PO ORDER BY PO_Key DESC` | 120 s (`--query`) | a read on one of the big tables, still tiny |

The hosts are prod `vox.odbc.plex.com` (8.34.94.50) and test
`vox.test.odbc.plex.com` (8.34.94.51). By default each pass probes prod, then test,
so every prod row has a test row from the same machine within about a minute: the
**test host is the control**. The same token and driver work on both, so a slow prod
next to a fast test rules out the token, the driver and the image.

The output is a markdown table ready to paste into a Plex case, preceded by the
machine's public IP (from `checkip.amazonaws.com`), the ODBC user and the port. Plex
can look up our sessions by that IP and time.

## How it works

- **Every step runs on a daemon thread with a wall-clock deadline** (`with_deadline`).
  The Plex driver ignores ODBC query timeouts (OPEN_ITEMS D28), so a hung call would
  otherwise block the script forever. A step that passes its deadline is reported as
  `no answer in Ns` and abandoned, not cancelled.
- **A hung session is not reused.** If a query hangs, the remaining queries for that
  pass are skipped (`-`), and the connection is not closed (closing would hang too).
- **The script ends with `os._exit(0)`**, because abandoned driver threads would
  otherwise keep the process alive.
- **Errors are reported, not raised.** A refusal or reset shows as `error Ns: <first
  140 characters>`, which tells a refused session (2404) or a reset (08S01, 2310) apart
  from no answer at all.
- **The query strings use `TOP`, not `LIMIT`.** The Plex engine rejects `LIMIT`.
- **Nothing is written anywhere.** It needs only `PLEX_ACCESS_TOKEN` and
  `PLEX_ODBC_USER`, the same as the ETL's `.env`.

## Reading the result

| What you see | What it means |
|---|---|
| DNS or TCP fails | a network problem between this machine and Plex: ours, or the internet's |
| TCP in milliseconds, connect `no answer` or tens of seconds, test fast | **Plex's prod ODBC service**: the network reached it, the login service did not answer |
| connect fine, queries 10-100x slower than test | Plex's prod query engine is degraded |
| connect `error ...: 2404` / `2310` / `08S01` | Plex refused or reset the session (the 10-22 to 10-27 pattern) |
| prod and test both slow | look at this machine or network first, then ask Plex |

Healthy numbers, from test throughout the outage: login 0.4-1.5 s, each tiny query
0.2-0.6 s from AWS or Cloud Run, about 1 s from the office. TCP takes 0.03 s from AWS
and 0.2 s from the office.

The ETL is stricter than the probe: it allows 60 s per login attempt (3 attempts) and
reads 500-row pages. So a probe login that takes 61-90 s is a failed ETL connect, and a
tiny probe query that works does not mean a 500-row page will.

## Running it

**In the ETL image (Mac, Windows or Linux with Docker)**, from the repo root:

```bash
docker run --rm --platform linux/amd64 --env-file .env -e PROBE_SOURCE="Mac, office network" -v "$PWD/scripts:/scripts:ro" --entrypoint python plex-to-big-query-etl /scripts/plex_odbc_probe.py --passes 3
```

On Apple Silicon the image must be built as amd64
(`DOCKER_DEFAULT_PLATFORM=linux/amd64 docker compose build`): the Plex driver exists
only for x86-64, and an arm64 image fails with "Can't open lib ivoa27.so".

**From a machine without Docker (AWS CloudShell, plain Amazon Linux)**, use the bundle:
the driver folder from the image, the probe and `scripts/plex_odbc_probe_run.sh`
(saved as `run.sh`). The full steps to build the bundle are in the incident doc,
section "A third angle: the probe from AWS CloudShell". On the target machine:

```bash
tar xzf plex_probe.tgz
export PLEX_ACCESS_TOKEN='...'
./plex_probe/run.sh --passes 3
```

`run.sh` installs unixODBC, PAM and pyodbc if missing (plain `pip3 install` first,
`--user` only as a fallback: CloudShell runs inside a virtualenv, where `--user`
fails). It writes an `odbc.ini` with `[ODBC] InstallDir` pointing at the bundled
driver (without it the driver fails with "Memory allocation error") and sets
`LD_LIBRARY_PATH` and `PLEX_DRIVER`. The bundle holds the Plex driver but no token.
Delete it afterwards (`rm -rf plex_probe plex_probe.tgz`).

**From Cloud Run**, run a real small job instead (for example
`plex-etl-sales-returns-test` and `plex-etl-sales-returns` with the operator
impersonation flag), and read its connect and query lines in Cloud Logging. The probe
is not deployed.

## Options

| Option | Default | Use |
|---|---|---|
| `--passes N` | 3 | rounds per host; 6 gives a steadier picture |
| `--hosts prod,test` | both | `--hosts test` for a baseline only, `--hosts prod` to halve the time |
| `--tcp S` | 10 | TCP deadline, seconds |
| `--connect S` | 90 | ODBC login deadline, seconds; above the ETL's 60 s on purpose, to see how slow it is |
| `--query S` | 120 | deadline per query, seconds |
| `--pause S` | 20 | seconds between passes |

Environment: `PLEX_ACCESS_TOKEN`, `PLEX_ODBC_USER` (both required), `PROBE_SOURCE` (a
label for the table, default the host name), `PLEX_DRIVER` (default
`/usr/oaodbc81/lib64/ivoa27.so`), `PLEX_PORT` (19995), `PLEX_SERVER_DATASOURCE`
(`ReportDataSource`).

## SQL Development Environment checks

During the outage the Plex SQL Development Environment (in the browser) and ODBC
read the same copy of the data, which stopped updating on 11-04 ~18:56 MT, while the
Plex screens stayed live. Two queries tell, in a minute, whether that copy is current.
SQL Development requires an alias on every table.

**1. How fresh is it?** The newest rows it can see. If they are hours older than
what the screens show, the copy is stale.

```sql
SELECT 'AR invoice' AS source, MAX(i.Invoice_Date) AS newest_date, MAX(i.Created_Date) AS newest_added
FROM Accounting_v_AR_Invoice AS i
UNION ALL
SELECT 'Shipper', MAX(s.Ship_Date), MAX(s.Add_Date)
FROM Sales_v_Shipper AS s
UNION ALL
SELECT 'Shipper invoice link', MAX(sai.Add_Date), MAX(sai.Add_Date)
FROM Sales_v_Shipper_AR_Invoice AS sai;
```

**2. Does it match the Shipping Revenue by Part Group screen?** Revenue per part group
from the invoice lines on revenue accounts (`4%`). It matched the screen to the cent
on every day from 10-19 to 11-03 (quantity can differ by a few lines). Set the dates
to the screen's Invoice Date range; the end date is exclusive. If `WITH ROLLUP` is
rejected, drop it and the `GROUPING(...)` parts and add the rows up.

```sql
SELECT
  CASE WHEN GROUPING(pg.Part_Group) = 1 THEN 'Grand Total' ELSE ISNULL(pg.Part_Group, '(no part)') END AS part_group,
  SUM(CASE WHEN d.Shipper_Line_Key IS NOT NULL AND d.Credit - d.Debit <> 0 THEN d.Quantity ELSE 0 END) AS quantity,
  SUM(CASE WHEN d.Shipper_Line_Key IS NOT NULL THEN d.Credit - d.Debit ELSE 0 END) AS shipped_revenue,
  SUM(CASE WHEN d.Shipper_Line_Key IS NULL THEN d.Credit - d.Debit ELSE 0 END) AS other_invoice_lines,
  SUM(d.Credit - d.Debit) AS net_revenue,
  COUNT(DISTINCT i.Invoice_No) AS invoices,
  MAX(i.Created_Date) AS newest_invoice_added
FROM Accounting_v_AR_Invoice AS i
JOIN Accounting_v_AR_Invoice_Dist AS d ON d.Invoice_Link = i.Invoice_Link
LEFT JOIN Part_v_Part AS p ON p.Part_Key = d.Part_Key
LEFT JOIN Part_v_Part_Group AS pg ON pg.Part_Group_Key = p.Part_Group_Key
WHERE i.Invoice_Date >= '2026-11-01' AND i.Invoice_Date < '2026-11-07'
  AND i.Void = 0 AND d.Account_No LIKE '4%'
GROUP BY pg.Part_Group WITH ROLLUP
ORDER BY GROUPING(pg.Part_Group), part_group;
```

**The screen's Grand Total columns** are quantity, account 40200, account 41000 and
Revenue (40200 + 41000). `net_revenue` above adds both accounts, so compare it with the
screen's last column, not the 40200 one. On 11-06 the screen read 260,951 /
$701,857.17 / -$1,765.80 / $700,091.37. The -$1,765.80 was one line (INV0000180,
Go-Live Temp part 14535 to CHAM1).

## What it found in November 2026

All from the same user and token, prod and test alternating:

| When (UTC) | From | TCP | Prod logins | Prod tiny reads | Test |
|---|---|---|---|---|---|
| 11-06 ~17:45 | Mac, office (149.88.25.130) | 0.2 s | 52 s or no answer in 90 s | 6-16 s | 4 s login, ~1 s reads |
| 11-06 18:49-19:00 | AWS us-east-2 (18.224.22.68) | 0.03 s | 2 of 6, in 43 s and 73 s | 7-21 s | 0.4-1.4 s, 0.2-0.6 s |
| 11-06 21:25-21:41 | AWS us-east-2 (3.16.213.75) | 0.03 s | 8 of 9, in 29-74 s | 3-16 s | 0.4-1.3 s, 0.2-0.3 s |

Three networks (Google Cloud us-central1, the office, AWS) gave one answer: the
network path to prod was instant, and Plex's prod ODBC login and query service was
the only thing failing. Prod recovered on 2026-11-08 around 04:45 MT (incident doc,
"Recovery").
