/**
 * Label Design — run the ETL on demand
 * ====================================
 *
 * A one-button web app: starts the Label Design Cloud Run job
 * (`plex-etl-label-design-test` until promoted — see README) so the team can
 * refresh `label_design_report` without waiting for the 09:30 / 13:30 runs,
 * and shows the last few runs and whether they worked.
 *
 * WHO CAN PRESS IT. The web app executes as the person who DEPLOYED it (their
 * Google identity starts the job), so nobody else needs GCP permissions. That
 * makes the allowlist the real gate: only emails in ALLOWED_EMAILS may start a
 * run; everyone else in the domain sees status only.
 *
 * WHAT STOPS IT BEING HAMMERED.
 *   - It refuses while an execution of the job is still running.
 *   - It refuses within COOLDOWN_MINUTES of the last start from this app.
 *   - A script lock serialises two clicks landing at the same moment, so the
 *     running-check and the start cannot interleave.
 * Every attempt — started or refused — is kept in RUN_LOG with who and why.
 *
 * It only STARTS the existing job; it cannot change it. The job's own config
 * (which Plex tenant, which dataset) is whatever Terraform deployed.
 */

var RUN_API = 'https://run.googleapis.com/v2';
var LOG_KEEP = 50;

// ── config ─────────────────────────────────────────────────────────────────

function prop_(key, fallback) {
  var v = PropertiesService.getScriptProperties().getProperty(key);
  if (v === null || v === '') {
    if (fallback !== undefined) return fallback;
    throw new Error('Script property ' + key + ' is not set (Project Settings → Script Properties).');
  }
  return v;
}

function config_() {
  return {
    project: prop_('RUN_PROJECT', 'voxdatalake'),
    region: prop_('RUN_REGION', 'us-central1'),
    job: prop_('JOB_NAME'),
    cooldownMin: Number(prop_('COOLDOWN_MINUTES', '10')),
    allowed: prop_('ALLOWED_EMAILS', '').split(',')
      .map(function (s) { return s.trim().toLowerCase(); })
      .filter(function (s) { return s; })
  };
}

function jobPath_(c) {
  return 'projects/' + c.project + '/locations/' + c.region + '/jobs/' + c.job;
}

function isProd_(c) {
  return !/-test$/.test(c.job);
}

// ── Cloud Run API ──────────────────────────────────────────────────────────

function api_(method, url, body) {
  var opts = {
    method: method,
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    muteHttpExceptions: true
  };
  if (body) opts.payload = JSON.stringify(body);
  var res = UrlFetchApp.fetch(url, opts);
  var code = res.getResponseCode();
  var text = res.getContentText();
  if (code >= 300) {
    // Surface Google's own message — "permission denied on run.jobs.run" is
    // far more useful to whoever set this up than a bare status code.
    var msg = text;
    try { msg = JSON.parse(text).error.message; } catch (e) {}
    throw new Error('Cloud Run API ' + code + ': ' + msg);
  }
  return text ? JSON.parse(text) : {};
}

function recentExecutions_(c, n) {
  var r = api_('get', RUN_API + '/' + jobPath_(c) + '/executions?pageSize=' + (n || 5));
  return (r.executions || []).map(function (e) {
    var done = !!e.completionTime;
    var ok = (e.succeededCount || 0) > 0;
    var failed = (e.failedCount || 0) > 0 || (e.cancelledCount || 0) > 0;
    return {
      name: e.name.split('/').pop(),
      started: e.startTime || e.createTime,
      finished: e.completionTime || null,
      state: !done ? 'running' : ok && !failed ? 'succeeded' : 'failed',
      logUrl: 'https://console.cloud.google.com/run/jobs/executions/details/' + c.region + '/' +
              e.name.split('/').pop() + '?project=' + c.project
    };
  });
}

// ── web app ────────────────────────────────────────────────────────────────

