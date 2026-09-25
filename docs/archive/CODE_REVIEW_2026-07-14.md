# Code Review — 2026-07-14

Full-codebase review of the ETL pipeline (`main.py`, `email_utils.py`, both
view SQL files, `deploy/cloudbuild.yaml`). 14 findings; all critical/high and
actionable medium/low findings were fixed the same day.

**Frontend analogy for the big picture:** most of these bugs were the backend
equivalent of "the API call failed but the spinner turned into a green
checkmark anyway" — failures that didn't surface, or destructive writes that
ran without a guard.

## Findings and resolutions

| # | Severity | Where | Finding | Resolution |
|---|---|---|---|---|
| 1 | **Critical** | `deploy/cloudbuild.yaml` | Smoke test executed the **production** job on every push to main — a buggy build would immediately WRITE_TRUNCATE prod tables | ✅ Smoke test now runs `plex-etl-test` (PlexTest dataset). Prod job gets the new image but must be triggered manually. |
| 2 | High | `main.py` `write_to_bigquery` | A 0-row Plex response (ODBC timeout, maintenance window) truncated the existing table **and** flattened its schema to all-STRING | ✅ Existing tables are never touched on a 0-row response; a warning is logged. Empty tables are only *created* if missing (so VIEWs can reference them). |
| 3 | High | `main.py` extraction loop | `date_col` columns were converted to tz-aware datetimes → landed as TIMESTAMP while all other dates landed as INT64 ns → view SQL zero-date sentinel bypassed, "no date" became `1970-01-01` | ✅ In-place conversion removed; all date conversion happens in the view SQL. Fallback branches also NULLIF against `1970-01-01`. |
| 4 | High | `main.py` `query_plex` | YAML values (`plex_view`, `filter`, `date_col`) interpolated into ODBC SQL with no validation — GCS-editable config is an untrusted boundary | ✅ `validate_extraction()`: identifier whitelist for view/table/date_col; filter rejects `;`, `--`, `/*`. Invalid entries are skipped as partial errors. |
| 5 | High | `main.py` view creation | View applied even after extraction failures, with a clean "Applied BigQuery view" event — email read as a healthy run against stale data | ✅ Warning event added when view is applied with partial errors; view SQL load/apply failures now count as partial errors (yellow PARTIAL email). |
| 6 | Medium | `main.py` `load_report_config` | Empty/scalar YAML → `yaml.safe_load` returns `None` → cryptic `AttributeError` | ✅ Explicit `isinstance(config, dict)` check with a clear error message. |
| 7 | Medium | `main.py` IAM auth | Missing `PLEX_ODBC_USER` produced `UID=;` silently; failure surfaced later as a misleading ODBC error | ✅ Warning logged at credential-fetch time naming the env var. |
| 8 | Medium | `main.py` `ensure_metadata_table` | `except Exception` treated a 403 permission error as "table missing" and masked it with a create_table failure | ✅ Catches only `NotFound`. |
| 9 | Medium | `main.py` `get_last_sync` | Dead code that interpolated `BQ_TABLE` into raw SQL (injection-pattern precedent) | ✅ Deleted. If incremental sync is added later, use BigQuery query parameters. |
| 10 | Medium | `main.py` watermark | `max_modified_at` recorded job start time, not the data's actual max — would silently drop records if incremental logic is ever added | ✅ Now computes the real max of `date_col` from the extracted DataFrame. |
| 11 | Low | `email_utils.py` | Event/error strings inserted into HTML unescaped — ODBC messages contain `<angle brackets>` that broke the email layout | ✅ `html.escape()` on list items and all non-HTML template values. |
| 12 | Low | `sales_orders_view.sql:184` | `Part_Group_Key` join column assumed, not verified — view creation succeeds (BigQuery defers validation) but querying fails with "Unrecognized name" | ✅ Verified 2026-07-15 — `PlexProd.sales_orders_report` queries successfully, which requires every column reference in the view SQL to resolve. |
| 13 | Low | `main.py` | Missing `plex_view`/`bq_table` YAML key raised `KeyError`, aborting all remaining extractions | ✅ Covered by `validate_extraction()` (finding 4). |
| 14 | Low | `main.py` | `get_last_sync` never called — incremental sync documented but not implemented | ✅ Dead code removed (finding 9); OPERATIONS.md already documents that every run is a full `WRITE_TRUNCATE` load. |

## Behavior changes to know about

1. **0 rows from Plex no longer clears the BigQuery table.** Yesterday's data
   stays; the run logs a warning. If you *want* to empty a table, do it in the
   BigQuery Console.
2. **Cloud Build never runs the prod job.** After a green build + test-job
   smoke run, trigger prod yourself:
   `gcloud run jobs execute plex-etl --region=us-central1`
3. **YAML configs are validated.** View/table/date_col must be plain
   identifiers (`A-Za-z0-9_`); filters may not contain `;`, `--`, or `/*`.
   A bad entry is skipped (PARTIAL email), not fatal.
4. **Date columns are converted only in the view SQL.** Don't add pandas date
   conversion back into `main.py`. The pattern (see CHEATSHEET.md for the full
   version) routes every branch through `CAST(col AS STRING)`:
   `DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(col AS STRING) AS INT64), 0), 1000)))`
   plus DATE and TIMESTAMP fallback branches. **Follow-up found in prod
   2026-07-15:** a direct `SAFE_CAST(INT64 AS DATE)` is an invalid cast *pair*
   and fails at view-query compile time — `SAFE_CAST` only protects against
   unparseable values, not unsupported type combinations. Routing through
   STRING makes the expression compile for any column type.

## Verification (2026-07-15)

All four views confirmed working after the SQL was pushed to GCS and every
job re-run: dates read as real DATEs (`2025-06-17`, not
`1750118400000000000`), zero-date sentinels read as NULL. Prod
`work_orders_report` compiles and queries but returns 0 rows —
`Part_v_Job`/`Part_v_Job_Op` are still empty on the prod Plex host.

## Open items

- ~~DataDirect ODBC license still on 15-day trial — resolve before prod cutover.~~ Licensed 2026-08-24.
- ~~SendGrid domain authentication: Gmail flags report emails with a
  "couldn't verify" warning.~~ Resolved 2026-08-21 (CNAME records added).
