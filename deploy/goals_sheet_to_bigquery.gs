/**
 * goals_sheet_to_bigquery.gs
 *
 * Pushes the Vox scorecard goals sheet into
 * `voxdatalake.<dataset>.scorecard_goals`, which every "% to Goal" tile on
 * the scorecard reads.
 *
 * WHY THIS EXISTS: a negotiated target is not a transaction Plex records, so
 * no amount of ETL work produces it. The goals live in a spreadsheet people
 * can actually edit, and this script is the bridge into BigQuery so the goal
 * sits in the same dataset as the actuals and can be joined in SQL rather
 * than blended in Looker Studio.
 *
 * SETUP (once):
 *   1. Extensions -> Apps Script from the goals spreadsheet.
 *   2. Paste this file in.
 *   3. Services (+) -> BigQuery API -> Add.  (Advanced service, v2.)
 *   4. Project Settings -> set the GCP project to voxdatalake so the script
 *      runs against the right project and billing account.
 *   5. Run pushGoalsToBigQuery() once manually and accept the OAuth prompt.
 *   6. Triggers -> add a time-driven trigger (hourly or daily is plenty —
 *      goals change rarely, and the ETL only reads the table once a day).
 *
 * SHEET LAYOUT — first row is headers, exactly these names in any order:
 *   metric | period_month | scope | goal_value | unit | note | updated_by
 *
 *   metric        revenue | sales | production
 *   period_month  any date cell; only year+month matter, normalised to the 1st
 *   scope         blank = company-wide. Otherwise the EXACT string the report
 *                 emits: a sales rep name, or a Plex work centre group
 *                 ("Encapsulating", not "Encapsulation" — the Plex spelling
 *                 differs from the scorecard tile name).
 *   goal_value    number. Commas/currency symbols are stripped.
 *   unit          USD | units   (a label for readers, nothing enforces it)
 *   note          free text
 *   updated_by    free text
 *
 * updated_at is stamped by this script, not the sheet.
 *
 * WRITE_TRUNCATE: the whole table is replaced on every push, so the sheet is
 * the single source of truth — delete a row there and it disappears here.
 * That is deliberate: an append-only load would accumulate duplicate goals
 * for the same month and every "% to Goal" tile would quietly double.
 */

var PROJECT_ID = 'voxdatalake';
var DATASET_ID = 'PlexTest';        // switch to 'PlexProd' at go-live
var TABLE_ID   = 'scorecard_goals';
var SHEET_NAME = 'Goals';           // tab name inside the spreadsheet

var VALID_METRICS = ['revenue', 'sales', 'production'];

function pushGoalsToBigQuery() {
  var rows = readSheetRows_();
  if (!rows.length) {
    throw new Error('No goal rows found on the "' + SHEET_NAME + '" tab. ' +
                    'Refusing to push — that would WRITE_TRUNCATE the table to empty ' +
                    'and blank every % to Goal tile.');
  }

  var ndjson = rows.map(function (r) { return JSON.stringify(r); }).join('\n');
  var blob = Utilities.newBlob(ndjson, 'application/octet-stream');

  var job = {
    configuration: {
      load: {
        destinationTable: {
          projectId: PROJECT_ID,
          datasetId: DATASET_ID,
          tableId: TABLE_ID
        },
        sourceFormat: 'NEWLINE_DELIMITED_JSON',
        writeDisposition: 'WRITE_TRUNCATE',
        // Schema is declared rather than autodetected: autodetect infers types
        // from whatever happens to be in the first rows, so a month where every
        // goal is a round number can land goal_value as INTEGER and break the
        // next push that has a decimal in it.
        schema: {
          fields: [
            { name: 'metric',       type: 'STRING',    mode: 'REQUIRED' },
            { name: 'period_month', type: 'DATE',      mode: 'REQUIRED' },
            { name: 'scope',        type: 'STRING',    mode: 'NULLABLE' },
            { name: 'goal_value',   type: 'FLOAT',     mode: 'REQUIRED' },
            { name: 'unit',         type: 'STRING',    mode: 'NULLABLE' },
            { name: 'note',         type: 'STRING',    mode: 'NULLABLE' },
            { name: 'updated_by',   type: 'STRING',    mode: 'NULLABLE' },
            { name: 'updated_at',   type: 'TIMESTAMP', mode: 'NULLABLE' }
          ]
        }
      }
    }
  };

  var result = BigQuery.Jobs.insert(job, PROJECT_ID, blob);
  Logger.log('Load job %s submitted — %s rows to %s.%s.%s',
             result.jobReference.jobId, rows.length, PROJECT_ID, DATASET_ID, TABLE_ID);
  return result.jobReference.jobId;
}

