# Local Setup Guide — Phase 1

## What this gets you

By the end of this guide you will have the ETL container running on your machine, connecting to real Plex via ODBC, and writing CSV files to `./output/`. No GCP account required.

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
- [ ] **Plex ODBC driver** — Linux 64-bit `.so` files from Plex support
  - See [PLEX_SUPPORT_TEMPLATE.md](PLEX_SUPPORT_TEMPLATE.md) for the request email template

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
```

**How to get there:**

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

6. Remove installer artifacts that are not needed in the image:
   ```powershell
   # These are safe to delete after extraction
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

Minimum required values for local mode:

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
Host = vox.odbc.plex.com     ← confirmed production host
Port = 19995                ← confirmed for both environments
```

If Plex support gave you a different hostname or port for your account, update those values now.

If you are connecting to the Plex **test environment**, set `PLEX_DSN=PlexTest` in `.env` and verify the `[PlexTest]` section in `odbc.ini` as well.

---

## Step 4 — Update the SQL query

The `query_plex()` function in [main.py](main.py) contains a placeholder query. You must replace it with the actual Plex view or report name and columns before the pipeline will extract real data.

Find this section in `main.py` (around line 150):

```python
def query_plex(conn: pyodbc.Connection, last_sync: datetime) -> pd.DataFrame:
    sql = f"""
        SELECT
            P.Plexus_Customer_No,
            P.Part_No,
            P.Part_Name,
            P.Quantity,
            P.Status,
            P.Modified_Date
        FROM
            Production_Order_v_Production_Order AS P
        WHERE
            P.Modified_Date > ?
        ORDER BY
            P.Modified_Date ASC
    """
```

**What to change:**
- Replace `Production_Order_v_Production_Order` with the actual Plex view or report name (get this from your Plex support contact)
- Replace the column list with the actual columns available in that view

**What NOT to change:**
- Keep `WHERE P.Modified_Date > ?` — this is what drives incremental loading. Replace `Modified_Date` with the correct timestamp column name if it differs in your view.
- Keep `ORDER BY P.Modified_Date ASC` (or the equivalent timestamp column)

Also update the reference on the line after the query that handles timezone conversion:

```python
if not df.empty and "Modified_Date" in df.columns:
```

Change `"Modified_Date"` to match whatever your timestamp column is actually called.

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
[INFO] LOCAL MODE — skipping BigQuery, full extract from epoch.
[INFO] Connecting to Plex via DSN: PlexProduction
[INFO] ODBC connection established.
[INFO] Querying Plex for records modified after 1970-01-01 00:00:00+00:00...
[INFO] Fetched 1234 rows from Plex.
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
