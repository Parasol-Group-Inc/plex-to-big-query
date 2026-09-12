/**
 * Vox — Manual Data entry (Apps Script web app)
 * ============================================
 *
 * One form for every number that has to be typed by a human rather than
 * extracted from Plex: goals, safety incidents, turnaround standards, part
 * costs. Anything else that turns up later is a registry entry, not a new app.
 *
 * This replaces the earlier goals-only app (`deploy/goals_web_app/`), which
 * covered one of the four and was never deployed.
 *
 * ── HOW IT FLOWS ───────────────────────────────────────────────────────────
 *
 *     web app  ──►  Google Sheet (one tab per dataset)  ──►  BigQuery table
 *                   the durable log                          the mirror
 *
 * The sheet is the middle man ON PURPOSE, and it is worth being clear about
 * why, because writing straight to BigQuery is the more obvious design:
 *
 *   - The sheet is the record of what people entered, readable and fixable
 *     without BigQuery access, and it survives a table being dropped or a
 *     dataset being swapped from test to production.
 *   - Nobody types INTO the sheet — the web app is the only writer. That is
 *     what keeps the "people break the sheets" problem away while still
 *     getting a human-readable log out of it.
 *   - The push is a LOAD job replacing the table, not a streaming insert, so
 *     a saved row is queryable immediately instead of sitting in a streaming
 *     buffer for a few seconds. That removes the one piece of user-visible
 *     weirdness the previous design had to document.
 *
 * Every tab is APPEND-ONLY: a save appends a row, an edit appends another, and
 * a retraction appends a tombstone (`is_deleted = TRUE`). Nothing is ever
 * overwritten, so two people editing the same key minutes apart cannot lose
 * each other's write and every change stays as history. The consuming views
 * take the newest row per key.
 *
 * ── DEPLOYING (this catches everyone once) ─────────────────────────────────
 * Saving the code does NOT update the live app — not even saving and running
 * it from the editor. You must Deploy > Manage deployments > edit > New
 * version, and doing so can change the web app URL.
 *
 * Deploy with: Execute as = Me, Who has access = Anyone within
 * Parasol Group Inc. The BigQuery writes then run as the deployer's account,
 * so people filling the form need no BigQuery permissions of their own.
 *
 * ── SETUP ─────────────────────────────────────────────────────────────────
 *  1. Services (+) > BigQuery API > Add.
 *  2. Project Settings > Script Properties:
 *       GCP_PROJECT   = voxdatalake
 *       BQ_DATASET    = PlexTest          (switch to PlexProd at go-live)
 *       SHEET_ID      = <the manual-data spreadsheet's id>
 *     Kept in properties rather than in the code so the same script can point
 *     at test or production without an edit that needs redeploying.
 *  3. Run `setupSheets()` once — it creates a tab per dataset with the right
 *     headers, and is safe to re-run (it never touches existing rows).
 *  4. Run `testReadsOnly()` — writes nothing, reports what it can see.
 */

// ── Registry ───────────────────────────────────────────────────────────────
//
// Adding a manual dataset means adding an entry here and running
// setupSheets(). It needs no new form code: the UI is generated from this.
//
// field types: 'month' (a date forced to the 1st), 'date', 'number', 'money',
//              'text', 'longtext', 'select'
//
// `optionsFrom` names an option set built in buildOptionSets_(). Options are
// READ FROM THE REPORTS wherever the value has to join back to one, because
// these joins are exact string matches: a goal whose scope doesn't match the
// report's spelling produces no error, just a NULL that reads as 0% forever.
// The live example is Plex spelling a work centre group `Encapsulating`
// where the scorecard tile says "Encapsulation".

