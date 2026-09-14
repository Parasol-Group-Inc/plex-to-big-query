/**
 * Label Design queue — BigQuery → Sheet → Monday holding board
 * ============================================================
 *
 * Replaces a twice-daily manual loop: download a report from NetSuite, paste
 * it into a Google Sheet, check it for duplicates by hand, upload the new rows
 * to Monday.
 *
 * The Cloud Run job `plex-etl-label-design` refreshes `label_design_report` in
 * BigQuery at 09:30 and 13:30 Mountain; this script runs in the 10:00 and
 * 14:00 hours and is what decides which of those rows are NEW. That is why the
 * notifications live here rather than in the pipeline: the pipeline knows a
 * query succeeded, only this knows what reached Monday.
 *
 * ── THE ONE RULE ───────────────────────────────────────────────────────────
 * The `historical` tab is READ AND NEVER WRITTEN. Not by this script, not in
 * any failure path, not as a fallback. People hand-edit notes and reason codes
 * there, and re-writing a row would destroy that work. Every write in this
 * file goes to the MONDAY tab or to a dated review tab, and every write path
 * passes through assertNotHistory_() so a future edit cannot quietly break it.
 *
 * ── DEDUPLICATION ──────────────────────────────────────────────────────────
 * ORDER NUMBER + LABEL SKU (the customer part number), checked against BOTH
 * tabs.
 *
 * Not the date, and not a row id: dates change, and an order can be cancelled
 * and reopened. The same customer part on a DIFFERENT order is legitimately a
 * new row and must repeat.
 *
 * The two sides spell the order number differently — the sheet says
 * "Sales Order #SO0110212" and Plex says "SO0110212" — so both are reduced to
 * a token before comparison. See orderToken_(), and see assessKeys_() for what
 * happens when that reduction stops working.
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
// Deliberately NOT "errors only". Every run emails the technical addresses,
// whether it worked or not — a silent success and a job that never fired look
// identical, and the whole point of automating this was that nobody notices
// when a manual step stops happening.

/** Technical email — every run, pass or fail. Counts, new rows, problems. */
var TECHNICAL_TO_EMAILS = [
  'jennilyn.tockstein@parasolgroupinc.com',
  'emilio.dominguez@parasolgroupinc.com',
  'marketing@parasolgroupinc.com'
];

/** Business summary — once a day, weekdays only. The people who USE the queue. */
var SUMMARY_TO_EMAILS = [
  'ashley.quintana@voxnutrition.com',
  'kelli.gooch@voxnutrition.com',
  'jennilyn.tockstein@parasolgroupinc.com',
  'emilio.dominguez@parasolgroupinc.com',
  'marketing@parasolgroupinc.com'
];

var FROM_ALIAS = 'bizops@parasolgroupinc.com';

// ── Tabs ───────────────────────────────────────────────────────────────────

var MAIN_TAB = 'MONDAY';          // written by this script — new orders only
var HISTORY_TAB = 'historical';   // READ ONLY. Never written. See header.

// Both tabs are matched case-insensitively against these, because tabs in this
// sheet have been renamed by hand before.
var MAIN_TAB_ALIASES = ['MONDAY', 'Monday', 'Label Design', 'NEW'];
var HISTORY_TAB_ALIASES = ['historical', 'history'];

// ── The sheet layout ───────────────────────────────────────────────────────
//
// This is the MONDAY tab's real header row, in its real order, as exported
// 2026-09-12. It is the contract between Plex and the team.
//
// `from` is the column in `label_design_report` that fills it. Columns with no
// `from` fall into two kinds, and the difference matters — the run email
// reports them separately rather than lumping them together as "blank":
//
//   kind 'team'   Filled in BY A PERSON during review. Blank is correct and
//                 permanent; there is nothing in Plex to put here, and the
//                 review step is the reason rows land on a HOLDING board.
//
//   kind 'gap'    Plex plausibly holds this and the view does not expose it
//                 yet. Blank is a to-do, not a design. These are the ones
//                 worth chasing, which is why they are flagged apart from the
//                 'team' columns — a section that cries wolf every run is a
//                 section everyone learns to skip.
//
// `alt` lists other spellings of the same column, so a header that differs
// between the two tabs ("Phone" vs "Phone Number") does not read as missing.
var SHEET_MAP = [
  { header: 'Date',            from: 'order_date',                kind: 'plex' },
  { header: 'Sales Order',     from: 'order_number',              kind: 'plex', format: 'salesOrder' },
  { header: 'Memo',            from: 'job_note',                  kind: 'plex' },
  { header: 'Customer',        from: 'customer_name',             kind: 'plex' },
  { header: 'Email',           from: 'customer_email',            kind: 'plex' },
  { header: 'Phone Number',    from: 'customer_phone',            kind: 'plex', alt: ['Phone'] },
  { header: 'WO Number',       from: null,                        kind: 'gap',
    note: 'The work order is raised after the label is approved, so an order still ' +
          'in Label Design usually has none yet. Would need Part_v_Job, which this ' +
          'pipeline does not extract.' },
  { header: 'Item',            from: null,                        kind: 'gap',
    note: 'The NetSuite item name. No Plex column reproduces it; the nearest ' +
          'equivalents already ship as Customer and Label SKU.' },
  { header: 'Sales Rep',       from: 'sales_rep_primary',         kind: 'plex' },
  { header: 'Label SKU',       from: 'customer_part_no',          kind: 'plex' },
  { header: 'Description',     from: 'customer_part_description', kind: 'plex' },
  { header: 'Reason Code',     from: null,                        kind: 'team' },
  { header: 'Label',           from: null,                        kind: 'team' },
  { header: 'Bottle Material', from: null,                        kind: 'team' },
  { header: 'LCR',             from: null,                        kind: 'team' },
  { header: 'Prop 65',         from: null,                        kind: 'team' }
];

/** Columns fetched from BigQuery. Derived from SHEET_MAP so the two cannot drift. */
var QUERY_COLUMNS = (function () {
  var cols = [];
  SHEET_MAP.forEach(function (c) { if (c.from && cols.indexOf(c.from) < 0) cols.push(c.from); });
  // Carried for diagnostics even though no sheet column shows them.
  ['order_status', 'line_status'].forEach(function (c) {
    if (cols.indexOf(c) < 0) cols.push(c);
  });
  return cols;
})();

/** The two columns dedupe depends on. Without BOTH, a tab cannot be trusted. */
var KEY_HEADERS = { order: 'Sales Order', sku: 'Label SKU' };

