/**
 * Label Design queue — BigQuery → Sheet → Monday holding board
 * ============================================================
 *
 * Replaces a twice-daily manual loop: download a report from NetSuite, paste
 * it into a Google Sheet, check it for duplicates by hand, upload the new rows
 * to Monday.
 *
 * The Cloud Run job `plex-etl-label-design` refreshes `label_design_report` in
 * BigQuery at 09:30 and 13:30 Mountain. This script has TWO separate steps,
 * and only the first one is on a schedule:
 *
 *   1. CHECK  — `checkForNewOrdersAuto` (10:00/14:00, automatic) or
 *               `checkForNewOrdersManual` (the sheet's menu/button). Reads
 *               BigQuery, dedupes against `historical` + the MONDAY tab, and
 *               APPENDS new rows to the MONDAY tab. Never touches Monday.com,
 *               never touches `historical`.
 *
 *   2. PUSH   — `pushToMondayAndArchiveManual` (menu/button only — no
 *               trigger). Reads whatever is currently on the MONDAY tab
 *               (including anything the team has hand-typed into Reason
 *               Code / Label / Bottle Material / Prop 65 / LCR during
 *               review), creates one Monday item per row, then ARCHIVES each
 *               successfully-pushed row into `historical` and clears it off
 *               the MONDAY tab.
 *
 * Splitting these lets the team review a row on the sheet — filling in the
 * columns Plex can't — before it goes to Monday, instead of it landing on the
 * board the instant BigQuery sees it.
 *
 * ── WHY A CHECK/PUSH SPLIT NEEDS "BANK-GRADE" HANDLING ─────────────────────
 * Push does two things that must never happen more than once for the same
 * row (create a Monday item, archive a sheet row) using two calls (BigQuery/
 * UrlFetchApp, then SpreadsheetApp) that Apps Script cannot wrap in a single
 * transaction. Two mechanisms make that safe instead of merely assumed safe:
 *
 *   - `withLock_()` — a script-wide lock. Check and Push (manual or
 *     scheduled) can never run concurrently, so one can never read a sheet
 *     mid-write by the other. See LOCK_WAIT_MS.
 *   - The `_PUSH_STATE` ledger — a hidden tab that records a Monday item id
 *     the INSTANT its create_item call succeeds, before anything else
 *     happens. That write is the one true "commit point": a crash, timeout
 *     or double-click before it means nothing happened yet (safe to retry);
 *     after it, the row is skipped on any future Push rather than re-pushed,
 *     no matter how many times the button is pressed or how far archiving
 *     got. See pushToMondayAndArchive_() for the full two-phase walkthrough
 *     and README.md for the diagrams.
 *
 * ── THE ONE RULE, REVISED ───────────────────────────────────────────────────
 * The `historical` tab is never overwritten, reordered, or read back and
 * rewritten — hand-edited notes and reason codes there are never at risk.
 * It is APPENDED TO exactly once per row, only by appendToHistory_(), only
 * for a row the ledger confirms already reached Monday, and only from
 * pushToMondayAndArchive_(). Every OTHER write path in this file (the MONDAY
 * tab, a dated review tab) is blocked from touching it by
 * assertNotHistory_(), so a future edit to those paths cannot quietly start
 * writing history again.
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
 *   BQ_LOCATION        US                  BigQuery dataset location
 *   SHEET_ID           <the duplicate sheet, not the live one>
 *   MONDAY_API_KEY     <long-lived token>
 *   MONDAY_BOARD_ID    <from the board URL>
 *
 * Run `testReadOnly()` first — it writes nothing, pushes nothing and emails
 * nobody. Then `installTriggers()` once (installs the CHECK schedule and the
 * daily summary — Push has no trigger, it is menu/button only). Opening the
 * sheet after that shows a "Label Design Sync" menu with both buttons —
 * `onOpen()` builds it automatically; no further setup is needed for that.
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
  // 'team' columns have no `from` — Plex/BigQuery never fills them, a person
  // does, on the MONDAY tab, during review. `field` is still given so the
  // PUSH step (which reads the tab's CURRENT values, not the original
  // BigQuery row) and MONDAY_COLUMNS can both address the same value by the
  // same key. See historyCellValue_() and pushToMondayAndArchive_().
  { header: 'Reason Code',     from: null, field: 'reason_code',     kind: 'team' },
  { header: 'Label',           from: null, field: 'label',           kind: 'team' },
  { header: 'Bottle Material', from: null, field: 'bottle_material', kind: 'team' },
  { header: 'LCR',             from: null, field: 'lcr',             kind: 'team' },
  { header: 'Prop 65',         from: null, field: 'prop_65',         kind: 'team' }
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
// TEST BOARD ("Tablero nuevo") — pasted from listMondayColumns() 2026-09-14.
// Re-run listMondayColumns() and paste over this block again once the PROD
// board exists with its own column ids; a board recreated in Monday gets new
// ids even if the titles are identical.
var MONDAY_COLUMNS = [
  { id: 'date_mm766apm',      field: 'order_date',               type: 'date' },      // Date
  { id: 'text_mm768xfm',      field: 'order_number',             type: 'text' },      // Sales Order
  { id: 'long_text_mm76j9e7', field: 'job_note',                 type: 'long_text' }, // Memo
  { id: 'text_mm76xzde',      field: 'customer_name',            type: 'text' },      // Customer
  { id: 'email_mm76fdf6',     field: 'customer_email',           type: 'text' },      // Email
  { id: 'phone_mm76306g',     field: 'customer_phone',           type: 'text' },      // Phone
  { id: 'text_mm76c8ke',      field: 'wo_number',                type: 'text' },      // WO Number (manual / not in queue yet)
  { id: 'text_mm76d5qv',      field: 'item',                     type: 'text' },      // Item (manual / not in queue yet)
  { id: 'text_mm76ch44',      field: 'sales_rep_primary',        type: 'text' },      // Sales Rep
  { id: 'text_mm76k5a2',      field: 'customer_part_no',         type: 'text' },      // Label SKU
  { id: 'text_mm76eq1v',      field: 'customer_part_description', type: 'text' },     // Description
  { id: 'text_mm76pht2',      field: 'reason_code',              type: 'text' },      // Reason Code (manual review)
  { id: 'text_mm76e86f',      field: 'label',                    type: 'text' },      // Label (manual review)
  { id: 'text_mm76bem0',      field: 'bottle_material',          type: 'text' },      // Bottle Material (manual review)
  { id: 'text_mm76wsfk',      field: 'prop_65',                  type: 'text' },      // Prop 65 (manual review)
  { id: 'text_mm76tgzp',      field: 'lcr',                      type: 'text' }       // LCR (manual review)
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
function location_()    { return optProp_('BQ_LOCATION') || 'US'; }
function sheet_()       { return SpreadsheetApp.openById(prop_('SHEET_ID')); }

// ── Locking ─────────────────────────────────────────────────────────────────
//
// A script-wide lock (not per-user, not per-document): Check and Push must
// never interleave their sheet writes, no matter whether they were triggered
// by the clock, by one person clicking a button, or by two people clicking
// two buttons at once. LockService.getScriptLock() is shared across every
// execution of this project, which is exactly the scope needed here.

var LOCK_WAIT_MS = 25 * 1000;

/**
 * Runs `fn` only while holding the script lock, and always releases it
 * afterwards. If the lock cannot be obtained within LOCK_WAIT_MS, throws
 * WITHOUT calling `fn` at all — "someone else is mid-run" must never mean
 * "run anyway and hope the interleaving is harmless".
 */
