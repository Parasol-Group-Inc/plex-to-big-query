/**
 * Vox Goals (Apps Script web app)  ·  v2, database-direct
 * ================================================================
 * People pick what they want to change, see the value currently in BigQuery,
 * edit it, and save. Saves write straight to BigQuery. No Google Sheet.
 *
 * HISTORY IS KEPT: a save INSERTs a new row; nothing is updated or deleted.
 * Every table is "newest row per key wins", and a removal is a row with
 * is_deleted = TRUE. The scorecard views already read the tables this way.
 *
 * ACCESS: PlexProd.manual_data_access lists who may edit each area
 * (sales_goals, production_goals, revenue_goals, safety, part_usage,
 * msl_rules) and who is an admin. Admins manage the list on the
 * "User access" tab. Every save checks access on the server, not just in the page.
 *
 * DEPLOY: Execute as = Me. Who has access = Anyone within Parasol Group Inc.
 * (Same-domain deployment is what lets the script see who is using it.)
 * Saving code does not update the live app: Deploy > Manage deployments >
 * edit > New version.
 *
 * SETUP: Services (+) > BigQuery API. Script Properties:
 *   GCP_PROJECT     = Cloud project that runs/bills the jobs
 *   BQ_DATA_PROJECT = voxdatalake   (optional, defaults to GCP_PROJECT)
 *   BQ_DATASET      = PlexProd
 */

// ── Areas ──────────────────────────────────────────────────────────────────

var AREAS = {
  sales_goals:      { label: 'Sales goals',      kind: 'goals', metric: 'sales',      unit: 'USD' },
  production_goals: { label: 'Production goals', kind: 'goals', metric: 'production', unit: 'units' },
  revenue_goals:    { label: 'Revenue goals',    kind: 'goals', metric: 'revenue',    unit: 'USD' },
  safety:           { label: 'Safety incidents', kind: 'safety' },
  part_usage:       { label: 'Part usage',       kind: 'part_usage' },
  msl_rules:        { label: 'MSL rules',        kind: 'msl_rules' },
  admin:            { label: 'User access',      kind: 'admin' }
};

var TABLES = {
  goals:   'scorecard_goals_app',
  safety:  'safety_incidents',
  usage:   'msl_item_inputs',
  rules:   'msl_rules',
  access:  'manual_data_access'
};

var COMPANY_WIDE = '(company-wide)';

// Last OSHA-recordable incident before the safety log existed. Matches
// VoxScorecardsLive.vw_sc_safe_days (105 safe days on 2026-11-05).
var SAFETY_BASELINE = '2026-07-23';

// Defaults must match the cfg CTE in approaching_msl_report.
var MSL_RULES = {
  usage_min_days: { def: '183', label: 'Days of Plex history needed',
    help: 'Until Plex has this many days of production, the report uses the usage entered on the Part usage tab where there is one; after that, Plex\'s own average over the same number of days. 183 is about 6 months (Jennilyn, 2026-11-10).' },
  disagree_pct:   { def: '25', label: 'Flag when usage differs by (%)',
    help: 'Flags a part when Plex usage and the usage entered on the Part usage tab differ by more than this.' },
  stale_days:     { def: '45', label: 'Entered usage stale after (days)',
    help: 'Flags usage figures dated older than this.' }
};

var INCIDENT_TYPES = ['Injury', 'Near miss', 'Property damage', 'Spill / release', 'Other'];
var USAGE_UPLOAD_MAX = 2000;

// ── Config / BigQuery plumbing ─────────────────────────────────────────────

function prop_(k) {
  var v = PropertiesService.getScriptProperties().getProperty(k);
  if (!v) throw new Error('Script property ' + k + ' is not set (Project Settings > Script Properties).');
  return v;
}
function project_()     { return prop_('GCP_PROJECT'); }
function dataProject_() { return PropertiesService.getScriptProperties().getProperty('BQ_DATA_PROJECT') || project_(); }
function dataset_()     { return prop_('BQ_DATASET'); }
function t_(name)       { return '`' + dataProject_() + '.' + dataset_() + '.' + name + '`'; }

