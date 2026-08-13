# Local Setup Guide — Phase 1

## What this gets you

By the end of this guide you will have the ETL container running on your machine, connecting to real Plex via ODBC, and writing CSV files to `./output/`. No GCP account required.

> **Which mode does this test?** This guide walks through the legacy
> single-view mode (`PLEX_VIEW`/`BQ_TABLE` env vars) — good for a quick
> "does the ODBC connection even work" check, but **no live Cloud Run job
> actually runs this way today**. Every real job sets `REPORT_CONFIG_GCS_PATH`
> instead and reads a multi-report YAML from GCS. See Step 4 below for how
> to locally test that path instead once basic connectivity is confirmed.

When the CSVs look correct — right columns, reasonable row counts, no obvious nulls — you are ready for [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).

---

## Prerequisites checklist

Before you start, confirm you have everything:

- [ ] **Docker Desktop** installed and running
  - Download: https://www.docker.com/products/docker-desktop/
  - Verify: `docker compose version` (should print a version number)
  - Must be in **Linux containers mode** (default on Windows — right-click the tray icon; if it says "Switch to Windows containers" you are already in Linux mode)
- [ ] **Git** — repo cloned to your machine
- [ ] **Plex ODBC credentials** from your Plex support contact:
  - ODBC username
  - ODBC password
  - CompanyCode
- [ ] **Plex ODBC driver** — see Step 1 below for the fast path (shared GCS bucket)
  - Only if that bucket isn't available: Linux 64-bit `.so` files from Plex support — see [PLEX_SUPPORT_TEMPLATE.md](PLEX_SUPPORT_TEMPLATE.md) for the request email template
- [ ] **GCP account with access to `voxdatalake`** — needed for Step 1's fast path and for Phase 2 later

---

## Step 1 — Populate the `driver/` folder

The Docker image needs the Plex Linux ODBC driver files. The `driver/` folder is gitignored so you must place them manually.

**Expected layout after this step:**

```
driver/
  lib64/
    ivoa27.so          ← main driver shared object
    ddtrc27.so         ← trace library
    (other .so files)
  rscshell             ← 32-bit utility bundled with the driver
  etc/
    lang/
      usenglish.msg
      msg.dat
  OAODBC64.LIC         ← driver license (see below)
```

### Fast path — pull the already-licensed driver from GCS (recommended)

The team maintains a licensed copy in Cloud Storage — same files Cloud Build
uses, already includes the applied license (`OAODBC64.LIC`), no re-licensing
needed:

```bash
gcloud storage cp -r gs://voxdatalake-build-assets/plex-odbc-driver/* driver/
```

Verify:
```bash
ls driver/lib64/        # Must show: ivoa27.so and ddtrc27.so
ls driver/OAODBC64.LIC   # Must exist
```

If you don't have `gcloud` access to `voxdatalake` yet, ask whoever manages
GCP access for this project to grant you `roles/storage.objectViewer` on the
`voxdatalake-build-assets` bucket — see the team guide's access section.

### Fallback path — extract from a fresh Plex driver package

Only needed if the GCS bucket is unavailable, or you're installing a new
driver version. This path does **not** include a license — see
[docs/APPLY_DRIVER_LICENSE.md](docs/APPLY_DRIVER_LICENSE.md) afterward if you
need one (the container prints a cosmetic warning without it; only escalates
to a hard error if Plex disables unlicensed ODBC access).

1. Get the Linux 64-bit driver package from Plex support (a `.zip` or `.tar` file).
2. Extract the archive into the `driver/` folder.
3. Inside the extracted files, locate `etc/tar/ivoaLinux64.tar`.
4. Extract `ivoaLinux64.tar` into `driver/` — this creates the `lib64/` directory.

   On Windows with the built-in `tar` command (PowerShell):
   ```powershell
   tar -xf driver\etc\tar\ivoaLinux64.tar -C driver\ lib64/
   ```

5. Verify:
   ```powershell
   ls driver\lib64\
   # Must show: ivoa27.so and ddtrc27.so
   ```

6. Remove installer artifacts that are not needed in the image (**skip this
   if you plan to apply a license per docs/APPLY_DRIVER_LICENSE.md** — that
   process needs `unixpi.ksh` and `makelic64`):
   ```powershell
   # These are safe to delete after extraction, once licensed
   Remove-Item driver\etc\tar -Recurse -Force
   Remove-Item driver\unixpi.ksh, driver\makelic64, driver\install.pi,
               driver\product.dat, driver\ddprocinfo -ErrorAction SilentlyContinue
   ```

---

## Step 2 — Create your `.env` file

```powershell
cp .env.example .env
```

Open `.env` and fill in the **Section 1** and **Section 2** fields. Leave the BigQuery and Secret Manager fields blank — they are not used in local mode.

Minimum required values for local mode — **IAM token auth (primary method, recommended)**:

```env
PLEX_ACCESS_TOKEN=your_plex_iam_token
PLEX_ODBC_USER=yourname.company
PLEX_HOST=vox.test.odbc.plex.com
PLEX_VIEW=Sales_v_PO
BQ_TABLE=production_orders
```

If you don't have an IAM token, the username/password DSN fallback still works:

```env
PLEX_ODBC_USER=your_plex_username
PLEX_ODBC_PASSWORD=your_plex_password
PLEX_COMPANY_CODE=your_company_code
PLEX_DSN=PlexProduction
BQ_TABLE=production_orders
```

`BQ_TABLE` is used as the prefix for the output CSV filename. Set it to a meaningful name for the data you are extracting (e.g. `production_orders`, `inventory`, `customers`).

---

## Step 3 — Verify the ODBC connection config