/** Reads the Goals tab and returns clean row objects, skipping blank lines. */
function readSheetRows_() {
  var sheet = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME);
  if (!sheet) throw new Error('No tab named "' + SHEET_NAME + '" in this spreadsheet.');

  var values = sheet.getDataRange().getValues();
  if (values.length < 2) return [];

  var headers = values[0].map(function (h) { return String(h).trim().toLowerCase(); });
  var idx = {};
  headers.forEach(function (h, i) { idx[h] = i; });

  ['metric', 'period_month', 'goal_value'].forEach(function (required) {
    if (!(required in idx)) {
      throw new Error('Missing required column "' + required + '" in the header row.');
    }
  });

  var stamp = new Date().toISOString();
  var out = [];
  var problems = [];

  for (var r = 1; r < values.length; r++) {
    var row = values[r];
    var metric = String(row[idx.metric] || '').trim().toLowerCase();
    // Skip fully blank rows silently — people leave gaps in spreadsheets.
    if (!metric && !row[idx.period_month] && !row[idx.goal_value]) continue;

    if (VALID_METRICS.indexOf(metric) === -1) {
      problems.push('Row ' + (r + 1) + ': metric "' + metric + '" is not one of ' + VALID_METRICS.join('/'));
      continue;
    }

    var month = toFirstOfMonth_(row[idx.period_month]);
    if (!month) {
      problems.push('Row ' + (r + 1) + ': period_month is not a readable date');
      continue;
    }

    var value = toNumber_(row[idx.goal_value]);
    if (value === null) {
      problems.push('Row ' + (r + 1) + ': goal_value "' + row[idx.goal_value] + '" is not a number');
      continue;
    }

    out.push({
      metric:       metric,
      period_month: month,
      scope:        cell_(row, idx.scope),
      goal_value:   value,
      unit:         cell_(row, idx.unit),
      note:         cell_(row, idx.note),
      updated_by:   cell_(row, idx.updated_by),
      updated_at:   stamp
    });
  }

  // Bad rows are skipped, not fatal — one typo shouldn't stop every other
  // goal from reaching the scorecard. They're logged loudly instead.
  if (problems.length) {
    Logger.log('Skipped %s row(s):\n%s', problems.length, problems.join('\n'));
  }
  return out;
}

/** Normalises any date-ish cell to the first of its month, as YYYY-MM-DD. */
function toFirstOfMonth_(v) {
  var d = (v instanceof Date) ? v : new Date(v);
  if (isNaN(d.getTime())) return null;
  var mm = ('0' + (d.getMonth() + 1)).slice(-2);
  return d.getFullYear() + '-' + mm + '-01';
}

/** Accepts 1234.5, "1,234.50", "$1,234" — returns null if not a number. */
function toNumber_(v) {
  if (typeof v === 'number') return isNaN(v) ? null : v;
  var cleaned = String(v).replace(/[^0-9.\-]/g, '');
  if (cleaned === '' || cleaned === '-' || cleaned === '.') return null;
  var n = Number(cleaned);
  return isNaN(n) ? null : n;
}

function cell_(row, i) {
  if (i === undefined) return null;
  var s = String(row[i] == null ? '' : row[i]).trim();
  return s === '' ? null : s;
}