/** STRING query parameter. Everything is passed as text and cast in SQL. */
function P(name, value) {
  return { name: name, parameterType: { type: 'STRING' },
           parameterValue: { value: value == null ? '' : String(value) } };
}

/**
 * Runs SQL with named parameters and returns rows as objects keyed by column
 * name (values are strings, or null). Waits for slow jobs and reads all pages.
 */
function q_(sql, params) {
  var res = BigQuery.Jobs.query({
    query: sql, useLegacySql: false, parameterMode: 'NAMED',
    queryParameters: params || [], timeoutMs: 30000
  }, project_());
  var ref = res.jobReference;
  while (!res.jobComplete) {
    Utilities.sleep(500);
    res = BigQuery.Jobs.getQueryResults(project_(), ref.jobId, { location: ref.location });
  }
  var fields = ((res.schema || {}).fields || []).map(function (f) { return f.name; });
  var rows = res.rows || [];
  var token = res.pageToken;
  while (token) {
    var more = BigQuery.Jobs.getQueryResults(project_(), ref.jobId, { location: ref.location, pageToken: token });
    rows = rows.concat(more.rows || []);
    token = more.pageToken;
  }
  return rows.map(function (r) {
    var o = {};
    r.f.forEach(function (c, i) { o[fields[i]] = c.v; });
    return o;
  });
}

// ── Who is using the app, and what may they touch ──────────────────────────

function me_() {
  var e = String(Session.getActiveUser().getEmail() || '').trim().toLowerCase();
  if (!e) throw new Error('Could not tell who you are. Open the app while signed in to your Parasol Group or Vox Nutrition account.');
  return e;
}

var ACCESS_SQL_ =
  'SELECT user_email, area FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY LOWER(user_email), area ' +
  'ORDER BY updated_at DESC) rn FROM {T}) WHERE rn = 1 AND NOT IFNULL(is_deleted, FALSE)';

function areasFor_(email) {
  return q_(ACCESS_SQL_.replace('{T}', t_(TABLES.access)) + ' AND LOWER(user_email) = @me', [P('me', email)])
    .map(function (r) { return r.area; });
}

/** Throws unless the current user may edit `area`. Admins may edit everything. */
function require_(area) {
  var email = me_();
  var mine = areasFor_(email);
  if (mine.indexOf('admin') === -1 && mine.indexOf(area) === -1) {
    throw new Error('You do not have access to ' + (AREAS[area] ? AREAS[area].label : area) + '. Ask an admin to add you.');
  }
  return email;
}

// ── Web app ────────────────────────────────────────────────────────────────