function withLock_(taskName, fn) {
  var lock = LockService.getScriptLock();
  var got = lock.tryLock(LOCK_WAIT_MS);
  if (!got) {
    throw new Error('Could not start "' + taskName + '" — a Check or Push is already running ' +
                    'elsewhere. Nothing was touched; try again in a minute.');
  }
  try {
    return fn();
  } finally {
    lock.releaseLock();
  }
}

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

function partKey_(v) {
  return String(v == null ? '' : v).trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
}

function normalizeReasonCode_(raw, map) {
  var source = String(raw == null ? '' : raw).trim();
  if (!source) return '';

  var direct = source.toUpperCase();
  if (map && map[direct]) return String(map[direct]);

  var lower = source.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  if (map) {
    var keys = Object.keys(map);
    for (var i = 0; i < keys.length; i++) {
      var key = String(keys[i]).trim();
      var keyUpper = key.toUpperCase();
      var keySnake = keyUpper.replace(/[^A-Z0-9]+/g, ' ').trim();
      if (lower === keySnake.toLowerCase()) return String(map[keys[i]]);
      if (keySnake.toLowerCase().indexOf(lower) >= 0 || lower.indexOf(keySnake.toLowerCase()) >= 0) {
        return String(map[keys[i]]);
      }
    }
  }

  return source.replace(/\s+/g, ' ').trim().toUpperCase();
}

function applyPartAttributes_(row, attributeMap) {
  var out = row ? Object.assign({}, row) : {};
  var key = partKey_(out.customer_part_no || out.customer_part || out.label_sku || out.Label_SKU);
  if (!key || !attributeMap || !attributeMap[key]) return out;

  var attrs = attributeMap[key];
  var fill = function (field, value) {
    if (!field) return;
    if (!out[field] || String(out[field]).trim() === '') out[field] = value;
  };

  fill('prop_65', attrs.prop_65);
  fill('label', attrs.label);
  fill('bottle_material', attrs.bottle_material);
  fill('reason_code', attrs.reason_code);
  fill('lcr', attrs.lcr);

  return out;
}

function generateLcr_(seed) {
  var alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  var prefix = String(seed == null ? '' : seed).replace(/[^A-Z0-9]/gi, '').slice(0, 6).toUpperCase();
  var chars = [];
  for (var i = 0; i < 14; i++) {
    chars.push(alphabet.charAt(Math.floor(Math.random() * alphabet.length)));
  }
  if (prefix) {
    for (var j = 0; j < prefix.length && j < chars.length; j++) {
      chars[j] = prefix.charAt(j);
    }
  }
  return chars.join('');
}

function reviewAutoConfig_() {
  var reasonMap = {};
  var partMap = {};
  try { reasonMap = JSON.parse(optProp_('REASON_CODE_MAP_JSON') || '{}'); } catch (e) {}
  try { partMap = JSON.parse(optProp_('PART_ATTRIBUTE_MAP_JSON') || '{}'); } catch (e) {}
  var enabled = String(optProp_('AUTO_GENERATE_LCR') || 'false').toLowerCase() === 'true';
  return {
    reasonCodeMap: reasonMap,
    partAttributeMap: partMap,
    autoGenerateLcr: enabled
  };
}

function applyAutoReviewFields_(fields, config) {
  var out = fields ? Object.assign({}, fields) : {};
  var reasonMap = config && config.reasonCodeMap ? config.reasonCodeMap : {};
  var partMap = config && config.partAttributeMap ? config.partAttributeMap : {};

  if (out.job_note && !out.reason_code) {
    out.reason_code = normalizeReasonCode_(out.job_note, reasonMap);
  }

  var partAttrs = partMap[partKey_(out.customer_part_no || out.customer_part || out.label_sku || out.Label_SKU)];
  if (partAttrs) {
    if (!out.prop_65 || String(out.prop_65).trim() === '') out.prop_65 = partAttrs.prop_65 || '';
    if (!out.label || String(out.label).trim() === '') out.label = partAttrs.label || '';
    if (!out.bottle_material || String(out.bottle_material).trim() === '') out.bottle_material = partAttrs.bottle_material || '';
    if (!out.reason_code || String(out.reason_code).trim() === '') out.reason_code = normalizeReasonCode_(partAttrs.reason_code || '', reasonMap);
  }

  if ((config && config.autoGenerateLcr) && (!out.lcr || String(out.lcr).trim() === '')) {
    out.lcr = generateLcr_(out.customer_part_no || out.order_number || out.customer_name || 'LCR');
  }

  return out;
}

