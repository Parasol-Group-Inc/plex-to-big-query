Plex Support Follow-Up — Production ODBC Session Refused
==========================================================

Context: this follows up on the earlier ServerDataSource/HY000 10300 issue on
our production endpoint. That error is gone, but a new one has appeared —
use this if the DataDirect trial-license angle in OPERATIONS doesn't
resolve it, or send now if you'd rather have Plex confirm in parallel.

Subject
-------
Follow-up: Production ODBC session refused (OpenAccess SDK error 2404)

Email body
----------
Hello Plex Support Team,

Following up on our ODBC integration for BigQuery reporting. Our test
environment connection works reliably, but connections to production are
being refused by the OpenAccess SDK service (not a network/driver-config
error — the TCP connection and driver handshake succeed, but the service
declines to open a session).

**Error details:**
- SQLSTATE: `08S01`
- Message: `[DataDirect][ODBC OpenAccess SDK driver][OpenAccess SDK Client]
  Session refused by service, connection closed (2404) (SQLDriverConnect)`
- Host: `vox.odbc.plex.com` (production) — port 19995
- ServerDataSource: `ReportDataSource`
- Account: `edominguez.parasol`
- Auth method: IAM access token (CustomProperties=authmethod=iam)
- Occurred: 2026-07-19 02:03 UTC and 2026-07-20 02:02 UTC (recurring,
  scheduled daily job)
- The identical token and account work without issue against our test
  host (`vox.test.odbc.plex.com`) minutes/hours apart from the failures.

**Questions for Plex Support:**
1. Is the `edominguez.parasol` account currently authorized to open ODBC
   report sessions against the **production** instance specifically? (We
   previously confirmed `ReportDataSource` resolves correctly on
   production — this is a different, session-level rejection.)
2. Is there a concurrent session limit or license seat count on our
   account/ODBC driver that could cause production sessions to be
   refused while test sessions succeed?
3. Is there any IP allowlist or firewall rule on the production
   OpenAccess SDK gateway that differs from test? Our egress IPs are from
   Google Cloud Run (us-central1) — happy to provide the exact IP range
   if useful.

Thank you,
[Your Name]
[Company Name]
[Contact Info]
