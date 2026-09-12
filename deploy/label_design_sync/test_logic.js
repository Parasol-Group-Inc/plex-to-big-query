/**
 * Tests for the pure logic in Code.gs.
 * =====================================
 *
 *   node deploy/label_design_sync/test_logic.js
 *
 * Run it after ANY change to SHEET_MAP, the tokenisers, or header resolution —
 * those three are where a silent, expensive mistake lives. A dedupe that stops
 * matching does not throw; it re-imports the entire archive onto the sheet and
 * onto the Monday board.
 *
 * It exercises the real logic against the real MONDAY header row committed in
 * assets/, with its real quirks: the trailing space in "Label ", "Phone" vs
 * "Phone Number", blank trailing headers, and the sheet spelling orders
 * "Sales Order #SO0110212" where Plex says "SO0110212".
 *
 * THE HISTORICAL EXPORT IS GITIGNORED. It is a live customer list — real names,
 * emails and order history — so it is backed up to the bucket rather than
 * carried in a repo that gets shared. When it is present these tests use it
 * (all ~5,182 rows); when it is not, they fall back to a small built-in fixture
 * of the same shape so every check still runs on a fresh clone. Only the row
 * COUNT differs, and the run says which mode it used.
 *
 * To work against the real archive:
 *
 *   gcloud storage cp \
 *     "gs://voxdatalake-terraform-state/plex-to-big-query/backups/latest/assets__Copy of Design in Monday- NEW - historical.csv" \
 *     "assets/Copy of Design in Monday- NEW - historical.csv"
 *
 * Apps Script's globals are stubbed and nothing here touches Sheets, BigQuery,
 * Monday or email — safe to run any time, and it needs no credentials.
 */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..', '..');

const src = fs.readFileSync(path.join(ROOT, 'deploy/label_design_sync/Code.gs'), 'utf8');

const sandbox = `
var PropertiesService={getScriptProperties:()=>({getProperty:()=>'', setProperty:()=>{}})};
var Logger={log:()=>{}};
var Utilities={formatDate:()=>'2026-09-12 1000'};
var Session={getScriptTimeZone:()=>'America/Denver'};
var SpreadsheetApp={}, MailApp={}, UrlFetchApp={}, BigQuery={}, ScriptApp={};
function voxLogoBlob_(){return null;}
`;
const mod = new Function(sandbox + src + `
return {SHEET_MAP, QUERY_COLUMNS, KEY_HEADERS, NEW_ROW_ALARM,
        resolveHeaders_, orderToken_, skuToken_, dedupeKeyFromValues_, dedupeKey_,
        cellValue_, normHeader_, assessKeys_, columnFlags_, esc_, rowsTable_,
        stats_, badge_, shell_, section_, para_, bullets_};
`)();

function readCsv(p) {
  const text = fs.readFileSync(p, 'utf8').replace(/^﻿/, '');
  const rows = []; let row = [], cur = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { cur += '"'; i++; } else q = false; } else cur += c; }
    else if (c === '"') q = true;
    else if (c === ',') { row.push(cur); cur = ''; }
    else if (c === '\n') { row.push(cur); rows.push(row); row = []; cur = ''; }
    else if (c !== '\r') cur += c;
  }
  if (cur || row.length) { row.push(cur); rows.push(row); }
  return rows;
}

const monday = readCsv(path.join(ROOT, 'assets/Copy of Design in Monday- NEW - MONDAY.csv'));

// The historical archive — the real export when it is on disk, otherwise a
// fixture with the SAME header row (note "Phone" not "Phone Number", the blank
// column 12, "Prop 65" present, and six blank trailing headers) and a handful
// of real-shaped rows.
const HIST_PATH = path.join(ROOT, 'assets/Copy of Design in Monday- NEW - historical.csv');
const HAVE_REAL_HIST = fs.existsSync(HIST_PATH);