function doGet() {
  return HtmlService.createTemplateFromFile('Index').evaluate()
    .setTitle('Label Design — run the sync')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** Everything the page shows, in one call. Never throws: errors are data. */
function getStatus() {
  var c, who = Session.getActiveUser().getEmail().toLowerCase();
  try { c = config_(); } catch (e) { return { setupNeeded: String(e.message) }; }
  var out = {
    job: c.job, project: c.project, isProd: isProd_(c), user: who,
    canRun: c.allowed.indexOf(who) !== -1, cooldownMin: c.cooldownMin,
    log: readLog_().slice(0, 8)
  };
  try { out.executions = recentExecutions_(c, 5); } catch (e) { out.apiError = String(e.message); }
  return out;
}

/** Start one run. Returns {ok, message} — refusals are answers, not errors. */
function runJob() {
  var c = config_();
  var who = Session.getActiveUser().getEmail().toLowerCase();
  if (!who) return refuse_(who, 'Could not identify you — open the app while signed in to your Parasol account.');
  if (c.allowed.indexOf(who) === -1) return refuse_(who, who + ' is not on this app\'s allowlist.');

  var lock = LockService.getScriptLock();
  if (!lock.tryLock(15000)) return refuse_(who, 'Someone else is starting a run right now — try again in a moment.');
  try {
    var running = recentExecutions_(c, 5).filter(function (e) { return e.state === 'running'; });
    if (running.length) {
      return refuse_(who, 'A run is already in progress (' + running[0].name + '). Wait for it to finish.');
    }
    var last = readLog_().filter(function (l) { return l.result === 'started'; })[0];
    if (last) {
      var mins = (Date.now() - new Date(last.at).getTime()) / 60000;
      if (mins < c.cooldownMin) {
        return refuse_(who, 'Last run was started ' + Math.round(mins) + ' min ago by ' + last.who +
                       '. Runs are at least ' + c.cooldownMin + ' min apart.');
      }
    }
    var op = api_('post', RUN_API + '/' + jobPath_(c) + ':run', {});
    var exec = (op.metadata && op.metadata.name) ? op.metadata.name.split('/').pop() : '(starting)';
    writeLog_({ at: new Date().toISOString(), who: who, result: 'started', detail: exec, job: c.job });
    return { ok: true, message: 'Started ' + exec + '. It usually takes 2–4 minutes; this page refreshes itself.' };
  } catch (e) {
    writeLog_({ at: new Date().toISOString(), who: who, result: 'error', detail: String(e.message), job: c.job });
    return { ok: false, message: String(e.message) };
  } finally {
    lock.releaseLock();
  }
}

function refuse_(who, why) {
  writeLog_({ at: new Date().toISOString(), who: who || '(unknown)', result: 'refused', detail: why,
              job: PropertiesService.getScriptProperties().getProperty('JOB_NAME') || '' });
  return { ok: false, message: why };
}

// ── run log (Script Properties; newest first) ──────────────────────────────

function readLog_() {
  try { return JSON.parse(PropertiesService.getScriptProperties().getProperty('RUN_LOG') || '[]'); }
  catch (e) { return []; }
}

function writeLog_(entry) {
  var log = readLog_();
  log.unshift(entry);
  PropertiesService.getScriptProperties().setProperty('RUN_LOG', JSON.stringify(log.slice(0, LOG_KEEP)));
}

// ── setup helper ───────────────────────────────────────────────────────────

/**
 * Run once from the editor after setting Script Properties. Starts nothing:
 * reads the job's recent executions, which proves the OAuth scope, the
 * project/region/job name and the deployer's permission all line up.
 */
function testSetup() {
  var c = config_();
  Logger.log('Job: %s  (%s)', jobPath_(c), isProd_(c) ? 'PRODUCTION' : 'test');
  Logger.log('Allowlist: %s', c.allowed.join(', ') || '(empty — nobody can start a run)');
  var ex = recentExecutions_(c, 3);
  Logger.log('Read %s recent executions: %s', ex.length,
             ex.map(function (e) { return e.name + ' ' + e.state; }).join(' | '));
}
