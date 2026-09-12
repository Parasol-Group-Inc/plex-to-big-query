
const BQ_PROJECT   = 'voxdatalake';
const BQ_DATASET   = 'VoxScorecardsLive';
const BQ_TABLE     = 'daily_sales_activity';
const MANAGER_EMAIL = 'ashley.quintana@voxnutrition.com';
const DOMAIN       = 'voxnutrition.com';

// Rep name → email map
const REP_EMAILS = {
  'Kami Butcher':    'kami.butcher@voxnutrition.com',
  'Tyler Hall':      'tyler.hall@voxnutrition.com',
  'Janet Pacheco':   'janet.pacheco@voxnutrition.com',
  'Ruben Espinosa':  'ruben.espinosa@voxnutrition.com',
  'Landen Epperson': 'landen.epperson@voxnutrition.com',
  'Aishah Alqasim':  'aishah.alqasim@voxnutrition.com',
  'Zeljan Avdic':    'zeljan.avdic@voxnutrition.com',
};

const ALL_REPS = Object.keys(REP_EMAILS);
// ─────────────────────────────────────────────────────────────


// ============================================================
//  SERVE THE FORM
// ============================================================
function doGet(e) {
  return HtmlService
    .createHtmlOutputFromFile('SalesActivity')
    .setTitle('Daily Sales Activity Log')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}


// ============================================================
//  HANDLE FORM SUBMISSION
// ============================================================
function submitActivityLog(payload) {
  const now = new Date().toISOString();

  const rows = [{
    insertId: `${payload.rep_name}_${payload.activity_date}_${Date.now()}`,
    json: {
      rep_name:             payload.rep_name,
      activity_date:        payload.activity_date,       // "YYYY-MM-DD"
      submitted_at:         now,
      is_pto:               payload.is_pto,
      emails_sent:          payload.emails_sent,
      calls_made:           payload.calls_made,
      meetings:             payload.meetings,
      visits_to_vox:        payload.visits_to_vox,
      social_dms:           payload.social_dms,
      other:                payload.other,
      total_activities:     payload.total_activities,
      leads_assigned:       payload.leads_assigned,
      leads_contacted:      payload.leads_contacted,
      notes:                payload.notes || '',
    }
  }];

  const request = {
    rows:         rows,
    skipInvalidRows: false,
    ignoreUnknownValues: false,
  };

  const response = BigQuery.Tabledata.insertAll(request, BQ_PROJECT, BQ_DATASET, BQ_TABLE);

  if (response.insertErrors && response.insertErrors.length > 0) {
    const errMsg = JSON.stringify(response.insertErrors);
    Logger.log('BigQuery insert error: ' + errMsg);
    throw new Error('BigQuery insert failed: ' + errMsg);
  }

  Logger.log(`Logged activity for ${payload.rep_name} on ${payload.activity_date}`);
  return { success: true };
}


// ============================================================
//  EMAIL TRIGGERS
//  Run installTriggers() ONE TIME manually to set these up
// ============================================================
function installTriggers() {
  // Remove any existing triggers first to avoid duplicates
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));

  // Daily at 7am MT (UTC-6 standard / UTC-7 daylight)
  // GAS trigger timezone follows the script's timezone setting
  // Set script timezone to America/Denver in Project Settings
  [ScriptApp.WeekDay.TUESDAY, ScriptApp.WeekDay.WEDNESDAY, 
    ScriptApp.WeekDay.THURSDAY, ScriptApp.WeekDay.FRIDAY].forEach(day => {
      ScriptApp.newTrigger('dailyMorningCheck')
        .timeBased()
        .onWeekDay(day)
        .atHour(7)
        .create();
  });

  // Friday at 5pm for weekly manager summary
  ScriptApp.newTrigger('fridayManagerSummary')
    .timeBased()
    .onWeekDay(ScriptApp.WeekDay.FRIDAY)
    .atHour(17)
    .create();

  Logger.log('Triggers installed successfully.');
}


