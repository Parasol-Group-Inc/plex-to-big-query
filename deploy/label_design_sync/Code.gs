/**
 * Label Design queue — BigQuery → Sheet → Monday holding board
 * ============================================================
 *
 * Replaces a twice-daily manual loop: download a report from NetSuite, paste
 * it into a Google Sheet, check it for duplicates by hand, upload the new rows
 * to Monday.
 *
 * Runs at 10:00 and 14:00 Mountain. The Cloud Run job refreshes
 * `label_design_report` in BigQuery beforehand; this script is what decides
 * which of those rows are NEW and pushes them onward — which is why the
 * notifications live here rather than in the pipeline. The pipeline knows a
 * query succeeded; only this knows what reached Monday.
 *
 * ── DEDUPLICATION ──────────────────────────────────────────────────────────
 * On ORDER NUMBER + CUSTOMER PART NUMBER, checked against BOTH tabs.
 *
 * Not the date, and not an id: dates change, and an order can be cancelled and
 * reopened. The same customer part on a DIFFERENT order is legitimately a new
 * row and must repeat.
 *
 * The historical tab is read but never written. People edit notes and reason
 * codes there by hand, and re-writing a row would overwrite that work — which
 * is the whole reason rows land in a HOLDING board rather than the live one.
 *
 * ── SETUP ─────────────────────────────────────────────────────────────────
 * Services (+) → BigQuery API → Add. Then Project Settings → Script
 * Properties:
 *
 *   GCP_PROJECT        parasoldatalake     jobs run and bill here
 *   BQ_DATA_PROJECT    voxdatalake         where the tables are
 *   BQ_DATASET         PlexTest            → PlexProd at go-live
 *   SHEET_ID           <the duplicate sheet, not the live one>
 *   MONDAY_API_KEY     <long-lived token>
 *   MONDAY_BOARD_ID    <from the board URL>
 *
 * Run `testReadOnly()` first — it writes nothing, pushes nothing and emails
 * nobody. Then `installTriggers()` once.
 */

// ── Who hears about what ───────────────────────────────────────────────────
//
// Deliberately NOT "errors only". Every run emails the ops addresses, whether
// it worked or not — a silent success and a job that never fired look
// identical, and the whole point of automating this was that nobody notices
// when a manual step stops happening.

var RUN_TO_EMAILS = [
  'emilio.dominguez@parasolgroupinc.com',
  'marketing@parasolgroupinc.com'
];

// The business summary: once a night, not per run.
var SUMMARY_TO_EMAILS = [
  'ashley.quintana@voxnutrition.com',
  'kelli.gooch@voxnutrition.com',
  'jennilyn.tockstein@parasolgroupinc.com'
];

var FROM_ALIAS = 'bizops@parasolgroupinc.com';

var MAIN_TAB = 'Label Design';       // written by this script
var HISTORY_TAB = 'historical';      // read only — hand-edited, never written

// Column order written to the sheet. Kept explicit rather than derived from
// the query, so a column added to the view doesn't silently shift the sheet.
var COLUMNS = [
  'order_number', 'customer_po', 'customer_name', 'customer_part_no',
  'line_status', 'order_status', 'due_date', 'order_date', 'job_note',
  'sales_rep_primary', 'sales_rep_secondary'
];

// ── Config plumbing ────────────────────────────────────────────────────────

function prop_(key) {
  var v = PropertiesService.getScriptProperties().getProperty(key);
  if (!v) throw new Error('Script property ' + key + ' is not set.');
  return v;
}
function project_()     { return prop_('GCP_PROJECT'); }
function dataProject_() {
  return PropertiesService.getScriptProperties().getProperty('BQ_DATA_PROJECT') || project_();
}
function dataset_()     { return prop_('BQ_DATASET'); }
function sheet_()       { return SpreadsheetApp.openById(prop_('SHEET_ID')); }

// ── The run ────────────────────────────────────────────────────────────────