var DATASETS = {

  goals: {
    label: 'Goals',
    blurb: 'Monthly targets — revenue, sales by rep, production by work centre group, and the company-wide figure for each. One entry can fill a run of months, so a year can be frontloaded in one go.',
    tab: 'goals',
    table: 'scorecard_goals_app',
    // Newest row per this combination wins; a tombstone retracts the key.
    key: ['metric', 'period_month', 'scope'],
    fields: [
      { name: 'metric', label: 'Goal type', type: 'select', required: true,
        optionsFrom: 'metrics' },
      { name: 'period_month', label: 'Month', type: 'month', required: true,
        help: 'Reports group by month, so this is always the 1st.' },
      { name: 'scope', label: 'Applies to', type: 'select', required: false,
        dependsOn: 'metric',
        optionsFromBy: { revenue: null, sales: 'salesReps', production: 'workcenterGroups' },
        help: 'Pick (company-wide) for the whole-team target, or a single rep / work centre group.' },
      { name: 'goal_value', label: 'Goal', type: 'money', required: true, min: 0 },
      { name: 'repeat_months', label: 'Apply to how many months?', type: 'number',
        required: false, min: 1, max: 24, defaultValue: 1,
        help: 'Goals are usually set at the start of the year and changed occasionally, so one entry can fill a run of months. Each month is written as its own row — editing one later does not disturb the others.' },
      { name: 'unit', label: 'Unit', type: 'derived' },   // set from the metric
      { name: 'note', label: 'Note', type: 'longtext', required: false, max: 500 }
    ],
    // repeat_months is an entry convenience, not a stored column.
    transient: ['repeat_months'],
    repeatField: 'repeat_months',
    repeatOver: 'period_month',
    // Shown live as someone types a rep goal: the running total against the
    // company-wide target. The two are allowed to differ — the team figure
    // sums actuals, not goals — so this reports the gap rather than blocking.
    liveCheck: 'repGoalSum'
  },

  incidents: {
    label: 'Safety incidents',
    blurb: 'One row per incident. "Days without an incident" is counted from these, so an empty log reads as a clean record — which is only true if it is being kept.',
    tab: 'incidents',
    table: 'safety_incidents',
    key: ['incident_date', 'area', 'incident_type'],
    fields: [
      { name: 'incident_date', label: 'Date of incident', type: 'date', required: true,
        noFuture: true },
      { name: 'area', label: 'Area', type: 'select', required: true,
        optionsFrom: 'workcenterGroups', allowOther: true,
        help: 'Work centre groups come from the production report; pick Other for anywhere else.' },
      { name: 'incident_type', label: 'Type', type: 'select', required: true,
        optionsFrom: 'incidentTypes' },
      { name: 'recordable', label: 'OSHA recordable?', type: 'select', required: true,
        optionsFrom: 'yesNo' },
      { name: 'days_lost', label: 'Days lost', type: 'number', required: false, min: 0 },
      { name: 'description', label: 'What happened', type: 'longtext', required: true, max: 1000 }
    ]
  },

  turnaround_standards: {
    label: 'Turnaround standards',
    blurb: 'The Performance and Bonus day counts per stock type. Nothing resembling these exists in Plex — today they live in the Weekly/Monthly TAT Analysis sheets, and this is where they move to.',
    tab: 'turnaround_standards',
    table: 'turnaround_standards',
    key: ['stock_type', 'effective_month'],
    fields: [
      { name: 'stock_type', label: 'Stock type', type: 'select', required: true,
        optionsFrom: 'stockTypes', allowOther: true },
      { name: 'effective_month', label: 'Effective from', type: 'month', required: true },
      { name: 'performance_days', label: 'Performance standard (days)', type: 'number',
        required: true, min: 0 },
      { name: 'bonus_days', label: 'Bonus standard (days)', type: 'number',
        required: true, min: 0 },
      { name: 'note', label: 'Note', type: 'longtext', required: false, max: 500 }
    ]
  },

  part_costs: {
    label: 'Part costs',
    blurb: 'A cost per part, keyed on the FULL Plex part number. A FALLBACK only — Plex costs parts itself via Part_v_Snapshot, which is simply unpopulated on this tenant. Use this if that stays empty.',
    tab: 'part_costs',
    table: 'part_cost_manual',
    key: ['part_no', 'effective_month'],
    fields: [
      { name: 'part_no', label: 'Part number', type: 'select', required: true,
        optionsFrom: 'partNumbers',
        help: 'Read from Plex, so it cannot be a near-miss like 12335 against 12335-01VOXNU-1.' },
      { name: 'effective_month', label: 'Effective from', type: 'month', required: true },
      { name: 'cost_ea', label: 'Cost each', type: 'money', required: true, min: 0 },
      { name: 'note', label: 'Note', type: 'longtext', required: false, max: 500 }
    ]
  }

};

