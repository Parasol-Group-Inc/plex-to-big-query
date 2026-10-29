# Claude Code and Google Cloud access (`claude-readonly` + `claude-operator`)

Written for developers on this repo, and for anyone who runs Claude Code in it.

**Short version:** Claude Code does not use your Google login. It runs gcloud
and bq as a read-only service account, `claude-readonly@voxdatalake.iam.gserviceaccount.com`,
through a gcloud configuration named `claude`. Since 2026-10-29 it can also
**write** by impersonating a second account, `claude-operator@voxdatalake.iam.gserviceaccount.com`.
The impersonation is added to one command at a time. With it, Claude can run
jobs, deploy, write to BigQuery, use GCS and read secrets. Without it, every
command is still read-only. Your own `default` configuration is untouched.

## Why two accounts

Claude Code runs shell commands for you. If it ran as you, a wrong command
could write to BigQuery, run a job, or change GCS. That is the kind of mistake
this repo has already paid for: a stale `gcloud storage cp` rolled prod back
(see "Known friction" in `CLAUDE.md`).

So reads, which are almost everything, go through an identity that cannot
write. A write has to name `claude-operator` explicitly, in the same command.
That makes every write deliberate, and Cloud Audit Logs record it as
"claude-readonly acting as claude-operator".

`claude-operator` has **no key**. The only way to act as it is to be
`claude-readonly` and ask for a short-lived token, so there is still exactly one
long-lived credential (the `claude-readonly` key on each laptop). Revoke all
write access by removing one binding (see "Turning it off" below).

## How it is wired

| Piece | Value |
|---|---|
| Read account | `claude-readonly@voxdatalake.iam.gserviceaccount.com`, JSON key, stored by gcloud under the `claude` configuration |
| Write account | `claude-operator@voxdatalake.iam.gserviceaccount.com`, no key |
| Write roles (project) | `roles/editor`, `roles/resourcemanager.projectIamAdmin`, `roles/iam.roleAdmin`, `roles/secretmanager.secretAccessor` |
| Who may impersonate it | only `claude-readonly` (`roles/iam.serviceAccountTokenCreator` on `claude-operator`) |
| gcloud configuration | `claude` (account = `claude-readonly`, project = `voxdatalake`) |
| Your own configuration | `default` (your `@parasolgroupinc.com` account) |
| How Claude picks it | `CLOUDSDK_ACTIVE_CONFIG_NAME=claude`, set for Claude Code only |
| API it needs | Cloud Resource Manager, enabled on `voxdatalake` 2026-10-29. A service account's calls are billed to its own project, so Terraform fails without it. Your login never needed it, because user logins are billed to gcloud's built-in project. |

`roles/editor` covers running and updating jobs, BigQuery writes, GCS, Cloud
Build, Cloud Functions and Scheduler. The two IAM roles are needed because
`terraform/main.tf` manages IAM bindings and a custom role. A deploy that
can't manage them fails halfway.

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

**Gotcha (2026-10-29):** the Windows laptop had **no** `claude` configuration
at all, so Claude ran there as Emilio's own full-access login. Nothing showed
it except `echo $CLOUDSDK_ACTIVE_CONFIG_NAME` printing nothing inside a Claude
session. Run that check on every machine.

## How Claude writes

**One gcloud command:** add the flag.

```bash
OP=claude-operator@voxdatalake.iam.gserviceaccount.com
gcloud run jobs execute plex-etl-sales-orders-test --region=us-central1 \
  --project=voxdatalake --wait --impersonate-service-account=$OP
```

gcloud prints `WARNING: This command is using service account impersonation`.
That warning is expected.

**A Terraform deploy:** `./scripts/deploy_as_claude.sh`. It mints a one-hour
token for `claude-operator`, exports it as `GOOGLE_OAUTH_ACCESS_TOKEN` (the
Google provider and the GCS state backend both read it), then runs
`./scripts/deploy.sh` unchanged. The preflight, the deploy guard,
`plan_review.py` and the typed confirmation all still apply. Claude runs it in
two steps:

