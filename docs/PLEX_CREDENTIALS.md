# Plex credentials: which login each part of the pipeline uses

Since 2026-11-17, prod runs on the company Plex user **`gcp.odbc.vox`**, not on a person's
login. Test still runs on `edominguez.parasol`, because the test ODBC host refuses `gcp.odbc.vox`
("An unknown error has occurred in validating the supplied..." credentials).

| What | Plex user | Where the credential lives | Set by |
|---|---|---|---|
| Prod ODBC (16 prod jobs incl. `plex-live-screens` comparison) | `gcp.odbc.vox` | user: `var.plex_odbc_user_prod` (default in `terraform/variables.tf`); IAM token: secret `plex-access-token-prod` | Terraform (`deploy.sh`) |
| Test ODBC (15 `*-test` jobs) | `edominguez.parasol` | user: `plex_odbc_user` in `terraform.tfvars`; token: secret `plex-access-token` | Terraform |
| Screens (`plex-live-screens`, web login) | `gcp.odbc.vox` | secrets `plex-portal-username` / `plex-portal-password` (version 2) | `gcloud secrets versions add`, no deploy |
| Plex REST API (watchdog `odbc_vs_plex`, `plex_api_lag`) | token made on Emilio's IT Manager login | secrets `plex-api-consumer-key` / `-secret` | unchanged; `gcp.odbc.vox` has no Developer Portal app yet |

Local `.env` holds the new user as `PLEX_GCP_ODBC_USER`, `PLEX_GCP_ODBC_USER_PASSWORD` and
`PLEX_GCP_ODBC_USER_TOKEN`. Every prod run logs `UID=gcp.odbc.vox`; every screens login is in
`PlexOps.plex_login_log.user`.

## Rotating
Never print a value; pipe it from `.env`:

```bash
printf '%s' "$PLEX_GCP_ODBC_USER_TOKEN" | gcloud secrets versions add plex-access-token-prod --data-file=- --project=voxdatalake --impersonate-service-account=claude-operator@voxdatalake.iam.gserviceaccount.com
printf '%s' "$PLEX_GCP_ODBC_USER_PASSWORD" | gcloud secrets versions add plex-portal-password --data-file=- --project=voxdatalake --impersonate-service-account=claude-operator@voxdatalake.iam.gserviceaccount.com
```

Jobs read `latest` at run time: no deploy or rebuild.

## Rolling back to the old login
- **Screens:** add the old username and password (`PLEX_PORTAL_USERNAME` / `PLEX_PORTAL_PASSWORD`
  in `.env`) as new versions of `plex-portal-username` / `plex-portal-password`.
- **Prod ODBC:** set `plex_odbc_user_prod = "edominguez.parasol"` and
  `secret_access_token_prod = "plex-access-token"` in `terraform.tfvars`, then `./scripts/deploy.sh`.
  Faster, no deploy: add the old token as a new version of `plex-access-token-prod`. That only works
  together with the user, so prefer the tfvars route.

## How it was verified (2026-11-17)
- ODBC probe (`scripts/plex_odbc_probe.py`) as `gcp.odbc.vox`: prod connect 3.7 s and both queries
  returned; test refused.
- `plex-live-screens` run in Cloud Run (execution `plex-live-screens-lbwll`): login ok in 5.9 s,
  releases 600 / shipments 510 / revenue 512 rows, the same as the run before.
- Local Docker on the Mac runs Chromium under x86 emulation and times out on Plex's heavy pages for
  **any** user; test screens in Cloud Run, not locally.