function dedupeKeyFromValues_(order, sku) {
  return orderToken_(order) + '|' + skuToken_(sku);
}

function dedupeKey_(row) {
  return dedupeKeyFromValues_(row.order_number, row.customer_part_no);
}

// ── The check ────────────────────────────────────────────────────────────
//
// Fetch → dedupe → append fresh rows to the MONDAY tab (or a dated REVIEW
// tab, if assessKeys_ is unhappy with the dedupe). NEVER pushes to Monday.com
// and NEVER touches `historical` — see pushToMondayAndArchive_() for that.

/** The shared core. Never throws — a failure has to reach an inbox/alert. */
function checkForNewOrders_() {
  var started = new Date();
  var result = {
    started: started,
    fetched: 0, alreadyPresent: 0, written: 0,
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
        result.warnings.push(
          'Rows were written to "' + target.name + '" instead of "' + MAIN_TAB + '". The ' +
          '"Push to Monday & Archive" button only ever reads "' + MAIN_TAB + '", so these ' +
          'rows will not reach Monday until a person reviews them and moves them onto "' +
          MAIN_TAB + '" by hand.');
      } else {
        result.warnings.push(
          result.written + ' new ' + (result.written === 1 ? 'row is' : 'rows are') +
          ' waiting on "' + target.name + '" for review, then the "Push to Monday & Archive" ' +
          'button.');
      }
    }
  } catch (e) {
    result.errors.push(String(e && e.message ? e.message : e));
    Logger.log('checkForNewOrders_ failed: %s', e);
  }

  result.finished = new Date();
  recordRun_(result, 'check');
  return result;
}

/** A same-shaped result for when the lock itself could not be obtained. */
function lockFailureResult_(e) {
  return {
    started: new Date(), finished: new Date(),
    fetched: 0, alreadyPresent: 0, written: 0,
    targetTab: '', quarantined: false,
    rows: [], errors: [String(e && e.message ? e.message : e)], warnings: [],
    headerReport: null, keyReport: null
  };
}

/**
 * The SCHEDULED entry point (10:00 / 14:00, every day — see installTriggers).
 * No UI to talk to from a time trigger, so this only ever emails.
 */
function checkForNewOrdersAuto() {
  var result;
  try {
    result = withLock_('Check for new orders (scheduled)', checkForNewOrders_);
  } catch (e) {
    result = lockFailureResult_(e);
  }
  sendRunEmail_(result, 'auto');
  return result;
}

/**
 * The MENU/BUTTON entry point — "1) Check for new orders" in the sheet's
 * "Label Design Sync" menu (see onOpen()). Same core as the scheduled run,
 * plus an on-screen summary so whoever clicked it doesn't have to wait on an
 * email to know what happened.
 */
function checkForNewOrdersManual() {
  var ui = safeUi_();

  var result;
  try {
    result = withLock_('Check for new orders', checkForNewOrders_);
  } catch (e) {
    result = lockFailureResult_(e);
  }
  sendRunEmail_(result, 'manual');

  if (ui) {
    var lines = [
      'In the queue:    ' + result.fetched,
      'Already known:   ' + result.alreadyPresent,
      'Written as new:  ' + result.written + (result.targetTab ? '   -> ' + result.targetTab : '')
    ];
    if (result.quarantined) {
      lines.push('', 'HELD FOR REVIEW — the dedupe looked wrong for this batch. See the email ' +
                     'and the dated REVIEW tab before moving anything to ' + MAIN_TAB + '.');
    }
    if (result.errors.length) lines.push('', 'PROBLEMS:', result.errors.join('\n'));
    ui.alert('Check for new orders', lines.join('\n'), ui.ButtonSet.OK);
  }

  return result;
}

/**
 * SpreadsheetApp.getUi() throws when there is no user interface to attach to
 * (a time-based trigger, or the script editor's Run button). Every menu
 * function calls this rather than the raw API so a lock failure or a stray
 * manual Run from the editor degrades to "email only" instead of throwing.
 */
function safeUi_() {
  try { return SpreadsheetApp.getUi(); } catch (e) { return null; }
}

/**
 * Builds the "Label Design Sync" menu — the two buttons the team asked for.
 * A custom menu is the standard, reliable way to give a Sheet a "button" that
 * runs Apps Script: it works for every viewer with no image/Drawing to keep
 * in sync. (A Drawing assigned to `checkForNewOrdersManual` /
 * `pushToMondayAndArchiveManual` works too, side by side with this menu, if a
 * literal on-sheet button is wanted as well — see README.md.)
 */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Label Design Sync')
    .addItem('1) Check for new orders', 'checkForNewOrdersManual')
    .addItem('2) Push to Monday & Archive', 'pushToMondayAndArchiveManual')
    .addSeparator()
    .addItem('Dry run (read-only, logs only)', 'testReadOnly')
    .addToUi();
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

  // `location` is a field on the QueryRequest body itself, not a separate
  // "optional args" parameter — BigQuery.Jobs.query(resource, projectId) only
  // takes two arguments. Passing it any other way is what produced
  // "Cannot parse  as CloudRegion." (the location silently arrived empty).
  var job = BigQuery.Jobs.query(
    { query: sql, useLegacySql: false, timeoutMs: 60000, location: location_() },
    project_());

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

/**
 * Like cellValue_(), but reads a plain `fields` object keyed by `col.field ||
 * col.from` instead of a raw BigQuery row. Used only by appendToHistory_(),
 * because a row being archived may carry values a PERSON typed into a 'team'
 * column (Reason Code, Label, Bottle Material, Prop 65, LCR) that BigQuery
 * never supplied and that cellValue_() would therefore always blank.
 */