1. `./scripts/deploy_as_claude.sh </dev/null` plans, prints the review and
   stops at the confirmation. Nothing is applied.
2. You read the review and say go. Claude then runs
   `printf '%s\n' <N> | ./scripts/deploy_as_claude.sh`, where `<N>` is the
   change count it printed. The script re-plans. If the count differs, the
   confirmation doesn't match and nothing is applied.

Same rules as for a human: primary folder, clean `main` equal to
`origin/main`. The tag push at the end uses the active `gh` account, which must
be `emiliodparasol` (see "GitHub" below).

**BigQuery writes:** not exercised yet. Read queries need nothing extra. On
the first write, check that it really ran as `claude-operator`, and record the
working command here.

**Not yet exercised as `claude-operator` (2026-10-29):**
`gcloud builds submit` (image deploys) and `gcloud functions deploy`
(dispatcher). Both should work with `--impersonate-service-account`, but the
first real use should be watched.

## What each identity can do

`claude-readonly` alone, observed 2026-10-23 and rechecked 2026-10-29:

| Action | Result |
|---|---|
| `bq query` on `PlexTest`, `PlexProd`, `PlexOps` etc. | allowed |
| `gcloud run jobs list` / describe, `gcloud logging read` | allowed |
| Create a table in `PlexTest` (`bigquery.tables.create`) | **denied** |
| `gcloud run jobs execute` (`run.jobs.run`) | **denied** (rechecked 2026-10-29) |
| `gcloud storage ls`, `gcloud secrets list`, `gcloud scheduler jobs list`, `gcloud functions list` | **denied** |

With `--impersonate-service-account=claude-operator@...` all of the above are
allowed, and so is `terraform plan`/`apply`. On 2026-10-29 the first plan as
`claude-operator` ran clean, with "No changes" against `main`.

## Things that will look like bugs and are not

- **`PERMISSION_DENIED` from a plain command.** Expected for any write. Add the
  impersonation flag if the write is intended; don't widen `claude-readonly`.
- **`iam.serviceAccounts.getAccessToken` denied when impersonating.** The
  session isn't running as `claude-readonly`; check
  `echo $CLOUDSDK_ACTIVE_CONFIG_NAME`. A user login can't impersonate the
  operator. Only `claude-readonly` was granted that.
- **Terraform: `Cloud Resource Manager API has not been used in project`.**
  The API was turned off again. Re-enable `cloudresourcemanager.googleapis.com`.
- **Claude cannot run the local health check.** `docker compose` needs a `.env`
  with the Plex credentials, which stay off Claude's machines. Run it yourself.

## Set up on a machine (Windows done 2026-10-29; Mac: do this)

The cloud side is already done: the operator account, its roles, the
impersonation grant and the API exist once for the project. Each laptop needs
only the local part. Check every step on the Mac, even where it was set up
before.

**1. gcloud `claude` configuration.** Skip if `gcloud config configurations list`
already shows `claude` with `claude-readonly`. Otherwise, in your own terminal:

```bash
gcloud iam service-accounts keys create "$HOME/claude-ro.json" --configuration=default \
  --iam-account=claude-readonly@voxdatalake.iam.gserviceaccount.com
gcloud config configurations create claude --no-activate
gcloud auth activate-service-account --key-file="$HOME/claude-ro.json" --configuration=claude
gcloud config set project voxdatalake --configuration=claude
rm "$HOME/claude-ro.json"
cat ~/.config/gcloud/active_config      # must print: default
```

**2. Point Claude Code at it.** Use the method for how you run Claude Code:

- **VS Code extension on the Mac:** in `~/Library/Application Support/Code/User/settings.json`, add
  `"claudeCode.environmentVariables": [{"name": "CLOUDSDK_ACTIVE_CONFIG_NAME", "value": "claude"}]`.
  Setting it in a Claude settings file did not take on the Mac (found 2026-10-24).
- **Windows, or the terminal CLI:** add `"CLOUDSDK_ACTIVE_CONFIG_NAME": "claude"` under `env` in
  `~/.claude/settings.json`.