/** The trigger entry point. Never throws — a failure has to reach an inbox. */
function syncNow() {
  var started = new Date();
  var result = {
    started: started,
    fetched: 0, alreadyPresent: 0, written: 0,
    pushed: 0, pushFailed: 0,
    rows: [], errors: []
  };

  try {
    var rows = fetchQueue_();
    result.fetched = rows.length;

    var seen = existingKeys_();
    var fresh = rows.filter(function (r) {
      var key = dedupeKey_(r);
      if (seen[key]) return false;
      seen[key] = true;          // guards against duplicates within one batch
      return true;
    });
    result.alreadyPresent = rows.length - fresh.length;

    if (fresh.length) {
      appendRows_(fresh);
      result.written = fresh.length;
      result.rows = fresh;

      var push = pushToMonday_(fresh);
      result.pushed = push.ok;
      result.pushFailed = push.failed;
      push.errors.forEach(function (e) { result.errors.push(e); });
    }
  } catch (e) {
    result.errors.push(String(e));
    Logger.log('syncNow failed: %s', e);
  }

  result.finished = new Date();
  recordRun_(result);
  sendRunEmail_(result);
  return result;
}

/**
 * The rolling window comes from the view (14 days), so this takes it whole.
 * Filtering again here would mean two places to change one rule.
 */
function fetchQueue_() {
  var sql =
    'SELECT ' + COLUMNS.join(', ') + ' FROM `' +
    dataProject_() + '.' + dataset_() + '.label_design_report` ' +
    'ORDER BY order_date DESC, order_number';

  var job = BigQuery.Jobs.query({ query: sql, useLegacySql: false, timeoutMs: 60000 }, project_());

  if (!job.jobComplete) {
    throw new Error('BigQuery did not finish within 60s — the queue was not read.');
  }

  return (job.rows || []).map(function (row) {
    var obj = {};
    COLUMNS.forEach(function (c, i) { obj[c] = row.f[i].v; });
    return obj;
  });
}

/**
 * Every key already on either tab. The historical tab is included because it
 * is what the team checks against — a row that has been worked and archived
 * must not come back as new.
 */
function existingKeys_() {
  var ss = sheet_();
  var seen = {};

  [MAIN_TAB, HISTORY_TAB].forEach(function (tabName) {
    var tab = ss.getSheetByName(tabName);
    if (!tab) return;
    var last = tab.getLastRow();
    if (last < 2) return;

    var headers = tab.getRange(1, 1, 1, tab.getLastColumn()).getDisplayValues()[0];
    var oi = headerIndex_(headers, 'order_number', 'Order Number', 'Order_Number');
    var pi = headerIndex_(headers, 'customer_part_no', 'Customer Part No', 'Customer_Part_No');
    if (oi < 0 || pi < 0) {
      throw new Error('Tab "' + tabName + '" has no order-number / customer-part columns. ' +
                      'Without them nothing can be deduplicated, so the run stops rather ' +
                      'than risk writing the whole queue again.');
    }

    tab.getRange(2, 1, last - 1, headers.length).getDisplayValues().forEach(function (r) {
      seen[norm_(r[oi]) + '|' + norm_(r[pi])] = true;
    });
  });

  return seen;
}

function headerIndex_(headers, /* ...candidates */) {
  for (var i = 1; i < arguments.length; i++) {
    var want = norm_(arguments[i]);
    for (var c = 0; c < headers.length; c++) {
      if (norm_(headers[c]) === want) return c;
    }
  }
  return -1;
}

/** Trims and upper-cases, so "  12345 " and "12345" are one key, not two. */
function norm_(v) {
  return String(v == null ? '' : v).trim().toUpperCase();
}

function dedupeKey_(row) {
  return norm_(row.order_number) + '|' + norm_(row.customer_part_no);
}

function appendRows_(rows) {
  var ss = sheet_();
  var tab = ss.getSheetByName(MAIN_TAB);
  if (!tab) {
    tab = ss.insertSheet(MAIN_TAB);
    tab.getRange(1, 1, 1, COLUMNS.length).setValues([COLUMNS]).setFontWeight('bold');
    tab.setFrozenRows(1);
  }
  var values = rows.map(function (r) {
    return COLUMNS.map(function (c) { return r[c] == null ? '' : r[c]; });
  });
  tab.getRange(tab.getLastRow() + 1, 1, values.length, COLUMNS.length).setValues(values);
}

// ── Monday ─────────────────────────────────────────────────────────────────

/**
 * Pushes into a HOLDING board, never the live one. Notes and reason codes get
 * reviewed and edited there before anyone moves an item across.
 *
 * One item at a time on purpose: a batch that fails halfway is worse than a
 * few individual failures, because the sheet has already been written and
 * there is no way to tell which half landed.
 */
