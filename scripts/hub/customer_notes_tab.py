#!/usr/bin/env python3
"""The "Customer notes" tab of the Plex Data Hub: the 2026-11 bulk update of customer Notes.

scripts/plex_customer_notes_bulk.py sets each customer's Note in Plex from
docs/reference/CustomerNotesResults9.csv, in verified batches (runbook:
docs/CUSTOMER_NOTES_BULK.md). This tab shows every row of the plan with its state as a pill
("Note written", "Appended", "Pending", or why it was flagged) and its own log history, plus the
batch log with every review and stop.

The plan and the log hold customer names and notes, so they stay out of git
(etl-manual/customer_note/ in the primary folder). build_hub.py injects the tab into the live page
only; with no plan there is no tab.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

START, END = "<!--custnotes-tab-start-->", "<!--custnotes-tab-end-->"
ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT.parent / "plex-to-big-query" / "etl-manual" / "customer_note"
PLAN, LOG, STOP = DIR / "bulk_plan.csv", DIR / "bulk_actions.jsonl", DIR / "BULK_STOPPED.txt"
# 2026-11-11 (Ashley: "will this pop up on the customer orders, or just the profile?"): screenshots
# of a read-only check in Plex, kept with the notes data (gitignored: they show customer data).
SHOTS = DIR / "ashley_check"
WHERE_SHOWN = [
    ("1_customer_details.png", "Customer Details (the profile): the Note field holds the note.", "yes"),
    ("6_order_form_681.png", "Order 681's form: its NOTES section is the order's own Internal Note, Printed Note, Special Instructions and Shipper Note; the customer note is not there.", "no"),
    ("7_tab_Notes.png", "Order 681's Notes tab (order notes): \"No Records Were Found\".", "no"),
    ("2_order_rapid_entry.png", "Order Line Rapid Entry for order 681: no customer note.", "no"),
]


def where_shown() -> str:
    """The 11-11 check of where a customer Note appears, with its screenshots inlined."""
    import base64
    if not SHOTS.exists():
        return ""
    figs = []
    for f, cap, shown in WHERE_SHOWN:
        fp = SHOTS / f
        if not fp.exists():
            continue
        b64 = base64.b64encode(fp.read_bytes()).decode()
        figs.append(f'<figure class="cn-fig"><img alt="{esc(cap)}" src="data:image/png;base64,{b64}" loading="lazy">'
                    f'<figcaption><b>{"Shows the note" if shown == "yes" else "Does not show it"}.</b> {esc(cap)}</figcaption></figure>')
    return ('<div class="block"><h2>Where the note shows in Plex</h2><p class="lede">Checked 2026-11-11 for Ashley, read-only, '
            'with L&amp;M Supplements (note starting "ACH Signed Prop 65") and its open order 681. The note is on the customer\'s '
            'profile only. It is not copied onto orders and none of the order screens show it: the sales order form, the order\'s '
            'Notes tab, Order Line Rapid Entry, the Sales Orders list, and the info icon beside Customer (field help only). '
            'Not checked: creating a new order (that would write to Plex) and printed documents such as the packing list. '
            'If a note must travel with an order, it belongs in one of the order\'s own notes.</p>'
            '<div class="cn-figs">' + "".join(figs) + '</div></div>')
NAV = '["platform", "Schedules & probe", ""]'
STATS = '  $("#q").disabled = '
MT = ZoneInfo("America/Denver")

FLAG_TEXT = {
    "flag-inactive": "Flag: inactive",
    "flag-name-mismatch": "Flag: name differs",
    "flag-not-in-plex": "Flag: code not in Plex",
    "flag-no-code": "Flag: no Plex code",
    "flag-no-customer-no": "Flag: no Customer No",
}

CHECKS = [
    ("1. Claude's plan", "Each row's Plex Customer Code matched to Plex's customers (API backup of all 4,109), its note and status read."),
    ("2. An independent Sonnet agent", "Built its own plan from the same two files without seeing the first: identical on all 3,162 rows with a code."),
    ("3. A different source", "Plex's ODBC customer table in BigQuery: every code, name and status agrees, and every customer to write has the Customer No the screen needs."),
    ("4. During the run", "Before each write the screen must show the planned customer and the backed-up note; after Apply the screen is reloaded and must hold the planned text; "
                          "after each batch every customer is read back through the API (the batch, all earlier ones, and no other customer changed), and Claude reviews it before the next batch."),
]

RULES = [
    ("Written", "Code and name identical to Plex, customer Active, Plex note empty: the comment becomes the Note."),
    ("Appended", "Same, but the customer already had a note: the comment is added on a new line below it, nothing is removed. Also flagged."),
    ("Not written, flagged", "Inactive customers (for now), a name that is not identical to Plex's, a code that is not in Plex, or a comment with no code."),
]


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def mt(ts: str) -> str:
    try:
        return dt.datetime.fromisoformat(ts).astimezone(MT).strftime("%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return ts


def gather() -> dict:
    plan = list(csv.DictReader(PLAN.open(encoding="utf-8", newline="")))
    log = [json.loads(x) for x in LOG.read_text(encoding="utf-8").splitlines() if x.strip()] if LOG.exists() else []
    by_seq: dict[str, list] = {}
    batch_of: dict[str, int] = {}
    verified: dict[int, str] = {}
    for e in log:
        if e["event"] == "batch-start":
            for s in e.get("seqs", []):
                batch_of[s] = e["batch"]
        if e["event"] == "verified":
            verified[e["batch"]] = e["ts"]
        if e.get("seq"):
            by_seq.setdefault(e["seq"], []).append(e)
    rows = []
    for p in plan:
        hist = []
        for e in by_seq.get(p["seq"], []):
            what = {"saved": "written and read back", "already-set": "already held the note",
                    "abort": "STOPPED: " + e.get("reason", "")}.get(e["event"], e["event"])
            hist.append(f'{mt(e["ts"])} batch {e.get("batch", "?")}: {what}')
        b = batch_of.get(p["seq"])
        if b and b in verified and any(e["event"] in ("saved", "already-set") for e in by_seq.get(p["seq"], [])):
            hist.append(f"{mt(verified[b])} batch {b}: verified through the API")
        saved = any(e["event"] in ("saved", "already-set") for e in by_seq.get(p["seq"], []))
        failed = any(e["event"] == "abort" for e in by_seq.get(p["seq"], []))
        cat = p["category"]
        if cat in ("write", "append"):
            state = ("Note written" if cat == "write" else "Appended") if saved else ("Stopped here" if failed else "Pending")
            kind = "ok" if saved and cat == "write" else "warn" if saved else "bad" if failed else "none"
        else:
            state, kind = FLAG_TEXT.get(cat, cat), "warn"
        rows.append({"seq": int(p["seq"]), "line": p["csv_line"], "code": p["code"], "name": p["plex_name"] or p["file_name"],
                     "file_name": p["file_name"], "status": p["plex_status"], "cat": cat, "state": state, "kind": kind,
                     "note": p["new_note"] or p["comment"], "before": p["before_note"], "hist": hist})
    runlog = [{"ts": mt(e["ts"]), "actor": e["actor"], "event": e["event"],
               "detail": e.get("text") or e.get("reason") or
               ", ".join(f"{k} {v}" for k, v in e.items() if k in ("batch", "size", "batch_saved", "total_done", "counts", "customers_checked"))}
              for e in log if e["event"] not in ("saved", "already-set")]
    return {"rows": rows, "runlog": runlog, "stopped": STOP.read_text(encoding="utf-8") if STOP.exists() else "",
            "taken": dt.datetime.now(MT).strftime("%Y-%m-%d %H:%M MT")}


def render_tab(d: dict) -> str:
    rows = d["rows"]
    n = lambda f: sum(1 for r in rows if f(r))
    stats = [(n(lambda r: r["state"] == "Note written"), "notes written"),
             (n(lambda r: r["state"] == "Appended"), "appended to an existing note"),
             (n(lambda r: r["state"] == "Pending"), "still to write"),
             (n(lambda r: r["cat"].startswith("flag")), "flagged, not written"),
             (len(rows), "rows with a comment")]
    stats_html = "".join(f'<div class="stat"><b>{v:,}</b><span>{esc(l)}</span></div>' for v, l in stats)
    stopped = (f'<div class="note"><b>Stopped.</b> Nothing runs until the reason is reviewed:<pre>{esc(d["stopped"])}</pre></div>'
               if d["stopped"] else "")
    checks = "".join(f"<dt>{esc(h)}</dt><dd>{esc(t)}</dd>" for h, t in CHECKS)
    rules = "".join(f"<dt>{esc(h)}</dt><dd>{esc(t)}</dd>" for h, t in RULES)
    runlog = ('<table class="cn-t"><thead><tr><th>When (MT)</th><th>Who</th><th>What</th><th>Detail</th></tr></thead><tbody>'
              + "".join(f'<tr><td>{esc(e["ts"])}</td><td>{esc(e["actor"])}</td><td>{esc(e["event"])}</td><td>{esc(e["detail"])}</td></tr>'
                        for e in reversed(d["runlog"])) + "</tbody></table>")
    states = sorted({r["state"] for r in rows}, key=lambda s: (not s.startswith("Note"), s))
    filters = '<button class="cn-f on" data-f="">All</button>' + "".join(
        f'<button class="cn-f" data-f="{esc(s)}">{esc(s)} ({n(lambda r, s=s: r["state"] == s):,})</button>' for s in states)
    # U+FFFD is escaped: 8 Plex customer names hold it (Plex's own data, e.g. "Equilibre sant\ufffd Naturel")
    # and the artifact service refuses a page with a raw replacement character.
    data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/").replace("\ufffd", "\\ufffd")
    css = """
