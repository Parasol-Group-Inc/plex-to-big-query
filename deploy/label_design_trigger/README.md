# Label Design — run the sync on demand (Apps Script web app)

A one-button page that starts the Label Design Cloud Run job, so the team can
refresh `label_design_report` without waiting for the scheduled runs at
09:30 / 13:30. It also shows the last five runs (with links to their logs)
and who started what from the app.

```
[button] ──► Apps Script (runs as the deployer) ──► Cloud Run Jobs API
                                                    POST …/jobs/plex-etl-label-design-test:run
                                                          │
                                        Plex ─► raw tables ─► label_design_report (BigQuery)
```

It only **starts** the existing job; it can't change the job's config, image
or target dataset. Those stay whatever Terraform deployed.

## Safety, and why each piece is there

| Guard | What it stops |
|---|---|
| **Test job first** (`JOB_NAME=plex-etl-label-design-test`) | Nobody reaches prod until the app has been used for real. Promotion is one property change, and the page turns red: **PRODUCTION**. |
| **Runs as the deployer + allowlist** (`ALLOWED_EMAILS`) | Nobody else needs GCP permissions, so the allowlist is the real gate. Anyone else in the domain gets a view-only page. |
| **Refuses while a run is in progress** | Two overlapping ETL runs write the same raw tables. |
| **Cooldown** (`COOLDOWN_MINUTES`, default 10) | Double-clicks and "is it working yet?" re-clicks. |
| **Script lock** | Two clicks in the same second both passing the running check. |
| **Run log** (`RUN_LOG` property, last 50) | Every start, refusal and error, with who and why, shown on the page. |

## Setup (once)

1. **Create an Apps Script project** in the Cloud project `parasoldatalake`,
   like the manual-data app (Project Settings → Google Cloud Platform
   project → change to its project *number*).
   - In that project, enable the **Cloud Run Admin API** (`run.googleapis.com`).
     API calls are billed and permitted against the script's Cloud project,
     not `voxdatalake`.
2. **Paste the files**, since Apps Script has no version control; this folder
   is the source of truth:
   - `Code.gs`
   - `Index.html` (the HTML file must be named `Index`)
   - `appsscript.json`. To see it: Project Settings → "Show appsscript.json
     manifest file in editor".
3. **Script Properties** (Project Settings → Script Properties):

   | Property | Value |
   |---|---|
   | `JOB_NAME` | `plex-etl-label-design-test` — **test until promoted** |
   | `ALLOWED_EMAILS` | comma-separated, e.g. `emilio.dominguez@parasolgroupinc.com, ashley…@…` |
   | `COOLDOWN_MINUTES` | `10` (optional) |
   | `RUN_PROJECT` / `RUN_REGION` | optional; default to `voxdatalake` / `us-central1` |

4. **Run `testSetup()`** from the editor. It starts nothing: it reads the
   job's recent executions, which proves the scope, the job name and your
   permission all line up.
   - It asks for consent the first time.
   - A `403 … run.jobs.run / run.executions.list` means the deploying account
     lacks Cloud Run access in `voxdatalake`.
5. **Deploy → New deployment → Web app.** Execute as: **Me**. Who has
   access: **Anyone within Parasol Group Inc**. Share the URL.

**Saving the code does not update the live app.** Use Deploy → Manage
deployments → edit → **New version** (same trap as the manual-data app).

## Promote to production (later)

Only after the test version has been used for real:

1. Set `JOB_NAME` = `plex-etl-label-design`. The badge turns red, **PRODUCTION**.
2. Properties are read on every request, so no redeploy is needed. Put it
   back to the test job to demote.

Every prod run sends the normal run email to the team, so a prod button
press is visible to everyone.

## Changing it

Edit here, in `ptbq-label-design` on `dev-label-design`, then commit with a
`CHANGELOG.md` entry; the hooks enforce both. Then paste into Apps Script and
deploy a new version. Apps Script isn't Terraform-managed, so `deploy.sh`
never touches it. The repo copy is the record of what should be live.