// Columns appended to every dataset, so who-changed-what is never optional.
var COMMON_FIELDS = [
  { name: 'submitted_by', type: 'text' },
  { name: 'submitted_at', type: 'timestamp' },
  { name: 'is_deleted',   type: 'bool' }
];

var METRIC_UNITS = { revenue: 'USD', sales: 'USD', production: 'units' };

// Shown in the dropdowns; stored as a blank scope, which is what the reports
// emit for a company-wide figure.
var COMPANY_WIDE = '(company-wide)';

// ── Config plumbing ────────────────────────────────────────────────────────

function prop_(key) {
  var v = PropertiesService.getScriptProperties().getProperty(key);
  if (!v) throw new Error('Script property ' + key + ' is not set. Project Settings > Script Properties.');
  return v;
}
/**
 * Which required properties are not set yet. Returned to the form rather than
 * thrown, so a fresh deployment explains itself instead of showing a raw
 * ScriptError — this is the first thing everyone hits, and "Could not load:
 * ScriptError" gives no clue that the fix is two minutes in Project Settings.
 */
function missingProps_() {
  var props = PropertiesService.getScriptProperties();
  // BQ_DATA_PROJECT is deliberately not required — it defaults to GCP_PROJECT.
  return ['GCP_PROJECT', 'BQ_DATASET', 'SHEET_ID'].filter(function (k) {
    return !props.getProperty(k);
  });
}

/**
 * The project that RUNS and bills the BigQuery jobs — the Apps Script
 * project's own Cloud project (Project Settings > Google Cloud Platform).
 */
function project_() { return prop_('GCP_PROJECT'); }

/**
 * The project the TABLES live in. Separate from the one above on purpose:
 * the Apps Script project and the data lake are not the same Cloud project
 * here, and conflating them sends every query looking for a dataset in the
 * script's own project, where it does not exist.
 *
 * Falls back to the job project, so a single-project setup needs no extra
 * property.
 */
function dataProject_() {
  return PropertiesService.getScriptProperties().getProperty('BQ_DATA_PROJECT')
         || project_();
}

function dataset_() { return prop_('BQ_DATASET'); }
function sheet_()   { return SpreadsheetApp.openById(prop_('SHEET_ID')); }

function fqn_(table) {
  return '`' + dataProject_() + '.' + dataset_() + '.' + table + '`';
}

/**
 * The columns that reach the sheet and the table, in order. Transient fields
 * (entry conveniences like "apply to N months") are deliberately excluded —
 * they shape what gets written, they are not themselves data.
 */
function allFields_(ds) {
  var transient = ds.transient || [];
  var kept = ds.fields.filter(function (f) { return transient.indexOf(f.name) === -1; });
  return kept.filter(function (f) { return f.type !== 'derived'; })
    .concat(kept.filter(function (f) { return f.type === 'derived'; }))
    .concat(COMMON_FIELDS);
}

// ── Web app entry point ────────────────────────────────────────────────────

