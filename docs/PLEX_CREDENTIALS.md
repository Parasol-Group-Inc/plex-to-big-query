# Plex credentials: which login each part of the pipeline uses

Since 2026-11-18, **every part of the pipeline uses the company Plex user `gcp.odbc.vox`**: ODBC
(prod and test), the screens login and the REST API. No job depends on a person's Plex login any
more. Steps: prod ODBC and screens on 2026-11-17, test ODBC, the API key and local scripts on
2026-11-18.

## Where each credential lives

| What | Credential | Where | Changed by |
|---|---|---|---|
| ODBC, all 31 jobs (16 prod on `vox.odbc.plex.com`, 15 test on `vox.test.odbc.plex.com`), incl. `plex-live-screens`' live ODBC comparison | user `gcp.odbc.vox` + IAM token | user: `var.plex_odbc_user_gcp` (default in `terraform/variables.tf`); token: secret **`plex-access-token-prod`** (the name is historical, it is used by test too) | user: Terraform (`deploy.sh`); token: `gcloud secrets versions add`, no deploy |
| Screens job web login (`plex-live-screens`) | `gcp.odbc.vox` + password | secrets `plex-portal-username` / `plex-portal-password` (version 2) | secret version, no deploy |
| REST API (watchdog `odbc_vs_plex`, `plex_api_lag.py`, `plex-api-*` Cloud Function, hub Label API tab) | Developer Portal app of `gcp.odbc.vox` (key issued 2026-11-18, does not expire) | secrets `plex-api-consumer-key` / `plex-api-consumer-secret` (version 2) | secret version, no deploy |

One token serves both ODBC hosts: the test host accepted `gcp.odbc.vox` from 2026-11-18 (it refused it on 11-17).

### Legacy, read by nothing (kept as a rollback)
- Secret `plex-access-token` (token of `edominguez.parasol`) and `var.plex_odbc_user` /
  `var.secret_access_token` (still set in `terraform.tfvars`, so they stay declared).
- Versions 1 of `plex-portal-*` and `plex-api-consumer-*`: Emilio's web login and the API app made
  on his IT Manager login.

## Local runs (laptop `.env`)

| `.env` name | Used by |
|---|---|
| `PLEX_GCP_ODBC_USER`, `PLEX_GCP_ODBC_USER_TOKEN` | `main.py` local runs (`docker compose`), `extract_schema_catalog.py`, `screen_recon.py` local, `plex_odbc_probe.py` |
| `PLEX_GCP_ODBC_USER`, `PLEX_GCP_ODBC_USER_PASSWORD` | web login: `plex_web_export.py` and everything that imports it (`plex_live_screens.py`, customer notes scripts) |
| `PLEX_GCP_API_CONSUMER_KEY`, `PLEX_GCP_API_CONSUMER_SECRET` | `plex_customer_notes_bulk.py` |

Each script takes the `PLEX_GCP_*` names **as a pair** when both are set (a user is never sent with
another user's token), else falls back to the older names (`PLEX_ODBC_USER` + `PLEX_ACCESS_TOKEN`,
`PLEX_PORTAL_*`, `PLEX_API_CONSUMER_*`). `main.local_odbc_env()` does this for ODBC. Cloud Run
sets none of the `PLEX_GCP_*` names. `scripts/dev_setup.sh` writes a new laptop's `.env` with
`PLEX_ODBC_USER=gcp.odbc.vox` and the token from `plex-access-token-prod`.

## Rotating
Never print a value; pipe it from `.env`:

```bash
printf '%s' "$PLEX_GCP_ODBC_USER_TOKEN" | gcloud secrets versions add plex-access-token-prod --data-file=- --project=voxdatalake --impersonate-service-account=claude-operator@voxdatalake.iam.gserviceaccount.com
printf '%s' "$PLEX_GCP_ODBC_USER_PASSWORD" | gcloud secrets versions add plex-portal-password --data-file=- --project=voxdatalake --impersonate-service-account=claude-operator@voxdatalake.iam.gserviceaccount.com
printf '%s' "$PLEX_GCP_API_CONSUMER_SECRET" | gcloud secrets versions add plex-api-consumer-secret --data-file=- --project=voxdatalake --impersonate-service-account=claude-operator@voxdatalake.iam.gserviceaccount.com
```

Jobs read `latest` at run time: no deploy or rebuild. Update `.env` too, for local runs.
Changing the password of `gcp.odbc.vox` in Plex breaks the screens login until
`plex-portal-password` has the new one (the screens job then suspends logins for 24 h; rerun with
`--force-login` after fixing).

## Rolling back to the old login
- **ODBC:** set `plex_odbc_user_gcp = "edominguez.parasol"` and
  `secret_access_token_gcp = "plex-access-token"` in `terraform.tfvars`, then `./scripts/deploy.sh`.
- **Screens / API:** add the old values (`PLEX_PORTAL_*`, `PLEX_API_CONSUMER_*` in `.env`) as new
  versions of `plex-portal-*` / `plex-api-consumer-*`.

## How it was verified
- 2026-11-17: ODBC probe as `gcp.odbc.vox`: prod ok, test refused. `plex-live-screens` in Cloud Run
  (`plex-live-screens-lbwll`): login 5.9 s, releases 600 / shipments 510 / revenue 512 rows, as before.
- 2026-11-18 08:30 MT deploy: prod run `plex-etl-part-routing-sgl29` connected as `gcp.odbc.vox`,
  249,645 rows, 3 views, 0 errors.
- 2026-11-18: test run `plex-etl-part-routing-test-jp72s` with per-execution overrides connected
  to the test host as `gcp.odbc.vox` (249,645 rows, 3 views, 0 errors). The new API key returned the
  same customers (4,112) and orders as the old one on both `connect.plex.com` and
  `test.connect.plex.com`; releases, parts and employees answered 200.
- Local Docker on the Mac runs Chromium under x86 emulation and times out on Plex's heavy pages for
  **any** user: test screens in Cloud Run, not locally.