function doGet() {
  return HtmlService.createTemplateFromFile('Index').evaluate()
    .setTitle('Vox Goals')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** Everything the page needs to start: who you are, which tabs you get, dropdown lists. */
function getBoot() {
  var email = me_();
  var mine = areasFor_(email);
  var isAdmin = mine.indexOf('admin') !== -1;
  var allowed = Object.keys(AREAS).filter(function (a) {
    return a === 'admin' ? isAdmin : (isAdmin || mine.indexOf(a) !== -1);
  });
  var areas = {};
  allowed.forEach(function (a) { areas[a] = { key: a, label: AREAS[a].label, kind: AREAS[a].kind, unit: AREAS[a].unit || '' }; });
  return {
    me: email, isAdmin: isAdmin, dataset: dataset_(), areas: areas, order: allowed,
    incidentTypes: INCIDENT_TYPES,
    workcenterGroups: safeList_('SELECT DISTINCT workcenter_group v FROM ' + t_('production_monthly_by_workcenter_group_report') +
                                ' WHERE workcenter_group IS NOT NULL ORDER BY 1'),
    year: Number(Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy'))
  };
}

function safeList_(sql) {
  try { return q_(sql).map(function (r) { return r.v; }); } catch (e) { return []; }
}

// ── Goals (sales / production / revenue) ───────────────────────────────────

/** Who/what a goal can apply to, per area. */
function goalScopes_(area) {
  var a = AREAS[area];
  if (a.metric === 'revenue') return [COMPANY_WIDE];
  if (a.metric === 'sales') {
    return [COMPANY_WIDE].concat(safeList_(
      'SELECT DISTINCT sales_rep v FROM ' + t_('sales_reps_report') + ' WHERE sales_rep IS NOT NULL ORDER BY 1'));
  }
  return [COMPANY_WIDE].concat(safeList_(
    'SELECT DISTINCT workcenter_group v FROM ' + t_('production_monthly_by_workcenter_group_report') +
    ' WHERE workcenter_group IS NOT NULL ORDER BY 1'));
}

/**
 * The goal grid for one area and year: one row per scope, one column per month,
 * each cell the goal in effect now (newest entry wins, from either goal source).
 */
function getGoals(area, year) {
  require_(area);
  var a = AREAS[area];
  if (!a || a.kind !== 'goals') throw new Error('Not a goal area: ' + area);
  year = Number(year);

  var rows = q_(
    'SELECT IFNULL(scope, "") scope, EXTRACT(MONTH FROM period_month) m, CAST(goal_value AS STRING) v, ' +
    '  updated_by, FORMAT_TIMESTAMP("%Y-%m-%d %H:%M", updated_at, "America/Denver") ts ' +
    'FROM ' + t_('scorecard_goals_resolved') + ' ' +
    'WHERE LOWER(metric) = @metric AND EXTRACT(YEAR FROM period_month) = CAST(@y AS INT64)',
    [P('metric', a.metric), P('y', year)]);

  var scopes = goalScopes_(area);
  var grid = {};
  scopes.forEach(function (s) { grid[s] = {}; });
  rows.forEach(function (r) {
    var s = r.scope === '' ? COMPANY_WIDE : r.scope;
    if (!grid[s]) { grid[s] = {}; scopes.push(s); }   // a scope with a goal but no longer in the list
    grid[s][Number(r.m)] = { value: Number(r.v), by: r.updated_by || '', at: r.ts || '' };
  });
  return { area: area, year: year, unit: a.unit, scopes: scopes, grid: grid };
}

/**
 * Save edited goal cells. changes: [{ scope, month (1-12), value }] where an
 * empty value means "remove this goal". One INSERT for the whole batch.
 */
function saveGoals(area, year, changes, note) {
  var email = require_(area);
  var a = AREAS[area];
  year = Number(year);
  if (!changes || !changes.length) return { ok: true, count: 0, message: 'Nothing changed.' };
  if (changes.length > 400) throw new Error('Too many changes in one save (max 400).');

  var validScopes = goalScopes_(area);
  var current = getGoals(area, year).grid;
  var params = [P('metric', a.metric), P('unit', a.unit), P('by', email), P('note', String(note || '').slice(0, 500))];
  var values = [];

  changes.forEach(function (c, i) {
    var scope = String(c.scope || '');
    var m = Number(c.month);
    if (!(m >= 1 && m <= 12)) throw new Error('Bad month: ' + c.month);
    if (validScopes.indexOf(scope) === -1 && !current[scope]) throw new Error('Unknown ' + (a.metric === 'sales' ? 'rep' : 'group') + ': ' + scope);
    var raw = String(c.value == null ? '' : c.value).replace(/[$,\s]/g, '');
    var remove = raw === '';
    if (!remove && !(isFinite(Number(raw)) && Number(raw) >= 0)) throw new Error('Goal must be a number of zero or more: ' + c.value);

    var month = year + '-' + ('0' + m).slice(-2) + '-01';
    params.push(P('s' + i, scope === COMPANY_WIDE ? '' : scope), P('m' + i, month), P('v' + i, remove ? '0' : raw),
                P('d' + i, remove ? 'true' : 'false'));
    values.push('(@metric, DATE(@m' + i + '), @s' + i + ', CAST(@v' + i + ' AS NUMERIC), NULLIF(@note, ""), @unit, @by, ' +
                'CURRENT_TIMESTAMP(), CAST(@d' + i + ' AS BOOL))');
  });

  q_('INSERT INTO ' + t_(TABLES.goals) +
     ' (metric, period_month, scope, goal_value, note, unit, updated_by, updated_at, is_deleted) VALUES ' +
     values.join(', '), params);
  return { ok: true, count: changes.length, message: 'Saved ' + changes.length + ' goal change' + (changes.length > 1 ? 's' : '') + '.' };
}

/** Last 25 goal edits for an area. */
function getGoalHistory(area) {
  require_(area);
  return q_(
    'SELECT FORMAT_DATE("%Y-%m", period_month) month, IFNULL(NULLIF(scope, ""), "' + COMPANY_WIDE + '") scope, ' +
    '  CAST(goal_value AS STRING) value, IFNULL(is_deleted, FALSE) removed, note, updated_by, ' +
    '  FORMAT_TIMESTAMP("%Y-%m-%d %H:%M", updated_at, "America/Denver") ts ' +
    'FROM ' + t_(TABLES.goals) + ' WHERE LOWER(metric) = @metric ORDER BY updated_at DESC LIMIT 25',
    [P('metric', AREAS[area].metric)]);
}

// ── Safety ─────────────────────────────────────────────────────────────────

var LIVE_INCIDENTS_ =
  'WITH live AS (SELECT * EXCEPT(rn) FROM (SELECT *, ROW_NUMBER() OVER (' +
  ' PARTITION BY incident_date, LOWER(TRIM(area)), LOWER(TRIM(incident_type)) ORDER BY updated_at DESC) rn ' +
  ' FROM {T}) WHERE rn = 1 AND NOT IFNULL(is_deleted, FALSE)) ';

function getSafety() {
  require_('safety');
  var incidents = q_(LIVE_INCIDENTS_.replace('{T}', t_(TABLES.safety)) +
    'SELECT CAST(incident_date AS STRING) incident_date, area, incident_type, recordable, ' +
    '  CAST(days_lost AS STRING) days_lost, description, updated_by ' +
    'FROM live ORDER BY incident_date DESC LIMIT 100');
  var lastRec = SAFETY_BASELINE;
  incidents.forEach(function (r) {
    if (String(r.recordable).toLowerCase() === 'true' && r.incident_date > lastRec) lastRec = r.incident_date;
  });
  var today = Utilities.formatDate(new Date(), 'America/Denver', 'yyyy-MM-dd');
  var safeDays = Math.round((Date.parse(today) - Date.parse(lastRec)) / 86400000);
  return { incidents: incidents, lastRecordable: lastRec, safeDays: safeDays, baseline: SAFETY_BASELINE };
}

function addIncident(f) {
  var email = require_('safety');
  var date = isoDate_(f.incident_date, 'Date of incident');
  if (date > Utilities.formatDate(new Date(), 'America/Denver', 'yyyy-MM-dd')) throw new Error('Date of incident cannot be in the future.');
  if (!String(f.area || '').trim()) throw new Error('Area is required.');
  if (INCIDENT_TYPES.indexOf(f.incident_type) === -1) throw new Error('Pick an incident type.');
  if (!String(f.description || '').trim()) throw new Error('Describe what happened.');
  var days = String(f.days_lost || '').trim();
  if (days && !(isFinite(Number(days)) && Number(days) >= 0)) throw new Error('Days lost must be a number.');

  q_('INSERT INTO ' + t_(TABLES.safety) +
     ' (incident_date, area, incident_type, recordable, days_lost, description, updated_by, updated_at, is_deleted) ' +
     'VALUES (DATE(@d), @a, @t, @r, SAFE_CAST(NULLIF(@dl, "") AS FLOAT64), @desc, @by, CURRENT_TIMESTAMP(), FALSE)',
     [P('d', date), P('a', String(f.area).trim()), P('t', f.incident_type),
      P('r', String(f.recordable) === 'true' ? 'true' : 'false'), P('dl', days),
      P('desc', String(f.description).trim().slice(0, 1000)), P('by', email)]);
  return { ok: true, message: 'Logged: ' + f.incident_type + ' in ' + f.area + ' on ' + date + '.' };
}

function retractIncident(k) {
  var email = require_('safety');
  q_('INSERT INTO ' + t_(TABLES.safety) +
     ' (incident_date, area, incident_type, recordable, days_lost, description, updated_by, updated_at, is_deleted) ' +
     'VALUES (DATE(@d), @a, @t, NULL, NULL, "retracted via web app", @by, CURRENT_TIMESTAMP(), TRUE)',
     [P('d', isoDate_(k.incident_date, 'Date')), P('a', k.area), P('t', k.incident_type), P('by', email)]);
  return { ok: true, message: 'Removed the ' + k.incident_type + ' on ' + k.incident_date + '.' };
}

// ── Part usage ─────────────────────────────────────────────────────────────
// Average daily usage per part (PlexProd.msl_item_inputs, a table we built and
// fill by hand). The minimum inventory quantity (MSL / reorder point) lives in
// Plex and is NOT edited here. Whatever usage is entered here is the usage the
// Approaching MSL report uses for that part, ahead of Plex's own figure.

var LIVE_USAGE_ =
  'WITH live AS (SELECT * EXCEPT(rn) FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY ns_item_id ORDER BY updated_at DESC) rn ' +
  ' FROM {T}) WHERE rn = 1 AND NOT IFNULL(is_deleted, FALSE)) ';

/** Find parts by Plex part number, NetSuite id or description, including Plex parts with no usage yet. */
function searchUsage(text) {
  require_('part_usage');
  var s = String(text || '').trim();
  if (s.length < 2) return [];
  return q_(LIVE_USAGE_.replace('{T}', t_(TABLES.usage)) +
    'SELECT ns_item_id, part_no, description, CAST(ns_avg_daily_usage AS STRING) usage, ' +
    '  CAST(as_of_date AS STRING) as_of_date, note, updated_by, ' +
    '  FORMAT_TIMESTAMP("%Y-%m-%d", updated_at, "America/Denver") updated ' +
    'FROM live WHERE CONTAINS_SUBSTR(CONCAT(IFNULL(part_no,""), " ", IFNULL(ns_item_id,""), " ", IFNULL(description,"")), @s) ' +
    'UNION ALL ' +
    'SELECT NULL, Part_No, Name, NULL, NULL, NULL, NULL, NULL FROM ' + t_('raw_Part_v_Part') + ' p ' +
    'WHERE CONTAINS_SUBSTR(CONCAT(IFNULL(Part_No,""), " ", IFNULL(Name,"")), @s) ' +
    '  AND NOT EXISTS (SELECT 1 FROM live WHERE live.part_no = p.Part_No) ' +
    'ORDER BY 2 LIMIT 50', [P('s', s)]);
}

function plexPartExists_(partNo) {
  return q_('SELECT 1 x FROM ' + t_('raw_Part_v_Part') + ' WHERE Part_No = @p LIMIT 1', [P('p', partNo)]).length > 0;
}

function usageRow_(f) {
  var partNo = String(f.part_no || '').trim();
  var nsId = String(f.ns_item_id || '').trim();
  if (!partNo && !nsId) throw new Error('Give a Plex part number or a NetSuite item.');
  if (!nsId) nsId = 'PLEX:' + partNo;      // Plex-only part: the part number is its id
  var usage = String(f.usage == null ? '' : f.usage).replace(/,/g, '').trim();
  if (usage === '') throw new Error('Enter an average daily usage (' + (partNo || nsId) + ').');
  if (!(isFinite(Number(usage)) && Number(usage) >= 0)) throw new Error('Usage must be a number of zero or more (' + (partNo || nsId) + ').');
  var asOf = f.as_of_date ? isoDate_(f.as_of_date, 'As of')
                          : Utilities.formatDate(new Date(), 'America/Denver', 'yyyy-MM-dd');
  return {
    ns_item_id: nsId, part_no: partNo, description: String(f.description || '').trim(), usage: usage,
    as_of_date: asOf, mapping_status: partNo ? 'confirmed' : 'needs part number', note: String(f.note || '').slice(0, 500)
  };
}

/** Save one part's usage. Replaces the usage in effect for that part (the old one stays in history). */
function saveUsage(f) {
  var email = require_('part_usage');
  var r = usageRow_(f);
  if (r.part_no && !plexPartExists_(r.part_no)) throw new Error('Part ' + r.part_no + ' is not in Plex (exact match needed).');
  // ns_reorder_point is carried forward from the part's previous row so the
  // reference column is not blanked by an edit made here.
  q_('INSERT INTO ' + t_(TABLES.usage) +
     ' (ns_item_id, part_no, description, ns_avg_daily_usage, ns_reorder_point, as_of_date, mapping_status, note, updated_by, updated_at, is_deleted) ' +
     'SELECT @id, NULLIF(@p, ""), NULLIF(@desc, ""), CAST(@u AS FLOAT64), ' +
     '  (SELECT ns_reorder_point FROM ' + t_(TABLES.usage) + ' WHERE ns_item_id = @id AND NOT IFNULL(is_deleted, FALSE) ORDER BY updated_at DESC LIMIT 1), ' +
     '  DATE(@asof), @ms, NULLIF(@note, ""), @by, CURRENT_TIMESTAMP(), FALSE',
     [P('id', r.ns_item_id), P('p', r.part_no), P('desc', r.description), P('u', r.usage),
      P('asof', r.as_of_date), P('ms', r.mapping_status), P('note', r.note), P('by', email)]);
  return { ok: true, message: 'Saved: ' + (r.part_no || r.ns_item_id) + ' now uses ' + Number(r.usage).toLocaleString() + ' per day.' };
}

function removeUsage(nsItemId) {
  var email = require_('part_usage');
  q_('INSERT INTO ' + t_(TABLES.usage) + ' (ns_item_id, note, updated_by, updated_at, is_deleted) ' +
     'VALUES (@id, "removed via web app", @by, CURRENT_TIMESTAMP(), TRUE)', [P('id', nsItemId), P('by', email)]);
  return { ok: true, message: 'Removed the usage for ' + nsItemId + '. The report falls back to Plex usage for it.' };
}

/**
 * CSV upload. Columns (header names): part_no, ns_item_id, description, usage,
 * as_of_date, note. part_no or ns_item_id plus usage are required. Every row is
 * checked first; if any fail, nothing is saved.
 */
function uploadUsage(csvText) {
  var email = require_('part_usage');
  var table = Utilities.parseCsv(String(csvText || '').replace(/^﻿/, ''));
  if (table.length < 2) throw new Error('The file has no data rows.');
  var h = table[0].map(function (x) { return String(x).trim().toLowerCase(); });
  if (h.indexOf('part_no') === -1 && h.indexOf('ns_item_id') === -1) throw new Error('Need a part_no or ns_item_id column.');
  if (h.indexOf('usage') === -1) throw new Error('Need a usage column.');
  var body = table.slice(1).filter(function (r) { return r.join('').trim() !== ''; });
  if (body.length > USAGE_UPLOAD_MAX) throw new Error('At most ' + USAGE_UPLOAD_MAX + ' rows per upload.');

  var errors = [], rows = [], seen = {};
  body.forEach(function (r, i) {
    var o = {};
    h.forEach(function (name, c) { o[name] = r[c]; });
    try {
      var row = usageRow_(o);
      if (seen[row.ns_item_id]) throw new Error('Repeats line ' + seen[row.ns_item_id]);
      seen[row.ns_item_id] = i + 2;
      rows.push(row);
    } catch (e) { errors.push('Line ' + (i + 2) + ': ' + String(e.message || e)); }
  });

  var parts = rows.map(function (r) { return r.part_no; }).filter(String);
  if (parts.length) {
    var found = {};
    q_('SELECT DISTINCT Part_No p FROM ' + t_('raw_Part_v_Part') + ' WHERE Part_No IN UNNEST(SPLIT(@list, "\\n"))',
       [P('list', parts.join('\n'))]).forEach(function (r) { found[r.p] = true; });
    rows.forEach(function (r) { if (r.part_no && !found[r.part_no]) errors.push(r.part_no + ' is not in Plex (exact match needed).'); });
  }
  if (errors.length) return { ok: false, errors: errors.slice(0, 15), errorCount: errors.length };

  // Load job (append), so a large file is one fast write.
  var cols = ['ns_item_id', 'part_no', 'description', 'ns_avg_daily_usage', 'as_of_date', 'mapping_status', 'note',
              'updated_by', 'updated_at', 'is_deleted'];
  var now = Utilities.formatDate(new Date(), 'UTC', "yyyy-MM-dd'T'HH:mm:ss'Z'");
  var csv = [cols.join(',')].concat(rows.map(function (r) {
    return [r.ns_item_id, r.part_no, r.description, r.usage, r.as_of_date, r.mapping_status, r.note,
            email, now, 'false'].map(csvCell_).join(',');
  })).join('\n');
  var job = BigQuery.Jobs.insert({ configuration: { load: {
    destinationTable: { projectId: dataProject_(), datasetId: dataset_(), tableId: TABLES.usage },
    sourceFormat: 'CSV', skipLeadingRows: 1, allowQuotedNewlines: true, writeDisposition: 'WRITE_APPEND',
    schemaUpdateOptions: ['ALLOW_FIELD_RELAXATION'],
    schema: { fields: [
      { name: 'ns_item_id', type: 'STRING' }, { name: 'part_no', type: 'STRING' }, { name: 'description', type: 'STRING' },
      { name: 'ns_avg_daily_usage', type: 'FLOAT' }, { name: 'as_of_date', type: 'DATE' },
      { name: 'mapping_status', type: 'STRING' }, { name: 'note', type: 'STRING' },
      { name: 'updated_by', type: 'STRING' }, { name: 'updated_at', type: 'TIMESTAMP' }, { name: 'is_deleted', type: 'BOOLEAN' }] }
  } } }, project_(), Utilities.newBlob(csv, 'text/csv', 'part_usage.csv'));
  waitForJob_(job.jobReference);
  return { ok: true, message: 'Saved usage for ' + rows.length + ' parts.' };
}

function csvCell_(v) {
  var s = v == null ? '' : String(v);
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

function waitForJob_(ref) {
  var deadline = Date.now() + 90000;
  while (Date.now() < deadline) {
    var j = BigQuery.Jobs.get(project_(), ref.jobId, { location: ref.location });
    if (j.status && j.status.state === 'DONE') {
      if (j.status.errorResult) throw new Error('Upload failed: ' + j.status.errorResult.message);
      return j;
    }
    Utilities.sleep(1000);
  }
  throw new Error('Upload did not finish within 90 seconds. Check before retrying.');
}

/** Summary line for the Part usage tab. */
function getUsageSummary() {
  require_('part_usage');
  return q_(LIVE_USAGE_.replace('{T}', t_(TABLES.usage)) +
    'SELECT COUNT(*) n, COUNTIF(part_no IS NOT NULL) mapped, CAST(MAX(as_of_date) AS STRING) newest FROM live')[0] || {};
}

// ── MSL rules ──────────────────────────────────────────────────────────────

function getRules() {
  require_('msl_rules');
  var cur = {};
  q_('SELECT rule, value FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY rule ORDER BY updated_at DESC) rn FROM ' +
     t_(TABLES.rules) + ') WHERE rn = 1 AND NOT IFNULL(is_deleted, FALSE)').forEach(function (r) { cur[r.rule] = r.value; });
  return Object.keys(MSL_RULES).map(function (k) {
    var v = cur[k] != null ? cur[k] : MSL_RULES[k].def;
    return { name: k, label: MSL_RULES[k].label, help: MSL_RULES[k].help, def: MSL_RULES[k].def, value: v };
  });
}

function saveRules(form) {
  var email = require_('msl_rules');
  var now = {};
  getRules().forEach(function (r) { now[r.name] = r.value; });
  var changed = [];
  Object.keys(MSL_RULES).forEach(function (k) {
    var v = String(form[k] == null ? '' : form[k]).trim();
    if (v === '' || !isFinite(Number(v)) || Number(v) < 0) throw new Error(MSL_RULES[k].label + ' must be a number of zero or more.');
    if (v !== String(now[k])) changed.push({ rule: k, value: v, from: now[k] });
  });
  if (!changed.length) return { ok: true, message: 'Nothing changed.' };
  var params = [P('by', email)], values = [];
  changed.forEach(function (c, i) {
    params.push(P('r' + i, c.rule), P('v' + i, c.value), P('n' + i, 'was ' + c.from));
    values.push('(@r' + i + ', @v' + i + ', @n' + i + ', @by, CURRENT_TIMESTAMP(), FALSE)');
  });
  q_('INSERT INTO ' + t_(TABLES.rules) + ' (rule, value, note, updated_by, updated_at, is_deleted) VALUES ' + values.join(', '), params);
  return { ok: true, message: 'Saved: ' + changed.map(function (c) { return c.rule + ' ' + c.from + ' → ' + c.value; }).join(', ') };
}

// ── Admin: who may edit what ───────────────────────────────────────────────

function requireAdmin_() {
  var email = me_();
  if (areasFor_(email).indexOf('admin') === -1) throw new Error('Only admins can manage user access.');
  return email;
}

/** Every user with any access, and their areas. */
function getAccess() {
  requireAdmin_();
  var users = {};
  q_(ACCESS_SQL_.replace('{T}', t_(TABLES.access))).forEach(function (r) {
    var e = String(r.user_email).toLowerCase();
    (users[e] = users[e] || []).push(r.area);
  });
  return {
    areas: Object.keys(AREAS).map(function (a) { return { key: a, label: a === 'admin' ? 'Admin' : AREAS[a].label }; }),
    users: Object.keys(users).sort().map(function (e) { return { email: e, areas: users[e] }; })
  };
}

/** Grant or remove one user's access to one area. */
function setAccess(email, area, allowed) {
  var by = requireAdmin_();
  email = String(email || '').trim().toLowerCase();
  if (!/^[^@\s]+@(parasolgroupinc|voxnutrition)\.com$/.test(email)) throw new Error('Use a full @parasolgroupinc.com or @voxnutrition.com email address.');
  if (!AREAS[area]) throw new Error('Unknown area: ' + area);
  if (area === 'admin' && !allowed) {
    if (email === by) throw new Error('You cannot remove your own admin access. Ask another admin.');
    var admins = getAccess().users.filter(function (u) { return u.areas.indexOf('admin') !== -1; });
    if (admins.length <= 1) throw new Error('There must always be at least one admin.');
  }
  q_('INSERT INTO ' + t_(TABLES.access) + ' (user_email, area, updated_by, updated_at, is_deleted) ' +
     'VALUES (@e, @a, @by, CURRENT_TIMESTAMP(), CAST(@d AS BOOL))',
     [P('e', email), P('a', area), P('by', by), P('d', allowed ? 'false' : 'true')]);
  return { ok: true, message: (allowed ? 'Gave ' : 'Removed ') + email + (allowed ? ' access to ' : ' from ') +
                              (area === 'admin' ? 'Admin' : AREAS[area].label) + '.' };
}

/** Remove a user from every area at once. */
function removeUser(email) {
  requireAdmin_();
  var u = getAccess().users.filter(function (x) { return x.email === String(email).toLowerCase(); })[0];
  if (!u) return { ok: true, message: 'No access to remove.' };
  // Admin last, so the "keep one admin" and "not yourself" checks apply.
  u.areas.sort(function (a, b) { return (a === 'admin') - (b === 'admin'); })
   .forEach(function (a) { setAccess(email, a, false); });
  return { ok: true, message: 'Removed all access for ' + email + '.' };
}

// ── Helpers ────────────────────────────────────────────────────────────────

/** Accepts YYYY-MM-DD (or a timestamp starting with it) and M/D/YYYY. */
function isoDate_(s, label) {
  var t = String(s || '').trim();
  var m = t.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return m[1] + '-' + m[2] + '-' + m[3];
  m = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (m) return m[3] + '-' + ('0' + m[1]).slice(-2) + '-' + ('0' + m[2]).slice(-2);
  throw new Error((label || 'Date') + ' must be a date, got: ' + s);
}

/** Run from the editor to check setup. Writes nothing. */
function testSetup() {
  Logger.log('running as: %s', me_());
  Logger.log('tables in: %s.%s', dataProject_(), dataset_());
  Logger.log('your areas: %s', areasFor_(me_()).join(', '));
  Logger.log('safety: %s', JSON.stringify(getSafety().safeDays) + ' safe days');
}