function doGet() {
  return HtmlService.createTemplateFromFile('Index')
    .evaluate()
    .setTitle('Vox — Manual Data')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function include(name) {
  return HtmlService.createHtmlOutputFromFile(name).getContent();
}

/**
 * The BigQuery advanced service is added through the editor, not through code,
 * so it is the other half of "why won't this load" on a new project.
 */
function hasBigQueryService_() {
  try { return typeof BigQuery !== 'undefined'; } catch (e) { return false; }
}

// ── Reads ──────────────────────────────────────────────────────────────────

/**
 * Apps Script's BigQuery service returns every value as a string regardless of
 * column type, so callers parse numbers where they need them.
 */
function query_(sql) {
  var job = BigQuery.Jobs.query({ query: sql, useLegacySql: false }, project_());
  return (job.rows || []).map(function (row) {
    return row.f.map(function (cell) { return cell.v; });
  });
}

function firstColumn_(sql) {
  return query_(sql).map(function (r) { return r[0]; });
}

/**
 * Every option list the forms need. Wrapped individually so one missing
 * report degrades that single dropdown rather than taking the whole app down
 * — the form then says so instead of silently offering nothing.
 */
function buildOptionSets_() {
  var sets = { errors: {} };

  sets.metrics = [
    { value: 'revenue',    label: 'Revenue (company-wide)' },
    { value: 'sales',      label: 'Sales (by rep)' },
    { value: 'production', label: 'Production (by work centre group)' }
  ];
  sets.yesNo = [
    { value: 'true',  label: 'Yes' },
    { value: 'false', label: 'No' }
  ];
  sets.incidentTypes = ['Injury', 'Near miss', 'Property damage', 'Spill / release', 'Other']
    .map(function (v) { return { value: v, label: v }; });
  sets.stockTypes = ['Capsules', 'Powder', 'Tablets', 'Softgels', 'Liquid', 'Gummies']
    .map(function (v) { return { value: v, label: v }; });

  function load(name, sql) {
    try {
      sets[name] = firstColumn_(sql).map(function (v) { return { value: v, label: v }; });
    } catch (e) {
      sets[name] = [];
      sets.errors[name] = String(e);
    }
  }

  load('salesReps',
    'SELECT DISTINCT sales_rep FROM ' + fqn_('sales_mtd_summary_report') +
    ' WHERE sales_rep IS NOT NULL ORDER BY sales_rep');

  load('workcenterGroups',
    'SELECT DISTINCT workcenter_group FROM ' +
    fqn_('production_monthly_by_workcenter_group_report') +
    ' WHERE workcenter_group IS NOT NULL ORDER BY workcenter_group');

  load('partNumbers',
    'SELECT DISTINCT Part_Number FROM ' + fqn_('part_v_part') +
    ' WHERE Part_Number IS NOT NULL ORDER BY Part_Number LIMIT 10000');

  // A company-wide target lives in the same table as the per-rep and
  // per-work-centre ones, so it is offered at the top of both lists rather
  // than needing its own form. Stored as a BLANK scope, which is what the
  // reports emit for it — see applyDatasetRules_.
  //
  // This matters for production in particular: a company-wide production goal
  // had no way in at all before, so the production tile could only ever be
  // compared against per-group targets that may not exist.
  ['salesReps', 'workcenterGroups'].forEach(function (name) {
    sets[name] = [{ value: COMPANY_WIDE, label: COMPANY_WIDE }].concat(sets[name] || []);
  });

  return sets;
}

/**
 * Everything the UI needs to render every form, in ONE call — the registry,
 * the option sets, and what has been entered so far.
 */
function getFormData() {
  // A fresh Apps Script project has no properties set. Report that as a state
  // the form can render, not as an exception.
  var missing = missingProps_();
  if (missing.length) {
    return { setupNeeded: true, missing: missing, bigQueryReady: hasBigQueryService_() };
  }

  var sets = buildOptionSets_();

  var datasets = {};
  Object.keys(DATASETS).forEach(function (k) {
    var ds = DATASETS[k];
    datasets[k] = {
      key: k,
      label: ds.label,
      blurb: ds.blurb,
      liveCheck: ds.liveCheck || null,
      fields: ds.fields.filter(function (f) { return f.type !== 'derived'; })
    };
  });

  return {
    project: project_(),
    dataProject: dataProject_(),
    dataset: dataset_(),
    datasets: datasets,
    options: sets,
    optionErrors: sets.errors,
    recent: recentRows_()
  };
}

/**
 * The last few entries per dataset, read from the SHEET rather than BigQuery,
 * so the form shows a save immediately and still shows it if the push is
 * lagging or failed. Row numbers travel with them — that is what a retraction
 * refers back to.
 */
function recentRows_(limitPerSet) {
  var limit = limitPerSet || 15;
  var ss = sheet_();
  var out = {};

  Object.keys(DATASETS).forEach(function (k) {
    var ds = DATASETS[k];
    var tab = ss.getSheetByName(ds.tab);
    if (!tab) { out[k] = []; return; }

    var last = tab.getLastRow();
    if (last < 2) { out[k] = []; return; }

    var headers = tab.getRange(1, 1, 1, tab.getLastColumn()).getValues()[0];
    var start = Math.max(2, last - limit + 1);
    var values = tab.getRange(start, 1, last - start + 1, headers.length)
                    .getDisplayValues();

    out[k] = values.map(function (row, i) {
      var obj = { _row: start + i };
      headers.forEach(function (h, c) { if (h) obj[h] = row[c]; });
      return obj;
    }).reverse();
  });

  return out;
}

/**
 * The running total behind a rep goal: all rep goals for that month against
 * the company-wide target, so drift is visible AT ENTRY TIME rather than
 * discovered in a report later. The two are deliberately allowed to differ,
 * because the team figure sums actuals rather than goals — turnover makes
 * them disagree by design. This reports the gap; it does not block on it.
 */
function getRepGoalSum(periodMonth) {
  var month = normalizeMonth_(periodMonth);
  var sql =
    'SELECT ' +
    '  SUM(IF(scope IS NOT NULL AND scope != "", goal_value, 0)) AS rep_total, ' +
    '  SUM(IF(scope IS NULL OR scope = "", goal_value, 0)) AS company_total, ' +
    '  COUNTIF(scope IS NOT NULL AND scope != "") AS rep_count ' +
    'FROM ' + fqn_('v2_scorecard_goals_resolved') + ' ' +
    'WHERE LOWER(metric) = "sales" AND period_month = DATE("' + month + '")';
  try {
    var rows = query_(sql);
    if (!rows.length) return { repTotal: 0, companyTotal: 0, repCount: 0 };
    return {
      repTotal: Number(rows[0][0] || 0),
      companyTotal: Number(rows[0][1] || 0),
      repCount: Number(rows[0][2] || 0)
    };
  } catch (e) {
    // A missing resolver view must not stop someone entering a goal.
    return { repTotal: 0, companyTotal: 0, repCount: 0, error: String(e) };
  }
}

// ── Validation ─────────────────────────────────────────────────────────────

function normalizeDate_(s) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(s || ''))) {
    throw new Error('Date must look like YYYY-MM-DD, got: ' + s);
  }
  return s;
}

