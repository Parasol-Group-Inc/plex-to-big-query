/**
 * Vox scorecard — Goals editor (Apps Script web app)
 * =================================================
 *
 * A small form that writes goals straight into BigQuery, so nobody has to
 * edit a Google Sheet that people keep breaking, and Jennilyn doesn't have to
 * hand-edit the table.
 *
 *   Jennilyn, 2026-09-09: "I don't want to do it in a sheet because people
 *   tend to break the Google Sheets all the time."
 *   And on the goals specifically: "it'd be nice to have an interface for them
 *   to be able to update it and have it update BigQuery."
 *
 * Modelled on her existing sales-KPI web app (same Apps Script + HTML shape).
 *
 * ── WHERE IT WRITES ────────────────────────────────────────────────────────
 * `<project>.<dataset>.scorecard_goals_app`, which is APPEND-ONLY. Every save
 * inserts a row; the newest row per (metric, period_month, scope) wins. Two
 * people editing the same goal minutes apart therefore cannot lose each
 * other's write, and every edit stays as history.
 *
 * Reports do NOT read this table directly. They read
 * `v2_scorecard_goals_resolved`, which prefers this table and falls back to
 * `scorecard_goals` (the spreadsheet ETL) for any goal not entered here — so
 * nothing goes blank while both sources are live. Deleting a goal here writes
 * a tombstone (`is_deleted = TRUE`), which restores the spreadsheet value
 * rather than blanking the tile.
 *
 * ── DEPLOYING (this catches everyone once) ─────────────────────────────────
 * Saving the code does NOT update the live app. You must Deploy > Manage
 * deployments > edit > New version. Jennilyn, same call: "if you make any
 * changes to the code, even if you save it and run it, it won't update it
 * unless you come in here and make a new version and deploy it. And sometimes
 * that changes the URL."
 *
 * Deploy with: Execute as = Me, Who has access = Anyone within
 * Parasol Group Inc. The BigQuery writes then run as the deployer's account,
 * so viewers need no BigQuery permissions of their own.
 *
 * ── SETUP ─────────────────────────────────────────────────────────────────
 *  1. Services (+) > BigQuery API > Add.
 *  2. Project Settings > Script Properties, add:
 *       GCP_PROJECT  = voxdatalake
 *       BQ_DATASET   = PlexTest        (switch to PlexProd at go-live)
 *     Kept in properties, not in the code, so the same script can point at
 *     test or production without an edit that needs redeploying.
 */

// ── Config ─────────────────────────────────────────────────────────────────

var GOALS_TABLE = 'scorecard_goals_app';
var SHEET_TABLE = 'scorecard_goals';          // the spreadsheet ETL's table
var RESOLVED_VIEW = 'v2_scorecard_goals_resolved';

var METRICS = {
  revenue: {
    label: 'Revenue',
    unit: 'USD',
    // Revenue is company-wide: one goal per month, no scope.
    scopeMode: 'none',
    scopeLabel: ''
  },
  sales: {
    label: 'Sales (by rep)',
    unit: 'USD',
    scopeMode: 'list',
    scopeLabel: 'Sales rep',
    // Offered alongside the real reps so a company-wide sales target can sit
    // in the same table. The reports render a blank scope as this label.
    extraScopes: ['(company-wide)']
  },
  production: {
    label: 'Production (by work centre group)',
    unit: 'units',
    scopeMode: 'list',
    scopeLabel: 'Work centre group'
  }
};

function prop_(key) {
  var v = PropertiesService.getScriptProperties().getProperty(key);
  if (!v) {
    throw new Error('Script property ' + key + ' is not set. Project Settings > Script Properties.');
  }
  return v;
}

function project_() { return prop_('GCP_PROJECT'); }
function dataset_() { return prop_('BQ_DATASET'); }

function fqn_(table) {
  return '`' + project_() + '.' + dataset_() + '.' + table + '`';
}

// ── Web app entry point ────────────────────────────────────────────────────