Open [config/odbc.ini](config/odbc.ini) and check the `[PlexProduction]` section:

```ini
[PlexProduction]
Host = odbc.plex.com         ← confirmed production host (no "vox." prefix)
Port = 19995                ← confirmed for both environments
```

> **Common mix-up:** `vox.odbc.plex.com` (with the `vox.` prefix) is the
> **test** host, under `[PlexTest]` — not production. Double-check which
> section you're editing.

If Plex support gave you a different hostname or port for your account, update those values now.

If you are connecting to the Plex **test environment**, set `PLEX_DSN=PlexTest` in `.env` and verify the `[PlexTest]` section in `odbc.ini` as well.

---

## Step 4 — Point it at a real Plex view

There's no query to hand-edit anymore — `query_plex()` in [main.py](../main.py) builds `SELECT * FROM {view}{filter}{order_by}` from three env vars, not a hardcoded column list:

```python
def query_plex(conn, plex_view=None, plex_filter=None, plex_date_col=None) -> pd.DataFrame:
    view     = plex_view     if plex_view     is not None else PLEX_VIEW
    filt     = plex_filter   if plex_filter   is not None else PLEX_FILTER
    date_col = plex_date_col if plex_date_col is not None else PLEX_DATE_COL
    sql = f"SELECT * FROM {view}{filter_clause}{order_clause}"
```

Set these in `.env` instead of editing any code:

```env
PLEX_VIEW=Sales_v_PO          # always {Database}_v_{ViewName} — no aliases
PLEX_FILTER=                 # a WHERE clause (include the word WHERE), or leave empty
PLEX_DATE_COL=                # a timestamp column for incremental sync, or leave empty for a full extract
```

**Every real deployed job actually runs a different mode entirely** — see
the note at the top of this file. Setting `PLEX_VIEW` here only exercises
this single-view fallback path (fine for a quick connectivity check of one
view); to reproduce what a real job does, set `REPORT_CONFIG_GCS_PATH` to
a local/scratch YAML instead (copy an existing `reports/*.yaml` as a
template) and leave `PLEX_VIEW` unset.

There is no `last_sync`/incremental-filtering logic to preserve here —
every local-mode run is a full extract regardless of `PLEX_DATE_COL`
(that only matters for the BigQuery `WRITE_APPEND` path, which local mode
never takes).

---

## Step 5 — Build the Docker image

```powershell
docker compose build
```

**Expected output:** `... Successfully built ...` and `... Successfully tagged ...`

**Common failures:**

| Error | Fix |
|---|---|
| `COPY driver/lib64` failed — file not found | `driver/lib64/ivoa27.so` is missing — redo Step 1 |
| `dpkg --add-architecture i386` failed | Docker is in Windows containers mode — switch to Linux mode |
| `pip install` failed — network error | Check Docker Desktop proxy/firewall settings |

The build takes 2–5 minutes the first time (downloading base image and apt packages).

---

## Step 6 — Run the pipeline

```powershell
docker compose up
```

The container will run once and exit. Watch the logs for these key lines:

```
[INFO] LOCAL MODE — skipping BigQuery, full extract.
[INFO] Connecting driver-direct to vox.test.odbc.plex.com:19995 (IAM token auth)
[INFO] ODBC connection established.
[INFO] Querying Plex [Sales_v_PO]...
[INFO] Fetched 1234 rows from Plex [Sales_v_PO].
[INFO] Wrote 1234 rows to /output/production_orders_20260519T020000Z.csv
```

---

## Step 7 — Inspect the output

```powershell
ls output\
# Should show: production_orders_20260519T020000Z.csv (or similar)
```

Open the CSV and verify:

- **Column names** match the Plex view columns you selected
- **Row count** looks reasonable for the dataset
- **No entirely null columns** that should have values
- **Timestamps** are present in the Modified_Date column (or equivalent)

Each run creates a new timestamped CSV. Old files are not overwritten, so you can run multiple times safely.

---

## Troubleshooting

### ODBC connection refused / timeout

```
pyodbc.OperationalError: ('HYT00', 'Login timeout expired')
```

- Confirm `Host` and `Port` in `config/odbc.ini` with Plex support
- Your IP address may need to be allowlisted by Plex — ask your Plex support contact

### Authentication error

```
pyodbc.Error: ('28000', 'Invalid authorization specification')
```

- Double-check `PLEX_ODBC_USER`, `PLEX_ODBC_PASSWORD`, and `PLEX_COMPANY_CODE` in `.env`
- CompanyCode is case-sensitive

### Empty CSV (0 rows)

The file is created but has only the header row:
- The view name in the SQL query may be incorrect — verify with Plex support
- The view may exist but have no data matching the `Modified_Date > ?` filter (unlikely since local mode uses epoch as the baseline, pulling all rows)

### `ivoa27.so: cannot open shared object file`

The driver `.so` files are missing or in the wrong location:
- Re-verify Step 1 — `driver/lib64/ivoa27.so` must exist before building
- Run `docker compose build` again after fixing the driver folder

### `KeyError: GCP_PROJECT`

The code is trying to run in bigquery mode:
- Check that `docker-compose.yml` still has `OUTPUT_MODE: local` in the environment block
- Do NOT set `OUTPUT_MODE=bigquery` in `.env` — docker-compose overrides it

---

## Running again

```powershell
docker compose up
```

No rebuild needed unless you changed `main.py`, `Dockerfile`, `requirements.txt`, or any file in `config/` or `driver/`. If you did change those:

```powershell
docker compose build && docker compose up
```

---

## Next step

Once your CSV output looks correct, proceed to **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** to deploy the pipeline to GCP.
