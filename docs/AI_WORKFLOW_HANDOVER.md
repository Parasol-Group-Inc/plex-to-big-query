# Handover: people, credentials and the Claude Code setup

Written for whoever takes over any part of this work, and for anyone who starts
using Claude Code on it. It answers three questions: what exists only on one
person's machine or account, how to back it up and restore it, and what has to
be re-done when a person or a credential rotates. It complements
[DISASTER_RECOVERY.md](DISASTER_RECOVERY.md) (the whole GCP account is lost);
this is about people and tools changing.

Status as of 2026-10-24. Facts below were read from the live setup that day;
update the dates when you change something.

## 1. What lives where

| Asset | Where it lives | In git? | Backed up | Notes |
|---|---|---|---|---|
| Code, docs, SQL, YAML | GitHub `Parasol-Group-Inc/plex-to-big-query` | yes | GitHub, plus a `repo-<stamp>.zip` in every backup | |
| QuickBooks pipeline | GitHub `quickbooks-to-biquery` | yes | GitHub | its own repo, own remote and project (`parasoldatalake`) |
| `terraform/terraform.tfvars` | primary folder only | no | `backup_to_bucket` | every real value behind the pipeline |
| `.env` | each machine | no | `backup_to_bucket` | the Mac and the Windows one differ; see "Backup" |
| `driver/` (licensed Plex ODBC driver) | each machine | no | zipped in the backup, and `gs://voxdatalake-build-assets/plex-odbc-driver/` | the bucket copy lacked `libicudata.so.42` until 2026-10-24 |
| `zipfiles/` (vendor packages, licence serials) | Windows machine only | no | `backup_to_bucket` from Windows | not on the Mac |
| Secret values (8) | Secret Manager | no | `secrets.env` in the backup | anyone who can read the backup can read them |
| Terraform state | `gs://voxdatalake-terraform-state` | no | copy in the backup | |
| `CLAUDE.md` (the AI's project instructions) | repo root | yes | GitHub | |
| Claude memory | `~/.claude/projects/<project>/memory/*.md` | no | see section 3 | 3 files on 2026-10-24 |
| Claude user settings | `~/.claude/settings.json` | no | see section 3 | model and effort only |
| Claude's gcloud identity | `claude` gcloud configuration | no | recreate (section 4) | service account `claude-readonly` |
| Env var that selects it | VS Code user settings, `claudeCode.environmentVariables` | no | see section 3 | `CLOUDSDK_ACTIVE_CONFIG_NAME=claude` |
| Service account key (JSON) | `~/.config/gcloud/legacy_credentials/claude-readonly@.../adc.json` | no | **do not back up** | recreate instead |

## 2. Credentials tied to a person

These break when the person leaves, resets a token or loses access. None of
them is a service account.

| Credential | Tied to | Where it shows | What to do on rotation |
|---|---|---|---|
| Plex IAM token and user | the Plex user `edominguez.parasol` | every run logs `UID=edominguez.parasol`; secrets `plex-access-token`, `plex-odbc-user` | get a dedicated Plex user for the pipeline, update the two secrets, rerun the health check |
| Monday API key | Jennette Boone's personal token | secret `monday-api-key`; see DISASTER_RECOVERY.md | a Monday service account and token |
| GCP project Owners | Emilio Dominguez and Jennilyn Tockstein | `roles/owner` | keep at least two Owners at all times (DISASTER_RECOVERY.md, Scenario A) |
| GitHub access | two `gh` logins on the Mac: `emiliodom` (no access to the repo), `emiliodparasol` (has it) | `gh auth status` | switch with `gh auth switch --user emiliodparasol` |
| Your gcloud login | your Google account | `gcloud auth list` | `gcloud auth login` again when the org policy expires it |
| `claude-readonly` key | a JSON key on one laptop | `gcloud auth list` shows the account | create a new key, activate it, delete the old key (section 4) |

The first row is the biggest single risk: production authenticates to Plex as
one person. If that user is disabled, every prod job fails with `ODBC connection
failed`, and the outage breaker will hold the whole fleet.

## 3. Back everything up

Run these as yourself, never through Claude: the backups bucket is not writable
by `claude-readonly`, and the backup reads secret values.

**The infrastructure backup** (`scripts/backup_to_bucket.ps1`): uploads the
local-only files, the zipped `driver/` and `zipfiles/`, `secrets.env`, a repo
archive and a state copy to
`gs://voxdatalake-terraform-state/plex-to-big-query/backups/<UTC stamp>/` and
refreshes `latest/`. It is PowerShell. On a Mac, `brew install --cask powershell`,
then `pwsh scripts/backup_to_bucket.ps1 -WhatIf` and, if the list is right, run it
without `-WhatIf`. It refreshes `latest/.env` with the machine's own `.env`, so a
Mac run replaces the Windows `.env` as the current one (the bucket is versioned,
so the old one stays recoverable). Run it from the Windows machine too, because
only that machine has `zipfiles/`.

**The AI workflow backup**: nothing in `~/.claude` is in git. Memory and settings
hold no secrets, so they can go up as plain files:

```
STAMP=$(date -u +%Y-%m-%dT%H%M%SZ)
D=gs://voxdatalake-terraform-state/plex-to-big-query/backups/ai-workflow/$STAMP
mkdir -p /tmp/ai-workflow-$STAMP
cp ~/.claude/settings.json /tmp/ai-workflow-$STAMP/
cp -R ~/.claude/projects/-Users-parasol-plex-to-big-query/memory /tmp/ai-workflow-$STAMP/
cp "$HOME/Library/Application Support/Code/User/settings.json" /tmp/ai-workflow-$STAMP/vscode-settings.json
gcloud storage cp -r /tmp/ai-workflow-$STAMP $D
```

Check `vscode-settings.json` before uploading: it is the whole VS Code user
settings file and may hold things that are not yours to share. If in doubt,
copy only the `claudeCode.environmentVariables` line into a note.

**Never** put the `claude-readonly` JSON key, a `.env`, or `secrets.env` in git,
a chat, a ticket or an artifact.

**Restore:** `scripts/restore_secrets.sh` for the secrets, `unzip` for the driver,
`gcloud storage cp` for the rest. Full runbook: DISASTER_RECOVERY.md.

## 4. Claude Code: how it is set up, and how to set it up again

Claude Code runs gcloud and `bq` as the read-only service account, so a wrong
command cannot write, deploy or read secrets. The mechanism and limits are in
[CLAUDE_CODE_IAM.md](CLAUDE_CODE_IAM.md). To rebuild it on a machine:

1. Get a key for `claude-readonly@voxdatalake.iam.gserviceaccount.com` from a
   project Owner. Never from a chat or a repo.
2. `gcloud config configurations create claude`, then
   `gcloud auth activate-service-account --key-file=<key> --configuration=claude`
   and `gcloud config set project voxdatalake --configuration=claude`. Delete the
   key file afterwards.
3. In VS Code user settings add
   `"claudeCode.environmentVariables": [{"name": "CLOUDSDK_ACTIVE_CONFIG_NAME", "value": "claude"}]`.
   In the terminal Claude Code CLI, put the variable under `env` in
   `~/.claude/settings.json` instead.
4. Make `default` the active gcloud configuration for your own terminal:
   `gcloud config configurations activate default`. If `~/.config/gcloud/active_config`
   says `claude`, your own deploys and copies fail as the read-only account.
5. Put the Homebrew `python` first on PATH (`/opt/homebrew/opt/python@3.15/libexec/bin`),
   because the git hooks and the Terraform deploy guard call `python`, not `python3`.
6. Restore the memory files from the backup into
   `~/.claude/projects/<mangled project path>/memory/`.
7. Check from inside a Claude session: `echo $CLOUDSDK_ACTIVE_CONFIG_NAME` prints
   `claude`, and a write such as `bq query --dry_run "CREATE TABLE ..."` is
   refused with `Access Denied`.

**Rotating the service account key:** an Owner creates a new key, you activate it
on the `claude` configuration, check step 7, then the Owner deletes the old key
in IAM. Also record the key's creation date (open item D17).

**What Claude will not do for you:** push to GitHub, open or merge a PR, or write
to GCS unless a permission rule allows it. When the permission classifier
refuses, the commit is still made locally and you run the push yourself. Rules
live in Claude Code settings, not in this repo.

## 5. Acknowledgement

Everyone who uses Claude Code on this repo, or takes over a credential above,
reads CLAUDE.md, CLAUDE_CODE_IAM.md and this page, then adds a line here in
the PR that merges their access. It records that they know:

- Claude's cloud access is read-only by design, and a `PERMISSION_DENIED` from it
  means "run it yourself", not "widen the account";
- credentials, `.env` files and the service account key never go in git, chats,
  tickets or artifacts;
- deploys are `./scripts/deploy.sh` from the primary folder, by a person;
- `--no-verify` and the hook override variables are never used without the
  owner's say-so, and are named when they are;
- the production pipeline depends on one person's Plex user and one person's
  Monday token (section 2), and a change to either needs a handover first.

| Name | Date | Role / what they took over | Read CLAUDE.md, IAM doc, this page |
|---|---|---|---|
| | | | |