.cn-figs{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:14px}
.cn-fig{margin:0;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:10px;min-width:0}
.cn-fig img{width:100%;height:auto;border-radius:4px;border:1px solid var(--line)}
.cn-fig figcaption{font-size:13px;color:var(--muted);margin-top:6px}
#s-custnotes .cn-bar { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 10px; align-items: center; }
#s-custnotes .cn-f { border: 1px solid var(--line); background: none; color: inherit; border-radius: 6px; padding: 3px 9px; font-size: 12px; cursor: pointer; }
#s-custnotes .cn-f.on { border-color: currentColor; font-weight: 600; }
#s-custnotes #cn-q { min-width: 220px; flex: 1; padding: 5px 8px; border: 1px solid var(--line); border-radius: 6px; background: none; color: inherit; }
#s-custnotes .cn-scroll { overflow: auto; max-height: 70vh; }
#s-custnotes .cn-t { border-collapse: collapse; width: 100%; font-size: 13px; }
#s-custnotes .cn-t th { position: sticky; top: 0; background: var(--bg, #fff); text-align: left; }
#s-custnotes .cn-t td, #s-custnotes .cn-t th { border-bottom: 1px solid var(--line); padding: 5px 8px; vertical-align: top; }
#s-custnotes .cn-note { white-space: pre-wrap; max-width: 420px; overflow-wrap: anywhere; }
#s-custnotes .cn-hist { font-size: 12px; color: var(--muted); white-space: nowrap; }
#s-custnotes .cn-sub { display: block; font-size: 11px; color: var(--muted); }
#s-custnotes pre { white-space: pre-wrap; margin: 6px 0 0; }
"""
    js = """