function historyCellValue_(col, fields) {
  var key = col.field || col.from;
  if (!key) return '';
  var v = fields[key];
  if (v == null || v === '') return '';

  if (col.format === 'salesOrder') {
    var s = String(v).trim();
    return /^sales\s*order/i.test(s) ? s : 'Sales Order #' + s;
  }
  return v;
}

/**
 * THE ONE SANCTIONED WRITE TO `historical`.
 * ============================================================================
 * Every other write path in this file is stopped from touching this tab by
 * assertNotHistory_() — this function is the deliberate, sole exception, and
 * it earns that by how it is called rather than by a comment promising to be
 * careful:
 *
 *   - Called ONLY from pushToMondayAndArchive_(), ONLY with rows the
 *     `_PUSH_STATE` ledger confirms already have a real Monday item id.
 *   - APPEND ONLY. Nothing already on the tab is read back, edited or
 *     reordered — a note typed in two years ago is never touched.
 *   - The caller has ALREADY checked each row's key against what's on this
 *     tab (readKeysFrom_) before calling this, so a row archived by an
 *     earlier, interrupted run is never appended a second time.
 */
function appendToHistory_(historyTab, historyInfo, rowsOfFields) {
  var width = Math.max(historyInfo.width, historyTab.getLastColumn(), 1);
  var index = historyInfo.index;

  var values = rowsOfFields.map(function (fields) {
    var line = [];
    for (var i = 0; i < width; i++) line.push('');
    SHEET_MAP.forEach(function (col) {
      var at = index[col.header];
      if (at == null || at < 0 || at >= width) return;
      line[at] = historyCellValue_(col, fields);
    });
    return line;
  });

  historyTab.getRange(historyTab.getLastRow() + 1, 1, values.length, width).setValues(values);
}

// ── Monday ─────────────────────────────────────────────────────────────────

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

/**
 * One row, one Monday item. Returns {ok, itemId} or {ok: false, error}
 * rather than throwing, and never touches the sheet — pushToMondayAndArchive_
 * decides what to do with the result, including writing the ledger entry that
 * makes this row's push permanent.
 *
 * `fields` is keyed by `col.from || col.field` (see SHEET_MAP), so it works
 * identically whether it came straight from BigQuery (the old flow) or from
 * the MONDAY tab's current, possibly team-edited values (the new flow) —
 * mondayColumnValues_() cannot tell the difference and does not need to.
 */
function pushOneToMonday_(fields) {
  var boardId = optProp_('MONDAY_BOARD_ID');
  var apiKey = optProp_('MONDAY_API_KEY');

  try {
    var autoConfig = reviewAutoConfig_();
    fields = applyAutoReviewFields_(fields, autoConfig);
    var name = (fields.customer_name || 'Unknown customer') + ' — ' + (fields.customer_part_no || '?');
    var vals = mondayColumnValues_(fields);

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

    var itemId = body.data && body.data.create_item && body.data.create_item.id;
    if (!itemId) throw new Error('Monday returned no item id: ' + res.getContentText());

    return { ok: true, itemId: itemId };
  } catch (e) {
    Logger.log('Monday push failed: %s', e);
    return { ok: false, error: String(e && e.message ? e.message : e) };
  }
}

// ── Push ledger — the write-ahead log for the two-phase Monday push ────────
//
// A hidden tab the team never needs to look at. It exists for one reason: to
// make it IMPOSSIBLE for the same row to create two Monday items, no matter
// how many times the Push button is clicked, how many people click it, or
// where a run gets interrupted.
//
// The rule: a row is pushed to Monday if and only if its dedupe key has no
// entry here yet. The entry is written the INSTANT create_item succeeds —
// before the row is touched again — so that write is the one true commit
// point. Everything before it is safe to redo from scratch; everything after
// it must never repeat the push, only finish archiving.
//
// The ledger should be EMPTY between Push runs. A non-empty ledger found at
// the START of a run means a previous run got interrupted between pushing and
// archiving — see pushToMondayAndArchive_(), which finishes that job rather
// than re-pushing.

var PUSH_STATE_TAB = '_PUSH_STATE';
var PUSH_STATE_HEADERS = ['dedupe_key', 'order_number', 'customer_part_no', 'monday_item_id', 'pushed_at'];

/** Gets or creates the ledger tab, hidden so it never shows up to the team. */
function pushStateTab_() {
  var ss = sheet_();
  var tab = ss.getSheetByName(PUSH_STATE_TAB);
  if (!tab) {
    tab = ss.insertSheet(PUSH_STATE_TAB);
    tab.getRange(1, 1, 1, PUSH_STATE_HEADERS.length).setValues([PUSH_STATE_HEADERS]);
    try { tab.hideSheet(); } catch (e) { /* fine if this account can't hide sheets */ }
  }
  return tab;
}

/** dedupe_key -> {itemId, pushedAt, rowIndex}. rowIndex is this tab's own row, for cleanup. */
function readPushState_(tab) {
  var lastRow = tab.getLastRow();
  var out = {};
  if (lastRow < 2) return out;

  tab.getRange(2, 1, lastRow - 1, PUSH_STATE_HEADERS.length).getValues().forEach(function (r, i) {
    var key = r[0];
    if (!key) return;
    out[key] = { itemId: r[3], pushedAt: r[4], rowIndex: i + 2 };
  });
  return out;
}

/**
 * THE COMMIT POINT. Called once, immediately, the moment pushOneToMonday_
 * reports success — never before, never batched, never delayed until after
 * other rows are processed. One appendRow() call is what makes "Monday has
 * this item" durable and re-run-proof.
 */
function recordPushState_(tab, key, fields, itemId) {
  tab.appendRow([key, fields.order_number || '', fields.customer_part_no || '',
                itemId, new Date().toISOString()]);
}

