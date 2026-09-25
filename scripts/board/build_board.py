# Builds the Vox Migration Board page. Content lives in board_data.py.
import io, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_data import GLOSSARY, TILES, FLAGS, FORMS, TABLES, RECENT

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migration_board.html")

DATA = json.dumps(dict(
    glossary=[dict(term=t, plain=p, why=w) for t, p, w in GLOSSARY],
    tiles=TILES,
    flags=FLAGS,
    forms=[dict(f, fields=[list(x) for x in f["fields"]]) for f in FORMS],
    tables=TABLES,
    recent=[dict(when=a, what=b, detail=c) for a, b, c in RECENT],
), ensure_ascii=False, indent=1)

HTML = """<title>Vox Migration Board</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@600;700;800&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --paper:#EEF3F1; --card:#FFFFFF; --sunk:#E4ECE9;
  --ink:#131A18; --muted:#56635E; --faint:#849790;
  --hair:#D9E3DE; --hair-2:#C7D4CE;
  --accent:#0E6E63; --accent-ink:#083F38; --accent-bg:#DFF1EC;
  --amber:#B8790C; --amber-bg:#FCF0DA;
  --rust:#A3432E;  --rust-bg:#F7E9E5;
  --steel:#3E6E8E; --steel-bg:#E7EFF3;
  --violet:#6B6478;--violet-bg:#EDEBF1;
  --disp:'Big Shoulders Display','Arial Narrow',sans-serif;
  --body:'IBM Plex Sans',-apple-system,BlinkMacSystemFont,sans-serif;
  --mono:'IBM Plex Mono',ui-monospace,Menlo,monospace;
  --shadow:0 1px 3px rgba(10,20,18,.06), 0 14px 30px -20px rgba(10,20,18,.22);
}
@media (prefers-color-scheme:dark){ :root:not([data-theme="light"]){
  --paper:#0E1613; --card:#151F1B; --sunk:#1B2723;
  --ink:#EAF1EE; --muted:#93A39C; --faint:#6F7E78;
  --hair:#28352F; --hair-2:#374540;
  --accent:#3FC9B4; --accent-ink:#BEF0E5; --accent-bg:#12332C;
  --amber:#E3A83F; --amber-bg:#332A16;
  --rust:#E08066;  --rust-bg:#35201A;
  --steel:#7FB3D4; --steel-bg:#182A34;
  --violet:#B7AFCB;--violet-bg:#241F2E;
  --shadow:0 1px 3px rgba(0,0,0,.35), 0 14px 30px -20px rgba(0,0,0,.6);
}}
:root[data-theme="dark"]{
  --paper:#0E1613; --card:#151F1B; --sunk:#1B2723;
  --ink:#EAF1EE; --muted:#93A39C; --faint:#6F7E78;
  --hair:#28352F; --hair-2:#374540;
  --accent:#3FC9B4; --accent-ink:#BEF0E5; --accent-bg:#12332C;
  --amber:#E3A83F; --amber-bg:#332A16;
  --rust:#E08066;  --rust-bg:#35201A;
  --steel:#7FB3D4; --steel-bg:#182A34;
  --violet:#B7AFCB;--violet-bg:#241F2E;
  --shadow:0 1px 3px rgba(0,0,0,.35), 0 14px 30px -20px rgba(0,0,0,.6);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--paper);color:var(--ink);font-family:var(--body);-webkit-font-smoothing:antialiased;line-height:1.55}
::selection{background:var(--accent-bg)}
.wrap{max-width:1180px;margin:0 auto;padding-inline:18px;padding-block:34px 90px}
a{color:var(--accent)}

/* Masthead */
header.top{border-bottom:2px solid var(--ink);padding-bottom:18px;margin-bottom:26px}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);margin:0 0 8px}
h1{font-family:var(--disp);font-weight:800;font-size:clamp(34px,6vw,58px);line-height:.92;margin:0;letter-spacing:.3px;text-wrap:balance}
.lede{font-size:16px;color:var(--muted);margin:14px 0 0;max-width:68ch}
.lede b{color:var(--ink);font-weight:600}

/* Start-here strip */
.start{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px;margin:24px 0 8px}
.scard{background:var(--card);border:1px solid var(--hair);border-radius:12px;padding:16px 18px;box-shadow:0 1px 2px rgba(10,20,18,.04)}
.scard h3{font-family:var(--disp);font-size:20px;font-weight:700;margin:0 0 6px;letter-spacing:.3px}
.scard p{margin:0;font-size:13.5px;color:var(--muted)}
.scard b{color:var(--ink);font-weight:600}

section{margin-top:44px}
.shead{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;border-bottom:1px solid var(--hair);padding-bottom:9px;margin-bottom:8px}
.shead h2{font-family:var(--disp);font-weight:700;font-size:25px;margin:0;letter-spacing:.4px;text-transform:uppercase}
.shead .count{font-family:var(--mono);font-size:11.5px;color:var(--faint)}
.snote{font-size:14px;color:var(--muted);margin:0 0 18px;max-width:78ch}
.snote b{color:var(--ink);font-weight:600}

/* Tiles */
.grp{margin-top:22px}
.grp h3{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);
  margin:0 0 10px;padding-bottom:6px;border-bottom:1px solid var(--hair)}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.tile{all:unset;cursor:pointer;background:var(--card);border:1px solid var(--hair);border-radius:11px;
  padding:14px 16px 15px;display:flex;flex-direction:column;gap:9px;transition:border-color .15s ease,transform .1s ease}
.tile:hover{border-color:var(--hair-2);transform:translateY(-1px)}
.tile:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tile .nm{font-weight:600;font-size:15px;line-height:1.3}
.tile .qn{font-size:13px;color:var(--muted);line-height:1.5}
.flow{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-family:var(--mono);font-size:10.5px}
.flow .from{color:var(--muted)}
.flow .arrow{color:var(--faint)}
.flow .to{color:var(--accent-ink);background:var(--accent-bg);padding:2px 7px;border-radius:5px;word-break:break-all}
:root[data-theme="dark"] .flow .to,:root:not([data-theme="light"]) .flow .to{color:var(--accent)}
.flow .to.none{background:var(--sunk);color:var(--muted)}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{font-family:var(--mono);font-size:9.5px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;
  padding:3px 8px;border-radius:999px;white-space:nowrap}
.chip.real{background:var(--accent-bg);color:var(--accent-ink)}
:root[data-theme="dark"] .chip.real,:root:not([data-theme="light"]) .chip.real{color:var(--accent)}
.chip.injected{background:var(--steel-bg);color:var(--steel)}
.chip.empty{background:var(--sunk);color:var(--muted)}
.chip.mixed{background:var(--violet-bg);color:var(--violet)}
.chip.open{background:var(--amber-bg);color:var(--amber)}
.src{font-family:var(--mono);font-size:9.5px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;padding:3px 8px;border-radius:999px}
.src.clean{background:var(--sunk);color:var(--muted)}
.src.flagged{background:var(--amber-bg);color:var(--amber)}
.src.broken{background:var(--rust-bg);color:var(--rust)}
.src.monday{background:var(--violet-bg);color:var(--violet)}
.src.manual{background:var(--steel-bg);color:var(--steel)}

/* Glossary */
.gsearch{display:flex;gap:10px;align-items:center;margin-bottom:14px;flex-wrap:wrap}
.gsearch input{font:inherit;font-size:14px;padding:9px 13px;border-radius:9px;border:1px solid var(--hair);
  background:var(--card);color:var(--ink);min-width:240px;flex:1}
.gsearch input:focus{outline:2px solid var(--accent);outline-offset:1px}
.gsearch .hits{font-family:var(--mono);font-size:11.5px;color:var(--faint)}
.terms{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:12px}
.term{background:var(--card);border:1px solid var(--hair);border-radius:11px;padding:13px 16px}
.term dt{font-weight:600;font-size:14.5px;margin:0 0 5px}
.term .p{font-size:13.5px;color:var(--ink);margin:0 0 7px;line-height:1.5}
.term .w{font-size:12.5px;color:var(--muted);margin:0;line-height:1.5;padding-left:11px;border-left:2px solid var(--accent-bg)}

/* Decisions */
.flags{display:flex;flex-direction:column;gap:12px}
.flag{background:var(--card);border:1px solid var(--hair);border-left:3px solid var(--amber);border-radius:11px;padding:15px 18px}
.flag .q{font-size:16px;font-weight:600;margin:0 0 8px;line-height:1.4;text-wrap:pretty}
.flag .meta{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:9px}
.flag .who{font-family:var(--mono);font-size:10px;letter-spacing:.05em;text-transform:uppercase;
  background:var(--amber-bg);color:var(--amber);padding:3px 9px;border-radius:999px}
.flag .tag{font-family:var(--mono);font-size:10px;letter-spacing:.05em;text-transform:uppercase;
  background:var(--sunk);color:var(--muted);padding:3px 9px;border-radius:999px}
.flag .c{font-size:13.5px;color:var(--muted);margin:0;line-height:1.6}
.flag .c b{color:var(--ink);font-weight:600}
.flag .c code{font-family:var(--mono);font-size:12px;background:var(--sunk);padding:1px 5px;border-radius:4px;color:var(--ink)}

/* Tables / forms / recent */
.rows{background:var(--card);border:1px solid var(--hair);border-radius:12px;overflow:hidden}
.row{display:grid;grid-template-columns:200px 1fr;gap:16px;padding:14px 18px;border-bottom:1px solid var(--hair)}
.row:last-child{border-bottom:none}
.row .k{font-family:var(--mono);font-size:12px;color:var(--accent-ink);word-break:break-all}
:root[data-theme="dark"] .row .k,:root:not([data-theme="light"]) .row .k{color:var(--accent)}
.row .v{font-size:13.5px;color:var(--muted);line-height:1.6}
.row .v b{color:var(--ink);font-weight:600}
.row .warn{display:block;margin-top:7px;background:var(--amber-bg);color:var(--ink);border-radius:7px;padding:8px 11px;font-size:13px}
@media (max-width:640px){.row{grid-template-columns:1fr;gap:5px}}

.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.tab{all:unset;cursor:pointer;font-family:var(--mono);font-size:11.5px;padding:8px 14px;border-radius:999px;
  border:1px solid var(--hair);background:var(--card);color:var(--muted)}
.tab[aria-selected="true"]{background:var(--accent-bg);border-color:var(--accent);color:var(--accent-ink);font-weight:600}
:root[data-theme="dark"] .tab[aria-selected="true"],:root:not([data-theme="light"]) .tab[aria-selected="true"]{color:var(--accent)}
.tab:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.fpanel{background:var(--card);border:1px solid var(--hair);border-radius:12px;overflow:hidden}
.fhead{padding:16px 18px;border-bottom:1px solid var(--hair);background:var(--paper)}
.fhead .fn{font-family:var(--disp);font-weight:700;font-size:21px;letter-spacing:.3px}
.fhead p{margin:6px 0 0;font-size:13.5px;color:var(--muted);max-width:76ch}
.fhead .fm{font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:8px}
.frow{display:grid;grid-template-columns:1fr 110px 1.6fr;gap:14px;padding:11px 18px;border-bottom:1px solid var(--hair);align-items:baseline}
.frow:last-of-type{border-bottom:none}
.frow .fl{font-size:13.5px;font-weight:600}
.frow .ft{font-family:var(--mono);font-size:10.5px;color:var(--muted)}
.frow .fh{font-size:12.5px;color:var(--muted);line-height:1.5}
@media (max-width:640px){.frow{grid-template-columns:1fr;gap:4px}}
.fnote{font-size:12.5px;padding:12px 18px;background:var(--sunk);line-height:1.55}

.recent{display:flex;flex-direction:column;gap:10px}
.rec{display:grid;grid-template-columns:78px 1fr;gap:14px;background:var(--card);border:1px solid var(--hair);
  border-radius:11px;padding:13px 16px}
.rec .when{font-family:var(--mono);font-size:11px;color:var(--faint);padding-top:3px}
.rec .what{font-size:14.5px;font-weight:600;margin:0 0 4px}
.rec .detail{font-size:13px;color:var(--muted);margin:0;line-height:1.55}
@media (max-width:640px){.rec{grid-template-columns:1fr;gap:4px}}

/* Drawer */
.scrim{position:fixed;inset:0;background:rgba(10,20,18,.34);opacity:0;pointer-events:none;transition:opacity .2s ease;z-index:40}
.scrim.show{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;right:0;height:100%;width:470px;max-width:94vw;background:var(--card);z-index:50;
  box-shadow:-16px 0 40px -12px rgba(10,20,18,.35);transform:translateX(100%);
  transition:transform .26s cubic-bezier(.2,.8,.2,1);display:flex;flex-direction:column}
.drawer.show{transform:translateX(0)}
.dhead{padding:22px 24px 15px;border-bottom:1px solid var(--hair);display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
.dhead .sec{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);display:block;margin-bottom:5px}
.dhead h3{margin:0;font-family:var(--disp);font-size:22px;font-weight:700;line-height:1.15}
.dclose{all:unset;cursor:pointer;width:30px;height:30px;border-radius:8px;display:flex;align-items:center;
  justify-content:center;color:var(--muted);background:var(--paper);flex-shrink:0}
.dclose:hover{color:var(--ink)}
.dclose:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.dbody{padding:18px 24px 40px;overflow-y:auto;flex:1}
.blk{margin-bottom:17px}
.blk .k{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.blk .v{font-size:13.5px;line-height:1.6}
.blk .v.mono{font-family:var(--mono);font-size:12px;background:var(--paper);border:1px solid var(--hair);
  padding:10px 12px;border-radius:8px;word-break:break-all}
.blk .v.warn{background:var(--amber-bg);padding:11px 13px;border-radius:8px;border:1px solid var(--amber)}

footer{margin-top:46px;padding-top:18px;border-top:1px solid var(--hair);font-family:var(--mono);
  font-size:11.5px;color:var(--faint);line-height:1.9;text-align:center}
@media (prefers-reduced-motion:reduce){.tile,.drawer,.scrim{transition:none}}
</style>

<div class="wrap">
  <header class="top">
    <p class="eyebrow">Vox Nutrition &middot; Plex migration</p>
    <h1>Migration&nbsp;Board</h1>
    <p class="lede">Every number on the MTD scorecard, in plain English: <b>what it answers</b>,
      <b>where it comes from today</b>, <b>where it will come from in Plex</b>, and <b>what is actually
      in it right now</b>. No prior knowledge assumed &mdash; the jargon is all translated further down.
      Open decisions are near the bottom; this page is the one place they are tracked.</p>
  </header>

  <div class="start">
    <div class="scard">
      <h3>What is happening</h3>
      <p>The scorecard is fed today by <b>26 sources</b> &mdash; mostly Google Sheets, some Monday.com.
        Five are broken and ten are flagged. We are moving each number onto Plex, the ERP the factory
        already runs on, read through BigQuery.</p>
    </div>
    <div class="scard">
      <h3>How to read a tile</h3>
      <p>Each card shows <b>today's source &rarr; the Plex view replacing it</b>, and a badge for what is
        in it right now. Click any tile for the plain-English question it answers and what is still
        unknown about it.</p>
    </div>
    <div class="scard">
      <h3>Real or test?</h3>
      <p><b>Real</b> means Vox's own data. <b>Test</b> means rows we injected on purpose to prove the
        wiring works &mdash; they are not Vox figures and are wiped nightly. A tile that stays blank with
        test data underneath is one we have to fix.</p>
    </div>
  </div>

  <section id="map">
    <div class="shead"><h2>Where every number comes from</h2><span class="count" id="tilecount"></span></div>
    <p class="snote">Grouped the way the scorecard is. The middle line of each card is the whole migration in
      one glance: <b>the source feeding it today</b>, then <b>the Plex view that replaces it</b>. A source
      marked <b>broken</b> or <b>flagged</b> is the audit's own verdict on the current dashboard, not ours.</p>
    <div id="sections"></div>
  </section>

  <section id="jargon">
    <div class="shead"><h2>Say that again, in English</h2><span class="count" id="gcount"></span></div>
    <p class="snote">Every term that has cost someone an explanation on this project. Each one says what it
      means, then <b>why it matters here</b> &mdash; which is usually where the trap is.</p>
    <div class="gsearch">
      <label for="gq" style="font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint)">Find a term</label>
      <input id="gq" type="search" placeholder="scrap, FPY, WIP, run rate&hellip;" autocomplete="off">
      <span class="hits" id="ghits"></span>
    </div>
    <div class="terms" id="terms"></div>
  </section>

  <section id="decisions">
    <div class="shead"><h2>Decisions we still need</h2><span class="count" id="flagcount"></span></div>
    <p class="snote">Each one blocks something specific, and each one is a judgement only Vox can make.
      Answered questions are retired from this list rather than kept for the record.</p>
    <div class="flags" id="flags"></div>
  </section>

  <section id="tables">
    <div class="shead"><h2>Two tables nothing here creates</h2><span class="count">hand-maintained</span></div>
    <p class="snote">Almost everything on this page is extracted from Plex automatically. These two are not
      &mdash; they hold numbers people negotiate rather than numbers a factory records.</p>
    <div class="rows" id="tablerows"></div>
  </section>

  <section id="forms">
    <div class="shead"><h2>The manual-data forms</h2><span class="count">2 forms &middot; one web app</span></div>
    <p class="snote">What Plex cannot hold gets typed into one small web app, which writes to a Google Sheet
      and mirrors it into BigQuery. <b>Nobody types into the sheet</b> &mdash; the form is the only writer,
      every tab is append-only, and every row records who entered it.</p>
    <div class="tabs" id="ftabs" role="tablist"></div>
    <div id="fpanels"></div>
  </section>

  <section id="recent">
    <div class="shead"><h2>What changed recently</h2><span class="count">22 Sep 2026</span></div>
    <p class="snote">Mostly things that looked fine and were not. Recorded because each one was invisible
      from the dashboard, which is the whole reason this page exists.</p>
    <div class="recent" id="recentlist"></div>
  </section>

  <footer>
    Every figure here was read straight out of BigQuery on 22 September 2026. Nothing is estimated.<br>
    View names and fields are identical in PlexTest and PlexProd, so a scorecard built against test
    switches over by changing the data source alone.<br>
    This page is redeployed to the same link as work lands &mdash; re-open it rather than asking for a new one.
  </footer>
</div>

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" role="dialog" aria-modal="true" aria-labelledby="dtitle">
  <div class="dhead">
    <div><span class="sec" id="dsec"></span><h3 id="dtitle"></h3></div>
    <button class="dclose" id="dclose" aria-label="Close">&#10005;</button>
  </div>
  <div class="dbody" id="dbody"></div>
</aside>

<script id="board-data" type="application/json">__DATA__</script>
<script>
(function(){
  var D = JSON.parse(document.getElementById('board-data').textContent);
  var KIND = {real:'Vox data', injected:'Test data', empty:'Nothing yet', mixed:'Mixed'};
  var SRC  = {clean:'works today', flagged:'flagged', broken:'broken today', monday:'Monday.com', manual:'typed by hand'};

  function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }

  // ── Tiles, grouped ──────────────────────────────────────────────────────
  var order = [], bySec = {};
  D.tiles.forEach(function(t){ if(!bySec[t.s]){ bySec[t.s]=[]; order.push(t.s); } bySec[t.s].push(t); });
  document.getElementById('tilecount').textContent =
    D.tiles.length + ' tiles \\u00b7 ' + D.tiles.filter(function(t){return t.kind==='real';}).length +
    ' carrying Vox data \\u00b7 ' + D.tiles.filter(function(t){return t.open;}).length + ' with something open';

  document.getElementById('sections').innerHTML = order.map(function(sec){
    return '<div class="grp"><h3>' + esc(sec) + '</h3><div class="tiles">' +
      bySec[sec].map(function(t){
        var i = D.tiles.indexOf(t);
        return '<button class="tile" data-i="' + i + '">' +
          '<span class="nm">' + esc(t.t) + '</span>' +
          '<span class="qn">' + esc(t.q) + '</span>' +
          '<span class="flow"><span class="from">today</span><span class="arrow">&rarr;</span>' +
            '<span class="to' + (t.v ? '' : ' none') + '">' + esc(t.v || 'stays where it is') + '</span></span>' +
          '<span class="chips">' +
            '<span class="src ' + t.todayst + '">' + esc(SRC[t.todayst]) + '</span>' +
            '<span class="chip ' + t.kind + '">' + esc(KIND[t.kind]) + ' \\u00b7 ' + esc(t.rows) + '</span>' +
            (t.open ? '<span class="chip open">open question</span>' : '') +
          '</span>' +
        '</button>';
      }).join('') + '</div></div>';
  }).join('');

  // ── Glossary ────────────────────────────────────────────────────────────
  var terms = document.getElementById('terms'), gq = document.getElementById('gq'),
      ghits = document.getElementById('ghits');
  document.getElementById('gcount').textContent = D.glossary.length + ' terms';

  function renderTerms(q){
    q = (q||'').trim().toLowerCase();
    var list = !q ? D.glossary : D.glossary.filter(function(g){
      return (g.term + ' ' + g.plain + ' ' + g.why).toLowerCase().indexOf(q) > -1;
    });
    ghits.textContent = q ? (list.length + ' of ' + D.glossary.length) : '';
    terms.innerHTML = list.length ? list.map(function(g){
      return '<dl class="term"><dt>' + esc(g.term) + '</dt>' +
        '<dd class="p">' + esc(g.plain) + '</dd>' +
        '<dd class="w">' + esc(g.why) + '</dd></dl>';
    }).join('') : '<p class="snote">No term matches that. Try a shorter word.</p>';
  }
  renderTerms('');
  gq.addEventListener('input', function(){ renderTerms(gq.value); });

  // ── Decisions ───────────────────────────────────────────────────────────
  document.getElementById('flagcount').textContent = D.flags.length + ' open';
  document.getElementById('flags').innerHTML = D.flags.map(function(f){
    return '<div class="flag"><p class="q">' + esc(f.q) + '</p>' +
      '<div class="meta"><span class="who">' + esc(f.who) + '</span>' +
      '<span class="tag">' + esc(f.tag) + '</span></div>' +
      '<p class="c">' + f.c + '</p></div>';
  }).join('');

  // ── Hand-maintained tables ──────────────────────────────────────────────
  document.getElementById('tablerows').innerHTML = D.tables.map(function(t){
    return '<div class="row"><span class="k">' + esc(t.name) + '</span><span class="v">' +
      esc(t.what) + '<br><b>Maintained by:</b> ' + esc(t.who) + '<br>' + t.state +
      '<span class="warn">' + esc(t.warn) + '</span></span></div>';
  }).join('');

  // ── Forms ───────────────────────────────────────────────────────────────
  var ftabs = document.getElementById('ftabs'), fpanels = document.getElementById('fpanels');
  ftabs.innerHTML = D.forms.map(function(f,i){
    return '<button class="tab" role="tab" id="tab-' + f.id + '" aria-controls="panel-' + f.id +
      '" aria-selected="' + (i===0) + '" data-f="' + f.id + '">' + esc(f.label) + '</button>';
  }).join('');
  fpanels.innerHTML = D.forms.map(function(f,i){
    return '<div class="fpanel" role="tabpanel" id="panel-' + f.id + '" aria-labelledby="tab-' + f.id + '"' +
      (i===0?'':' hidden') + '><div class="fhead"><div class="fn">' + esc(f.label) + '</div>' +
      '<p>' + esc(f.blurb) + '</p><div class="fm">Writes to ' + esc(f.table) +
      ' &middot; one row per ' + esc(f.key) + '</div></div>' +
      f.fields.map(function(x){
        return '<div class="frow"><span class="fl">' + esc(x[0]) + '</span><span class="ft">' +
          esc(x[1]) + '</span><span class="fh">' + esc(x[2]) + '</span></div>';
      }).join('') + '<p class="fnote">' + esc(f.note) + '</p></div>';
  }).join('');
  ftabs.addEventListener('click', function(e){
    var b = e.target.closest('.tab'); if(!b) return;
    D.forms.forEach(function(f){
      var on = f.id === b.dataset.f;
      document.getElementById('tab-' + f.id).setAttribute('aria-selected', on);
      document.getElementById('panel-' + f.id).hidden = !on;
    });
  });

  // ── Recently changed ────────────────────────────────────────────────────
  document.getElementById('recentlist').innerHTML = D.recent.map(function(r){
    return '<div class="rec"><span class="when">' + esc(r.when) + '</span><div>' +
      '<p class="what">' + esc(r.what) + '</p>' +
      '<p class="detail">' + esc(r.detail) + '</p></div></div>';
  }).join('');

  // ── Drawer ──────────────────────────────────────────────────────────────
  var drawer = document.getElementById('drawer'), scrim = document.getElementById('scrim'),
      dsec = document.getElementById('dsec'), dtitle = document.getElementById('dtitle'),
      dbody = document.getElementById('dbody'), last = null;

  function blk(k, v, cls){
    return '<div class="blk"><div class="k">' + k + '</div><div class="v' + (cls||'') + '">' + v + '</div></div>';
  }
  function open(t, el){
    last = el;
    dsec.textContent = t.s;
    dtitle.textContent = t.t;
    var b = blk('The question it answers', esc(t.q));
    b += blk('Where it comes from today', esc(t.today) + ' &mdash; <b>' + esc(SRC[t.todayst]) + '</b>');
    b += blk('Where it comes from in Plex', esc(t.v || 'Nothing. This one stays where it is.'), t.v ? ' mono' : '');
    b += blk('In it right now', '<b>' + esc(KIND[t.kind]) + '</b> &mdash; ' + esc(t.rows) +
      (t.kind === 'injected' ? '<br>Injected on purpose to prove the wiring. Not a Vox figure, and wiped nightly.' : ''));
    if (t.open) b += blk('Still open', esc(t.open), ' warn');
    dbody.innerHTML = b;
    dbody.scrollTop = 0;
    drawer.classList.add('show'); scrim.classList.add('show');
    document.getElementById('dclose').focus();
  }
  function close(){
    drawer.classList.remove('show'); scrim.classList.remove('show');
    if (last) last.focus();
  }
  document.getElementById('sections').addEventListener('click', function(e){
    var btn = e.target.closest('.tile'); if(!btn) return;
    open(D.tiles[+btn.dataset.i], btn);
  });
  document.getElementById('dclose').addEventListener('click', close);
  scrim.addEventListener('click', close);
  document.addEventListener('keydown', function(e){ if(e.key === 'Escape') close(); });
})();
</script>
"""

io.open(OUT, "w", encoding="utf-8", newline="").write(HTML.replace("__DATA__", DATA))
print("wrote", OUT, len(HTML) + len(DATA), "chars")
