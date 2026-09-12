/**
 * Sheet → BigQuery push
 * =====================
 *
 * Replaces each dataset's BigQuery table from its sheet tab, using a LOAD job
 * rather than streaming inserts or DML.
 *
 * Why a load job:
 *   - A streaming insert leaves the row in a buffer for a few seconds before
 *     it is queryable, which reads to the person who just saved as "it didn't
 *     work" and invites a second save.
 *   - DML is rate-limited per table, and a shared form can hit that.
 *   - WRITE_TRUNCATE from the sheet makes the SHEET the record of truth: the
 *     table is a mirror that can be rebuilt at any time by pushing again. If
 *     the table is dropped, or the dataset is swapped from test to production,
 *     nothing is lost.
 *
 * The tabs are append-only, so replacing the table is not destructive — the
 * full history goes across on every push, and the consuming views take the
 * newest row per key.
 */

// ── Push ───────────────────────────────────────────────────────────────────

/**
 * Push one dataset. Throws on failure; callers that must not fail the user's
 * save use tryPush_() instead.
 */
function pushDataset(datasetKey) {
  var ds = DATASETS[datasetKey];
  if (!ds) throw new Error('Unknown dataset: ' + datasetKey);

  var tab = sheet_().getSheetByName(ds.tab);
  if (!tab) throw new Error('No sheet tab named "' + ds.tab + '". Run setupSheets().');

  var fields = allFields_(ds);
  var lastRow = tab.getLastRow();

  // An empty tab still replaces the table, so that retracting the only row
  // leaves an empty table rather than a stale one.
  var rows = [];
  if (lastRow >= 2) {
    var headers = tab.getRange(1, 1, 1, tab.getLastColumn()).getValues()[0];
    var values = tab.getRange(2, 1, lastRow - 1, headers.length).getValues();
    rows = values.map(function (row) {
      var obj = {};
      headers.forEach(function (h, i) { if (h) obj[h] = row[i]; });
      return obj;
    }).filter(function (obj) {
      // Skip wholly blank rows — a stray Enter in the sheet should not become
      // a row of nulls in a table a scorecard reads.
      return fields.some(function (f) { return String(obj[f.name] || '').trim() !== ''; });
    });
  }

  var csv = toCsv_(fields, rows);
  var blob = Utilities.newBlob(csv, 'text/csv', ds.table + '.csv');

  var job = {
    configuration: {
      load: {
        // Destination is the DATA project; the job itself runs in the
        // script's own project (the second argument to Jobs.insert below).
        destinationTable: {
          projectId: dataProject_(),
          datasetId: dataset_(),
          tableId: ds.table
        },
        schema: { fields: bqSchema_(fields) },
        sourceFormat: 'CSV',
        skipLeadingRows: 1,
        allowQuotedNewlines: true,
        writeDisposition: 'WRITE_TRUNCATE',
        createDisposition: 'CREATE_IF_NEEDED',
        // Schema drift should fail loudly rather than quietly write a table no
        // report will match.
        maxBadRecords: 0
      }
    }
  };

  var inserted = BigQuery.Jobs.insert(job, project_(), blob);
  var result = waitForJob_(inserted.jobReference.jobId);

  Logger.log('Pushed %s rows to %s.%s.%s', rows.length, dataProject_(), dataset_(), ds.table);
  return { rows: rows.length, jobId: result.jobReference.jobId };
}

/**
 * Push, but never throw. A failed push must not fail the user's save: the row
 * is already in the sheet, which is the record, and the hourly trigger will
 * carry it across. The form tells the person which of the two happened.
 */
function tryPush_(datasetKey) {
  try {
    var r = pushDataset(datasetKey);
    return { ok: true, message: 'Live in BigQuery (' + r.rows + ' rows).' };
  } catch (e) {
    Logger.log('Push failed for %s: %s', datasetKey, e);
    return {
      ok: false,
      message: 'Saved to the sheet, but the BigQuery push failed — it will ' +
               'retry within the hour. Reports may lag until then. (' + e + ')'
    };
  }
}

/** Push every dataset. The hourly trigger's entry point, and a manual repair. */
function pushAll() {
  var out = {};
  Object.keys(DATASETS).forEach(function (k) {
    try {
      out[k] = pushDataset(k);
    } catch (e) {
      out[k] = { error: String(e) };
      Logger.log('pushAll: %s failed: %s', k, e);
    }
  });
  Logger.log(JSON.stringify(out));
  return out;
}

/**
 * A load job is asynchronous. Without waiting, a failure would be invisible
 * and the form would report success for a push that did not happen.
 */
function waitForJob_(jobId) {
  var deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    var job = BigQuery.Jobs.get(project_(), jobId);
    if (job.status && job.status.state === 'DONE') {
      if (job.status.errorResult) {
        throw new Error('Load job failed: ' + job.status.errorResult.message);
      }
      return job;
    }
    Utilities.sleep(1000);
  }
  throw new Error('Load job did not finish within 60s: ' + jobId);
}

// ── CSV and schema ─────────────────────────────────────────────────────────

var BQ_TYPES = {
  month: 'DATE', date: 'DATE', timestamp: 'TIMESTAMP',
  number: 'FLOAT64', money: 'NUMERIC',
  bool: 'BOOL',
  text: 'STRING', longtext: 'STRING', select: 'STRING', derived: 'STRING'
};

function bqSchema_(fields) {
  return fields.map(function (f) {
    return {
      name: f.name,
      type: BQ_TYPES[f.type] || 'STRING',
      // Everything nullable on purpose: a required field is enforced at entry,
      // and a REQUIRED column here would turn one bad historical row into a
      // failed load for the whole table.
      mode: 'NULLABLE'
    };
  });
}

function toCsv_(fields, rows) {
  var lines = [fields.map(function (f) { return f.name; }).join(',')];
  rows.forEach(function (row) {
    lines.push(fields.map(function (f) {
      return csvCell_(f, row[f.name]);
    }).join(','));
  });
  return lines.join('\n');
}

function csvCell_(field, value) {
  if (value === null || value === undefined || value === '') return '';

  var type = BQ_TYPES[field.type] || 'STRING';

  // Sheets hands back a Date object for anything it parsed as a date, and its
  // toString is not a format BigQuery accepts.
  if (value instanceof Date) {
    var tz = Session.getScriptTimeZone();
    value = type === 'TIMESTAMP'
      ? Utilities.formatDate(value, 'UTC', "yyyy-MM-dd'T'HH:mm:ss'Z'")
      : Utilities.formatDate(value, tz, 'yyyy-MM-dd');
  }

  if (type === 'BOOL') {
    var s = String(value).toLowerCase();
    return (s === 'true' || s === 'yes' || s === '1') ? 'true' : 'false';
  }

  if (type === 'FLOAT64' || type === 'NUMERIC') {
    var n = Number(String(value).replace(/[$,]/g, ''));
    return isFinite(n) ? String(n) : '';
  }

  return quote_(String(value));
}

function quote_(s) {
  if (/[",\n\r]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
  return s;
}

// ── Trigger ────────────────────────────────────────────────────────────────

/**
 * Run once from the editor. The hourly push is a safety net, not the main
 * path — saves push inline. It exists so a push that failed while someone was
 * entering data repairs itself without anyone noticing it broke.
 */
function installTriggers() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'pushAll') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('pushAll').timeBased().everyHours(1).create();
  Logger.log('Hourly pushAll trigger installed.');
}