/** Removes ledger entries for rows that have just been safely archived. */
function clearPushState_(tab, keys) {
  if (!keys.length) return;
  var ledger = readPushState_(tab);
  var rowIndexes = [];
  keys.forEach(function (k) { if (ledger[k]) rowIndexes.push(ledger[k].rowIndex); });

  // Highest row first — deleting a row shifts every row below it.
  rowIndexes.sort(function (a, b) { return b - a; }).forEach(function (rowIndex) {
    tab.deleteRow(rowIndex);
  });
}

/**
 * PUSH & ARCHIVE — the manual, two-phase operation behind the second button.
 * ============================================================================
 * Reads the MONDAY tab as it stands right now (including anything the team
 * has hand-typed into the review columns), and for every row:
 *
 *   PHASE 1 — PUSH (idempotent)
 *     If the ledger already has an item id for this row's key, skip pushing
 *     (it was already done, possibly by an interrupted earlier run) and just
 *     remember the id. Otherwise call Monday's create_item; on success,
 *     record the id in the ledger IMMEDIATELY (see recordPushState_) before
 *     moving to the next row. A failure here leaves the row exactly as it
 *     was — still on the MONDAY tab, no ledger entry, eligible to be retried
 *     next time the button is pressed.
 *
 *   PHASE 2 — ARCHIVE (idempotent)
 *     Every row that now has a ledger item id is eligible. If its key is
 *     already on `historical` (an earlier run got this far before being
 *     interrupted), it is NOT appended again — only cleared. Otherwise all
 *     eligible rows are appended to `historical` in one batch write; only
 *     once that write returns without throwing are the corresponding rows
 *     deleted from the MONDAY tab (bottom row first, so earlier row numbers
 *     stay valid), and their ledger entries removed.
 *
 * If the archive write itself fails, nothing is deleted and nothing is lost:
 * the rows stay on the MONDAY tab, their ledger entries stay put, and the
 * next Push run picks up exactly where this one stopped.
 *
 * Always run inside withLock_() by its callers — see
 * pushToMondayAndArchiveManual().
 */
function pushToMondayAndArchive_() {
  var result = {
    started: new Date(), finished: null,
    candidates: 0, pushed: 0, alreadyPushed: 0, pushFailed: 0,
    archived: 0, staleCleared: 0, remaining: 0,
    errors: [], warnings: []
  };

  if (!optProp_('MONDAY_BOARD_ID') || !optProp_('MONDAY_API_KEY')) {
    result.errors.push('Monday is not configured (MONDAY_BOARD_ID / MONDAY_API_KEY) — nothing ' +
                       'was pushed. Rows are untouched on "' + MAIN_TAB + '".');
    result.finished = new Date();
    return result;
  }
  if (!mondayIsMapped_()) {
    result.errors.push('Monday board columns are not mapped yet: every id in MONDAY_COLUMNS is ' +
                       'still null. Run listMondayColumns() from the editor, paste the map it ' +
                       'prints, and try again. Nothing was pushed; rows are untouched on "' +
                       MAIN_TAB + '".');
    result.finished = new Date();
    return result;
  }

  var ss = sheet_();
  var mainTab = findTab_(ss, MAIN_TAB_ALIASES);
  if (!mainTab) {
    result.warnings.push('No "' + MAIN_TAB + '" tab found — nothing to push.');
    result.finished = new Date();
    recordRun_(result, 'push');
    return result;
  }

  var lastRow = mainTab.getLastRow();
  var lastCol = Math.max(mainTab.getLastColumn(), 1);
  var headers = lastRow >= 1 ? mainTab.getRange(1, 1, 1, lastCol).getDisplayValues()[0] : [];
  var info = resolveHeaders_(mainTab.getName(), headers);

  if (!info.hasKeys) {
    result.errors.push('The "' + mainTab.getName() + '" tab is missing its "' + KEY_HEADERS.order +
                       '" / "' + KEY_HEADERS.sku + '" columns — refusing to push. Nothing was ' +
                       'touched.');
    result.finished = new Date();
    recordRun_(result, 'push');
    return result;
  }

  var dataRowCount = Math.max(lastRow - 1, 0);
  if (dataRowCount === 0) {
    result.finished = new Date();
    recordRun_(result, 'push');
    return result;
  }

  var values = mainTab.getRange(2, 1, dataRowCount, lastCol).getDisplayValues();

  // One snapshot per row, keyed by its CURRENT sheet row number (2-based) —
  // taken up front, before anything is deleted, so row numbers used for
  // deletion later cannot be invalidated by an in-between write.
  var rows = [];
  values.forEach(function (v, i) {
    var order = v[info.index[KEY_HEADERS.order]];
    var sku = v[info.index[KEY_HEADERS.sku]];
    if (normHeader_(order) === '' && normHeader_(sku) === '') return;   // blank row

    var fields = {};
    SHEET_MAP.forEach(function (col) {
      var at = info.index[col.header];
      var key = col.field || col.from;
      if (key) fields[key] = at != null ? v[at] : '';
    });

    rows.push({ sheetRow: i + 2, key: dedupeKeyFromValues_(order, sku), fields: fields });
  });
  result.candidates = rows.length;
  if (!rows.length) {
    result.finished = new Date();
    recordRun_(result, 'push');
    return result;
  }

  var ledgerTab = pushStateTab_();
  var ledger = readPushState_(ledgerTab);

  // ── Phase 1: push ────────────────────────────────────────────────────────
  rows.forEach(function (r) {
    var entry = ledger[r.key];
    if (entry) {
      result.alreadyPushed++;
      r.itemId = entry.itemId;
      return;
    }

    var push = pushOneToMonday_(r.fields);
    if (push.ok) {
      recordPushState_(ledgerTab, r.key, r.fields, push.itemId);   // commit point
      ledger[r.key] = { itemId: push.itemId, pushedAt: new Date().toISOString() };
      r.itemId = push.itemId;
      result.pushed++;
    } else {
      result.pushFailed++;
      result.errors.push('Monday push failed for ' + (r.fields.order_number || r.key) + ': ' +
                         push.error);
    }
  });

  // ── Phase 2: archive ─────────────────────────────────────────────────────
  var historyTab = findTab_(ss, HISTORY_TAB_ALIASES);
  if (!historyTab) {
    result.errors.push('No "' + HISTORY_TAB + '" tab found — pushed rows are staying on "' +
                       mainTab.getName() + '" rather than being archived blind. Nothing was ' +
                       'lost; fix the tab and press the button again.');
    result.finished = new Date();
    recordRun_(result, 'push');
    return result;
  }

  var historyKeys = {};
  var historyInfo = readKeysFrom_(historyTab, historyKeys);
  if (!historyInfo.hasKeys) {
    result.errors.push('The "' + historyTab.getName() + '" tab is missing its "' +
                       KEY_HEADERS.order + '" / "' + KEY_HEADERS.sku + '" columns — refusing to ' +
                       'archive blind. Pushed rows are staying on "' + mainTab.getName() + '".');
    result.finished = new Date();
    recordRun_(result, 'push');
    return result;
  }

  var eligible = rows.filter(function (r) { return !!r.itemId; });
  var toAppend = eligible.filter(function (r) { return !historyKeys[r.key]; });
  var stale = eligible.filter(function (r) { return historyKeys[r.key]; });

  if (toAppend.length) {
    try {
      appendToHistory_(historyTab, historyInfo, toAppend.map(function (r) { return r.fields; }));
      result.archived = toAppend.length;
    } catch (e) {
      result.errors.push('Writing to "' + historyTab.getName() + '" failed: ' + e + '. Pushed ' +
                         'rows are staying on "' + mainTab.getName() + '" — nothing was deleted, ' +
                         'nothing was lost. Press the button again once this is fixed.');
      result.finished = new Date();
      recordRun_(result, 'push');
      return result;
    }
  }
  result.staleCleared = stale.length;

  // Only now — the archive write has already succeeded — is it safe to clear
  // rows off the MONDAY tab. Bottom row first, so earlier row numbers in this
  // same batch stay valid mid-delete.
  var clearedKeys = [];
  eligible.slice().sort(function (a, b) { return b.sheetRow - a.sheetRow; }).forEach(function (r) {
    mainTab.deleteRow(r.sheetRow);
    clearedKeys.push(r.key);
  });
  clearPushState_(ledgerTab, clearedKeys);

  result.remaining = rows.length - eligible.length;
  result.finished = new Date();
  recordRun_(result, 'push');
  return result;
}