function pushToMonday_(rows) {
  var out = { ok: 0, failed: 0, errors: [] };
  var boardId = PropertiesService.getScriptProperties().getProperty('MONDAY_BOARD_ID');
  var apiKey = PropertiesService.getScriptProperties().getProperty('MONDAY_API_KEY');

  if (!boardId || !apiKey) {
    out.errors.push('Monday is not configured (MONDAY_BOARD_ID / MONDAY_API_KEY) — ' +
                    'rows are in the sheet but were not pushed.');
    out.failed = rows.length;
    return out;
  }

  rows.forEach(function (r) {
    try {
      var name = r.customer_name + ' — ' + r.customer_part_no;
      var vals = {
        text_order:    String(r.order_number || ''),
        text_po:       String(r.customer_po || ''),
        text_part:     String(r.customer_part_no || ''),
        text_rep:      String(r.sales_rep_primary || ''),
        long_text_note:{ text: String(r.job_note || '') }
      };
      if (r.due_date) vals.date_due = { date: String(r.due_date).slice(0, 10) };

      var query =
        'mutation ($board: ID!, $name: String!, $vals: JSON!) {' +
        '  create_item (board_id: $board, item_name: $name, column_values: $vals) { id }' +
        '}';

      var res = UrlFetchApp.fetch('https://api.monday.com/v2', {
        method: 'post',
        contentType: 'application/json',
        headers: { Authorization: apiKey, 'API-Version': '2023-10' },
        payload: JSON.stringify({
          query: query,
          variables: { board: boardId, name: name, vals: JSON.stringify(vals) }
        }),
        muteHttpExceptions: true
      });

      var body = JSON.parse(res.getContentText());
      // Monday answers 200 with an "errors" array rather than an HTTP error,
      // so the status code alone would report success on a rejected mutation.
      if (body.errors) throw new Error(JSON.stringify(body.errors));
      out.ok++;
    } catch (e) {
      out.failed++;
      out.errors.push('Monday push failed for order ' + r.order_number + ': ' + e);
      Logger.log('Monday push failed: %s', e);
    }
  });

  return out;
}

// ── Run log, for the nightly summary ───────────────────────────────────────
//
// Kept in Script Properties rather than a tab: it is scaffolding for the
// summary email, not business data, and it should not be something anyone has
// to look at or can accidentally edit.

function recordRun_(r) {
  var props = PropertiesService.getScriptProperties();
  var log = [];
  try { log = JSON.parse(props.getProperty('RUN_LOG') || '[]'); } catch (e) { log = []; }

  log.push({
    at: r.started.toISOString(),
    fetched: r.fetched, written: r.written, dupes: r.alreadyPresent,
    pushed: r.pushed, pushFailed: r.pushFailed,
    errors: r.errors.length
  });

  // Two runs a day; a fortnight of history is plenty and keeps the property
  // well inside its size limit.
  if (log.length > 30) log = log.slice(log.length - 30);
  props.setProperty('RUN_LOG', JSON.stringify(log));
}

function runsToday_() {
  var props = PropertiesService.getScriptProperties();
  var log = [];
  try { log = JSON.parse(props.getProperty('RUN_LOG') || '[]'); } catch (e) { return []; }
  var today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
  return log.filter(function (e) {
    return Utilities.formatDate(new Date(e.at), Session.getScriptTimeZone(), 'yyyy-MM-dd') === today;
  });
}

// ── Email ──────────────────────────────────────────────────────────────────

/** Every run, pass or fail. */
function sendRunEmail_(r) {
  var failed = r.errors.length > 0;
  var subject = '[Label Design] ' + (failed ? 'Problem on ' : '') +
                r.written + ' new ' + (r.written === 1 ? 'row' : 'rows') +
                ' — ' + fmtTime_(r.started);

  var body = [
    'Label Design sync — ' + fmtDateTime_(r.started),
    '',
    'In the Plex queue:      ' + r.fetched,
    'Already on the sheet:   ' + r.alreadyPresent,
    'Written as new:         ' + r.written,
    'Pushed to Monday:       ' + r.pushed + (r.pushFailed ? '   (' + r.pushFailed + ' FAILED)' : ''),
    ''
  ];

  if (r.rows.length) {
    body.push('New rows:');
    r.rows.slice(0, 40).forEach(function (x) {
      body.push('  ' + x.order_number + '  ' + (x.customer_part_no || '—') +
                '  ' + (x.customer_name || '') +
                (x.sales_rep_primary ? '  (' + x.sales_rep_primary + ')' : ''));
    });
    if (r.rows.length > 40) body.push('  ...and ' + (r.rows.length - 40) + ' more.');
    body.push('');
  }

  if (failed) {
    body.push('PROBLEMS:');
    r.errors.forEach(function (e) { body.push('  - ' + e); });
    body.push('');
    body.push('Rows already written to the sheet are safe — the next run will not repeat them.');
    body.push('');
  }

  body.push('Dataset: ' + dataProject_() + '.' + dataset_());
  body.push('This email is sent on every run, successful or not.');

  send_(RUN_TO_EMAILS, subject, body.join('\n'));
}