function doGet() {
  return HtmlService.createTemplateFromFile('Index')
    .evaluate()
    .setTitle('Vox Scorecard Goals')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function include(name) {
  return HtmlService.createHtmlOutputFromFile(name).getContent();
}

// ── Reads ──────────────────────────────────────────────────────────────────

/**
 * Runs a query and returns rows as arrays of strings. Apps Script's BigQuery
 * service returns every value as a string regardless of column type, so the
 * client parses numbers where it needs them.
 */
function query_(sql) {
  var job = BigQuery.Jobs.query({ query: sql, useLegacySql: false }, project_());
  // A large result set would need pagination; these are goals, so one page.
  return (job.rows || []).map(function (row) {
    return row.f.map(function (cell) { return cell.v; });
  });
}

/**
 * Everything the form needs to render, in ONE call — the metric list, the
 * scope options for each, and the goals already on file.
 */
function getFormData() {
  var out = {
    dataset: dataset_(),
    project: project_(),
    metrics: {},
    goals: [],
    salesReps: [],
    workcenterGroups: []
  };

  Object.keys(METRICS).forEach(function (k) {
    out.metrics[k] = {
      label: METRICS[k].label,
      unit: METRICS[k].unit,
      scopeMode: METRICS[k].scopeMode,
      scopeLabel: METRICS[k].scopeLabel
    };
  });

  // Scope options come from the REPORTS, not typed by hand, because `scope`
  // is an exact string join — a goal whose scope doesn't match the report's
  // spelling yields a NULL goal and reads as 0% forever. The classic example:
  // Plex says "Encapsulating", the scorecard tile says "Encapsulation".
  try {
    out.salesReps = query_(
      'SELECT DISTINCT sales_rep FROM ' + fqn_('sales_mtd_summary_report') +
      ' WHERE sales_rep IS NOT NULL ORDER BY sales_rep'
    ).map(function (r) { return r[0]; });
  } catch (e) {
    out.salesReps = [];
    out.repsError = String(e);
  }

  try {
    out.workcenterGroups = query_(
      'SELECT DISTINCT workcenter_group FROM ' +
      fqn_('production_monthly_by_workcenter_group_report') +
      ' WHERE workcenter_group IS NOT NULL ORDER BY workcenter_group'
    ).map(function (r) { return r[0]; });
  } catch (e) {
    out.workcenterGroups = [];
    out.groupsError = String(e);
  }

  // Existing goals, with their source, so the form shows what is already set
  // and whether it came from this app or is still coming from the sheet.
  try {
    out.goals = query_(
      'SELECT metric, FORMAT_DATE("%Y-%m-%d", period_month), IFNULL(scope, ""), ' +
      'CAST(goal_value AS STRING), IFNULL(unit, ""), IFNULL(note, ""), goal_source ' +
      'FROM ' + fqn_(RESOLVED_VIEW) + ' ORDER BY metric, period_month, scope'
    ).map(function (r) {
      return {
        metric: r[0], period_month: r[1], scope: r[2],
        goal_value: Number(r[3]), unit: r[4], note: r[5], goal_source: r[6]
      };
    });
  } catch (e) {
    out.goalsError = String(e);
  }

  return out;
}

/**
 * The running total Emilio asked for in the 2026-09-09 call: when someone
 * edits a rep's goal, show the sum of all rep goals for that month against
 * the company-wide target, so drift is visible AT ENTRY TIME rather than
 * discovered in a report later.
 *
 * The two are deliberately allowed to differ — Jennilyn: "even if their
 * individual goals don't add up to this goal, we're just going to sum
 * everything for the team." This reports the gap, it does not block on it.
 */
function getRepGoalSum(periodMonth) {
  var sql =
    'SELECT ' +
    '  SUM(IF(scope IS NOT NULL AND scope NOT IN ("", "(company-wide)"), goal_value, 0)) AS rep_total, ' +
    '  SUM(IF(scope IS NULL OR scope IN ("", "(company-wide)"), goal_value, 0)) AS company_total, ' +
    '  COUNTIF(scope IS NOT NULL AND scope NOT IN ("", "(company-wide)")) AS rep_count ' +
    'FROM ' + fqn_(RESOLVED_VIEW) + ' ' +
    'WHERE LOWER(metric) = "sales" AND period_month = DATE("' + safeDate_(periodMonth) + '")';
  var rows = query_(sql);
  if (!rows.length) return { repTotal: 0, companyTotal: 0, repCount: 0 };
  return {
    repTotal: Number(rows[0][0] || 0),
    companyTotal: Number(rows[0][1] || 0),
    repCount: Number(rows[0][2] || 0)
  };
}

// ── Writes ─────────────────────────────────────────────────────────────────

function safeDate_(s) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(s || ''))) {
    throw new Error('Month must look like YYYY-MM-DD, got: ' + s);
  }
  return s;
}

/**
 * Insert one goal. Validates before writing, because a bad row here reaches
 * a leadership tile.
 *
 * form = { metric, period_month (YYYY-MM-01), scope, goal_value, note }
 */