function normalizeMonth_(s) {
  var d = normalizeDate_(s);
  // Reports group by month; a goal dated mid-month would silently form its own
  // bucket and never match. Snap rather than reject — the UI only offers a
  // month, so a stray day is a caller error, not a user one.
  return d.slice(0, 8) + '01';
}

function validateField_(f, raw) {
  var v = (raw == null ? '' : String(raw)).trim();

  if (!v) {
    if (f.required) throw new Error(f.label + ' is required.');
    return '';
  }

  switch (f.type) {
    case 'month':
      return normalizeMonth_(v);
    case 'date':
      v = normalizeDate_(v);
      if (f.noFuture && v > todayStr_()) {
        throw new Error(f.label + ' cannot be in the future.');
      }
      return v;
    case 'number':
    case 'money': {
      var n = Number(v.replace(/[$,]/g, ''));
      if (!isFinite(n)) throw new Error(f.label + ' must be a number, got: ' + raw);
      if (f.min != null && n < f.min) throw new Error(f.label + ' cannot be below ' + f.min + '.');
      return n;
    }
    case 'longtext':
      return v.slice(0, f.max || 1000);
    default:
      return v;
  }
}

// ── Writes ─────────────────────────────────────────────────────────────────

/**
 * Save one row. Validates against the registry, appends to the sheet, then
 * pushes that tab to BigQuery.
 *
 * The push is attempted inline so a saved value is queryable straight away.
 * If it fails, the SAVE STILL STANDS — the sheet is the record of truth and
 * the hourly trigger will carry it across. The caller is told which happened
 * rather than being shown a success that only half happened.
 */
