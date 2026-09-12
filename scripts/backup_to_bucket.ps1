#Requires -Version 5.1
<#
.SYNOPSIS
    Backs this repo and its local-only files up to the versioned GCS bucket.

.DESCRIPTION
    Everything here already lives in git EXCEPT a short list of files that are
    deliberately gitignored and therefore exist on exactly one laptop. Those are
    the reason this script exists — losing the machine loses them:

      terraform/terraform.tfvars   every real value behind the pipeline
      .env                         the local docker-compose credentials
      assets/*.csv                 the sheet exports the Label Design mapping
                                   was derived from
      terraform/*.tfstate          only if a local state file is still present.
                                   Normally there is none: state lives in the
                                   `backend "gcs"` block in terraform/main.tf,
                                   in this same bucket under a different prefix.
                                   A local file means a migration left one
                                   behind, and it is worth keeping a copy.

    A full repo archive goes up alongside them. That is belt and braces — the
    repo is on GitHub — but it costs pennies and it means one command restores
    a working machine rather than "clone, then remember the four other things".

    Destination (versioned bucket, same one Terraform keeps its state in):

      gs://voxdatalake-terraform-state/plex-to-big-query/backups/<UTC stamp>/

    A timestamped folder per run, so a backup can never overwrite the one that
    would have saved you. `latest/` is also refreshed, for restore convenience.

.PARAMETER WhatIf
    Lists exactly what would be uploaded and to where. Uploads nothing.

.EXAMPLE
    pwsh scripts/backup_to_bucket.ps1 -WhatIf
    pwsh scripts/backup_to_bucket.ps1

.NOTES
    REAUTH. `gcloud storage` on this project periodically fails with
    "Reauthentication failed. cannot prompt during non-interactive execution"
    even though `gcloud auth list` shows an active account — an org policy
    requiring periodic interactive login. It cannot be scripted around. Run
    `gcloud auth login` in your own terminal first, then this.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string] $Bucket = 'gs://voxdatalake-terraform-state',
    [string] $Prefix = 'plex-to-big-query/backups'
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Stamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHHmmssZ')
$Dest = "$Bucket/$Prefix/$Stamp"
$Latest = "$Bucket/$Prefix/latest"

Write-Host ''
Write-Host 'Label Design / plex-to-big-query — backup' -ForegroundColor Cyan
Write-Host "  repo -> $RepoRoot"
Write-Host "  dest -> $Dest"
Write-Host ''

# ── Preflight ──────────────────────────────────────────────────────────────
# Checked up front rather than discovered halfway through a half-finished
# upload, which is the state that makes a backup untrustworthy.
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw 'gcloud is not on PATH. Install the Google Cloud SDK, then re-run.'
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'git is not on PATH.'
}

# ── The files that exist nowhere else ──────────────────────────────────────
$LocalOnly = @(
    'terraform/terraform.tfvars',
    '.env'
) + (Get-ChildItem -Path (Join-Path $RepoRoot 'assets') -Filter '*.csv' -ErrorAction SilentlyContinue |
     ForEach-Object { "assets/$($_.Name)" }
) + (Get-ChildItem -Path (Join-Path $RepoRoot 'terraform') -Filter '*.tfstate*' -ErrorAction SilentlyContinue |
     ForEach-Object { "terraform/$($_.Name)" })

$Present = @()
$Absent = @()
foreach ($rel in $LocalOnly) {
    if (Test-Path (Join-Path $RepoRoot $rel)) { $Present += $rel } else { $Absent += $rel }
}

Write-Host 'Local-only files (gitignored — the point of this script):' -ForegroundColor Yellow
foreach ($f in $Present) {
    $size = (Get-Item (Join-Path $RepoRoot $f)).Length
    Write-Host ("  + {0,-42} {1,10:N0} bytes" -f $f, $size)
}
foreach ($f in $Absent) {
    # Absence is reported, never silent. A .env that has quietly stopped
    # existing is exactly the thing a backup is supposed to tell you about.
    Write-Host ("  - {0,-42} NOT PRESENT" -f $f) -ForegroundColor DarkGray
}
Write-Host ''

# ── The repo archive ───────────────────────────────────────────────────────
# `git archive HEAD` rather than zipping the working directory: it takes
# exactly what is committed, so the archive can never smuggle in the very
# credentials that are gitignored for a reason. The local-only files above are
# uploaded separately and deliberately.
$ArchiveName = "repo-$Stamp.zip"
$ArchivePath = Join-Path ([System.IO.Path]::GetTempPath()) $ArchiveName

$Head = (& git -C $RepoRoot rev-parse --short HEAD).Trim()
$Dirty = (& git -C $RepoRoot status --porcelain)
Write-Host "Repo archive: git archive HEAD ($Head)" -ForegroundColor Yellow
if ($Dirty) {
    Write-Host '  NOTE working tree has uncommitted changes; the archive holds HEAD only.' -ForegroundColor DarkYellow
}

if ($PSCmdlet.ShouldProcess($ArchivePath, 'git archive')) {
    $prev = $ErrorActionPreference          # same native-stderr hazard as above
    $ErrorActionPreference = 'Continue'
    try { & git -C $RepoRoot archive --format=zip -o $ArchivePath HEAD 2>&1 | Out-Null }
    finally { $ErrorActionPreference = $prev }
    if ($LASTEXITCODE -ne 0) { throw "git archive failed with exit code $LASTEXITCODE." }
    Write-Host ("  wrote {0} ({1:N0} bytes)" -f $ArchiveName, (Get-Item $ArchivePath).Length)
}
Write-Host ''

# ── Upload ─────────────────────────────────────────────────────────────────
function Send-ToBucket {
    param([string] $Source, [string] $Target)

    if (-not $PSCmdlet.ShouldProcess($Target, "upload $Source")) {
        Write-Host "  would upload  $Source  ->  $Target"
        return
    }
    # gcloud writes progress to STDERR even on success, and Windows PowerShell
    # 5.1 wraps native-command stderr in an ErrorRecord — which, under
    # $ErrorActionPreference = 'Stop', kills the script on a *successful*
    # upload. So the preference is relaxed across the call and the outcome is
    # judged by $LASTEXITCODE, the only reliable signal for a native exe here.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & gcloud storage cp $Source $Target 2>&1 | Out-Null }
    finally { $ErrorActionPreference = $prev }

    if ($LASTEXITCODE -ne 0) {
        throw "Upload failed for $Source (exit $LASTEXITCODE). If this is a " +
              "reauth error, run 'gcloud auth login' in your own terminal and re-run."
    }
    Write-Host "  uploaded  $Target" -ForegroundColor Green
}

Write-Host 'Uploading:' -ForegroundColor Yellow
foreach ($rel in $Present) {
    $flat = $rel -replace '[\\/]', '__'      # keep a flat, unambiguous object name
    Send-ToBucket -Source (Join-Path $RepoRoot $rel) -Target "$Dest/$flat"
    Send-ToBucket -Source (Join-Path $RepoRoot $rel) -Target "$Latest/$flat"
}
if (Test-Path $ArchivePath) {
    Send-ToBucket -Source $ArchivePath -Target "$Dest/$ArchiveName"
    Send-ToBucket -Source $ArchivePath -Target "$Latest/repo-latest.zip"
    Remove-Item $ArchivePath -Force -ErrorAction SilentlyContinue
}

# A manifest, so a restorer can tell at a glance what a folder holds and which
# commit it came from without downloading and unzipping the archive first.
$ManifestPath = Join-Path ([System.IO.Path]::GetTempPath()) "MANIFEST-$Stamp.txt"
$Manifest = @(
    "plex-to-big-query backup"
    "taken:   $Stamp (UTC)"
    "host:    $env:COMPUTERNAME"
    "commit:  $Head"
    "dirty:   $(if ($Dirty) { 'yes - working tree had uncommitted changes' } else { 'no' })"
    ""
    "local-only files included:"
) + ($Present | ForEach-Object { "  $_" }) + @(
    ""
    "local-only files NOT present on this machine:"
) + ($Absent | ForEach-Object { "  $_" }) + @(
    ""
    "restore:"
    "  gcloud storage cp $Latest/terraform__terraform.tfvars terraform/terraform.tfvars"
    "  gcloud storage cp $Latest/.env .env"
    "  cd terraform && terraform init   # state comes from the gcs backend"
)

if ($PSCmdlet.ShouldProcess("$Dest/MANIFEST.txt", 'write manifest')) {
    $Manifest | Set-Content -Path $ManifestPath -Encoding utf8
    Send-ToBucket -Source $ManifestPath -Target "$Dest/MANIFEST.txt"
    Send-ToBucket -Source $ManifestPath -Target "$Latest/MANIFEST.txt"
    Remove-Item $ManifestPath -Force -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host "Done. $Dest" -ForegroundColor Cyan
Write-Host ''