const HIST_FIXTURE = [
  ['Date', 'Sales Order', 'Memo', 'Customer', 'Email', 'Phone', 'WO Number', 'Item',
   'Sales Rep', 'Label SKU', 'Description', 'Reason Code', '', 'Bottle Material',
   'Prop 65', 'LCR', '', '', '', '', '', ''],
  ['2025-01-16', 'Sales Order #SO0110212', 'Update to current V code. Standard Label.',
   'Sequoia Group LLC', 'alcomfort.m@gmail.com', '', 'WO0023971', 'Sequoia Group 14620+s3221',
   'Tyler Hall', 's3221', 'Sleep Well Gummies 60ct 250cc Clear/Black CRC Lid +Standard Label (s3221)',
   'Updated label review', 'LCR A00550', '', '', '', '', '', '', '', '', ''],
  ['2025-01-16', 'Sales Order #SO0110687', 'New label review - customer', 'VitaUp Corp',
   'info@vitaup.org', '', 'WO0023993', 'VitaUp 13066.60.175cc.B.W+CS2676', 'Kami Butcher',
   'CS2676', 'Ashwagandha 60ct 175cc Black Bottle/White Lid +Outsourced Label (CS2676)',
   'New label review', 'LCR A00551', '', '', '', '', '', '', '', '', '']
];
// Padded to clear the NEW_ROW_ALARM archive floor (50) so the alarm checks are
// meaningful in fixture mode too.
if (!HAVE_REAL_HIST) {
  for (let i = 0; i < 60; i++) {
    const r = HIST_FIXTURE[1].slice();
    r[1] = 'Sales Order #SO01' + String(20000 + i);
    r[9] = 'FX' + i;
    HIST_FIXTURE.push(r);
  }
}
const hist = HAVE_REAL_HIST ? readCsv(HIST_PATH) : HIST_FIXTURE;

let fail = 0;
function ok(cond, label, extra) {
  console.log((cond ? '  PASS  ' : '  FAIL  ') + label + (extra ? '  ' + extra : ''));
  if (!cond) fail++;
}

console.log(HAVE_REAL_HIST
  ? '\nArchive: the REAL historical export (' + (hist.length - 1) + ' rows).'
  : '\nArchive: built-in FIXTURE — the real export is gitignored and not on disk.\n' +
    '         Same shape, fewer rows. See the header of this file to fetch the real one.');

console.log('\n=== 1. MONDAY tab header resolution ===');
const m = mod.resolveHeaders_('MONDAY', monday[0]);
console.log('  mapped   :', Object.keys(m.index).join(', '));
console.log('  missing  :', m.missing.join(', ') || 'none');
console.log('  unknown  :', m.unknown.join(', ') || 'none');
ok(m.hasKeys, 'MONDAY tab has both dedupe key columns');
ok(m.index['Phone Number'] === 5, 'Phone Number resolved at index 5');
ok(m.index['Label'] === 12, 'trailing-space "Label " matched to Label at 12');
ok(m.missing.join() === 'Prop 65', 'only Prop 65 missing from MONDAY', '-> ' + m.missing.join());
ok(m.unknown.length === 0, 'no unknown columns on MONDAY');

console.log('\n=== 2. historical tab header resolution ===');
const h = mod.resolveHeaders_('historical', hist[0]);
console.log('  missing  :', h.missing.join(', ') || 'none');
console.log('  unknown  :', h.unknown.join(', ') || 'none');
ok(h.hasKeys, 'historical has both dedupe key columns');
ok(h.index['Phone Number'] === 5, 'historical "Phone" matched via alt -> index 5');
ok(h.unknown.length === 0, 'blank trailing headers NOT reported as unknown columns');

console.log('\n=== 3. order-number tokenisation across the two spellings ===');
ok(mod.orderToken_('Sales Order #SO0110212') === 'SO0110212', 'sheet spelling -> SO0110212');
ok(mod.orderToken_('SO0110212') === 'SO0110212', 'plex spelling -> SO0110212');
ok(mod.orderToken_('  so0110212 ') === 'SO0110212', 'case/space insensitive');
ok(mod.dedupeKeyFromValues_('Sales Order #SO0110212', 's3221')
  === mod.dedupeKeyFromValues_('SO0110212', 'S3221'), 'both sides produce the SAME key');

console.log('\n=== 4. dedupe against the archive ===');
const keys = {};
const oi = h.index[mod.KEY_HEADERS.order], si = h.index[mod.KEY_HEADERS.sku];
let archived = 0;
for (let i = 1; i < hist.length; i++) {
  const r = hist[i];
  if (!r || (!r[oi] && !r[si])) continue;
  keys[mod.dedupeKeyFromValues_(r[oi], r[si])] = true;
  archived++;
}
console.log('  archive rows:', archived, ' distinct keys:', Object.keys(keys).length);
ok(archived >= 50, 'archive parsed', '(' + archived + ' rows)');

