<#
  scorecard_status.ps1 — does every scorecard tile have data behind it?
  ====================================================================

  Answers, in one pass, the question that actually matters before a demo:
  for each view the Vox scorecard reads, does it EXIST, and does it have ROWS?

  Those are three different failures that look identical on a dashboard tile:

    MISSING  — the view was never created. The job can exit 0 and still leave
               this state (view creation fails while extractions succeed), so
               a clean `gcloud run jobs execute` proves nothing on its own.
    EMPTY    — the view exists and returns 0 rows. Usually means the Plex test
               tenant has no data of that kind yet, NOT that anything is broken.
    n rows   — real data.

  Usage (PowerShell, from the repo root):

      ./scripts/scorecard_status.ps1                     # PlexTest
      ./scripts/scorecard_status.ps1 -Dataset PlexProd
      ./scripts/scorecard_status.ps1 -Csv status.csv     # also write a CSV
      ./scripts/scorecard_status.ps1 -Quality            # + raw Quality tables

  Requires a working `bq`. If it reports a reauth failure, run
  `gcloud auth login` in an interactive terminal first — the org's security
  policy expires credentials periodically and it cannot be scripted around.

  The bq invocation looks odd on purpose. On this machine `bq` cannot be
  driven from git-bash at all, piping SQL from PowerShell prepends a UTF-8 BOM
  that BigQuery rejects, and passing SQL as an argument breaks on any file
  whose first line is a `--` comment. Redirecting a file through `cmd` avoids
  all three.
#>

param(
  [string]$Project = 'voxdatalake',
  [string]$Dataset = 'PlexTest',
  [string]$Csv = '',
  # Also count the raw Quality tables. Use this on a day Quality is creating
  # test data — see the note by $QualityRaw.
  [switch]$Quality
)

$ErrorActionPreference = 'Continue'

# The views the scorecard reads, grouped by the area of the board they feed.
# Keep this in step with `display_name: "Vox Scorecard | ..."` in reports/*.yaml.
$Views = [ordered]@{
  'Revenue'     = @(
    'sales_revenue_summary_report',
    'sales_revenue_run_rate_report',
    'shipping_revenue_report',
    'shipping_daily_report',
    'shipping_pending_revenue_report',
    'revenue_vs_goal_report',
    'v2_revenue_vs_goal_report'
  )
  'Sales'       = @(
    'sales_mtd_summary_report',
    'sales_mtd_by_status_change_report',
    'sales_order_value_by_status_report',
    'pipeline_plex_value_report',
    'sales_vs_goal_report',
    'v2_sales_vs_goal_report'
  )
  'Production'  = @(
    'production_monthly_by_workcenter_group_report',
    'production_vs_goal_report',
    'v2_production_vs_goal_report',
    'mfg_job_open_caps_report',
    'bottling_job_open_report'
  )
  'Quality'     = @(
    'quality_fpy_by_area_month_report',
    'quality_cost_by_category_report',
    'quality_disposition_cost_report',
    'quality_turnaround_time_report',
    'quality_deviation_report',
    'quality_nonconformance_report'
  )
  'Inventory'   = @(
    'part_on_hand_inventory_report',
    'inventory_top_quantity_report',
    'inventory_avg_daily_usage_report',
    'inventory_out_of_stock_report',
    'inventory_available_to_sell_report',
    'inventory_valuation_total_report',
    'part_cycle_count_report'
  )
  'Goal source' = @(
    'scorecard_goals',
    'scorecard_goals_app',
    'v2_scorecard_goals_resolved'
  )
  'Operational' = @(
    'label_design_report'
  )
}

# Quality is checked twice: the views above, and the RAW tables below. When
# someone creates test data in Plex, the question is not "does the view work"
# but "did the record reach BigQuery at all" — and a view returning 0 rows
# cannot tell those apart. The raw counts can.
$QualityRaw = @(
  'raw_Quality_v_Problem',
  'raw_Quality_v_Deviation',
  'raw_Quality_v_Deviation_Part',
  'raw_Quality_v_Deviation_Job',
  'raw_Quality_v_Final_Disposition',
  'raw_Quality_v_Initial_Disposition'
)

$tmp = Join-Path $env:TEMP ("scorecard_status_" + [guid]::NewGuid().ToString('N') + ".sql")
$results = @()
$authFailed = $false

