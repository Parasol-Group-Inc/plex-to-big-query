#!/usr/bin/env python3
"""The "Label Design API" tab of the Plex Data Hub (2026-11-11): what Plex's REST API
(connect.plex.com) offers for Label Design, measured read-only, next to ODBC and the screens.

Content comes from docs/hub/label_api_survey.json (a GET-only survey; examples of contact
fields hidden). build_hub.py injects it into the live page like reliability_tab.py.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SURVEY = ROOT / "docs" / "hub" / "label_api_survey.json"
START, END = "<!--labelapi-tab-start-->", "<!--labelapi-tab-end-->"
NAV = '["platform", "Schedules & probe", ""]'
STATS = '  $("#q").disabled = '
KEY, LABEL = "labelapi", "Label Design API"


def esc(s) -> str:
    return html.escape(str(s))


def code(s):
    return f"<code>{esc(s)}</code>"


def table(head, rows):
    h = "".join(f"<th>{esc(x)}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tbl-wrap"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


SOURCES = [
    ("Plex REST API (connect.plex.com)", "live, to the minute", "about 1 s for every Label Design release",
     "none (API key and secret)", "orders, lines, releases, customers, parts, employees; no Job Note or priority",
     "watchdog odbc_vs_plex (since 11-11); proposed: Label Design trigger"),
    ("Plex ODBC (vox.odbc.plex.com)", "a copy refreshed about every 4 h (seen ~09:00, 13:00, 17:00 MT), data ~1 h old at each refresh",
     "seconds per table", "ODBC user", "every table and column", "every ETL report"),
    ("Plex web screens (Playwright)", "live", "about 2 min for the releases screen (one page per order)",
     "portal user, logged and screenshotted", "what the screens show, including Job Note and priority",
     "plex-live-screens: Label Design lines ODBC lacks; checks"),
]

COVERAGE = [
    ("Sales Order", "orders.orderNumber", "yes"),
    ("Customer PO", "orders.poNumber", "yes"),
    ("Date (order date)", "orders.orderDate", "yes"),
    ("Customer Name", "orders.customerId → customers.name", "yes"),
    ("Email, Phone Number", "customers.email, customers.phone", "yes (customer level)"),
    ("Inside Sales Rep (AM)", "orders.insideSalesId or customers.assignedToId → employees", "yes, one more lookup"),
    ("Sales Rep (BDM)", "orders.outsideSalesIds or customers.assignedTo2Id → employees", "yes, one more lookup"),
    ("Release status, due date, quantity", "releases.status, dueDate, quantity", "yes"),
    ("Description (part number, revision, name)", "lines.partId → parts.number, revision, name", "yes"),
    ("Item (customer part number)", "lines.customerPartId", "id only; no customer-part endpoint found"),
    ("Memo, Reason Code (from the Job Note)", "—", "no: the Job Note is not in the API"),
    ("Priority", "—", "no"),
    ("Label Part #, Label Size, Printing Material, Bottle Material", "BOM + part attributes", "no BOM endpoint found; parts.allergens only"),
    ("Part / PO / SO links", "Plex internal keys (PartKey, PO_Key)", "no: the API uses its own ids"),
]

QUIRKS = [
    "Paging is ignored: `limit` and `offset` change nothing; every call returns the whole set (648 orders in about 1 s).",
    "Unknown parameters are ignored silently, not refused. `modifiedDateBegin` works on releases, not on orders.",
    "Status filters are exact strings (`Label Design`, `Pending Fulfillment`).",
    "Order lines need one call per order (0.9 s each with our 0.35 s spacing; 191 orders took 172 s). Cache them and fetch only new orders.",
    "No rate-limit headers came back. The repo spaces calls 0.35 s apart (Plex's limit is about 200 a minute).",
    "Ids are UUIDs, not Plex's PO_Key / Release_Key, so joining to our ODBC tables goes through order number, part number and dates.",
]

DIAGRAM = """flowchart LR
  People["People in Plex&lt;br/&gt;orders, releases, approvals"]
  DB[("Plex database")]
  API["REST API&lt;br/&gt;connect.plex.com&lt;br/&gt;live, ~1 s"]
  ODBC["ODBC copy&lt;br/&gt;refreshed ~every 4 h"]
  UI["Web screens&lt;br/&gt;live, ~2 min, login"]
  Trig["Proposed trigger&lt;br/&gt;every 10-15 min: new Label Design release?"]
  Scr["plex-live-screens&lt;br/&gt;releases screen"]
  ETL["Label Design ETL&lt;br/&gt;every 15 min"]
  WD["Watchdog odbc_vs_plex&lt;br/&gt;every 30 min"]
  View["label_design_report&lt;br/&gt;ODBC lines + lines only the screen has"]
  Mon["Monday&lt;br/&gt;Plex Import Test → Design &amp; QA"]
  People --&gt; DB
  DB --&gt; API
  DB --&gt; ODBC
  DB --&gt; UI
  API -.-&gt; Trig
  Trig -.-&gt;|"yes: read now"| Scr
  API --&gt; WD
  ODBC --&gt; WD
  UI --&gt; Scr --&gt; View
  ODBC --&gt; ETL --&gt; View
  View --&gt;|"push; fills blanks later"| Mon"""


def render_tab() -> str:
    d = json.loads(SURVEY.read_text())
    calls = table(["What", "Request", "Rows", "Seconds"], [
        (esc(c["label"]), code(c["path"] + ("?" + "&".join(f"{k}={v}" for k, v in c["params"].items()) if c["params"] else "")),
         esc(c["rows"]), esc(c["seconds"])) for c in d["calls"]])
    stats = [(str(d["ld_releases"]), "releases in Label Design (all order statuses)"),
             (str(d["ld_changed_24h"]), "of them changed in the last 24 h"),
             (str(d["queue_size"]), f"Label Design lines on Pending Fulfillment orders ({d['queue_orders']} orders)"),
             ("~1 s", "to ask the API for all of them"), ("~2 min", "for the same from the screen")]
    stats_html = "".join(f'<div class="stat"><b>{esc(v)}</b><span>{esc(l)}</span></div>' for v, l in stats)
    fields = []
    names = {"releases": "Release (/sales/v1/releases)", "orders": "Order (/sales/v1/orders)",
             "lines": "Order line (/sales/v1/orders/{id}/lines)", "customer": "Customer (/mdm/v1/customers/{id})",
             "part": "Part (/mdm/v2/parts/{id})"}
    for ent, title in names.items():
        fs = d["fields"].get(ent) or {}
        if not fs:
            continue
        rows = [(code(k), esc(v["type"]), esc("" if v["example"] is None else v["example"])) for k, v in fs.items()]
        fields.append(f'<details class="env"><summary>{esc(title)} · {len(fs)} fields</summary>'
                      + table(["Field", "Type", "Example"], rows) + "</details>")
    statuses = ", ".join(f"{esc(s)} {n}" for s, n in d["order_status_counts"])
    return f"""{START}<section id="s-{KEY}" data-tab="{KEY}" hidden><div class="ref">