// Rows exactly as Plex would return them: the bare order number, no prefix.
const plexLike = [1, 2].map(i => ({
  order_number: String(hist[i][oi]).replace(/^Sales Order #/, ''),
  customer_part_no: hist[i][si],
  customer_name: hist[i][3], order_date: hist[i][0],
  job_note: hist[i][2], customer_email: hist[i][4],
  sales_rep_primary: hist[i][8], customer_part_description: hist[i][10]
}));
const stillNew = plexLike.filter(r => !keys[mod.dedupeKey_(r)]);
ok(stillNew.length === 0, 'already-archived orders recognised as NOT new',
  '-> ' + stillNew.length + ' leaked through');
ok(!keys[mod.dedupeKey_({ order_number: 'SO9999999', customer_part_no: 'ZZ0001' })],
  'a genuinely new order is not falsely matched');

console.log('\n=== 5. row placement uses the TAB column order ===');
const row = plexLike[0];
const width = monday[0].length;
const line = new Array(width).fill('');
mod.SHEET_MAP.forEach(c => { const at = m.index[c.header]; if (at != null) line[at] = mod.cellValue_(c, row); });
monday[0].forEach((hh, i) => console.log('   ' + String(i).padStart(2) + ' ' + hh.trim().padEnd(16) + '| ' + String(line[i]).slice(0, 46)));
ok(line.length === width, 'row width matches the tab (' + width + ')');
ok(/^Sales Order #/.test(line[1]), 'Sales Order keeps the sheet own "Sales Order #" convention');
ok(line[11] === '' && line[12] === '' && line[13] === '' && line[14] === '',
  'team-review columns (Reason Code, Label, Bottle Material, LCR) left blank');
ok(line[6] === '' && line[7] === '', 'gap columns (WO Number, Item) left blank');
ok(line[4] === row.customer_email && line[10] === row.customer_part_description,
  'Email and Description filled from the new view columns');

console.log('\n=== 6. QUERY_COLUMNS derived from SHEET_MAP ===');
console.log('  ', mod.QUERY_COLUMNS.join(', '));
ok(mod.QUERY_COLUMNS.includes('customer_email') &&
  mod.QUERY_COLUMNS.includes('customer_phone') &&
  mod.QUERY_COLUMNS.includes('customer_part_description'),
  'the three new view columns are queried');
ok(new Set(mod.QUERY_COLUMNS).size === mod.QUERY_COLUMNS.length, 'no duplicate columns in the SELECT');

console.log('\n=== 7. the key-mismatch alarm ===');
const tabsStub = { report: { history: { rowCount: archived, sampleOrders: [String(hist[1][oi])] } } };
const many = Array.from({ length: 200 }, (_, i) => ({ order_number: 'X' + i, customer_part_no: 'P' + i }));
const a1 = mod.assessKeys_(many, many, tabsStub);
ok(a1.alarm === true, '200 new / 0 matched -> ALARM (held back, not pushed)');
console.log('    ' + a1.warnings[0].slice(0, 160) + '...');
ok(mod.assessKeys_(many, many.slice(0, 5), tabsStub).alarm === false, '5 new of 200 -> normal day');
ok(mod.assessKeys_(many, many, { report: { history: { rowCount: 0, sampleOrders: [] } } }).alarm === false,
  'empty archive -> no alarm (a first run legitimately writes everything)');

console.log('\n=== 8. column flags for the team email ===');
const flags = mod.columnFlags_({ main: m });
console.log('   gaps   :', flags.gaps.map(g => g.split(' — ')[0]).join(', '));
console.log('   team   :', flags.team.join(', '));
console.log('   missing:', flags.missing.join(', ') || 'none');
ok(flags.gaps.length === 2, 'WO Number and Item reported as real gaps');
ok(flags.team.indexOf('Prop 65') < 0, 'Prop 65 not flagged as a team column - not on the MONDAY tab');

console.log('\n=== 9. HTML email renders ===');
const html = mod.shell_('Sync ok', 'voxdatalake.PlexTest', mod.badge_('OK', 'ok'),
  mod.stats_([[12, 'In queue'], [10, 'Already there']]) + mod.section_('New rows') + mod.rowsTable_(plexLike));
ok(html.indexOf('cid:voxlogo') > 0, 'inline logo referenced');
ok(html.indexOf('<style') < 0, 'no <style> block (Gmail strips it) - all styles inline');
ok(html.indexOf('display:flex') < 0, 'no flexbox (Outlook stacks it)');
ok(mod.esc_('<script>&"') === '&lt;script&gt;&amp;&quot;', 'HTML escaping works');
fs.writeFileSync(path.join(require('os').tmpdir(), 'label_design_preview.html'), html);

console.log('\n' + (fail ? 'FAILURES: ' + fail : 'ALL CHECKS PASSED'));
process.exit(fail ? 1 : 0);