/**
 * The MENU/BUTTON entry point — "2) Push to Monday & Archive". No trigger
 * calls this; it only ever runs from the sheet's menu or an assigned Drawing
 * button (see onOpen(), README.md).
 */
function pushToMondayAndArchiveManual() {
  var ui = safeUi_();

  var result;
  try {
    result = withLock_('Push to Monday & Archive', pushToMondayAndArchive_);
  } catch (e) {
    result = {
      started: new Date(), finished: new Date(),
      candidates: 0, pushed: 0, alreadyPushed: 0, pushFailed: 0,
      archived: 0, staleCleared: 0, remaining: 0,
      errors: [String(e && e.message ? e.message : e)], warnings: []
    };
  }

  sendPushEmail_(result);

  if (ui) {
    var lines = [
      'On the MONDAY tab: ' + result.candidates,
      'Pushed to Monday:  ' + result.pushed +
        (result.alreadyPushed ? '  (+' + result.alreadyPushed + ' already pushed, resumed)' : ''),
      'Archived:          ' + result.archived,
      'Left on the sheet: ' + result.remaining
    ];
    if (result.pushFailed) lines.push(result.pushFailed + ' push(es) FAILED — left on the sheet, will retry next time.');
    if (result.errors.length) lines.push('', 'PROBLEMS:', result.errors.join('\n'));
    ui.alert('Push to Monday & Archive', lines.join('\n'), ui.ButtonSet.OK);
  }

  return result;
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

  Logger.log('Board: ' + board.name);
  Logger.log('TITLE                        ID                     TYPE');
  board.columns.forEach(function (c) {
    Logger.log(c.title + ' | ' + c.id + ' | ' + c.type);
  });

  // Best-effort title guess, purely to save typing.
  var guessFor = {
    order_date:             ['date', 'order date', 'created'],
    order_number:           ['sales order', 'order', 'order number', 'so'],
    job_note:               ['memo', 'note', 'job note', 'notes'],
    customer_name:          ['customer', 'client', 'account'],
    customer_email:         ['email', 'e-mail'],
    customer_phone:         ['phone', 'phone number'],
    wo_number:              ['wo number', 'work order', 'work order number'],
    item:                   ['item'],
    sales_rep_primary:      ['sales rep', 'rep', 'bdm', 'salesperson'],
    customer_part_no:       ['label sku', 'sku', 'customer part', 'part'],
    customer_part_description: ['description', 'item description', 'label description'],
    reason_code:            ['reason code'],
    label:                  ['label'],
    bottle_material:        ['bottle material'],
    prop_65:                ['prop 65', 'prop65'],
    lcr:                    ['lcr']
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

function recordRun_(r, kind) {
  var props = PropertiesService.getScriptProperties();
  var log = [];
  try { log = JSON.parse(props.getProperty('RUN_LOG') || '[]'); } catch (e) { log = []; }

  var entry = {
    at: r.started.toISOString(),
    kind: kind || 'check',
    warnings: (r.warnings || []).length,
    errors: (r.errors || []).length
  };
  if (entry.kind === 'push') {
    entry.candidates = r.candidates; entry.pushed = r.pushed; entry.alreadyPushed = r.alreadyPushed;
    entry.pushFailed = r.pushFailed; entry.archived = r.archived; entry.remaining = r.remaining;
  } else {
    entry.fetched = r.fetched; entry.written = r.written; entry.dupes = r.alreadyPresent;
    entry.quarantined = r.quarantined ? 1 : 0;
  }
  log.push(entry);

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

/** Technical email — every Check run, pass or fail. Never covers Push. */
function sendRunEmail_(r, mode) {
  var failed = r.errors.length > 0;
  var warned = r.warnings.length > 0;

  var subject = '[Label Design] ' +
    (failed ? 'FAILED — ' : r.quarantined ? 'HELD FOR REVIEW — ' : warned ? 'Check — ' : '') +
    r.written + ' new ' + (r.written === 1 ? 'row' : 'rows') +
    (mode === 'manual' ? ' (manual)' : '') +
    ' — ' + fmtDateTime_(r.started);

  var kind = failed ? 'error' : (warned || r.quarantined) ? 'warn' : 'ok';
  var state = failed ? 'PROBLEM'
            : r.quarantined ? 'HELD FOR REVIEW'
            : warned ? 'COMPLETED WITH WARNINGS' : 'OK';

  var html = stats_([
    [r.fetched, 'In queue'],
    [r.alreadyPresent, 'Already there'],
    [r.written, 'Written'],
    [r.quarantined ? 'HELD' : r.written, 'Awaiting push']
  ]);

  html += section_('Where the rows went');
  html += para_(r.written
    ? 'Written to <b>' + esc_(r.targetTab) + '</b>.' +
      (r.quarantined
        ? ' <b>Held for review</b> — a person needs to look before these can be pushed.'
        : ' Waiting there for someone to press <b>"Push to Monday &amp; Archive"</b> — this ' +
          'step never pushes on its own.')
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
                'This is a <b>check</b> — it never pushes to Monday. That only happens when ' +
                'someone presses "Push to Monday &amp; Archive" in the sheet\'s menu.');

  var text = [
    'Label Design check — ' + fmtDateTime_(r.started) + (mode === 'manual' ? ' (manual)' : ''),
    'Status: ' + state,
    '',
    'In the Plex queue:    ' + r.fetched,
    'Already on the sheet: ' + r.alreadyPresent,
    'Written as new:       ' + r.written + (r.targetTab ? '   -> ' + r.targetTab : ''),
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
        shell_('Check ' + state.toLowerCase(), dataProject_() + '.' + dataset_(),
               badge_(state, kind), html),
        text.join('\n'));
}

/**
 * Technical email for a Push & Archive run — always manual, so always sent
 * (there is no daily-summary equivalent that would otherwise cover it).
 */
function sendPushEmail_(r) {
  var failed = r.errors.length > 0;
  var kind = failed ? 'error' : (r.pushFailed ? 'warn' : 'ok');
  var state = failed ? 'PROBLEM' : r.pushFailed ? 'COMPLETED WITH FAILURES' : 'OK';

  var subject = '[Label Design] Push & Archive — ' +
    (failed ? 'FAILED — ' : '') +
    r.pushed + ' pushed, ' + r.archived + ' archived — ' + fmtDateTime_(r.started);

  var html = stats_([
    [r.candidates, 'On MONDAY tab'],
    [r.pushed, 'Pushed'],
    [r.alreadyPushed, 'Already pushed (resumed)'],
    [r.archived, 'Archived']
  ]);

  html += section_('What happened');
  html += para_(
    r.pushed + ' item(s) created on Monday, ' + r.archived + ' row(s) moved to "' +
    HISTORY_TAB + '" and removed from "' + MAIN_TAB + '".' +
    (r.alreadyPushed ? ' ' + r.alreadyPushed + ' row(s) had already been pushed by an earlier, ' +
      'interrupted run and were not pushed a second time.' : '') +
    (r.staleCleared ? ' ' + r.staleCleared + ' row(s) were already on "' + HISTORY_TAB +
      '" from an earlier interrupted run and were not duplicated there.' : '') +
    (r.remaining ? ' ' + r.remaining + ' row(s) remain on "' + MAIN_TAB + '" — see Problems.' : '')
  );

  if (r.pushFailed) {
    html += section_('Push failures — left on the sheet, safe to retry');
    html += bullets_(r.errors.filter(function (e) { return /Monday push failed/.test(e); }), '#92400e');
  }

  var otherErrors = r.errors.filter(function (e) { return !/Monday push failed/.test(e); });
  if (otherErrors.length) {
    html += section_('Problems');
    html += bullets_(otherErrors, '#991b1b');
    html += para_('Nothing already pushed or archived was lost or duplicated — see README.md ' +
                  'for exactly what is guaranteed at each step.');
  }

  html += section_('Run');
  html += para_('Started ' + esc_(fmtDateTime_(r.started)) + ', took ' +
                Math.round((r.finished - r.started) / 1000) + 's.<br>' +
                'Triggered manually from the sheet\'s "Label Design Sync" menu. There is no ' +
                'automatic trigger for this step.');

  var text = [
    'Label Design Push & Archive — ' + fmtDateTime_(r.started),
    'Status: ' + state,
    '',
    'On MONDAY tab:            ' + r.candidates,
    'Pushed to Monday:         ' + r.pushed,
    'Already pushed (resumed): ' + r.alreadyPushed,
    'Push failed:              ' + r.pushFailed,
    'Archived:                 ' + r.archived,
    'Already archived (stale): ' + r.staleCleared,
    'Remaining on sheet:       ' + r.remaining,
    ''
  ];
  if (r.errors.length) {
    text.push('PROBLEMS:');
    r.errors.forEach(function (e) { text.push('  - ' + e); });
  }

  send_(TECHNICAL_TO_EMAILS, subject,
        shell_('Push & Archive ' + state.toLowerCase(), dataProject_() + '.' + dataset_(),
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
  var written = 0, pushed = 0, archived = 0, problems = 0, fetched = 0, held = 0;
  runs.forEach(function (e) {
    problems += (e.errors || 0);
    if (e.kind === 'push') {
      pushed += (e.pushed || 0);
      archived += (e.archived || 0);
      problems += (e.pushFailed || 0);
    } else {
      written += (e.written || 0);
      held += (e.quarantined || 0);
      fetched = Math.max(fetched, e.fetched || 0);
    }
  });
  var checkRuns = runs.filter(function (e) { return e.kind !== 'push'; });

  var today = fmtDate_(new Date());
  var covering = dow === 1 ? 'since Friday, including the weekend' : 'since yesterday';
  var expected = dow === 1 ? 6 : 2;   // Monday covers Sat+Sun+Mon = 3 days x 2 checks

  var kind, state;
  if (!checkRuns.length) { kind = 'error'; state = 'NO CHECK RAN'; }
  else if (problems)     { kind = 'warn';  state = 'PROBLEMS'; }
  else if (held)         { kind = 'warn';  state = 'HELD FOR REVIEW'; }
  else if (!written)     { kind = 'quiet'; state = 'NOTHING NEW'; }
  else                   { kind = 'ok';    state = written + ' NEW'; }

  var html = stats_([
    [written, 'New rows'],
    [pushed, 'Pushed'],
    [archived, 'Archived'],
    [checkRuns.length + ' / ' + expected, 'Checks run']
  ]);

  html += section_('Where things stand');
  if (!checkRuns.length) {
    html += para_('<b>No check ran ' + esc_(covering) + '.</b> New Plex orders may be waiting ' +
                  'and no one would know it yet. This is worth telling Emilio about — it is not ' +
                  'a quiet day, it is a stopped job.');
  } else if (problems) {
    html += para_('<b>' + problems + ' problem' + (problems === 1 ? '' : 's') + ' occurred.</b> ' +
                  'Some rows may be on the sheet but not on the Monday board, or a push may have ' +
                  'failed. Emilio has the detail in the per-run emails.');
  } else if (held) {
    html += para_('<b>One or more checks were held back for review.</b> Those rows are safe on a ' +
                  'dated review tab in the sheet and were deliberately not written to "' +
                  MAIN_TAB + '" until someone has looked at them.');
  } else if (!written) {
    html += para_('<b>Nothing new ' + esc_(covering) + '</b> — every order in Label Design was ' +
                  'already known. That is a normal day, not a broken one.');
  } else {
    html += para_('<b>' + written + ' new ' + (written === 1 ? 'order' : 'orders') + '</b> reached ' +
                  'the "' + MAIN_TAB + '" tab ' + esc_(covering) + ', waiting for someone to press ' +
                  '"Push to Monday &amp; Archive". The queue currently holds ' + fetched +
                  ' order lines in Label Design from the last 14 days.' +
                  (pushed ? ' ' + pushed + ' row(s) were also pushed to Monday and archived ' +
                    esc_(covering) + '.' : ''));
  }

  if (dow === 1) {
    html += para_('<i>Monday\'s summary covers Saturday and Sunday as well. The automatic check ' +
                  'runs every day so the queue is current when you arrive; only this email ' +
                  'pauses at the weekend. Pushing to Monday is always manual, on any day.</i>');
  }

  var text = [
    'Label Design — ' + today,
    '',
    'Status: ' + state,
    '',
    'New rows added ' + covering + ': ' + written,
    'Pushed to Monday:       ' + pushed,
    'Archived:               ' + archived,
    'Currently in the queue: ' + fetched + '   (Label Design, last 14 days)',
    'Checks run:             ' + checkRuns.length + ' of an expected ' + expected
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
 * Run once from the editor, and again any time this file is redeployed with
 * new/renamed trigger entry points (function names are captured as strings by
 * ScriptApp — a rename does not follow itself automatically; the old trigger
 * keeps pointing at a function that no longer exists and silently stops
 * firing). Set the script's timezone to America/Denver in Project Settings
 * FIRST — Apps Script hour triggers follow it, so the wrong timezone silently
 * runs the check at the wrong times.
 *
 * Apps Script only guarantees the hour, not the minute, so "10:00" means
 * somewhere inside the 10:00 hour. That is exactly why the Cloud Run job is
 * scheduled at 09:30 and 13:30 — a full half-hour of headroom in front of each
 * window. Move one and you must move the other.
 *
 * THE CHECK RUNS EVERY DAY. THE SUMMARY RUNS MONDAY TO FRIDAY. Orders are
 * entered at the weekend and the queue has to be current on Monday morning,
 * but nobody wants a Sunday email — so Monday's summary covers the weekend
 * instead (runsSinceLastSummary_).
 *
 * PUSH TO MONDAY & ARCHIVE HAS NO TRIGGER, INTENTIONALLY. It only ever runs
 * from the sheet's "Label Design Sync" menu (checkForNewOrdersManual /
 * pushToMondayAndArchiveManual) — see README.md for why this stayed manual.
 *
 * NOTE this deletes every existing trigger in the project first. Don't run it
 * in a project that has other triggers you care about.
 */
function installTriggers() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });

  // Every day, both runs. Check only — never pushes to Monday.
  [10, 14].forEach(function (h) {
    ScriptApp.newTrigger('checkForNewOrdersAuto').timeBased().everyDays(1).atHour(h).create();
  });

  // Weekdays only, 18:00.
  [ScriptApp.WeekDay.MONDAY, ScriptApp.WeekDay.TUESDAY, ScriptApp.WeekDay.WEDNESDAY,
   ScriptApp.WeekDay.THURSDAY, ScriptApp.WeekDay.FRIDAY].forEach(function (day) {
    ScriptApp.newTrigger('sendDailySummary').timeBased().onWeekDay(day).atHour(18).create();
  });

  Logger.log('Triggers installed: checkForNewOrdersAuto at 10 and 14 every day; ' +
             'sendDailySummary at 18 Monday to Friday. ' +
             'Push to Monday & Archive has no trigger — menu/button only.');
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