(() => {
  const root = document.getElementById("s-custnotes"); if (!root) return;
  const rows = JSON.parse(document.getElementById("cn-data").textContent);
  const body = root.querySelector("#cn-body"), q = root.querySelector("#cn-q"), shown = root.querySelector("#cn-shown");
  let f = "";
  const e = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  function draw() {
    const t = q.value.trim().toLowerCase();
    const list = rows.filter(r => (!f || r.state === f) && (!t || (r.code + " " + r.name + " " + r.file_name + " " + r.note).toLowerCase().includes(t)));
    shown.textContent = list.length.toLocaleString() + " shown";
    body.innerHTML = list.slice(0, 600).map(r =>
      `<tr><td><b>${e(r.code || "-")}</b><span class="cn-sub">file line ${e(r.line)}</span></td>` +
      `<td>${e(r.name)}${r.file_name && r.file_name !== r.name ? `<span class="cn-sub">file: ${e(r.file_name)}</span>` : ""}<span class="cn-sub">${e(r.status)}</span></td>` +
      `<td><span class="pill ${r.kind}">${e(r.state)}</span></td>` +
      `<td class="cn-note">${e(r.note)}${r.cat === "append" ? `<span class="cn-sub">was: ${e(r.before)}</span>` : ""}</td>` +
      `<td class="cn-hist">${r.hist.map(e).join("<br>") || "-"}</td></tr>`).join("") +
      (list.length > 600 ? `<tr><td colspan="5" class="cn-sub">First 600 of ${list.length.toLocaleString()}; search or filter to narrow.</td></tr>` : "");
  }
  root.querySelectorAll(".cn-f").forEach(b => b.addEventListener("click", () => {
    root.querySelectorAll(".cn-f").forEach(x => x.classList.remove("on")); b.classList.add("on"); f = b.dataset.f; draw(); }));
  q.addEventListener("input", draw);
  draw();
})();
"""
    return (
        f'{START}<style>{css}</style><section id="s-custnotes" data-tab="custnotes" hidden><div class="ref">'
        f'<div class="block"><h2>Customer notes: bulk update from the customer list</h2>'
        f'<p class="lede">Each customer\'s comment from <code>CustomerNotesResults9.csv</code> is written to the <b>Note</b> '
        f'on Plex\'s Customer Details screen (NOTES section; not the Brief Note, not the Contact Information note), '
        f'by a program that uses the screen the way a person would, in small batches that are checked before the next one starts. '
        f'Status as of {esc(d["taken"])}.</p>{stopped}<div class="stats" style="margin:0">{stats_html}</div></div>'
        f'<div class="two"><div class="block"><h2>What gets written</h2><dl class="kv">{rules}</dl></div>'
        f'<div class="block"><h2>Four checks</h2><dl class="kv">{checks}</dl></div></div>'
        f'{where_shown()}'
        f'<div class="block"><h2>Every row</h2><div class="cn-bar">{filters}<input id="cn-q" type="search" placeholder="Search code, customer or note"> '
        f'<span id="cn-shown" class="cn-sub"></span></div><div class="cn-scroll"><table class="cn-t"><thead><tr><th>Code</th><th>Customer</th>'
        f'<th>State</th><th>Note</th><th>Log history (MT)</th></tr></thead><tbody id="cn-body"></tbody></table></div></div>'
        f'<div class="block"><h2>Run log</h2><p class="lede">Every plan, batch, verification, review, stop and resume, newest first. '
        f'Backup of all customers taken before the plan: <code>etl-manual/customer_note/</code>.</p><div class="cn-scroll">{runlog}</div></div>'
        f'</div></section><script type="application/json" id="cn-data">{data}</script><script>{js}</script>{END}')


def inject(page: str, tab: str) -> str:
    if START in page:
        page = re.sub(re.escape(START) + ".*?" + re.escape(END) + "\n?", lambda m: "", page, flags=re.S)
        page = page.replace(', ["custnotes", "Customer notes", ""]', "").replace('  if (k === "custnotes") $("#stats").hidden = true;\n', "")
    anchor = '  <section id="s-history"'
    for needle in (anchor, NAV, STATS):
        if page.count(needle) != 1:
            sys.exit(f"hub page changed shape: expected exactly one {needle!r}, found {page.count(needle)}")
    page = page.replace(anchor, tab + "\n" + anchor)
    page = page.replace(NAV, NAV + ', ["custnotes", "Customer notes", ""]')
    page = page.replace(STATS, '  if (k === "custnotes") $("#stats").hidden = true;\n' + STATS)
    return page


def add(live: str) -> str:
    if not PLAN.exists():
        return live
    return inject(live, render_tab(gather()))


if __name__ == "__main__":
    sys.exit(__doc__)