/** Once a night, to the people who use the queue rather than run it. */
function sendDailySummary() {
  var runs = runsToday_();
  var written = 0, pushed = 0, problems = 0, fetched = 0;
  runs.forEach(function (e) {
    written += e.written; pushed += e.pushed;
    problems += e.errors + e.pushFailed; fetched = Math.max(fetched, e.fetched);
  });

  var today = fmtDate_(new Date());
  var body = [
    'Label Design — ' + today,
    '',
    'New rows added today:    ' + written,
    'Pushed to Monday:        ' + pushed,
    'Currently in the queue:  ' + fetched + '   (orders in Label Design, last 14 days)',
    'Syncs run:               ' + runs.length + (runs.length === 2 ? '' : '   (expected 2)'),
    ''
  ];

  if (!runs.length) {
    body.push('NO SYNC RAN TODAY. Nothing new reached the board — anything in Plex is');
    body.push('still waiting. Worth telling Emilio.');
    body.push('');
  } else if (problems) {
    body.push(problems + ' problem(s) occurred. Some rows may be on the sheet but not on');
    body.push('the Monday board. Emilio has the detail.');
    body.push('');
  } else if (!written) {
    body.push('Nothing new today — every order in Label Design was already on the board.');
    body.push('');
  }

  body.push('New items land on the holding board, not the live one, so notes and reason');
  body.push('codes can still be reviewed before anything moves across.');

  send_(SUMMARY_TO_EMAILS, '[Label Design] Daily summary — ' + today, body.join('\n'));
}

function send_(to, subject, body) {
  if (!to.length) return;
  MailApp.sendEmail({
    to: to.join(','),
    from: FROM_ALIAS,
    replyTo: FROM_ALIAS,
    subject: subject,
    body: body + '\n\n--\nAutomated from Plex. Please do not reply.'
  });
}

function fmtDate_(d)     { return Utilities.formatDate(d, Session.getScriptTimeZone(), 'd MMM yyyy'); }
function fmtTime_(d)     { return Utilities.formatDate(d, Session.getScriptTimeZone(), 'HH:mm'); }
function fmtDateTime_(d) { return Utilities.formatDate(d, Session.getScriptTimeZone(), 'd MMM yyyy HH:mm z'); }

// ── Triggers ───────────────────────────────────────────────────────────────

/**
 * Run once from the editor. Set the script's timezone to America/Denver in
 * Project Settings first — Apps Script hour triggers follow it, so the wrong
 * timezone silently runs the sync at the wrong times.
 *
 * Apps Script only guarantees the hour, not the minute, so "10:00" means
 * somewhere inside the 10:00 hour. That is well within tolerance here.
 */
function installTriggers() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });

  [10, 14].forEach(function (h) {
    ScriptApp.newTrigger('syncNow').timeBased().everyDays(1).atHour(h).create();
  });

  ScriptApp.newTrigger('sendDailySummary').timeBased().everyDays(1).atHour(18).create();

  Logger.log('Triggers installed: syncNow at 10 and 14, sendDailySummary at 18.');
}

// ── Dry run (writes nothing, pushes nothing, emails nobody) ────────────────

function testReadOnly() {
  var rows = fetchQueue_();
  var seen = existingKeys_();
  var fresh = rows.filter(function (r) { return !seen[dedupeKey_(r)]; });

  Logger.log('jobs run in:      %s', project_());
  Logger.log('tables read from: %s.%s', dataProject_(), dataset_());
  Logger.log('in the queue:     %s', rows.length);
  Logger.log('already on sheet: %s', rows.length - fresh.length);
  Logger.log('would write:      %s', fresh.length);
  fresh.slice(0, 10).forEach(function (r) {
    Logger.log('  %s  %s  %s', r.order_number, r.customer_part_no, r.customer_name);
  });
}