Restart the Claude session.

**3. Check inside a Claude session.** Ask Claude to run each of these:

```bash
echo $CLOUDSDK_ACTIVE_CONFIG_NAME                                   # claude
gcloud config list --format='value(core.account)'                   # claude-readonly@...
gcloud run jobs execute plex-etl-sales-orders-test --region=us-central1 \
  --project=voxdatalake --async                                     # PERMISSION_DENIED run.jobs.run
gcloud run jobs describe plex-etl-sales-orders-test --region=us-central1 --project=voxdatalake \
  --impersonate-service-account=claude-operator@voxdatalake.iam.gserviceaccount.com \
  --format='value(metadata.name)'                                   # plex-etl-sales-orders-test
```

**4. Terraform.** From the primary folder on a clean `main`, ask Claude to run
`./scripts/deploy_as_claude.sh </dev/null`. You should get "Nothing to
deploy", or a review that stops at the confirmation.

**5. GitHub (PRs and the deploy tag push).** Only `emiliodparasol` can merge on
`Parasol-Group-Inc`. `emiliodom` gets `MergePullRequest` permission errors.

```bash
gh auth login                        # if emiliodparasol isn't listed yet
gh auth switch --user emiliodparasol
git -C <primary folder> config --local credential.https://github.com.username emiliodparasol
```

Then copy the hook and register it, and allow `gh pr`:

```bash
mkdir -p ~/.claude/hooks && cp scripts/claude/auto-merge-pr.sh ~/.claude/hooks/
```

In `~/.claude/settings.json`:

```json
"permissions": { "allow": [
  "Bash(gh pr create:*)", "Bash(gh pr merge:*)", "Bash(gh pr view:*)",
  "Bash(gh pr list:*)", "Bash(gh pr checks:*)", "Bash(gh pr diff:*)" ] },
"autoMode": { "allow": [
  "Creating, viewing and merging dev* -> main pull requests on the Parasol-Group-Inc/plex-to-big-query repo (gh pr create / gh pr merge), from any of its folders (plex-to-big-query, ptbq-*), when I ask for it" ] },
"hooks": { "PostToolUse": [ { "matcher": "Bash", "hooks": [
  { "type": "command", "command": "bash \"$HOME/.claude/hooks/auto-merge-pr.sh\"", "timeout": 30 } ] } ] }
```

Merge these into the existing keys rather than replacing them; the
`session_branch_guard.py` hooks must stay. The hook merges any PR that `gh pr
create` opens, straight away. It merges Parasol PRs as `emiliodparasol` using a
per-command token, so the active `gh` account never changes. It needs `python`
on PATH, not `jq`.

## Turning it off

Remove write access entirely (Owner, own terminal):

```bash
gcloud iam service-accounts remove-iam-policy-binding \
  claude-operator@voxdatalake.iam.gserviceaccount.com --project=voxdatalake \
  --member=serviceAccount:claude-readonly@voxdatalake.iam.gserviceaccount.com \
  --role=roles/iam.serviceAccountTokenCreator --configuration=default
```

Claude is read-only again immediately, and nothing else changes. To remove it
for good, also delete the `claude-operator` service account.

## Open items

- The `claude-readonly` key is long-lived and now leads to write access through
  impersonation. A leaked key is a project-wide write credential. Record each
  key's creation date and rotate it (open item D17, `AI_WORKFLOW_HANDOVER.md` §4).
- `claude-readonly`'s own roles are still inferred from behaviour, not read
  from the policy. An Owner can list them:
  `gcloud projects get-iam-policy voxdatalake --flatten="bindings[].members" --filter="bindings.members:claude-" --format="table(bindings.members,bindings.role)"`.

## Related

- `CLAUDE.md`: deploy locks, hooks, "Known friction" (gcloud reauth, GitHub 403).
- [AI_WORKFLOW_HANDOVER.md](AI_WORKFLOW_HANDOVER.md) §4: rebuild and key rotation.
- `docs/OPERATIONS.md`: how to read `etl_dispatch_log` and `job_run_log`.