function saveRow(datasetKey, form) {
  var ds = DATASETS[datasetKey];
  if (!ds) throw new Error('Unknown dataset: ' + datasetKey);

  var values = {};
  ds.fields.forEach(function (f) {
    if (f.type === 'derived') return;
    values[f.name] = validateField_(f, form[f.name]);
  });

  applyDatasetRules_(datasetKey, values);

  values.submitted_by = activeUser_();
  values.submitted_at = nowIso_();
  values.is_deleted = false;

  // Frontloading: one entry can fill a run of consecutive months. Goals are
  // typically set once at the start of a year and changed occasionally, so
  // entering twelve of them one at a time is the common case, not the rare
  // one. Each month is written as its OWN row rather than as a range, so a
  // later edit to one month leaves the rest alone.
  var months = repeatMonths_(ds, values, form);
  months.forEach(function (m) {
    var row = shallowCopy_(values);
    if (ds.repeatOver) row[ds.repeatOver] = m;
    appendToSheet_(ds, row);
  });

  var push = tryPush_(datasetKey);

  return {
    ok: true,
    pushed: push.ok,
    count: months.length,
    message: describe_(datasetKey, values) +
             (months.length > 1 ? ' — and ' + (months.length - 1) + ' further month' +
                                  (months.length > 2 ? 's' : '') +
                                  ', through ' + months[months.length - 1].slice(0, 7) : ''),
    pushMessage: push.message
  };
}

/**
 * The months one save should write. Always at least the month entered.
 * Capped by the field's own max so a typo cannot write years of rows.
 */
function repeatMonths_(ds, values, form) {
  var start = ds.repeatOver ? values[ds.repeatOver] : null;
  if (!ds.repeatField || !start) return [start];

  var field = ds.fields.filter(function (f) { return f.name === ds.repeatField; })[0] || {};
  var n = Math.floor(Number(form[ds.repeatField] || 1));
  if (!isFinite(n) || n < 1) n = 1;
  if (field.max && n > field.max) n = field.max;

  var out = [];
  for (var i = 0; i < n; i++) out.push(addMonths_(start, i));
  return out;
}

function addMonths_(monthStr, n) {
  var y = Number(monthStr.slice(0, 4));
  var m = Number(monthStr.slice(5, 7)) - 1 + n;
  var d = new Date(Date.UTC(y, m, 1));
  return Utilities.formatDate(d, 'UTC', 'yyyy-MM-dd');
}

function shallowCopy_(o) {
  var c = {};
  Object.keys(o).forEach(function (k) { c[k] = o[k]; });
  return c;
}

/**
 * Retract an entry. Appends a tombstone rather than deleting the row, so the
 * audit trail survives.
 *
 * For goals this matters twice over: the resolver reads a tombstone as "the
 * app has nothing to say about this key", which puts the SPREADSHEET-sourced
 * goal back rather than blanking the tile — the only sensible reading while
 * both goal sources are live.
 */
function retractRow(datasetKey, keyValues) {
  var ds = DATASETS[datasetKey];
  if (!ds) throw new Error('Unknown dataset: ' + datasetKey);

  var values = {};
  var transient = ds.transient || [];
  ds.fields.forEach(function (f) {
    if (f.type === 'derived' || transient.indexOf(f.name) !== -1) return;
    var isKey = ds.key.indexOf(f.name) !== -1;
    values[f.name] = isKey ? validateField_(f, keyValues[f.name])
                           : (f.type === 'number' || f.type === 'money' ? 0 : '');
  });

  applyDatasetRules_(datasetKey, values);

  values.note = 'retracted via web app';
  values.submitted_by = activeUser_();
  values.submitted_at = nowIso_();
  values.is_deleted = true;

  appendToSheet_(ds, values);
  var push = tryPush_(datasetKey);

  return {
    ok: true,
    pushed: push.ok,
    message: 'Retracted ' + ds.key.map(function (k) { return values[k]; }).join(' · '),
    pushMessage: push.message
  };
}