// ── Monday board columns ───────────────────────────────────────────────────
//
// THE ONLY THING YOU NEED TO EDIT TO TURN THE MONDAY PUSH ON.
//
// Monday column IDs are **per-board** and are **not** the column titles — a
// column headed "Sales Order" might have the id `text8` or `text_mkp3q1`. They
// cannot be guessed, and a wrong id does not error loudly: Monday answers 200
// with an `errors` array (handled below), so the row simply never appears.
//
// Run `listMondayColumns()` from the editor. It prints every column on the
// board with its real id and type, AND prints a ready-to-paste replacement for
// this block. Paste it over this object and the push is live.
//
// `field` is the column in `label_design_report`. `type` tells the builder how
// Monday wants the value shaped — a plain text column takes a string, a date
// column takes `{date: "YYYY-MM-DD"}`, a long-text column takes `{text: "..."}`.
//
// An entry whose `id` is still null is SKIPPED rather than sent, so a partly
// filled-in map pushes the columns you have mapped instead of failing whole.
// The item's own name is built separately (customer — part), so a board with
// nothing but its name column still receives usable items.
var MONDAY_COLUMNS = [
  { id: null, field: 'order_number',      type: 'text' },
  { id: null, field: 'customer_part_no',  type: 'text' },
  { id: null, field: 'customer_name',     type: 'text' },
  { id: null, field: 'sales_rep_primary', type: 'text' },
  { id: null, field: 'customer_email',    type: 'text' },
  { id: null, field: 'job_note',          type: 'long_text' },
  { id: null, field: 'order_date',        type: 'date' }
];

/**
 * If a run would write more than this many rows AND the archive is not empty,
 * something is wrong with the KEYS rather than with the business — the
 * likeliest cause being that Plex changed how it spells an order number and
 * orderToken_() no longer reduces both sides to the same string. The failure
 * that guards against is re-writing thousands of already-worked rows onto the
 * sheet and onto the Monday board.
 *
 * Rows are not discarded when this trips: they go to a dated review tab and
 * nothing is pushed to Monday, so a person can look before anything is
 * irreversible. 60 is comfortably above a real day (single digits to low tens)
 * and far below a re-import of the whole queue.
 */
var NEW_ROW_ALARM = 60;

// ── Config plumbing ────────────────────────────────────────────────────────

function prop_(key) {
  var v = PropertiesService.getScriptProperties().getProperty(key);
  if (!v) throw new Error('Script property ' + key + ' is not set.');
  return v;
}
function optProp_(key) {
  return PropertiesService.getScriptProperties().getProperty(key) || '';
}
function project_()     { return prop_('GCP_PROJECT'); }
function dataProject_() { return optProp_('BQ_DATA_PROJECT') || project_(); }
function dataset_()     { return prop_('BQ_DATASET'); }
function sheet_()       { return SpreadsheetApp.openById(prop_('SHEET_ID')); }

// ── Text normalisation ─────────────────────────────────────────────────────

/** Trims and upper-cases, so "  12345 " and "12345" are one value, not two. */
function norm_(v) {
  return String(v == null ? '' : v).trim().toUpperCase();
}

/** Header comparison: case, surrounding space and inner runs of space ignored. */
function normHeader_(v) {
  return String(v == null ? '' : v).replace(/\s+/g, ' ').trim().toUpperCase();
}

/**
 * Reduces both spellings of an order number to one token.
 *
 *   "Sales Order #SO0110212"  ->  "SO0110212"
 *   "  so0110212 "            ->  "SO0110212"
 *
 * Everything that is not a letter or digit is dropped, then a leading
 * "SALESORDER" is removed. If Plex ever starts returning a bare numeric order
 * number while the sheet keeps the SO-prefixed one, this stops matching — and
 * assessKeys_() is what notices.
 */
function orderToken_(v) {
  return norm_(v).replace(/[^A-Z0-9]/g, '').replace(/^SALESORDER/, '');
}

function skuToken_(v) {
  return norm_(v).replace(/[^A-Z0-9]/g, '');
}

function dedupeKeyFromValues_(order, sku) {
  return orderToken_(order) + '|' + skuToken_(sku);
}

function dedupeKey_(row) {
  return dedupeKeyFromValues_(row.order_number, row.customer_part_no);
}

// ── The run ────────────────────────────────────────────────────────────────