<div class="block"><h2>Label Design from Plex's API</h2>
<p class="lede">Plex has three ways in: its REST API, the ODBC copy our ETL reads, and the web screens. For Label Design the API
answers "which releases are in Label Design right now?" in about a second, live, with no browser and no login. It lacks the Job Note,
the priority and Plex's internal keys, so it can tell us <b>when</b> to read the screen, not replace it. Surveyed read-only on
{esc(d.get("surveyed_at", ""))}; nothing was written. Examples of contact fields are hidden.</p>
<div class="stats" style="margin:0">{stats_html}</div></div>
<div class="block"><h2>Architecture</h2><p class="lede">Solid arrows run today; dotted ones are the proposed trigger.</p>
<div class="diagram"><pre class="mermaid">{DIAGRAM}</pre></div></div>
<div class="block"><h2>The three sources</h2>{table(["Source", "How current", "Speed", "Login", "Data", "Used for"], [tuple(esc(x) for x in r) for r in SOURCES])}</div>
<div class="block"><h2>Every Monday column: can the API supply it?</h2>{table(["Monday column", "API field", "Available"], [(esc(a), code(b) if b != "—" else "—", esc(c)) for a, b, c in COVERAGE])}
<p class="lede">The queue rebuilt from the API (Label Design releases on Pending Fulfillment orders dated 10-18 or later) matched the screen's lines exactly on order, part and due date: 64 of 64 on 11-11. All orders by status today: {statuses}.</p></div>
<div class="block"><h2>Calls measured</h2>{calls}</div>
<div class="block"><h2>Fields, by endpoint</h2>{"".join(fields)}</div>
<div class="two"><div class="panel"><h3>Quirks and limits</h3><ul class="plain">{"".join(f"<li>{esc(x)}</li>" for x in QUIRKS)}</ul></div>
<div class="panel"><h3>The proposed trigger</h3><ol class="steps">
<li>Every 10-15 minutes on weekdays, call <code>GET /sales/v1/releases?status=Label Design</code> (about 1 s).</li>
<li>Compare the release ids with the last call. A new id means a new Label Design release.</li>
<li>If there is one, start the releases screen read at once; it brings the full line, Job Note included, and the push sends it to Monday.</li>
<li>If not, skip the screen: no browser, no Plex login.</li>
<li>ODBC still fills in the details and confirms the line after its next refresh.</li></ol>
<p>Result: a new order on Monday in about 15 minutes instead of up to an hour. Not built yet; waiting for a go.</p></div></div>
<div class="block"><h2>How to call it</h2><pre class="code">{esc('''GET https://connect.plex.com/sales/v1/releases?status=Label%20Design
X-Plex-Connect-Api-Key:    <secret plex-api-consumer-key>
X-Plex-Connect-Api-Secret: <secret plex-api-consumer-secret>
Accept: application/json''')}</pre></div>
</div></section>{END}"""


def inject(page: str, tab: str) -> str:
    if START in page:
        page = re.sub(re.escape(START) + ".*?" + re.escape(END) + "\n?", lambda m: "", page, flags=re.S)
        page = page.replace(f', ["{KEY}", "{LABEL}", ""]', "").replace(f'  if (k === "{KEY}") $("#stats").hidden = true;\n', "")
    anchor = '  <section id="s-history"'
    for needle in (anchor, NAV, STATS):
        if page.count(needle) != 1:
            sys.exit(f"hub page changed shape: expected exactly one {needle!r}, found {page.count(needle)}")
    page = page.replace(anchor, tab + "\n" + anchor)
    page = page.replace(NAV, NAV + f', ["{KEY}", "{LABEL}", ""]')
    page = page.replace(STATS, f'  if (k === "{KEY}") $("#stats").hidden = true;\n' + STATS)
    return page


def add(live: str) -> str:
    if not SURVEY.exists():   # the survey file is kept locally until committed
        return live
    return inject(live, render_tab())


if __name__ == "__main__":
    sys.exit(__doc__)