/** Rules that belong to one dataset rather than to a field. */
function applyDatasetRules_(datasetKey, values) {
  if (datasetKey === 'goals') {
    var metric = String(values.metric || '').toLowerCase();
    if (!METRIC_UNITS[metric]) throw new Error('Unknown goal type: ' + values.metric);
    values.metric = metric;
    values.unit = METRIC_UNITS[metric];

    if (metric === 'revenue') {
      values.scope = '';                       // company-wide by definition
    } else if (values.scope === '(company-wide)') {
      values.scope = '';                       // what the reports emit
    } else if (!values.scope) {
      throw new Error(metric === 'sales' ? 'Pick a sales rep.' : 'Pick a work centre group.');
    }
  }

  if (datasetKey === 'incidents') {
    values.recordable = String(values.recordable) === 'true';
  }
}

function appendToSheet_(ds, values) {
  var ss = sheet_();
  var tab = ss.getSheetByName(ds.tab) || createTab_(ss, ds);
  var headers = tab.getRange(1, 1, 1, tab.getLastColumn()).getValues()[0];
  tab.appendRow(headers.map(function (h) {
    var v = values[h];
    return v === undefined || v === null ? '' : v;
  }));
}

function activeUser_() {
  // Empty for a viewer outside the domain; never let that become a blank that
  // hides who changed a target.
  return Session.getActiveUser().getEmail() || 'unknown';
}

function nowIso_() {
  return Utilities.formatDate(new Date(), 'UTC', "yyyy-MM-dd'T'HH:mm:ss'Z'");
}

function todayStr_() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
}

function describe_(datasetKey, v) {
  if (datasetKey === 'goals') {
    var who = v.scope || 'company-wide';
    var amount = (v.unit === 'USD' ? '$' : '') + Number(v.goal_value).toLocaleString() +
                 (v.unit === 'units' ? ' units' : '');
    return 'Saved: ' + DATASETS.goals.label + ' — ' + v.metric + ' — ' + who +
           ' — ' + String(v.period_month).slice(0, 7) + ' — ' + amount;
  }
  if (datasetKey === 'incidents') {
    return 'Logged: ' + v.incident_type + ' in ' + v.area + ' on ' + v.incident_date;
  }
  return 'Saved to ' + DATASETS[datasetKey].label + '.';
}

// ── Sheet setup ────────────────────────────────────────────────────────────

function createTab_(ss, ds) {
  var tab = ss.insertSheet(ds.tab);
  var headers = allFields_(ds).map(function (f) { return f.name; });
  tab.getRange(1, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
  tab.setFrozenRows(1);
  // The sheet is a log the app writes, not a form people fill in. Saying so
  // on the sheet itself is the cheapest way to keep it that way.
  tab.getRange(1, headers.length + 2).setValue(
    'Written by the Manual Data web app. Do not edit by hand — edits here are ' +
    'overwritten and are not pushed to BigQuery.');
  return tab;
}

/** Safe to re-run: creates missing tabs and never touches existing rows. */
function setupSheets() {
  var ss = sheet_();
  Object.keys(DATASETS).forEach(function (k) {
    var ds = DATASETS[k];
    if (!ss.getSheetByName(ds.tab)) {
      createTab_(ss, ds);
      Logger.log('Created tab: %s', ds.tab);
    } else {
      Logger.log('Tab already present: %s', ds.tab);
    }
  });
}

// ── Local sanity check (run from the editor, writes nothing) ───────────────

function testReadsOnly() {
  var d = getFormData();
  if (d.setupNeeded) {
    Logger.log('NOT CONFIGURED — missing script properties: %s', d.missing.join(', '));
    return;
  }
  Logger.log('jobs run in: %s', d.project);
  Logger.log('tables read from: %s.%s', d.dataProject, d.dataset);
  Object.keys(d.datasets).forEach(function (k) {
    Logger.log('%s — %s rows in the sheet', k, (d.recent[k] || []).length);
  });
  Logger.log('sales reps: %s', (d.options.salesReps || []).length);
  Logger.log('work centre groups: %s', (d.options.workcenterGroups || []).length);
  Logger.log('part numbers: %s', (d.options.partNumbers || []).length);
  Object.keys(d.optionErrors || {}).forEach(function (k) {
    Logger.log('OPTION ERROR %s: %s', k, d.optionErrors[k]);
  });
}