/** The trigger entry point. Never throws — a failure has to reach an inbox. */
function syncNow() {
  var started = new Date();
  var result = {
    started: started,
    fetched: 0, alreadyPresent: 0, written: 0,
    pushed: 0, pushFailed: 0,
    targetTab: '', quarantined: false,
    rows: [], errors: [], warnings: [],
    headerReport: null, keyReport: null
  };

  try {
    var rows = fetchQueue_();
    result.fetched = rows.length;

    var tabs = readTabs_();
    result.headerReport = tabs.report;
    tabs.report.warnings.forEach(function (w) { result.warnings.push(w); });

    var seen = tabs.keys;
    var fresh = rows.filter(function (r) {
      var key = dedupeKey_(r);
      if (seen[key]) return false;
      seen[key] = true;          // guards against duplicates within one batch
      return true;
    });
    result.alreadyPresent = rows.length - fresh.length;

    // Does the dedupe still work at all? Decided BEFORE anything is written.
    result.keyReport = assessKeys_(rows, fresh, tabs);
    result.keyReport.warnings.forEach(function (w) { result.warnings.push(w); });

    if (fresh.length) {
      var target = writeTarget_(tabs, result.keyReport);
      result.targetTab = target.name;
      result.quarantined = target.quarantined;

      appendRows_(target, fresh);
      result.written = fresh.length;
      result.rows = fresh;

      if (target.quarantined) {
        // Nothing goes to Monday from a held run. The point is that a person
        // looks first.
        result.warnings.push(
          'Rows were written to "' + target.name + '" and NOT pushed to Monday. ' +
          'Nothing is lost and nothing is duplicated — but someone has to look at ' +
          'that tab before these reach the board.');
      } else {
        var push = pushToMonday_(fresh);
        result.pushed = push.ok;
        result.pushFailed = push.failed;
        push.errors.forEach(function (e) { result.errors.push(e); });
      }
    }
  } catch (e) {
    result.errors.push(String(e && e.message ? e.message : e));
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
    'SELECT ' + QUERY_COLUMNS.join(', ') + ' FROM `' +
    dataProject_() + '.' + dataset_() + '.label_design_report` ' +
    'ORDER BY order_date DESC, order_number';

  var job = BigQuery.Jobs.query(
    { query: sql, useLegacySql: false, timeoutMs: 60000 }, project_());

  if (!job.jobComplete) {
    throw new Error('BigQuery did not finish within 60s — the queue was not read. ' +
                    'Nothing was written; the next run picks it up.');
  }

  return (job.rows || []).map(function (row) {
    var obj = {};
    QUERY_COLUMNS.forEach(function (c, i) { obj[c] = row.f[i].v; });
    return obj;
  });
}

// ── Reading the sheet ──────────────────────────────────────────────────────

function findTab_(ss, aliases) {
  var all = ss.getSheets();
  for (var a = 0; a < aliases.length; a++) {
    var want = normHeader_(aliases[a]);
    for (var i = 0; i < all.length; i++) {
      if (normHeader_(all[i].getName()) === want) return all[i];
    }
  }
  return null;
}

/**
 * Works out where each mapped column sits on a tab, and what is on that tab
 * that we do not recognise.
 *
 * An unrecognised column is NOT an error — the team adds columns, and it is
 * their sheet. It is reported so they hear from us that those columns stay
 * blank on new rows, rather than discovering it themselves weeks later.
 */
function resolveHeaders_(tabName, headers) {
  var index = {};      // canonical header -> column index on this tab
  var missing = [];
  var used = {};

  SHEET_MAP.forEach(function (col) {
    var candidates = [col.header].concat(col.alt || []);
    var found = -1;
    for (var c = 0; c < candidates.length && found < 0; c++) {
      var want = normHeader_(candidates[c]);
      for (var i = 0; i < headers.length; i++) {
        if (normHeader_(headers[i]) === want) { found = i; break; }
      }
    }
    if (found >= 0) { index[col.header] = found; used[found] = true; }
    else { missing.push(col.header); }
  });

  var unknown = [];
  headers.forEach(function (h, i) {
    // Blank trailing headers are the sheet's unused columns, not a column
    // somebody added — the historical export has six of them.
    if (!used[i] && normHeader_(h) !== '') unknown.push(String(h).trim());
  });

  return {
    tab: tabName,
    index: index,
    missing: missing,
    unknown: unknown,
    hasKeys: index[KEY_HEADERS.order] != null && index[KEY_HEADERS.sku] != null,
    width: headers.length,
    headers: headers,
    rowCount: 0,
    sampleOrders: []
  };
}

/**
 * Every key already on either tab, plus what we learned about their headers.
 *
 * The historical tab is included because it is what the team checks against —
 * a row that has been worked and archived must not come back as new.
 */
function readTabs_() {
  var ss = sheet_();
  var keys = {};
  var report = { main: null, history: null, warnings: [] };

  var historyTab = findTab_(ss, HISTORY_TAB_ALIASES);
  if (!historyTab) {
    // Refusing to continue is the safe choice: without the archive every row
    // ever worked looks new, and the run would re-import thousands of them.
    throw new Error(
      'No "' + HISTORY_TAB + '" tab found in this sheet. That tab is the archive ' +
      'every row is checked against, so without it nothing can be deduplicated ' +
      'and the run would re-import the entire queue. Stopping instead. Nothing ' +
      'was written.');
  }

  report.history = readKeysFrom_(historyTab, keys);
  if (!report.history.hasKeys) {
    throw new Error(
      'The "' + historyTab.getName() + '" tab has no "' + KEY_HEADERS.order + '" / "' +
      KEY_HEADERS.sku + '" columns (it has: ' +
      report.history.headers.filter(String).join(', ') + '). Without them nothing ' +
      'can be deduplicated, so the run stops rather than risk writing the whole ' +
      'queue again. Nothing was written.');
  }

  var mainTab = findTab_(ss, MAIN_TAB_ALIASES);
  if (mainTab) {
    report.main = readKeysFrom_(mainTab, keys);
    if (!report.main.hasKeys) {
      report.warnings.push(
        'The "' + mainTab.getName() + '" tab is missing its "' + KEY_HEADERS.order +
        '" / "' + KEY_HEADERS.sku + '" columns, so rows already on it could not be ' +
        'checked. New rows go to a dated review tab rather than being appended to a ' +
        'layout we cannot read.');
    }
  } else {
    report.warnings.push(
      'No "' + MAIN_TAB + '" tab found — it was created with the standard header row.');
  }

  return { keys: keys, report: report, main: mainTab, history: historyTab };
}

/** Reads one tab's keys into `into`. Never writes. */
function readKeysFrom_(tab, into) {
  var lastRow = tab.getLastRow();
  var lastCol = Math.max(tab.getLastColumn(), 1);
  var headers = lastRow >= 1
    ? tab.getRange(1, 1, 1, lastCol).getDisplayValues()[0]
    : [];

  var info = resolveHeaders_(tab.getName(), headers);
  info.rowCount = Math.max(lastRow - 1, 0);

  if (!info.hasKeys || info.rowCount === 0) return info;

  var oi = info.index[KEY_HEADERS.order];
  var si = info.index[KEY_HEADERS.sku];

  tab.getRange(2, 1, info.rowCount, lastCol).getDisplayValues().forEach(function (r) {
    var order = r[oi], sku = r[si];
    if (normHeader_(order) === '' && normHeader_(sku) === '') return;   // blank row
    into[dedupeKeyFromValues_(order, sku)] = true;
    if (info.sampleOrders.length < 3 && normHeader_(order) !== '') {
      info.sampleOrders.push(String(order).trim());
    }
  });

  return info;
}

/**
 * Is the dedupe actually working?
 *
 * The check is deliberately crude, because the failure it exists for is crude:
 * if the two sides stop spelling the order number the same way, EVERY row
 * looks new at once. A real day produces single digits to low tens of new
 * rows, so a run that suddenly wants to write most of a non-trivial queue is
 * reporting a key problem, not a busy morning.
 */
function assessKeys_(allRows, freshRows, tabs) {
  var out = { alarm: false, warnings: [], matched: allRows.length - freshRows.length };
  var archived = tabs.report.history ? tabs.report.history.rowCount : 0;

  if (!allRows.length) return out;
  if (archived < 50) return out;   // a small or empty archive legitimately matches nothing
  if (freshRows.length <= NEW_ROW_ALARM) return out;

  out.alarm = true;

  if (out.matched === 0) {
    var samples = (tabs.report.history.sampleOrders || []).slice(0, 2).join(', ');
    out.warnings.push(
      freshRows.length + ' of ' + allRows.length + ' rows look new, and NOT ONE matched ' +
      'the ' + archived + ' rows already on the archive tab. That is almost certainly ' +
      'the order number being spelled differently on the two sides rather than a ' +
      'genuinely new queue' + (samples ? ' (the sheet has orders like: ' + samples + ')' : '') +
      '. Nothing was pushed to Monday and nothing was appended to the working tab.');
  } else {
    out.warnings.push(
      freshRows.length + ' new rows is well above a normal day (single digits to low ' +
      'tens), so the run was held back for review rather than pushed to Monday.');
  }

  return out;
}

// ── Writing ────────────────────────────────────────────────────────────────

/**
 * Decides which tab this run writes to. NEVER returns the historical tab —
 * that is asserted rather than left to the callers to remember.
 */
function writeTarget_(tabs, keyReport) {
  var ss = sheet_();
  var quarantine = keyReport.alarm ||
                   (tabs.report.main != null && !tabs.report.main.hasKeys);

  if (!quarantine) {
    var tab = tabs.main;
    if (!tab) {
      tab = ss.insertSheet(MAIN_TAB);
      var headers = SHEET_MAP.map(function (c) { return c.header; });
      tab.getRange(1, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
      tab.setFrozenRows(1);
      tabs.report.main = resolveHeaders_(tab.getName(), headers);
    }
    assertNotHistory_(tab);
    return { sheet: tab, name: tab.getName(), info: tabs.report.main, quarantined: false };
  }

  // "Make another tab" — a dated review tab carrying OUR canonical headers, so
  // the rows stay readable even when the working tab's layout is not.
  var stamp = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HHmm');
  var name = 'REVIEW ' + stamp;
  var overflow = ss.insertSheet(name);
  var cols = SHEET_MAP.map(function (c) { return c.header; });
  overflow.getRange(1, 1, 1, cols.length).setValues([cols]).setFontWeight('bold');
  overflow.setFrozenRows(1);
  assertNotHistory_(overflow);

  return { sheet: overflow, name: name, info: resolveHeaders_(name, cols), quarantined: true };
}

/**
 * The one rule, enforced rather than remembered. Every write path goes through
 * this, so "never write historical" cannot be broken by a future edit that
 * forgets about it.
 */
function assertNotHistory_(tab) {
  var name = normHeader_(tab.getName());
  for (var i = 0; i < HISTORY_TAB_ALIASES.length; i++) {
    if (normHeader_(HISTORY_TAB_ALIASES[i]) === name) {
      throw new Error('Refusing to write to the "' + tab.getName() + '" tab. It is ' +
                      'hand-edited and is only ever read.');
    }
  }
}

/** Formats one value for one sheet column. */
function cellValue_(col, row) {
  if (!col.from) return '';                      // 'team' and 'gap' columns
  var v = row[col.from];
  if (v == null || v === '') return '';

  if (col.format === 'salesOrder') {
    var s = String(v).trim();
    // Match the sheet's own convention rather than introducing a second one.
    return /^sales\s*order/i.test(s) ? s : 'Sales Order #' + s;
  }
  return v;
}

/**
 * Appends to the target tab, positioning each value by the TAB'S OWN header
 * order rather than ours. A team member who reorders columns gets their order
 * respected instead of a scrambled sheet.
 */
function appendRows_(target, rows) {
  assertNotHistory_(target.sheet);

  var width = Math.max(target.info.width, target.sheet.getLastColumn(), 1);
  var index = target.info.index;

  var values = rows.map(function (r) {
    var line = [];
    for (var i = 0; i < width; i++) line.push('');
    SHEET_MAP.forEach(function (col) {
      var at = index[col.header];
      if (at == null || at < 0 || at >= width) return;   // column not on this tab
      line[at] = cellValue_(col, r);
    });
    return line;
  });

  target.sheet.getRange(target.sheet.getLastRow() + 1, 1, values.length, width)
              .setValues(values);
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
/**
 * Builds one row's `column_values` from MONDAY_COLUMNS.
 *
 * Unmapped columns (id still null) and empty values are both omitted rather
 * than sent blank — Monday rejects some column types outright when handed an
 * empty string, and a blank write would also clobber a value a reviewer had
 * already typed on the board.
 */
function mondayColumnValues_(r) {
  var vals = {};

  MONDAY_COLUMNS.forEach(function (c) {
    if (!c.id) return;                       // not mapped yet — skip, don't send
    var raw = r[c.field];
    if (raw == null || raw === '') return;   // nothing to say about this field

    if (c.type === 'date') {
      // Monday wants YYYY-MM-DD. order_date already arrives in that shape from
      // BigQuery; the slice guards against a timestamp sneaking in.
      vals[c.id] = { date: String(raw).slice(0, 10) };
    } else if (c.type === 'long_text') {
      vals[c.id] = { text: String(raw) };
    } else {
      vals[c.id] = String(raw);
    }
  });

  return vals;
}

/** True once at least one column has been mapped to a real board id. */
function mondayIsMapped_() {
  return MONDAY_COLUMNS.some(function (c) { return !!c.id; });
}

function pushToMonday_(rows) {
  var out = { ok: 0, failed: 0, errors: [] };
  var boardId = optProp_('MONDAY_BOARD_ID');
  var apiKey = optProp_('MONDAY_API_KEY');

  if (!boardId || !apiKey) {
    out.errors.push('Monday is not configured (MONDAY_BOARD_ID / MONDAY_API_KEY) — ' +
                    'rows are on the sheet but were not pushed to the board.');
    out.failed = rows.length;
    return out;
  }

  if (!mondayIsMapped_()) {
    // Reported as a problem rather than pushed. Items WOULD be created — with
    // a name and not one populated column — and a board quietly filling up with
    // empty rows is worse than a clear message saying what is missing.
    out.errors.push('Monday board columns are not mapped yet: every id in ' +
                    'MONDAY_COLUMNS is still null, so items would arrive with a ' +
                    'name and nothing else. Run listMondayColumns() from the Apps ' +
                    'Script editor, paste the map it prints, and re-run. Rows are ' +
                    'safe on the sheet and will not be written again.');
    out.failed = rows.length;
    return out;
  }

  rows.forEach(function (r) {
    try {
      var name = (r.customer_name || 'Unknown customer') + ' — ' + (r.customer_part_no || '?');
      var vals = mondayColumnValues_(r);

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
      // Monday answers 200 with an "errors" array rather than an HTTP error, so
      // the status code alone would report success on a rejected mutation.
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

/**
 * Prints the board's real column ids, and a ready-to-paste MONDAY_COLUMNS.
 * ========================================================================
 *
 * Run this once from the editor after the holding board exists, with
 * MONDAY_API_KEY and MONDAY_BOARD_ID set. It reads nothing else, writes
 * nothing, creates nothing and emails nobody.
 *
 * It exists because Monday's column ids are per-board and are not the column
 * titles, so the map above cannot be written without looking at the board — and
 * a wrong id fails silently (200 with an `errors` array), which is a miserable
 * thing to debug by hand.
 *
 * The title match below is a best guess offered for convenience, not a
 * decision: CHECK the printed map before pasting it. A board with two columns
 * called something like "Email" will guess one of them.
 */
function listMondayColumns() {
  var boardId = optProp_('MONDAY_BOARD_ID');
  var apiKey = optProp_('MONDAY_API_KEY');
  if (!boardId || !apiKey) {
    Logger.log('Set MONDAY_BOARD_ID and MONDAY_API_KEY in Script Properties first.');
    return;
  }

  var res = UrlFetchApp.fetch('https://api.monday.com/v2', {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: apiKey, 'API-Version': '2023-10' },
    payload: JSON.stringify({
      query: 'query ($board: [ID!]) { boards (ids: $board) { name columns { id title type } } }',
      variables: { board: [boardId] }
    }),
    muteHttpExceptions: true
  });

  var body = JSON.parse(res.getContentText());
  if (body.errors) { Logger.log('Monday returned errors: %s', JSON.stringify(body.errors)); return; }

  var board = body.data && body.data.boards && body.data.boards[0];
  if (!board) { Logger.log('No board with id %s is visible to this token.', boardId); return; }

  Logger.log('Board: %s', board.name);
  Logger.log('%-28s %-22s %s', 'TITLE', 'ID', 'TYPE');
  board.columns.forEach(function (c) {
    Logger.log('%-28s %-22s %s', c.title, c.id, c.type);
  });

  // Best-effort title guess, purely to save typing.
  var guessFor = {
    order_number:      ['sales order', 'order', 'order number', 'so'],
    customer_part_no:  ['label sku', 'sku', 'customer part', 'part'],
    customer_name:     ['customer', 'client', 'account'],
    sales_rep_primary: ['sales rep', 'rep', 'bdm', 'salesperson'],
    customer_email:    ['email', 'e-mail'],
    job_note:          ['memo', 'note', 'job note', 'notes'],
    order_date:        ['date', 'order date', 'created']
  };

  Logger.log('');
  Logger.log('--- paste over MONDAY_COLUMNS, AFTER checking each id ---');
  Logger.log('var MONDAY_COLUMNS = [');
  MONDAY_COLUMNS.forEach(function (col) {
    var wanted = guessFor[col.field] || [];
    var hit = null;
    for (var w = 0; w < wanted.length && !hit; w++) {
      board.columns.forEach(function (c) {
        if (!hit && normHeader_(c.title) === normHeader_(wanted[w])) hit = c;
      });
    }
    Logger.log("  { id: %s, field: '%s', type: '%s' },%s",
      hit ? "'" + hit.id + "'" : 'null',
      col.field, col.type,
      hit ? '   // ' + hit.title + ' (' + hit.type + ')' : '   // NO MATCH — fill in by hand');
  });
  Logger.log('];');
}

// ── Run log, for the summary ───────────────────────────────────────────────
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
    quarantined: r.quarantined ? 1 : 0,
    warnings: r.warnings.length,
    errors: r.errors.length
  });

  // Two runs a day, and Monday's summary has to reach back over a weekend — 40
  // entries is about a fortnight, comfortably inside the property size cap.
  if (log.length > 40) log = log.slice(log.length - 40);
  props.setProperty('RUN_LOG', JSON.stringify(log));
}

/**
 * Runs since the last summary was sent, not "runs today".
 *
 * That difference is what makes the weekend work: syncs run seven days a week
 * but the summary only goes out on weekdays, so Monday's email has to cover
 * Saturday and Sunday as well or two days of activity are never reported to
 * anyone at all.
 */
function runsSinceLastSummary_() {
  var props = PropertiesService.getScriptProperties();
  var log = [];
  try { log = JSON.parse(props.getProperty('RUN_LOG') || '[]'); } catch (e) { return []; }

  var since = props.getProperty('LAST_SUMMARY_AT');
  var cutoff = since ? new Date(since) : startOfToday_();

  return log.filter(function (e) { return new Date(e.at) > cutoff; });
}

function startOfToday_() {
  var stamp = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy/MM/dd 00:00:00');
  return new Date(stamp);
}

// ── Email ──────────────────────────────────────────────────────────────────
//
// Vox Nutrition branding, matching templates/report.html in the repo root —
// the same Leaf Blue bar, Slate Navy Georgia headings and inline wordmark, so
// the pipeline's own emails and this script's emails read as one system.
//
// Every email ships an HTML body AND a plain-text body. The text version is
// not a courtesy: it is what a phone's notification preview and a screen
// reader actually use.
//
// Styles are inline attributes rather than a <style> block because Gmail
// strips <style> from the body of a received message.

var VOX_BLUE = '#1f8ccb';
var VOX_NAVY = '#215a7c';
var VOX_DIVIDER = '#aecfe6';

function shell_(title, subtitle, badge, bodyHtml) {
  return '' +
  '<div style="margin:0;padding:24px 0;background:#f4f7f9;font-family:Arial,Helvetica,sans-serif;color:#333;">' +
    '<div style="max-width:640px;margin:0 auto;background:#fff;border-top:5px solid ' + VOX_BLUE + ';' +
                'border-radius:4px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.05);">' +

      '<div style="padding:24px 28px 18px;border-bottom:2px solid ' + VOX_DIVIDER + ';">' +
        '<img src="cid:voxlogo" alt="Vox Nutrition" width="160" style="width:160px;height:auto;display:block;border:0;">' +
        '<p style="margin:14px 0 0;font-size:10px;letter-spacing:1.8px;text-transform:uppercase;color:#9ca3af;">' +
          'Label Design Queue &nbsp;&middot;&nbsp; Automated from Plex</p>' +
      '</div>' +

      '<div style="padding:24px 28px;">' +
        '<h1 style="font-family:Georgia,\'Times New Roman\',serif;font-size:20px;font-weight:700;' +
                   'color:' + VOX_NAVY + ';margin:0 0 4px;">' + esc_(title) + '</h1>' +
        '<p style="font-size:12px;color:#6b7280;margin:0 0 18px;font-family:\'Courier New\',monospace;">' +
          esc_(subtitle) + '</p>' +
        badge + bodyHtml +
      '</div>' +

      '<div style="padding:18px 28px;background:#fafafa;border-top:1px solid #eee;' +
                  'color:#888;font-size:11px;line-height:1.7;">' +
        '<b style="color:#6b7280;">Vox Nutrition</b> &mdash; Label Design queue<br>' +
        'New items land on the <b>holding</b> board, not the live one, so notes and reason ' +
        'codes can still be reviewed before anything moves across.<br>' +
        'Automated message. Please do not reply.' +
      '</div>' +

    '</div>' +
  '</div>';
}

function badge_(text, kind) {
  var c = {
    ok:    { bg: '#d1fae5', fg: '#065f46' },
    warn:  { bg: '#fef3c7', fg: '#92400e' },
    error: { bg: '#fee2e2', fg: '#991b1b' },
    quiet: { bg: '#e2eff8', fg: VOX_NAVY }
  }[kind] || { bg: '#e2eff8', fg: VOX_NAVY };

  return '<span style="display:inline-block;padding:6px 14px;border-radius:20px;font-size:12px;' +
         'font-weight:700;letter-spacing:0.4px;margin-bottom:18px;background:' + c.bg + ';' +
         'color:' + c.fg + ';">' + esc_(text) + '</span>';
}

/** A row of headline numbers. Table, not flexbox — Outlook stacks flexbox. */
function stats_(pairs) {
  var cells = pairs.map(function (p) {
    return '<td style="padding:12px 8px;text-align:center;border-right:1px solid #e8eef3;">' +
             '<span style="font-size:16px;font-weight:700;color:' + VOX_NAVY + ';display:block;' +
                          'margin-bottom:3px;">' + esc_(String(p[0])) + '</span>' +
             '<span style="font-size:10px;color:#9ca3af;text-transform:uppercase;' +
                          'letter-spacing:0.8px;">' + esc_(p[1]) + '</span>' +
           '</td>';
  }).join('');
  return '<table role="presentation" style="width:100%;border:1px solid ' + VOX_DIVIDER + ';' +
         'border-collapse:collapse;margin-bottom:22px;"><tr>' + cells + '</tr></table>';
}

function section_(label) {
  return '<div style="font-family:Georgia,\'Times New Roman\',serif;font-size:11px;font-weight:700;' +
         'text-transform:uppercase;letter-spacing:0.08em;color:' + VOX_NAVY + ';' +
         'border-bottom:1px solid ' + VOX_DIVIDER + ';padding:0 0 5px;margin:22px 0 10px;">' +
         esc_(label) + '</div>';
}

/** Takes HTML — callers escape their own interpolations. */
function para_(html) {
  return '<p style="font-size:13px;line-height:1.6;margin:0 0 12px;color:#374151;">' + html + '</p>';
}

function bullets_(items, color) {
  if (!items.length) {
    return '<p style="font-size:12px;color:#9ca3af;font-style:italic;margin:0 0 12px;">None</p>';
  }
  return '<ul style="margin:0 0 12px;padding-left:18px;font-size:12px;line-height:1.6;color:' +
         (color || '#374151') + ';">' +
         items.map(function (i) { return '<li style="padding:2px 0;">' + esc_(i) + '</li>'; }).join('') +
         '</ul>';
}

function esc_(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** The new rows, as a table. Capped — this is a notification, not a report. */
function rowsTable_(rows) {
  var head = ['Order', 'Label SKU', 'Customer', 'Sales Rep'];
  var html = '<table role="presentation" style="width:100%;border-collapse:collapse;font-size:12px;">' +
    '<tr>' + head.map(function (h) {
      return '<th style="text-align:left;padding:7px 6px;border-bottom:1px solid ' + VOX_DIVIDER + ';' +
             'color:' + VOX_NAVY + ';font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">' +
             esc_(h) + '</th>';
    }).join('') + '</tr>';

  rows.slice(0, 40).forEach(function (r, i) {
    var cells = [r.order_number, r.customer_part_no, r.customer_name, r.sales_rep_primary];
    html += '<tr style="background:' + (i % 2 ? '#f9fafb' : '#ffffff') + ';">' +
      cells.map(function (c) {
        return '<td style="padding:7px 6px;border-bottom:1px solid #f1f5f9;">' + esc_(c || '—') + '</td>';
      }).join('') + '</tr>';
  });
  html += '</table>';

  if (rows.length > 40) {
    html += '<p style="font-size:11px;color:#9ca3af;margin:8px 0 0;">…and ' +
            (rows.length - 40) + ' more, all on the sheet.</p>';
  }
  return html;
}

/**
 * Columns the sheet has and Plex did not fill, split by WHY.
 *
 * This is the "flag it so we can tell the team" part. The kinds are reported
 * separately because only some of them are a to-do: a 'team' column is meant
 * to be blank until a person reviews the row, and reporting that as a problem
 * every single run would train everyone to skip the section that also carries
 * the real gaps.
 */
function columnFlags_(headerReport) {
  var main = headerReport && headerReport.main;
  var gaps = [], team = [];

  SHEET_MAP.forEach(function (c) {
    if (main && main.index[c.header] == null) return;   // not on the tab at all
    if (c.kind === 'gap') gaps.push(c.header + ' — ' + c.note);
    if (c.kind === 'team') team.push(c.header);
  });

  return {
    gaps: gaps,
    team: team,
    missing: main ? main.missing.slice() : [],
    unknown: main ? main.unknown.slice() : []
  };
}

/** Technical email — every run, pass or fail. */
function sendRunEmail_(r) {
  var failed = r.errors.length > 0;
  var warned = r.warnings.length > 0;

  var subject = '[Label Design] ' +
    (failed ? 'FAILED — ' : r.quarantined ? 'HELD FOR REVIEW — ' : warned ? 'Check — ' : '') +
    r.written + ' new ' + (r.written === 1 ? 'row' : 'rows') +
    ' — ' + fmtDateTime_(r.started);

  var kind = failed ? 'error' : (warned || r.quarantined) ? 'warn' : 'ok';
  var state = failed ? 'PROBLEM'
            : r.quarantined ? 'HELD FOR REVIEW'
            : warned ? 'COMPLETED WITH WARNINGS' : 'OK';

  var html = stats_([
    [r.fetched, 'In queue'],
    [r.alreadyPresent, 'Already there'],
    [r.written, 'Written'],
    [r.pushed + (r.pushFailed ? ' / ' + r.pushFailed + ' failed' : ''), 'To Monday']
  ]);

  html += section_('Where the rows went');
  html += para_(r.written
    ? 'Written to <b>' + esc_(r.targetTab) + '</b>.' +
      (r.quarantined ? ' <b>Not</b> pushed to Monday — this run was held back.' : '')
    : 'Nothing new this run. The historical tab was read and never written, as always.');

  if (r.rows.length) {
    html += section_('New rows');
    html += rowsTable_(r.rows);
  }

  if (failed) {
    html += section_('Problems');
    html += bullets_(r.errors, '#991b1b');
    html += para_('Rows already written to the sheet are safe — the next run will not repeat them.');
  }

  if (warned) {
    html += section_('Worth knowing');
    html += bullets_(r.warnings, '#92400e');
  }

  var flags = columnFlags_(r.headerReport);
  if (flags.unknown.length || flags.missing.length || flags.gaps.length) {
    html += section_('Sheet columns — for the team');
    if (flags.unknown.length) {
      html += para_('<b>Columns on the tab that we do not fill.</b> Nothing is wrong with ' +
                    'them; this is so you know they stay blank on new rows:');
      html += bullets_(flags.unknown);
    }
    if (flags.missing.length) {
      html += para_('<b>Columns we can fill but the tab does not have.</b> Add the header ' +
                    'and the next run populates it:');
      html += bullets_(flags.missing);
    }
    if (flags.gaps.length) {
      html += para_('<b>Columns Plex does not currently supply.</b> Genuine gaps, not ' +
                    'review fields:');
      html += bullets_(flags.gaps);
    }
    if (flags.team.length) {
      html += para_('Filled in by a person during review, so blank is correct: <i>' +
                    esc_(flags.team.join(', ')) + '</i>.');
    }
  }

  html += section_('Run');
  html += para_('Dataset <b>' + esc_(dataProject_() + '.' + dataset_()) + '</b><br>' +
                'Started ' + esc_(fmtDateTime_(r.started)) + ', took ' +
                Math.round((r.finished - r.started) / 1000) + 's.<br>' +
                'This email is sent on <b>every</b> run, successful or not.');

  var text = [
    'Label Design sync — ' + fmtDateTime_(r.started),
    'Status: ' + state,
    '',
    'In the Plex queue:    ' + r.fetched,
    'Already on the sheet: ' + r.alreadyPresent,
    'Written as new:       ' + r.written + (r.targetTab ? '   -> ' + r.targetTab : ''),
    'Pushed to Monday:     ' + r.pushed + (r.pushFailed ? '   (' + r.pushFailed + ' FAILED)' : ''),
    ''
  ];
  r.rows.slice(0, 40).forEach(function (x) {
    text.push('  ' + x.order_number + '  ' + (x.customer_part_no || '—') + '  ' +
              (x.customer_name || ''));
  });
  if (r.errors.length) {
    text.push('', 'PROBLEMS:');
    r.errors.forEach(function (e) { text.push('  - ' + e); });
  }
  if (r.warnings.length) {
    text.push('', 'WORTH KNOWING:');
    r.warnings.forEach(function (w) { text.push('  - ' + w); });
  }
  text.push('', 'Dataset: ' + dataProject_() + '.' + dataset_());

  send_(TECHNICAL_TO_EMAILS, subject,
        shell_('Sync ' + state.toLowerCase(), dataProject_() + '.' + dataset_(),
               badge_(state, kind), html),
        text.join('\n'));
}

/**
 * Business summary — weekdays only, to the people who USE the queue.
 *
 * Weekday-only is a deliberate asymmetry with the sync itself, which runs seven
 * days a week: orders arrive at the weekend and the queue must be fresh on
 * Monday morning, but nobody wants a Sunday email about it. Monday's edition
 * therefore covers Saturday and Sunday too — see runsSinceLastSummary_().
 */
function sendDailySummary() {
  // Belt and braces. installTriggers() only installs Mon–Fri, but a trigger
  // added by hand should not produce a weekend email.
  var dow = new Date().getDay();  // 0 Sun … 6 Sat
  if (dow === 0 || dow === 6) {
    Logger.log('Weekend — no summary sent. Monday covers these runs.');
    return;
  }

  var runs = runsSinceLastSummary_();
  var written = 0, pushed = 0, problems = 0, fetched = 0, held = 0;
  runs.forEach(function (e) {
    written += e.written;
    pushed += e.pushed;
    problems += (e.errors || 0) + (e.pushFailed || 0);
    held += (e.quarantined || 0);
    fetched = Math.max(fetched, e.fetched);
  });

  var today = fmtDate_(new Date());
  var covering = dow === 1 ? 'since Friday, including the weekend' : 'since yesterday';
  var expected = dow === 1 ? 6 : 2;   // Monday covers Sat+Sun+Mon = 3 days x 2 runs

  var kind, state;
  if (!runs.length)  { kind = 'error'; state = 'NO SYNC RAN'; }
  else if (problems) { kind = 'warn';  state = 'PROBLEMS'; }
  else if (held)     { kind = 'warn';  state = 'HELD FOR REVIEW'; }
  else if (!written) { kind = 'quiet'; state = 'NOTHING NEW'; }
  else               { kind = 'ok';    state = written + ' NEW'; }

  var html = stats_([
    [written, 'New rows'],
    [pushed, 'To Monday'],
    [fetched, 'In queue'],
    [runs.length + ' / ' + expected, 'Syncs run']
  ]);

  html += section_('Where things stand');
  if (!runs.length) {
    html += para_('<b>No sync ran ' + esc_(covering) + '.</b> Nothing new has reached the ' +
                  'board, and anything sitting in Plex is still waiting. This is worth ' +
                  'telling Emilio about — it is not a quiet day, it is a stopped job.');
  } else if (problems) {
    html += para_('<b>' + problems + ' problem' + (problems === 1 ? '' : 's') + ' occurred.</b> ' +
                  'Some rows may be on the sheet but not on the Monday board. Emilio has the ' +
                  'detail in the per-run emails.');
  } else if (held) {
    html += para_('<b>One or more runs were held back for review.</b> Those rows are safe on a ' +
                  'dated review tab in the sheet and were deliberately not pushed to Monday ' +
                  'until someone has looked at them.');
  } else if (!written) {
    html += para_('<b>Nothing new ' + esc_(covering) + '</b> — every order in Label Design was ' +
                  'already on the board. That is a normal day, not a broken one.');
  } else {
    html += para_('<b>' + written + ' new ' + (written === 1 ? 'order' : 'orders') + '</b> reached ' +
                  'the holding board ' + esc_(covering) + '. The queue currently holds ' + fetched +
                  ' order lines in Label Design from the last 14 days.');
  }

  if (dow === 1) {
    html += para_('<i>Monday\'s summary covers Saturday and Sunday as well. The sync itself runs ' +
                  'every day so the queue is current when you arrive; only this email pauses at ' +
                  'the weekend.</i>');
  }

  var text = [
    'Label Design — ' + today,
    '',
    'Status: ' + state,
    '',
    'New rows added ' + covering + ': ' + written,
    'Pushed to Monday:       ' + pushed,
    'Currently in the queue: ' + fetched + '   (Label Design, last 14 days)',
    'Syncs run:              ' + runs.length + ' of an expected ' + expected
  ].join('\n');

  send_(SUMMARY_TO_EMAILS, '[Label Design] Summary — ' + today,
        shell_('Label Design — ' + today,
               'Daily summary for the sales and design teams',
               badge_(state, kind), html),
        text);

  PropertiesService.getScriptProperties().setProperty('LAST_SUMMARY_AT', new Date().toISOString());
}

/**
 * Sends with the Vox wordmark inline.
 *
 * The `from` alias is attempted and then dropped on failure rather than being
 * allowed to kill the send: MailApp rejects a `from` that is not a verified
 * alias on the sending account, and an email that arrives from the wrong
 * address is enormously better than one that does not arrive at all.
 */
function send_(to, subject, htmlBody, textBody) {
  if (!to.length) return;

  var payload = {
    to: to.join(','),
    subject: subject,
    htmlBody: htmlBody,
    body: textBody + '\n\n--\nAutomated from Plex. Please do not reply.',
    name: 'Vox Nutrition — Label Design',
    replyTo: FROM_ALIAS
  };

  var logo = voxLogoBlob_();
  if (logo) payload.inlineImages = { voxlogo: logo };

  try {
    payload.from = FROM_ALIAS;
    MailApp.sendEmail(payload);
  } catch (e) {
    Logger.log('Send with alias %s failed (%s); retrying as the script owner.', FROM_ALIAS, e);
    delete payload.from;
    MailApp.sendEmail(payload);
  }
}

function fmtDate_(d)     { return Utilities.formatDate(d, Session.getScriptTimeZone(), 'd MMM yyyy'); }
function fmtDateTime_(d) { return Utilities.formatDate(d, Session.getScriptTimeZone(), 'd MMM yyyy HH:mm z'); }

// ── Triggers ───────────────────────────────────────────────────────────────

/**
 * Run once from the editor. Set the script's timezone to America/Denver in
 * Project Settings FIRST — Apps Script hour triggers follow it, so the wrong
 * timezone silently runs the sync at the wrong times.
 *
 * Apps Script only guarantees the hour, not the minute, so "10:00" means
 * somewhere inside the 10:00 hour. That is exactly why the Cloud Run job is
 * scheduled at 09:30 and 13:30 — a full half-hour of headroom in front of each
 * window. Move one and you must move the other.
 *
 * THE SYNC RUNS EVERY DAY. THE SUMMARY RUNS MONDAY TO FRIDAY. Orders are
 * entered at the weekend and the queue has to be current on Monday morning,
 * but nobody wants a Sunday email — so Monday's summary covers the weekend
 * instead (runsSinceLastSummary_).
 *
 * NOTE this deletes every existing trigger in the project first. Don't run it
 * in a project that has other triggers you care about.
 */
function installTriggers() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });

  // Every day, both runs.
  [10, 14].forEach(function (h) {
    ScriptApp.newTrigger('syncNow').timeBased().everyDays(1).atHour(h).create();
  });

  // Weekdays only, 18:00.
  [ScriptApp.WeekDay.MONDAY, ScriptApp.WeekDay.TUESDAY, ScriptApp.WeekDay.WEDNESDAY,
   ScriptApp.WeekDay.THURSDAY, ScriptApp.WeekDay.FRIDAY].forEach(function (day) {
    ScriptApp.newTrigger('sendDailySummary').timeBased().onWeekDay(day).atHour(18).create();
  });

  Logger.log('Triggers installed: syncNow at 10 and 14 every day; ' +
             'sendDailySummary at 18 Monday to Friday.');
}

// ── Dry run (writes nothing, pushes nothing, emails nobody) ────────────────

function testReadOnly() {
  var rows = fetchQueue_();
  var tabs = readTabs_();
  var fresh = rows.filter(function (r) { return !tabs.keys[dedupeKey_(r)]; });
  var keyReport = assessKeys_(rows, fresh, tabs);

  Logger.log('jobs run in:      %s', project_());
  Logger.log('tables read from: %s.%s', dataProject_(), dataset_());
  Logger.log('in the queue:     %s', rows.length);
  Logger.log('already on sheet: %s', rows.length - fresh.length);
  Logger.log('would write:      %s', fresh.length);
  Logger.log('would go to:      %s', keyReport.alarm ? 'a dated REVIEW tab (held back)' : MAIN_TAB);

  if (tabs.report.main) {
    Logger.log('MONDAY tab — columns we do not fill:            %s',
               tabs.report.main.unknown.join(', ') || 'none');
    Logger.log('MONDAY tab — columns we could fill but it lacks: %s',
               tabs.report.main.missing.join(', ') || 'none');
  }
  Logger.log('archive rows read: %s', tabs.report.history.rowCount);

  tabs.report.warnings.forEach(function (w) { Logger.log('WARNING: %s', w); });
  keyReport.warnings.forEach(function (w) { Logger.log('WARNING: %s', w); });

  fresh.slice(0, 10).forEach(function (r) {
    Logger.log('  %s  %s  %s', r.order_number, r.customer_part_no, r.customer_name);
  });
}
