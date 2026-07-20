Plex Support Follow-Up — Production ODBC Session Refused
==========================================================

Context: this follows up on the earlier ServerDataSource/HY000 10300 issue on
our production endpoint. That error is gone, but a new one has appeared.

**Update 2026-07-20 (driver license):** we confirmed our DataDirect OEM SDK
Client driver license (Serial 004193623) was NOT applied — the Dockerfile
never ran the vendor installer. We applied it properly (ran the real
`unixpi.ksh` installer, generated a valid `OAODBC64.LIC`, rebuilt and
redeployed) and re-tested against production. **The identical error
persists** even with a correctly licensed driver, ruling out client-side
licensing as the cause.

**Update 2026-07-20 (network isolation test):** we then reproduced this
error from a SECOND, completely independent network — running the exact
same account, token, driver, and connection parameters locally (outside
Google Cloud entirely) directly against `vox.odbc.plex.com`. **Identical
failure, in under one second, from a different IP/network.** This rules out
Google Cloud Run's egress IP/network as the cause. Two independent client
environments (Google Cloud Run in us-central1, and a separate
office/home network) are both refused identically by production, while the
same account and token succeed against `vox.test.odbc.plex.com` every day
without issue. This is conclusively an account/session-level restriction on
the production OpenAccess SDK service, not a network, driver, or client
configuration issue on our end.

This is now confirmed and ready to send to Plex Support.

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
4. We confirmed this is not a client-side driver licensing issue — our
   DataDirect OEM SDK Client license (Serial 004193623) is correctly
   applied and the identical error persists.
5. We confirmed this is not a network/firewall/IP-allowlist issue — we
   reproduced the identical failure from two independent networks (Google
   Cloud Run in us-central1, and a separate office/home network), both
   using the same account and token. We are confident this is a
   server-side, account-level restriction specific to production ODBC
   report access — could you confirm whether ODBC/OpenAccess SDK reporting
   access is enabled for `edominguez.parasol` on the production instance?
   (Regular Plex application login and reporting work fine for this
   account on production — only the ODBC/OpenAccess SDK path is affected.)

Thank you,
[Your Name]
[Company Name]
[Contact Info]