// ============================================================
//  DAILY 7AM CHECK — email reps missing yesterday's log
// ============================================================
function dailyMorningCheck() {
  const yesterday = getPreviousWorkday();
  if (!yesterday) return; // skip if yesterday was a weekend

  const submitted = getSubmittedReps(yesterday);
  const missing   = ALL_REPS.filter(r => !submitted.includes(r));

  if (missing.length === 0) {
    Logger.log(`All reps submitted for ${yesterday}. No reminder emails needed.`);
    return;
  }

  missing.forEach(rep => {
    const repEmail = REP_EMAILS[rep];
    const subject  = `Action needed: Log your sales activities for ${formatDate(yesterday)}`;
    const body     = `Hi ${rep.split(' ')[0]},\n\n` +
      `We noticed your daily activity log for ${formatDate(yesterday)} hasn't been submitted yet.\n\n` +
      `Please fill it out as soon as possible:\n${getFormUrl()}\n\n` +
      `If you were out of office, just check the PTO box when you submit.\n\n` +
      `Thanks!\nVox Sales Ops\n\n--\nPlease do not reply to this email.`;

    MailApp.sendEmail({
      to:      repEmail,
      cc:      MANAGER_EMAIL,
      from:    'bizops@parasolgroupinc.com',
      replyTo: 'bizops@parasolgroupinc.com',   
      subject: subject,
      body:    body,
    });

    Logger.log(`Reminder sent to ${rep} (${repEmail}) for ${yesterday}`);
  });
}


// ============================================================
//  FRIDAY 5PM — manager summary of missing days this week
// ============================================================
function fridayManagerSummary() {
  const weekDays  = getCurrentWeekWorkdays();   // Mon–Fri (excluding today if needed)
  const missing   = {};                         // { repName: [dates] }

  weekDays.forEach(date => {
    const submitted = getSubmittedReps(date);
    ALL_REPS.forEach(rep => {
      if (!submitted.includes(rep)) {
        if (!missing[rep]) missing[rep] = [];
        missing[rep].push(date);
      }
    });
  });

  const missingReps = Object.keys(missing);
  if (missingReps.length === 0) {
    Logger.log('All reps fully submitted this week. No Friday summary needed.');
    return;
  }

  let body = `Hi Ashley,\n\nHere's a summary of missing sales activity logs for the week of ${formatDate(weekDays[0])}:\n\n`;

  missingReps.forEach(rep => {
    const dates = missing[rep].map(d => formatDate(d)).join(', ');
    body += `• ${rep}: missing ${dates}\n`;
  });

  body += `\nReps have been or will be individually reminded.\n\nVox Sales Ops`;

  MailApp.sendEmail({
    to:      MANAGER_EMAIL,
    from:    'bizops@parasolgroupinc.com',
    subject: `Weekly Activity Log Summary — Missing Entries (${formatDate(weekDays[0])})`,
    body:    body,
  });

  Logger.log('Friday summary sent to manager.');
}


// ============================================================
//  BIGQUERY HELPERS
// ============================================================

// Returns array of rep names who submitted for a given date string "YYYY-MM-DD"
function getSubmittedReps(dateStr) {
  const query = `
    SELECT DISTINCT rep_name
    FROM \`${BQ_PROJECT}.${BQ_DATASET}.${BQ_TABLE}\`
    WHERE activity_date = '${dateStr}'
  `;

  const request = {
    query:        query,
    useLegacySql: false,
    timeoutMs:    10000,
  };

  try {
    const response = BigQuery.Jobs.query(request, BQ_PROJECT);
    if (!response.rows) return [];
    return response.rows.map(row => row.f[0].v);
  } catch(e) {
    Logger.log('BQ query error: ' + e.toString());
    return [];
  }
}


// ============================================================
//  DATE HELPERS
// ============================================================

// Returns "YYYY-MM-DD" for the previous workday (Mon if today is Mon returns Fri)
function getPreviousWorkday() {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  // Skip Sunday (0) and Saturday (6)
  if (d.getDay() === 0) d.setDate(d.getDate() - 2);
  if (d.getDay() === 6) d.setDate(d.getDate() - 1);
  // If today is Monday, previous workday is Friday
  return toDateStr(d);
}

// Returns array of "YYYY-MM-DD" strings for Mon–Fri of the current week
// Only includes days up to and including today
function getCurrentWeekWorkdays() {
  const today  = new Date();
  const day    = today.getDay(); // 0=Sun, 1=Mon...
  const monday = new Date(today);
  monday.setDate(today.getDate() - (day === 0 ? 6 : day - 1));

  const days = [];
  for (let i = 0; i < 5; i++) {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    if (d <= today) days.push(toDateStr(d));
  }
  return days;
}

function toDateStr(date) {
  const pad = n => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}`;
}

function formatDate(dateStr) {
  // "2024-06-14" → "June 14, 2024"
  const [y, m, d] = dateStr.split('-').map(Number);
  const months = ['January','February','March','April','May','June',
                  'July','August','September','October','November','December'];
  return `${months[m-1]} ${d}, ${y}`;
}

// Returns the deployed web app URL (stored in Script Properties after first deploy)
function getFormUrl() {
  const props = PropertiesService.getScriptProperties();
  return props.getProperty('FORM_URL') || '[PASTE YOUR WEB APP URL IN SCRIPT PROPERTIES AS FORM_URL]';
}

