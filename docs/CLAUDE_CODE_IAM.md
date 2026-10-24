# Claude Code and Google Cloud access (the `claude-readonly` service account)

Written for developers on this repo, and for anyone who runs Claude Code in it.

**Short version:** Claude Code does not use your Google login. It runs gcloud
and bq as a separate, read-only service account, `claude-readonly@voxdatalake.iam.gserviceaccount.com`,
through a gcloud configuration named `claude`. It can read BigQuery, Cloud Run
and logs. It cannot write anything, deploy, or read secrets. Your own
`default` configuration is untouched.

## Why it exists

Claude Code runs shell commands for you. If it ran as you, a wrong command
could write to BigQuery, run a job, or change GCS. That is the kind of mistake
this repo has already paid for (a stale `gcloud storage cp` rolled prod back;
see "Known friction" in `CLAUDE.md`). A separate identity with read-only IAM
makes that impossible at the cloud level, whatever Claude is told to do.

Deploys stay human: `./scripts/deploy.sh` from the primary folder, as you.

## How it is wired

| Piece | Value |
|---|---|
| Service account | `claude-readonly@voxdatalake.iam.gserviceaccount.com`, project `voxdatalake` |
| Credential type | JSON key. gcloud stores it in `~/.config/gcloud/legacy_credentials/claude-readonly@.../adc.json` |
| gcloud configuration | `claude` (account = the service account, project = `voxdatalake`) |
| Your own configuration | `default` (your `@parasolgroupinc.com` account) |
| How Claude picks it | The environment variable `CLOUDSDK_ACTIVE_CONFIG_NAME=claude`, set for the Claude Code session only |

`CLOUDSDK_ACTIVE_CONFIG_NAME` overrides gcloud's active configuration for any
process that inherits it. Your own terminal should not have it, and gcloud's
persistent active configuration (`~/.config/gcloud/active_config`, set with
`gcloud config configurations activate`) must be **`default`**. Check with
`cat ~/.config/gcloud/active_config`.

**Gotcha (2026-10-23):** that file had been left on `claude`, so a normal
terminal also ran as the read-only account. Storage copies and `deploy.sh`
failed with `claude-readonly ... PERMISSION_DENIED`, even though
`echo $CLOUDSDK_ACTIVE_CONFIG_NAME` was empty. Fix:
`gcloud config configurations activate default`. For one command, add
`--configuration=default`.

**Check it took effect.** Ask Claude to run, inside the session:

```
echo $CLOUDSDK_ACTIVE_CONFIG_NAME
```

It should print `claude`. Run in your own terminal it should print nothing,
and `gcloud config configurations list` there should show `default` active.

## What it can and cannot do

Observed on 2026-10-23 by running each call as the account (the policy itself
isn't readable by this account; see "Open question" below).

| Action | Result |
|---|---|
| `bq query` on `PlexTest`, `PlexProd`, `PlexOps` etc. | allowed |
| `bq ls` the project's datasets | allowed |
| Create a table in `PlexTest` (`bigquery.tables.create`) | **denied** |
| `gcloud run jobs list` / describe | allowed |
| `gcloud logging read` | allowed |
| `gcloud storage ls` (list buckets) | **denied** |
| `gcloud secrets list` (Plex credentials live in Secret Manager) | **denied** |
| `gcloud scheduler jobs list` | **denied** |
| `gcloud functions list` | **denied** |
| `gcloud projects get-iam-policy`, `gcloud iam service-accounts ...` | **denied** (and the Resource Manager API is disabled on the project) |

So, in practice: Claude can answer "did prod run?" (read `PlexOps.etl_dispatch_log`),
inspect view output, read job logs and list Cloud Run jobs. It cannot run a job
(`run.jobs.run` is not granted), change data, touch GCS, or see credentials.

## Things that will look like bugs and are not

- **`gcloud ... PERMISSION_DENIED` from Claude.** Expected for anything in the
  denied rows above. Don't widen the account to make it go away; run the
  command yourself in your own terminal.
- **Claude cannot run the local health check.** `docker compose` needs a `.env`
  with the Plex credentials, and Claude has no access to them by design. Run it
  yourself (see `CLAUDE.md`, "Quick health check"). If Claude reports "Docker
  permission denied", that is the sandbox, not IAM.
- **`terraform plan` from Claude fails or shows nothing.** Terraform needs far
  more than read-only access, and `tf_guard.py` also restricts it. Run plans yourself.
- **Dry-run write probes** (`bq query --dry_run` of a `CREATE TABLE`) are a safe
  way to confirm the account is still read-only. The expected answer is
  `Access Denied ... bigquery.tables.create`.

## For a developer setting this up on a new machine

You need the service account's JSON key from whoever administers the project
(a human with IAM admin). Never commit it, paste it into a chat, or put it in
the repo. Then, once:

```
gcloud config configurations create claude
gcloud auth activate-service-account --key-file=<path to key> --configuration=claude
gcloud config set project voxdatalake --configuration=claude
```

Delete the key file from wherever it was downloaded once gcloud has stored it.
Then set `CLOUDSDK_ACTIVE_CONFIG_NAME=claude` for Claude Code only. Put it under
`env` in `~/.claude/settings.json` (applies to every Claude session on your
machine), or in `.claude/settings.local.json` (this repo only, not committed).
Do **not** export it in `~/.zshrc`, and do not leave `claude` as the activated
configuration: either would switch your own terminal, and
`deploy.sh` and Terraform, onto the read-only account.

On 2026-10-23 the variable was present in the running Claude session but not in
any of `~/.claude/settings*.json`, `.claude/settings*.json` or the zsh
startup files. It is being injected some other way (likely the VS Code extension's
environment setting). Whoever owns this setup should note where, so it can be
recreated.

## Open question: the exact roles

This account can't read its own IAM policy, so the roles below are **inferred
from the behaviour above, not read from the policy**. An admin should confirm
and then replace this section with the real list:

```
gcloud projects get-iam-policy voxdatalake \
  --flatten="bindings[].members" \
  --filter="bindings.members:claude-readonly" \
  --format="value(bindings.role)"
```

Behaviour is consistent with: BigQuery data viewer and job user (read plus run
queries), Cloud Run viewer, Logs viewer. Check also whether the key has a rotation date
and who holds it. The key is a long-lived credential: if it leaks, anyone
holding it can read every dataset, including production data.

## Related

- `CLAUDE.md`: deploy locks, hooks, "Known friction" (gcloud reauth, GitHub 403).
- `docs/OPERATIONS.md`: how to read `etl_dispatch_log` and `job_run_log`.
- `docs/DISASTER_RECOVERY.md`: account-loss and ownership notes.