function Invoke-Count {
  param([string]$FullName)

  "SELECT COUNT(*) AS n FROM ``$FullName``" | Out-File -FilePath $script:tmp -Encoding ascii
  $raw = cmd /c "bq query --use_legacy_sql=false --project_id=$script:Project --format=csv < `"$script:tmp`" 2>&1"
  $text = ($raw | Out-String)

  if ($text -match 'Reauthentication failed|credentials') {
    return @{ State = 'AUTH'; Count = $null; Detail = 'reauth required' }
  }
  if ($text -match 'Not found|was not found') {
    return @{ State = 'MISSING'; Count = $null; Detail = 'view does not exist' }
  }
  # The CSV body is the last line that is purely digits.
  $n = ($raw | Where-Object { $_ -match '^\d+$' } | Select-Object -Last 1)
  if ($null -eq $n) {
    $firstErr = ($raw | Where-Object { $_ -match '\S' } | Select-Object -First 1)
    return @{ State = 'ERROR'; Count = $null; Detail = "$firstErr" }
  }
  $n = [int]$n
  if ($n -eq 0) { return @{ State = 'EMPTY'; Count = 0; Detail = '' } }
  return @{ State = 'ROWS'; Count = $n; Detail = '' }
}

Write-Host ""
Write-Host "Scorecard data check — $Project.$Dataset" -ForegroundColor White
Write-Host ("=" * 62)

foreach ($area in $Views.Keys) {
  Write-Host ""
  Write-Host $area -ForegroundColor Cyan

  foreach ($view in $Views[$area]) {
    $r = Invoke-Count -FullName "$Project.$Dataset.$view"

    if ($r.State -eq 'AUTH') {
      $authFailed = $true
      Write-Host "  ! bq needs reauthentication — run 'gcloud auth login' interactively." -ForegroundColor Red
      break
    }

    switch ($r.State) {
      'ROWS'    { $label = "{0,9:N0} rows" -f $r.Count; $colour = 'Green' }
      'EMPTY'   { $label = "        0 rows"; $colour = 'Yellow' }
      'MISSING' { $label = "       MISSING"; $colour = 'Red' }
      default   { $label = "         ERROR"; $colour = 'Red' }
    }

    Write-Host ("  {0}  {1}" -f $label, $view) -ForegroundColor $colour
    if ($r.Detail -and $r.State -eq 'ERROR') {
      Write-Host ("              {0}" -f $r.Detail) -ForegroundColor DarkGray
    }

    $results += [pscustomobject]@{
      area = $area; view = $view; state = $r.State
      row_count = $r.Count; detail = $r.Detail; dataset = $Dataset
    }
  }

  if ($authFailed) { break }
}

if ($authFailed) {
  Write-Host ""
  Write-Host "Stopped: credentials expired. Nothing above this point is reliable." -ForegroundColor Red
  exit 1
}

# ── Quality raw tables ──────────────────────────────────────────────────────
# Only when asked for: this is the check to run the same day Quality creates
# destruction / deviation / rework test data, because the test tenant resets
# and the evidence does not survive to the next morning.
if ($Quality) {
  Write-Host ""
  Write-Host "Quality — raw tables (did the record reach BigQuery?)" -ForegroundColor Cyan

  foreach ($tbl in $QualityRaw) {
    $r = Invoke-Count -FullName "$Project.$Dataset.$tbl"
    if ($r.State -eq 'AUTH') { $authFailed = $true; break }

    switch ($r.State) {
      'ROWS'    { $label = "{0,9:N0} rows" -f $r.Count; $colour = 'Green' }
      'EMPTY'   { $label = "        0 rows"; $colour = 'Yellow' }
      'MISSING' { $label = "       MISSING"; $colour = 'Red' }
      default   { $label = "         ERROR"; $colour = 'Red' }
    }
    Write-Host ("  {0}  {1}" -f $label, $tbl) -ForegroundColor $colour

    $results += [pscustomobject]@{
      area = 'Quality raw'; view = $tbl; state = $r.State
      row_count = $r.Count; detail = $r.Detail; dataset = $Dataset
    }
  }

  Write-Host ""
  Write-Host "  A raw table with rows and a view with none means the VIEW is wrong." -ForegroundColor DarkGray
  Write-Host "  Both empty means the record never left Plex — check the extraction ran." -ForegroundColor DarkGray
}

Remove-Item $tmp -ErrorAction SilentlyContinue

Write-Host ""
Write-Host ("=" * 62)
$withRows = @($results | Where-Object { $_.state -eq 'ROWS' }).Count
$empty    = @($results | Where-Object { $_.state -eq 'EMPTY' }).Count
$missing  = @($results | Where-Object { $_.state -in @('MISSING','ERROR') }).Count

Write-Host ("{0} with data   {1} empty   {2} missing/error   ({3} checked)" -f `
  $withRows, $empty, $missing, $results.Count)

if ($missing -gt 0) {
  Write-Host ""
  Write-Host "MISSING is the one to act on — an empty view usually just means the" -ForegroundColor DarkGray
  Write-Host "Plex tenant has no data of that kind yet; a missing one means a view" -ForegroundColor DarkGray
  Write-Host "failed to create, which a job's exit code will not have told you." -ForegroundColor DarkGray
}

if ($Csv) {
  $results | Export-Csv -Path $Csv -NoTypeInformation -Encoding UTF8
  Write-Host ""
  Write-Host "Written: $Csv"
}