function saveGoal(form) {
  var metric = String(form.metric || '').toLowerCase();
  if (!METRICS[metric]) throw new Error('Unknown metric: ' + form.metric);

  var month = safeDate_(form.period_month);
  if (month.slice(-2) !== '01') {
    // The reports group by month; a goal dated mid-month would silently form
    // its own bucket and never match.
    throw new Error('Goals are per month — the date must be the 1st, got ' + month);
  }

  var value = Number(form.goal_value);
  if (!isFinite(value)) throw new Error('Goal value must be a number, got: ' + form.goal_value);
  if (value < 0) throw new Error('Goal value cannot be negative.');

  var cfg = METRICS[metric];
  var scope = String(form.scope == null ? '' : form.scope).trim();
  if (cfg.scopeMode === 'none') {
    scope = '';   // revenue is company-wide; ignore anything sent
  } else if (!scope) {
    throw new Error('Pick a ' + cfg.scopeLabel.toLowerCase() + '.');
  }
  // The reports render a blank scope as "(company-wide)"; store the blank.
  if (scope === '(company-wide)') scope = '';

  insertRows_([{
    metric: metric,
    period_month: month,
    scope: scope,
    goal_value: value,
    unit: cfg.unit,
    note: String(form.note || '').slice(0, 500),
    updated_by: activeUser_(),
    updated_at: nowIso_(),
    is_deleted: false
  }]);

  return { ok: true, message: describe_(metric, month, scope, value, cfg.unit) };
}

/**
 * Retract a goal entered here. Writes a tombstone rather than deleting the
 * row, so the audit trail survives — and because the resolver treats a
 * tombstone as "this app has nothing to say about this key", the spreadsheet
 * value comes back rather than the tile going blank.
 */
function deleteGoal(form) {
  var metric = String(form.metric || '').toLowerCase();
  if (!METRICS[metric]) throw new Error('Unknown metric: ' + form.metric);
  var month = safeDate_(form.period_month);
  var scope = String(form.scope == null ? '' : form.scope).trim();
  if (scope === '(company-wide)') scope = '';

  insertRows_([{
    metric: metric,
    period_month: month,
    scope: scope,
    goal_value: 0,
    unit: METRICS[metric].unit,
    note: 'retracted via web app',
    updated_by: activeUser_(),
    updated_at: nowIso_(),
    is_deleted: true
  }]);

  return {
    ok: true,
    message: 'Retracted. If the spreadsheet still has a goal for this ' +
             'month it will show again; otherwise the tile has no goal.'
  };
}

function activeUser_() {
  // Empty for a viewer outside the domain; never let that become a NULL that
  // hides who changed a target.
  return Session.getActiveUser().getEmail() || 'unknown';
}

function nowIso_() {
  return Utilities.formatDate(new Date(), 'UTC', "yyyy-MM-dd'T'HH:mm:ss'Z'");
}

function describe_(metric, month, scope, value, unit) {
  var who = scope || 'company-wide';
  var amount = (unit === 'USD' ? '$' : '') + value.toLocaleString() +
               (unit === 'units' ? ' units' : '');
  return 'Saved: ' + METRICS[metric].label + ' — ' + who + ' — ' +
         month.slice(0, 7) + ' — ' + amount;
}

/**
 * Insert via tabledata.insertAll (the streaming buffer) rather than a DML
 * INSERT. A DML statement would need a query job per save and BigQuery limits
 * concurrent DML on one table, which a form with several people using it can
 * hit; insertAll is built for exactly this shape of write.
 *
 * Rows are readable by queries within a few seconds. If a save appears not to
 * have taken effect immediately, that delay is why — reload rather than
 * saving twice, since a second save would just add another row.
 */
function insertRows_(rows) {
  var payload = {
    rows: rows.map(function (r) {
      return { insertId: Utilities.getUuid(), json: r };
    }),
    // One bad row should not silently drop the good ones, and a schema drift
    // should shout rather than write garbage.
    skipInvalidRows: false,
    ignoreUnknownValues: false
  };
  var res = BigQuery.Tabledata.insertAll(payload, project_(), dataset_(), GOALS_TABLE);
  if (res.insertErrors && res.insertErrors.length) {
    throw new Error('BigQuery rejected the write: ' + JSON.stringify(res.insertErrors));
  }
  return res;
}

// ── Local sanity check (run from the editor, writes nothing) ───────────────

function testReadsOnly() {
  var d = getFormData();
  Logger.log('dataset: %s', d.dataset);
  Logger.log('reps: %s', d.salesReps.join(', ') || '(none)');
  Logger.log('groups: %s', d.workcenterGroups.join(', ') || '(none)');
  Logger.log('goals on file: %s', d.goals.length);
  if (d.goalsError) Logger.log('goals ERROR: %s', d.goalsError);
  if (d.repsError) Logger.log('reps ERROR: %s', d.repsError);
  if (d.groupsError) Logger.log('groups ERROR: %s', d.groupsError);
}
