#!/usr/bin/env python3
"""The "QuickBooks" tab of the Plex Data Hub: fleet health, the Kaya and ODF scorecards, the
project reference and the pipeline atlas.

Moved here from quickbooks-to-biquery/scripts/build_hub_qbo_tab.py on 2026-10-23, because a
hub published from this repo's build used to delete the tab (it happened on 2026-10-22).
`build_hub.py` now calls render_tab() and inject() itself whenever it writes the live page,
so there is one publish step and nothing to run afterwards.

Every scorecard component shows the BigQuery query behind it, and the figures on the page come
from running that same text, so a card and its query cannot disagree. Anything BigQuery does
not hold (Kaya's channel mix, ODF's deposits) has no component.

Standalone use (inject the tab into any hub page; idempotent, replaces the text between the two
marker comments):

    python scripts/hub/qbo_tab.py --hub hub.html --out hub_with_qbo.html

Reads BigQuery in parasoldatalake through application-default credentials, so it needs your own
gcloud login (not the claude-readonly service account) and Python 3.12 or newer. The health
findings and reference tables are dated snapshots written into HEALTH_ASOF below; refresh them
by hand when the picture changes. The atlas view embeds docs/hub/qbo_atlas.html.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

from google.cloud import bigquery

START, END = "<!--qbo-tab-start-->", "<!--qbo-tab-end-->"
HEALTH_ASOF = "2026-10-21 04:00 UTC"
BQ_PROJECT = "parasoldatalake"

# One set of table references per client. Kaya is read through the views in
# Marketing Dashboard (the settled design: one copy of the data, views over it);
# ODF has no second home, so its queries read the dataset directly.
CLIENTS = {
    "kaya": {
        "key": "kaya",
        "name": "Kaya Naturals",
        "title": "KAYA NATURALS MTD SCORECARD",
        "ds": "marketing-dashboard-506920.kaya_quickbooks_prod",
        "base": "parasoldatalake.kaya_quickbooks_prod",
        "pnl": "kaya_qbo_ProfitAndLoss", "bs": "kaya_qbo_BalanceSheet", "ap": "kaya_qbo_apAging",
        "inv": "kaya_invoices",
        "service": "kaya-reports", "scheduler": "quickbooks-kaya-reports", "at": "04:00 UTC",
        "inv_service": "kaya-invoices", "inv_scheduler": "quickbooks-kaya", "inv_at": "04:30 UTC",
        "revenue_note": "Kaya's revenue is marketplace settlements (SalesReceipts, mostly Amazon, eBay and TikTok). "
                        "The P&L total includes them, but the channel split is not in BigQuery.",
    },
    "odf": {
        "key": "odf",
        "name": "On Demand Fulfillment",
        "title": "ON DEMAND FULFILLMENT MTD SCORECARD",
        "ds": "parasoldatalake.odf_quickbooks_prod",
        "base": "parasoldatalake.odf_quickbooks_prod",
        "pnl": "odf_qbo_ProfitAndLoss", "bs": "odf_qbo_BalanceSheet", "ap": "odf_qbo_apAging",
        "service": "odf-reports", "scheduler": "quickbooks-odf-reports", "at": "03:00 UTC",
        "revenue_note": "ODF's revenue arrives as bank Deposits. The P&L total includes them, but no invoice "
                        "or deposit detail is in BigQuery.",
    },
}

# One query per scorecard component. The page shows each query under its card
# and gather() runs the very same text, so a card and its query cannot disagree.
REVENUE_SQL = """\
SELECT
  total_income_mtd                        AS income_mtd,
  total_income                            AS income_ytd,
  gross_profit                            AS gross_profit_ytd,
  SAFE_DIVIDE(gross_profit, total_income) AS gross_margin_ytd
FROM @PNL@
QUALIFY ROW_NUMBER() OVER (ORDER BY report_date DESC) = 1"""

PROFIT_SQL = """\
SELECT
  net_operating_income                                  AS noi_ytd,
  net_operating_income_mtd                              AS noi_mtd,
  SAFE_DIVIDE(net_operating_income, total_income)       AS noi_margin_ytd,
  SAFE_DIVIDE(gross_profit_mtd, total_income_mtd)       AS gross_margin_mtd
FROM @PNL@
QUALIFY ROW_NUMBER() OVER (ORDER BY report_date DESC) = 1"""

CASH_SQL = """\
SELECT
  total_bank_accounts                                           AS bank,
  total_accounts_payable                                        AS ap,
  total_accounts_receivable                                     AS ar,
  total_credit_cards                                            AS credit_cards,
  total_bank_accounts - total_accounts_payable - total_credit_cards AS cash_after_payables,
  SAFE_DIVIDE(total_bank_accounts, total_accounts_payable)      AS cash_to_ap
FROM @BS@
QUALIFY ROW_NUMBER() OVER (ORDER BY as_of_date DESC) = 1"""

VENDOR_SQL = """\
SELECT
  entity_name AS vendor,
  total       AS balance,
  SAFE_DIVIDE(total, SUM(total) OVER ()) AS share
FROM @AP@
WHERE report_date = (SELECT MAX(report_date) FROM @AP@)
  AND NOT is_grand_total
ORDER BY balance DESC"""

WEEKLY_SQL = """\
SELECT report_date, total_income AS income_ytd
FROM @PNL@
QUALIFY MOD(ROW_NUMBER() OVER (ORDER BY report_date DESC) - 1, 7) = 0
ORDER BY report_date DESC
LIMIT 6"""

FRESH_SQL = """\
SELECT
  MAX(run_at)               AS last_run,
  COUNT(*)                  AS runs,
  COUNTIF(status = 'SUCCESS') AS ok
FROM @AUD@
WHERE run_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)"""

INVOICE_SQL = """\
SELECT
  COUNT(*)           AS invoices,
  SUM(total_amount)  AS billed,
  SUM(balance)       AS open_balance,
  MAX(txn_date)      AS last_invoice
FROM @INV@"""

INVOICE_CUSTOMER_SQL = """\
SELECT
  customer_name,
  SUM(total_amount) AS billed,
  SAFE_DIVIDE(SUM(total_amount), SUM(SUM(total_amount)) OVER ()) AS share
FROM @INV@
GROUP BY customer_name
ORDER BY billed DESC
LIMIT 3"""

# Snapshot dates and depth of history, for the build sheets' "as of" and "history" lines.
HISTORY_SQL = """\
SELECT
  (SELECT AS STRUCT MIN(report_date) AS first, MAX(report_date) AS last, COUNT(*) AS n FROM @PNL@) AS pnl,
  (SELECT AS STRUCT MIN(as_of_date) AS first, MAX(as_of_date) AS last, COUNT(*) AS n FROM @BS@) AS bs,
  (SELECT AS STRUCT MIN(report_date) AS first, MAX(report_date) AS last, COUNT(DISTINCT report_date) AS n FROM @AP@) AS ap"""

# Looker Studio data sources, one custom query each, named <client>_<source> in Looker.
# A card's build sheet names the source it reads and the charts to put on it.
LOOKER_SNAPSHOT_SQL = """\
WITH p AS (
  SELECT * FROM @PNL@
  QUALIFY ROW_NUMBER() OVER (ORDER BY report_date DESC) = 1
), b AS (
  SELECT * FROM @BS@
  QUALIFY ROW_NUMBER() OVER (ORDER BY as_of_date DESC) = 1
)
SELECT
  p.report_date,
  p.total_income                 AS income_ytd,
  p.gross_profit                 AS gross_profit_ytd,
  p.net_operating_income         AS noi_ytd,
  p.total_income_mtd             AS income_mtd,
  p.gross_profit_mtd,
  p.net_operating_income_mtd     AS noi_mtd,
  SAFE_DIVIDE(p.gross_profit, p.total_income)                     AS gross_margin_ytd,
  SAFE_DIVIDE(p.net_operating_income, p.total_income)             AS noi_margin_ytd,
  SAFE_DIVIDE(p.gross_profit_mtd, p.total_income_mtd)             AS gross_margin_mtd,
  SAFE_DIVIDE(p.net_operating_income_mtd, p.total_income_mtd)     AS noi_margin_mtd,
  b.total_bank_accounts          AS bank,
  b.total_accounts_receivable    AS ar,
  b.total_accounts_payable       AS ap,
  b.total_credit_cards           AS credit_cards,
  b.total_bank_accounts - b.total_accounts_payable - b.total_credit_cards AS cash_after_payables,
  SAFE_DIVIDE(b.total_bank_accounts, b.total_accounts_payable)    AS cash_to_ap
FROM p CROSS JOIN b"""

LOOKER_TREND_SQL = """\
SELECT
  p.report_date,
  p.total_income           AS income_ytd,
  p.gross_profit           AS gross_profit_ytd,
  p.net_operating_income   AS noi_ytd,
  p.total_income_mtd       AS income_mtd,
  b.total_bank_accounts    AS bank,
  b.total_accounts_payable AS ap
FROM @PNL@ AS p
LEFT JOIN @BS@ AS b ON b.as_of_date = p.report_date
ORDER BY p.report_date"""

LOOKER_RUNS_SQL = """\
SELECT run_at, status, token_rotated, error_message
FROM @AUD@
ORDER BY run_at DESC"""

LOOKER_INVOICES_SQL = """\
SELECT txn_date, customer_name, total_amount, balance
FROM @INV@"""


def sql_for(template: str, c: dict) -> str:
    refs = {"@PNL@": c["pnl"], "@BS@": c["bs"], "@AP@": c["ap"], "@AUD@": "reports_runs_audit"}
    if "inv" in c:
        refs["@INV@"] = c["inv"]
    for token, table in refs.items():
        template = template.replace(token, f"`{c['ds']}.{table}`")
    return template


# ---------------------------------------------------------------- data

def rows(client: bigquery.Client, template: str, c: dict) -> list[dict]:
    return [dict(r.items()) for r in client.query(sql_for(template, c)).result()]


def gather(client: bigquery.Client) -> dict:
    out = {}
    for key, c in CLIENTS.items():
        snap = {}
        for t in (REVENUE_SQL, PROFIT_SQL, CASH_SQL):
            snap.update(rows(client, t, c)[0])
        out[key] = {"snap": snap, "vendors": rows(client, VENDOR_SQL, c),
                    "weekly": rows(client, WEEKLY_SQL, c)[::-1], "fresh": rows(client, FRESH_SQL, c)[0]}
        out[key]["history"] = rows(client, HISTORY_SQL, c)[0]
        if "inv" in c:
            out[key]["invoices"] = rows(client, INVOICE_SQL, c)[0]
            out[key]["customers"] = rows(client, INVOICE_CUSTOMER_SQL, c)
    return out


# ---------------------------------------------------------------- formatting

def money(x: float, short: bool = False) -> str:
    if x is None:
        return "n/a"
    sign = "−" if x < 0 else ""
    a = abs(x)
    if short:
        if a >= 1e6:
            return f"{sign}${a / 1e6:.2f}M"
        if a >= 1e3:
            return f"{sign}${a / 1e3:.0f}K"
    return f"{sign}${a:,.0f}"


def pct(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:.{digits}f}%"


def esc(s) -> str:
    return html.escape(str(s))


def fig(value: str, key: str, big: bool = False, flag: bool = False, gap: bool = False) -> str:
    cls = "fig" + (" big" if big else "") + (" flag" if flag else "") + (" gap" if gap else "")
    return f'<div class="{cls}"><span class="v">{esc(value)}</span><span class="k">{esc(key)}</span></div>'


def card(title: str, body: str) -> str:
    return f'<div class="vb-card"><h3>{esc(title)}</h3>{body}</div>'


def hbar(label: str, share: float, shown: str) -> str:
    return (f'<div class="stage"><b>{esc(label)}</b><div class="hbar"><i style="width:{max(share, 0.02) * 100:.1f}%"></i>'
            f'<span>{esc(shown)}</span></div></div>')


def bars(points: list[tuple[str, float]], fmt) -> str:
    top = max(v for _, v in points) or 1
    cells = "".join(f'<i style="height:{max(v / top * 100, 8):.0f}%" title="{esc(l)}">{esc(fmt(v))}</i>' for l, v in points)
    labels = " · ".join(l for l, _ in points)
    return f'<div class="tat">{cells}</div><span class="k" style="text-transform:none;letter-spacing:0">{esc(labels)}</span>'


def code_block(sql: str, label: str) -> str:
    return (f'<div class="codebar"><span class="path">{esc(label)}</span>'
            f'<button class="btn" data-copy>Copy SQL</button></div><pre class="code">{esc(sql)}</pre>')


def pill(kind: str, text: str) -> str:
    return f'<span class="pill {kind}">{esc(text)}</span>'


def table(head: list[str], rows: list[list[str]], raw_cols: set[int] = frozenset()) -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in head)
    body = "".join(
        "<tr>" + "".join(f"<td>{c if i in raw_cols else esc(c)}</td>" for i, c in enumerate(r)) + "</tr>"
        for r in rows)
    return f'<div class="tbl-wrap"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


# ---------------------------------------------------------------- boards

def how(sources: list[tuple[str, str]]) -> str:
    """The 'get it from BigQuery' drawer under a card: one labelled, copyable query each."""
    blocks = "".join(code_block(sql, label) for label, sql in sources)
    return f'<details class="how"><summary>Get it from BigQuery</summary>{blocks}</details>'


def comp(title: str, body: str, sources: list[tuple[str, str]], c: dict, sheet: str = "") -> str:
    """A scorecard component: the figures, the query (or queries) behind them, and its build sheet."""
    button = (f'<button class="lk" data-open="qbo:{esc(sheet)}">Build sheet: tables, SQL, reference amounts</button>'
              if sheet else "")
    return card(title, body + button + how([(label, sql_for(sql, c)) for label, sql in sources]))


def weekly_points(weekly: list[dict]) -> list[tuple[str, float]]:
    return [(r["report_date"].strftime("%b %d").replace(" 0", " "), r["income_ytd"]) for r in weekly]


def vendor_card(vendors: list[dict], note: str, c: dict) -> str:
    total = sum(v["balance"] for v in vendors)
    bars_ = "".join(hbar(v["vendor"], v["share"], f'{money(v["balance"])} · {pct(v["share"], 0)}') for v in vendors[:5])
    return comp(f"Payables by vendor ({len(vendors)} vendors · {money(total)})",
                bars_ + f'<span class="k" style="text-transform:none;letter-spacing:0">{esc(note)}</span>',
                [("Vendors, latest payables aging (the card shows the top 5)", VENDOR_SQL)], c, f"{c['key']}-vendors")


def trend_card(weekly: list[dict], c: dict) -> str:
    return comp("Income YTD by week",
                bars(weekly_points(weekly), lambda v: money(v, True)).replace(
                    'class="tat"', 'class="tat" style="height:110px"'),
                [("Every 7th daily snapshot, newest 6", WEEKLY_SQL)], c, f"{c['key']}-trend")


def freshness_card(f: dict, c: dict) -> str:
    last = f["last_run"].astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return comp("Data freshness",
                fig(last, "Last load", big=True) +
                f'<div class="figs">{fig(f"{f["ok"]}/{f["runs"]}", "Loads OK · 30 days")}'
                f'{fig("Daily", "Snapshot cadence")}</div>',
                [("Last load and 30-day success count", FRESH_SQL)], c, f"{c['key']}-fresh")


def invoice_card(d: dict, c: dict) -> str:
    i = d["invoices"]
    last = i["last_invoice"].isoformat() if i["last_invoice"] else "none"
    cust = "".join(hbar(r["customer_name"], r["share"], f'{money(r["billed"])} · {pct(r["share"], 0)}') for r in d["customers"])
    return comp("Invoices on file",
                fig(f'{i["invoices"]:,}', "Invoices, full mirror", big=True) +
                f'<div class="figs">{fig(money(i["billed"], True), "Billed, all time")}'
                f'{fig(money(i["open_balance"]), "Open balance", flag=(i["open_balance"] or 0) > 0)}'
                f'{fig(last, "Last invoice")}</div>' + cust,
                [("Invoice totals", INVOICE_SQL), ("Top 3 customers by amount billed", INVOICE_CUSTOMER_SQL)], c, f"{c['key']}-invoices")


def revenue_card(s: dict, c: dict) -> str:
    return comp("Revenue",
                fig(money(s["income_mtd"]), "Income MTD", big=True) +
                f'<div class="figs">{fig(money(s["income_ytd"], True), "Income YTD")}'
                f'{fig(pct(s["gross_margin_ytd"]), "Gross margin YTD")}'
                f'{fig(money(s["gross_profit_ytd"], True), "Gross profit YTD")}</div>',
                [("Latest profit and loss snapshot", REVENUE_SQL)], c, f"{c['key']}-revenue")


def profit_card(s: dict, c: dict) -> str:
    cogs_gap = (s["gross_margin_mtd"] or 0) >= 0.999
    note = ('<span class="k" style="text-transform:none;letter-spacing:0">A 100% month-to-date margin means '
            'no cost of goods is booked yet this month.</span>') if cogs_gap else ""
    return comp("Profitability",
                fig(money(s["noi_ytd"]), "Net operating income YTD", big=True) +
                f'<div class="figs">{fig(money(s["noi_mtd"]), "NOI MTD", flag=s["noi_mtd"] < 0)}'
                f'{fig(pct(s["noi_margin_ytd"]), "NOI margin YTD")}'
                f'{fig(pct(s["gross_margin_mtd"]), "Gross margin MTD", flag=cogs_gap)}</div>' + note,
                [("Latest profit and loss snapshot", PROFIT_SQL)], c, f"{c['key']}-profit")


def cash_card(s: dict, c: dict) -> str:
    ratio = s["cash_to_ap"]
    return comp("Cash & payables",
                fig(money(s["bank"]), "Bank balance", big=True) +
                f'<div class="figs">{fig(money(s["ap"]), "Payables")}'
                f'{fig(money(s["ar"]), "Receivables")}'
                f'{fig(money(s["cash_after_payables"]), "Cash after payables", flag=s["cash_after_payables"] < 0)}</div>'
                + (f'<span class="k" style="text-transform:none;letter-spacing:0">Cash covers payables {ratio:.2f}x.</span>'
                   if ratio is not None else ""),
                [("Latest balance sheet", CASH_SQL)], c, f"{c['key']}-cash")


def board(key: str, d: dict, vendor_note: str, extra: str) -> str:
    s, c = d["snap"], CLIENTS[key]
    row1 = revenue_card(s, c) + profit_card(s, c) + cash_card(s, c)
    row2 = vendor_card(d["vendors"], vendor_note, c) + trend_card(d["weekly"], c)
    row3 = extra + freshness_card(d["fresh"], c)
    cols = "" if extra else ' style="grid-template-columns:1fr"'
    return (f'<div class="vb"><div class="vb-title">{esc(c["title"])}</div>'
            f'<div class="vb-row">{row1}</div><div class="vb-row">{row2}</div><div class="vb-row"{cols}>{row3}</div></div>')


def kaya_board(d: dict) -> str:
    return board("kaya", d, "One affiliate holds most of the payables - confirm whether that is intercompany.",
                 invoice_card(d, CLIENTS["kaya"]))


def odf_board(d: dict) -> str:
    return board("odf", d, "Top two vendors are over 80% of payables; several look like affiliates - confirm before reading it as supplier risk.", "")


# ---------------------------------------------------------------- build sheets
# Each card's "Build sheet" opens in the hub's own modal (BUILDERS.qbo, registered by the
# JS below): where the figure comes from, its columns, the SQL, the reference amounts to
# check a rebuild against, and how to build the card in Looker Studio.

COLUMNS = {
    "pnl": [
        ("report_date", "DATE", "Snapshot date: the end of the year-to-date period. One row per day."),
        ("start_period", "DATE", "Start of the year-to-date period (1 January)."),
        ("end_period", "DATE", "End of the year-to-date period."),
        ("total_income", "FLOAT64", "Total Income, year to date."),
        ("gross_profit", "FLOAT64", "Gross Profit (income less cost of goods sold), year to date."),
        ("net_operating_income", "FLOAT64", "Net Operating Income (gross profit less expenses), year to date."),
        ("total_income_mtd", "FLOAT64", "Total Income, this month."),
        ("gross_profit_mtd", "FLOAT64", "Gross Profit, this month."),
        ("net_operating_income_mtd", "FLOAT64", "Net Operating Income, this month."),
        ("raw_json", "STRING", "The full QuickBooks report response, for anything not broken out."),
        ("ingested_at", "TIMESTAMP", "When the pipeline loaded the row (UTC)."),
    ],
    "bs": [
        ("report_date", "DATE", "Date the report was pulled (same as as_of_date)."),
        ("as_of_date", "DATE", "Balance sheet date. One row per day."),
        ("total_bank_accounts", "FLOAT64", "Total Bank Accounts (cash)."),
        ("total_accounts_receivable", "FLOAT64", "Total Accounts Receivable."),
        ("total_accounts_payable", "FLOAT64", "Total Accounts Payable."),
        ("total_credit_cards", "FLOAT64", "Total Credit Cards (a liability; negative means a credit balance)."),
        ("raw_json", "STRING", "The full QuickBooks report response."),
        ("ingested_at", "TIMESTAMP", "When the pipeline loaded the row (UTC)."),
    ],
    "ap": [
        ("report_date", "DATE", "Snapshot date. One row per vendor per day."),
        ("entity_id", "STRING", "QuickBooks vendor id."),
        ("entity_name", "STRING", "Vendor name, as on the A/P Aging Summary."),
        ("total", "FLOAT64", "What is owed to the vendor, all aging buckets."),
        ("is_grand_total", "BOOL", "Marks a summary row. None is written today; filter it anyway."),
        ("raw_json", "STRING", "The vendor's row as QuickBooks returned it, with the aging buckets."),
        ("ingested_at", "TIMESTAMP", "When the pipeline loaded the row (UTC)."),
    ],
    "aud": [
        ("run_id", "STRING", "Run id, shared with the report rows of the same run."),
        ("run_at", "TIMESTAMP", "Run start (UTC)."),
        ("status", "STRING", "SUCCESS, PARTIAL or FAILED."),
        ("reports_requested", "STRING", "JSON list of the reports asked for."),
        ("reports_completed", "STRING", "JSON list of the reports that loaded."),
        ("row_counts_json", "STRING", "Rows loaded per report."),
        ("token_rotated", "BOOL", "A new QuickBooks refresh token was saved."),
        ("error_message", "STRING", "Empty on SUCCESS."),
    ],
    "inv": [
        ("invoice_id", "STRING", "QuickBooks invoice id."),
        ("doc_number", "STRING", "Invoice number."),
        ("txn_date", "DATE", "Invoice date."),
        ("due_date", "DATE", "Due date."),
        ("customer_id", "STRING", "QuickBooks customer id."),
        ("customer_name", "STRING", "Customer name."),
        ("subtotal", "FLOAT", "Before tax."),
        ("tax_amount", "FLOAT", "Tax."),
        ("total_amount", "FLOAT", "Invoice total."),
        ("balance", "FLOAT", "Still unpaid."),
        ("updated_at", "TIMESTAMP", "Last change in QuickBooks."),
        ("ingested_at", "TIMESTAMP", "When the pipeline loaded the row (UTC)."),
    ],
}

# kind -> (QuickBooks report, grain, where to see the same numbers in QuickBooks)
TABLE_ROLE = {
    "pnl": ("Profit and Loss", "one row per day",
            "Reports › Profit and Loss, period <b>This Year-to-date</b> (and <b>This Month</b> for MTD), "
            "accounting method <b>Cash</b>"),
    "bs": ("Balance Sheet", "one row per day",
           "Reports › Balance Sheet, as of the snapshot date, accounting method <b>Accrual</b>"),
    "ap": ("A/P Aging Summary", "one row per vendor per day", "Reports › A/P Aging Summary, as of the snapshot date"),
    "aud": ("Run audit", "one row per run", "nothing: this is the pipeline's own log"),
    "inv": ("Invoices", "one row per invoice, full mirror rewritten each run",
            "Sales › Invoices, or Reports › Invoice List"),
}

LOOKER_SOURCES = {
    "snapshot": ("latest P&L and balance sheet, one row", LOOKER_SNAPSHOT_SQL),
    "vendors": ("latest payables by vendor", VENDOR_SQL),
    "trend": ("every daily snapshot, P&L with the same day's balance sheet", LOOKER_TREND_SQL),
    "runs": ("pipeline runs", LOOKER_RUNS_SQL),
    "invoices": ("invoice mirror", LOOKER_INVOICES_SQL),
}


def fq(c: dict, kind: str) -> tuple[str, str]:
    """(the table a card reads, the base table under it): the same for ODF, a view over a table for Kaya."""
    name = {"pnl": c["pnl"], "bs": c["bs"], "ap": c["ap"], "aud": "reports_runs_audit", "inv": c.get("inv", "")}[kind]
    return f'{c["ds"]}.{name}', f'{c["base"]}.{name}'


def kv_html(pairs: list[tuple[str, str]]) -> str:
    return '<dl class="kv">' + "".join(f"<dt>{esc(k)}</dt><dd>{v}</dd>" for k, v in pairs if v) + "</dl>"


def sheet(c: dict, d: dict, *, title: str, question: str, kinds: list[str], refs: list[tuple[str, str, str]],
          asof: str, card_sql: list[tuple[str, str]], looker: str, charts: list[str], watch: str = "",
          extra: str = "") -> dict:
    """One build sheet: tabs of HTML ("h") or SQL ("q", shown with the hub's code viewer)."""
    h = d["history"]
    kind = kinds[0]
    read_as, base = fq(c, kind)
    if kind == "inv":
        svc = (f'<code>{esc(c["inv_service"])}</code> (Cloud Run), scheduler <code>{esc(c["inv_scheduler"])}</code>, '
               f'daily {esc(c["inv_at"])}, <code>qbo_invoice_sync.py</code>')
    else:
        svc = (f'<code>{esc(c["service"])}</code> (Cloud Run), scheduler <code>{esc(c["scheduler"])}</code>, '
               f'daily {esc(c["at"])}, <code>qbo_reports.py</code>')
    history = (f'{h[kind]["n"]} daily snapshots, {h[kind]["first"]} to {h[kind]["last"]}'
               if kind in ("pnl", "bs", "ap") else "")
    via = (f'<code>{esc(read_as)}</code>, a <code>SELECT *</code> view over <code>{esc(base)}</code>'
           if read_as != base else f'<code>{esc(base)}</code> (base table, no view)')
    overview = (
        f'<p class="quote">{esc(question)}</p>'
        + (f'<div class="callout watch"><b class="l">Watch out</b>{watch}</div>' if watch else "")
        + f'<h3 style="margin:18px 0 10px">Reference amounts, as of {esc(asof)}</h3>'
        + '<p class="lede">A rebuilt card should show these numbers for the same snapshot date.</p>'
        + table(["Figure", "Value", "Column or expression"],
                [[a, b, f"<code>{esc(x)}</code>"] for a, b, x in refs], {2})
        + extra
        + '<h3 style="margin:22px 0 10px">Where it comes from</h3>'
        + kv_html([
            ("In QuickBooks", "<br>".join(f"{TABLE_ROLE[k][0]}: {TABLE_ROLE[k][2]}" for k in kinds)),
            ("Pipeline", svc),
            ("Read from", via),
            ("Also uses", "<br>".join(f'<code>{esc(fq(c, k)[0])}</code> ({TABLE_ROLE[k][1]})' for k in kinds[1:])),
            ("Grain", TABLE_ROLE[kind][1]),
            ("History", history),
            ("Company", esc(c["name"])),
        ]))
    columns = "".join(
        f'<h3 style="margin:{0 if i == 0 else 22}px 0 10px"><code>{esc(fq(c, k)[0])}</code></h3>'
        + table(["Column", "Type", "Meaning"], [[f"<code>{n}</code>", t, m] for n, t, m in COLUMNS[k]], {0})
        for i, k in enumerate(kinds))
    label, src_sql = LOOKER_SOURCES[looker]
    name = f'{c["key"]}_{looker}'
    access = (f'<code>{esc(c["ds"])}</code> and <code>{esc(c["base"])}</code> (a view reads its base table)'
              if c["ds"] != c["base"] else f'<code>{esc(c["base"])}</code>')
    steps = (
        '<ol class="steps">'
        '<li>Looker Studio › <b>Add data</b> › <b>BigQuery</b> › <b>Custom query</b>, billing project '
        '<code>parasoldatalake</code>.</li>'
        f'<li>Paste the query below and name the data source <code>{esc(name)}</code> ({esc(label)}). '
        'Every card that names this source can share it.</li>'
        f"<li>Data credentials: the owner's. That account needs read access to {access}.</li>"
        + "".join(f"<li>{x}</li>" for x in charts)
        + '<li>Data freshness: 12 hours. Snapshots land once a day.</li>'
        '<li>Check the card against the reference amounts on the Overview tab.</li>'
        '<li>Share with named viewers only: these are company financials.</li></ol>')
    return {
        "title": f'{c["name"]} · {title}',
        "sub": f'<span class="tag">{esc(c["name"])}</span><span class="pill ok">Daily</span>'
               f'<span class="tag">{esc(read_as)}</span>',
        "tabs": [
            ["Overview", [{"h": overview}]],
            ["Columns", [{"h": columns}]],
            ["BigQuery SQL", [{"q": sql_for(q, c), "p": lbl} for lbl, q in card_sql]],
            ["Looker build", [{"h": steps}, {"q": sql_for(src_sql, c), "p": f"Data source {name}"}]],
        ],
    }


def sheets(data: dict) -> dict:
    out = {}
    for key, c in CLIENTS.items():
        d = data[key]
        s, h, f = d["snap"], d["history"], d["fresh"]
        p_asof, b_asof, a_asof = str(h["pnl"]["last"]), str(h["bs"]["last"]), str(h["ap"]["last"])
        out[f"{key}-revenue"] = sheet(
            c, d, title="Revenue", question="How much did we sell this month and this year, and at what margin?",
            kinds=["pnl"], asof=p_asof, card_sql=[("Revenue card", REVENUE_SQL)], looker="snapshot",
            refs=[("Income MTD", money(s["income_mtd"]), "total_income_mtd"),
                  ("Income YTD", money(s["income_ytd"]), "total_income"),
                  ("Gross profit YTD", money(s["gross_profit_ytd"]), "gross_profit"),
                  ("Gross margin YTD", pct(s["gross_margin_ytd"]), "gross_profit / total_income")],
            charts=["Scorecard chart <code>income_mtd</code>, large (Currency).",
                    "Scorecard charts <code>income_ytd</code> and <code>gross_profit_ytd</code> (Currency), "
                    "<code>gross_margin_ytd</code> (Percent)."],
            watch=esc(c["revenue_note"]) + " The P&amp;L is on a <b>Cash</b> basis: income counts when it is received.")
        out[f"{key}-profit"] = sheet(
            c, d, title="Profitability", question="Are we making money after expenses, this month and this year?",
            kinds=["pnl"], asof=p_asof, card_sql=[("Profitability card", PROFIT_SQL)], looker="snapshot",
            refs=[("Net operating income YTD", money(s["noi_ytd"]), "net_operating_income"),
                  ("NOI MTD", money(s["noi_mtd"]), "net_operating_income_mtd"),
                  ("NOI margin YTD", pct(s["noi_margin_ytd"]), "net_operating_income / total_income"),
                  ("Gross margin MTD", pct(s["gross_margin_mtd"]), "gross_profit_mtd / total_income_mtd")],
            charts=["Scorecard chart <code>noi_ytd</code>, large (Currency).",
                    "Scorecard charts <code>noi_mtd</code> (Currency), <code>noi_margin_ytd</code> and "
                    "<code>gross_margin_mtd</code> (Percent). Colour <code>noi_mtd</code> red below 0."],
            watch="A 100% month-to-date gross margin means no cost of goods is booked yet this month, "
                  "not a real margin. The P&amp;L is on a <b>Cash</b> basis.")
        out[f"{key}-cash"] = sheet(
            c, d, title="Cash & payables", question="How much cash do we have against what we owe?",
            kinds=["bs"], asof=b_asof, card_sql=[("Cash & payables card", CASH_SQL)], looker="snapshot",
            refs=[("Bank balance", money(s["bank"]), "total_bank_accounts"),
                  ("Payables", money(s["ap"]), "total_accounts_payable"),
                  ("Receivables", money(s["ar"]), "total_accounts_receivable"),
                  ("Credit cards", ("−" if s["credit_cards"] < 0 else "") + f'${abs(s["credit_cards"]):,.2f}', "total_credit_cards"),
                  ("Cash after payables", money(s["cash_after_payables"]),
                   "total_bank_accounts - total_accounts_payable - total_credit_cards"),
                  ("Cash to payables", "n/a" if s["cash_to_ap"] is None else f'{s["cash_to_ap"]:.2f}x',
                   "total_bank_accounts / total_accounts_payable")],
            charts=["Scorecard chart <code>bank</code>, large (Currency).",
                    "Scorecard charts <code>ap</code>, <code>ar</code> and <code>cash_after_payables</code> "
                    "(Currency), <code>cash_to_ap</code> (Number, 2 decimals)."],
            watch="The balance sheet is <b>Accrual</b> and the P&amp;L is <b>Cash</b>, so don't divide one by "
                  "the other. Payables equal the A/P aging vendor total to the dollar.")
        vend = d["vendors"]
        out[f"{key}-vendors"] = sheet(
            c, d, title="Payables by vendor", question="Who do we owe, and how concentrated is it?",
            kinds=["ap", "bs"], asof=a_asof, card_sql=[("Payables by vendor card", VENDOR_SQL)], looker="vendors",
            refs=[("Vendors with a balance", f"{len(vend)}", "COUNT(*) at the latest report_date"),
                  ("Total payables", money(sum(v["balance"] for v in vend)), "SUM(total)"),
                  ("Balance sheet payables", money(s["ap"]), "total_accounts_payable, must match")],
            extra='<h3 style="margin:22px 0 10px">Every vendor</h3>' + table(
                ["Vendor", "Balance", "Share"], [[v["vendor"], money(v["balance"]), pct(v["share"])] for v in vend]),
            charts=["Bar chart, horizontal: dimension <code>vendor</code>, metric <code>balance</code>, "
                    "sorted by balance descending, 5 bars.",
                    "Optional table: <code>vendor</code>, <code>balance</code>, <code>share</code> (Percent)."],
            watch="Several of the largest vendors look like affiliates. Confirm intercompany balances before "
                  "reading this as supplier risk.")
        out[f"{key}-trend"] = sheet(
            c, d, title="Income YTD by week", question="Is year-to-date income growing at the pace we expect?",
            kinds=["pnl", "bs"], asof=p_asof, card_sql=[("Income trend card", WEEKLY_SQL)], looker="trend",
            refs=[(r["report_date"].isoformat(), money(r["income_ytd"]), "total_income") for r in d["weekly"]],
            charts=["Time series: dimension <code>report_date</code> (Date), metric <code>income_ytd</code>. "
                    "The card samples every 7th day; Looker can plot every day.",
                    "Optional second series <code>bank</code> on the right axis."],
            watch=f'Year to date resets on 1 January, so the line drops to zero then. Snapshots start '
                  f'{h["pnl"]["first"]}; nothing earlier is in BigQuery.')
        last = f["last_run"].astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        out[f"{key}-fresh"] = sheet(
            c, d, title="Data freshness", question="Did last night's load run, and is it reliable?",
            kinds=["aud"], asof=last, card_sql=[("Freshness card", FRESH_SQL)], looker="runs",
            refs=[("Last load", last, "MAX(run_at)"),
                  ("Loads OK, 30 days", f'{f["ok"]}/{f["runs"]}', "COUNTIF(status = 'SUCCESS') / COUNT(*)")],
            charts=["Scorecard chart <code>run_at</code>, aggregation Max (Date hour).",
                    "Table: <code>run_at</code>, <code>status</code>, <code>error_message</code>, 10 rows."],
            watch=f'A last load older than about 26 hours means the {esc(c["at"])} run did not land.')
        if "inv" in c:
            i = d["invoices"]
            last_inv = i["last_invoice"].isoformat() if i["last_invoice"] else "none"
            out[f"{key}-invoices"] = sheet(
                c, d, title="Invoices on file", question="What have we invoiced, and what is still open?",
                kinds=["inv"], asof=last_inv, looker="invoices",
                card_sql=[("Invoice totals", INVOICE_SQL), ("Top 3 customers", INVOICE_CUSTOMER_SQL)],
                refs=[("Invoices", f'{i["invoices"]:,}', "COUNT(*)"),
                      ("Billed, all time", money(i["billed"]), "SUM(total_amount)"),
                      ("Open balance", money(i["open_balance"]), "SUM(balance)"),
                      ("Last invoice", last_inv, "MAX(txn_date)")]
                     + [(r["customer_name"], money(r["billed"]), "SUM(total_amount) for the customer")
                        for r in d["customers"]],
                charts=["Scorecard charts: Record Count, SUM <code>total_amount</code>, SUM <code>balance</code>.",
                        "Bar chart: dimension <code>customer_name</code>, metric SUM <code>total_amount</code>, 3 bars."],
                watch="Invoices are a small side of Kaya's sales. Most revenue is marketplace SalesReceipts, "
                      "which are not in BigQuery, so don't read invoice totals as revenue.")
    return out


# ---------------------------------------------------------------- health + reference

def health_view() -> str:
    stats = [("210", "pipeline runs, last 30 days"), ("99.0%", "SUCCESS (208 of 210)"), ("0", "FAILED runs"),
             ("2", "PARTIAL runs (BigQuery 503)"), ("0", "refresh-token failures since 09-08"), ("109", "tests passing")]
    strip = "".join(f'<div class="stat"><b>{esc(b)}</b><span>{esc(s)}</span></div>' for b, s in stats)

    fleet = table(
        ["Pipeline", "Cloud Run service", "Scheduler (UTC)", "Last run", "30d OK", "Token rotated", "Secret (versions)"],
        [
            ["PCS invoices", "quickbooks-prod", "05:00", "10-20 05:00", "30/30", "0", "qbo-refresh-token (125)"],
            ["PCS reports", "pcs-reports", "01:00", "10-21 01:00", "29/30 (1 partial)", "30", "qbo-refresh-token (125)"],
            ["QSM invoices", "qsm-reports (legacy name)", "01:30", "10-21 01:30", "30/30", "30", "qsm-qbo-refresh-token (105)"],
            ["QSM reports", "qsm-financial-reports", "02:00 (Denver 20:00)", "10-21 02:00", "30/30", "0", "qsm-qbo-refresh-token (105)"],
            ["Kaya invoices", "kaya-invoices", "04:30", "10-20 04:30", "30/30", "0", "kaya-qbo-refresh-token (43)"],
            ["Kaya reports", "kaya-reports", "04:00", "10-21 04:01", "29/30 (1 partial)", "30", "kaya-qbo-refresh-token (43)"],
            ["ODF reports", "odf-reports", "03:00", "10-21 03:00", "30/30", "30", "odf-qbo-refresh-token (41)"],
        ])

    tokens = f"""<div class="panel"><h3>Refresh tokens {pill("ok", "healthy")}</h3><ul class="plain">
<li><b>No <code>invalid_grant</code> since 2026-09-08.</b> The last two failures in the audit tables are QSM on 09-07 and 09-08, the lockout that was recovered that day.</li>
<li><b>Rotation is working.</b> Each company's refresh token is replaced every night: the new version landed today in all four secrets (125, 105, 43 and 41 versions). Only the first service to run each night shows <code>token_rotated=true</code>; its sibling reports false because Intuit returns the same token within ~24 hours. That is expected, not a fault.</li>
<li><b>The stagger holds.</b> Every company's two services fire 30 minutes to 4 hours apart. On 2026-11-01 US daylight time ends and the two Denver-timed jobs move to 03:00 UTC; the gap to their sibling grows to 90 minutes, so there is still no collision.</li>
<li><b>Silence is covered.</b> A refresh token dies after about 100 idle days. <code>pipeline-monitor</code> (06:00 UTC daily) flags a stale pipeline long before that, and proved itself on 10-13 and 10-16.</li>
</ul></div>"""

    errors = f"""<div class="panel"><h3>Error logs {pill("warn", "2 transient partials")}</h3><ul class="plain">
<li><b>No FAILED run in 30 days</b> across 210 runs, and every run sent its notification.</li>
<li><b>Two PARTIAL runs, same cause.</b> Kaya reports on 10-13 (ProfitAndLoss) and PCS reports on 10-16 (BalanceSheet) each hit a Google <code>503</code> while polling a BigQuery load job (<code>qbo_reports.py:528</code>, <code>job.result()</code>). Intuit and QBO were fine.</li>
<li><b>No data was lost.</b> Every company has a snapshot row for all 41 days since 09-10 in both P&amp;L and balance sheet; the next night was a clean SUCCESS.</li>
<li><b>The monitor worked.</b> Its 06:00 alert emailed three people on both days.</li>
</ul></div>"""

    docs = f"""<div class="panel"><h3>Documentation {pill("ok", "current")}</h3><ul class="plain">
<li><b>Brought up to date on 2026-10-21.</b> <code>CLICKUP_TEAM_GUIDE.md</code> now describes all four companies, the eight services, the monitor and the healthy state (its section 9 had still said "all four pipelines are down" from 2026-09-06).</li>
<li><b>ODF is in every guide:</b> the ClickUp guide, <code>GCLOUD_CHEATSHEET.md</code> (new fleet table, 7a), <code>STUDY_GUIDE.md</code> and <code>CREDENTIAL_HANDOVER.md</code>.</li>
<li><b>Schema doc matches the data:</b> <code>TABLE_SCHEMA_QBO_REPORTS.md</code> now says snapshots are daily, that no grand-total row is written, and that Kaya and ODF hold three report tables (no AR aging).</li>
<li><b>Also current:</b> the README, atlas, incident log and a new <code>CHANGELOG.md</code>; the repo is clean on <code>main</code> and the 109 tests pass.</li>
</ul></div>"""

    return f"""<div class="ref">
<div class="block"><h2>Project health</h2>
<p class="lede">Checked {HEALTH_ASOF} against BigQuery audit tables, Cloud Logging, Secret Manager, Cloud Scheduler, Cloud Run and the repo. <b>Verdict: healthy.</b> The two PARTIAL runs are kept below as a record of the one transient failure the fleet has had since the lockout.</p>
<div class="stats" style="margin:0">{strip}</div></div>
<div class="two">{tokens}{errors}</div>
{docs}
<div class="block"><h2>Fleet</h2>{fleet}</div>
</div>"""


def reference_view() -> str:
    arch = """<div class="diagram"><pre class="mermaid">flowchart LR
  Intuit["Intuit QuickBooks Online&lt;br/&gt;4 companies, own app each"]
  SM["Secret Manager&lt;br/&gt;client id, secret, refresh token per company"]
  Sch["Cloud Scheduler&lt;br/&gt;7 jobs, staggered"]
  Inv["Invoice sync services&lt;br/&gt;PCS, QSM, Kaya"]
  Rep["Reports services&lt;br/&gt;PCS, QSM, Kaya, ODF"]
  BQ[("BigQuery parasoldatalake&lt;br/&gt;one dataset per company")]
  MD[("Marketing Dashboard&lt;br/&gt;Kaya views")]
  Mon["pipeline-monitor&lt;br/&gt;06:00 UTC"]
  Mail["SendGrid emails"]
  Board["Scorecards: this tab"]
  Sch --&gt; Inv
  Sch --&gt; Rep
  Intuit --&gt; Inv
  Intuit --&gt; Rep
  SM &lt;--&gt;|"read token, write rotated token first"| Inv
  SM &lt;--&gt;|"same"| Rep
  Inv --&gt; BQ
  Rep --&gt; BQ
  BQ --&gt; MD
  BQ --&gt; Board
  MD --&gt; Board
  BQ --&gt;|"audit tables"| Mon
  Mon --&gt; Mail
  Inv --&gt; Mail
  Rep --&gt; Mail</pre></div>"""

    facts = """<dl class="kv">
<dt>What it is</dt><dd>Nightly pipelines that copy four companies' QuickBooks Online data into BigQuery: invoices, plus profit and loss, balance sheet and aging reports.</dd>
<dt>Cloud project</dt><dd><code>parasoldatalake</code>, region <code>us-central1</code>. BigQuery datasets are multi-region <code>US</code>. Note the local gcloud default is <code>voxdatalake</code>, the Plex project: always pass <code>--project parasoldatalake</code>.</dd>
<dt>Repo</dt><dd>GitHub <code>Parasol-Group-Inc/quickbooks-to-biquery</code>, branch <code>main</code>, one commit per milestone.</dd>
<dt>Code</dt><dd>Two company-neutral modules serve every client: <code>qbo_invoice_sync.py</code> and <code>qbo_reports.py</code>, plus <code>pipeline_monitor.py</code>. A new client is configuration, never a forked module.</dd>
<dt>Email</dt><dd>SendGrid to emilio.dominguez@, jennilyn.tockstein@ and marketing@ parasolgroupinc.com. Healthy since 2026-07-16.</dd>
<dt>Service defaults</dt><dd>512Mi, 1 CPU, 540s timeout, not publicly invokable, service account <code>7050005773-compute@developer.gserviceaccount.com</code>.</dd>
</dl>"""

    clients = table(
        ["Company", "Pipelines", "Dataset", "Revenue lives in", "DAYS_BACK", "Live since"],
        [
            ["PCS - Premium Container Supply", "invoices + reports", "pcs_quickbooks_prod", "Invoice", "30 (Jennilyn)", "before 2026-07"],
            ["QSM - Quality Supplement Mfg", "invoices + reports", "qsm_quickbooks_prod", "Invoice", "30 (Jennilyn)", "before 2026-07"],
            ["Kaya Naturals", "invoices + reports", "kaya_quickbooks_prod", "SalesReceipt (65 in 2026, $2.26M)", "0, full mirror", "2026-09-08"],
            ["On Demand Fulfillment", "reports only", "odf_quickbooks_prod", "Deposit (1,010 in 2026, $12.3M)", "n/a", "2026-09-10"],
        ])

    invariants = """<ul class="plain">
<li><b>Persist the rotated refresh token before anything else.</b> Intuit invalidates the old one the moment it issues the new one; a timeout before the write is a permanent lockout. This is what caused the 2026-09-02 outage.</li>
<li><b>Never run two pipelines on one company's token from different places.</b> Each company's two services share one secret, so they must never fire in the same minute.</li>
<li><b>Schedules use <code>Etc/UTC</code> for new jobs</b> so they cannot drift at daylight-saving changes.</li>
<li><b>Survey before building for a new client:</b> <code>python scripts/qbo_entity_survey.py --company NAME --year 2026</code>. Two of four clients record no invoices.</li>
<li><b>The 30-day window and the invoice dedup are stakeholder requirements</b> from Jennilyn, not defaults.</li>
<li><b>Verify against the cloud, not the docs.</b> Every past incident involved a doc or .env that had drifted from reality.</li>
<li><b>Never put a client_secret or refresh token in a file or chat.</b> Straight to Secret Manager. Take credentials from the <code>Authorization: Basic</code> blob, never a retyped client id.</li>
</ul>"""

    runbook = """<ol class="steps">
<li>Read the error <i>body</i> first. <code>invalid_client</code> and <code>invalid_grant</code> have completely different fixes.</li>
<li><b>Redeploy first.</b> Deploying needs no valid token, and storing good tokens onto vulnerable code risks undoing the recovery.</li>
<li><code>python scripts/restore_qbo_token.py --secret NAME --realm ID --basic-auth BLOB --auth-code CODE</code> for each company. It stores the token Intuit <i>returns</i> and confirms the company name.</li>
<li>Trigger every job and check load counts and the audit row. Do not use "a new secret version appeared" as the check on restore day: Intuit returns the same token within ~24 hours.</li>
</ol>"""

    commands = """<div class="panel"><h3>Everyday commands</h3><pre class="struct">python scripts/pipeline_health.py          # fleet status, flags failures and silence
python -m pytest                           # 109 tests, no network needed
python scripts/restore_qbo_token.py ...    # lockout recovery
python scripts/qbo_entity_survey.py ...    # which QBO entity holds a client's revenue
gcloud run services describe NAME --project parasoldatalake --region us-central1</pre></div>"""

    docs = table(
        ["Need", "Document"],
        [
            ["What is deployed right now", "INCIDENT_AND_CLEANUP_2026-07-02.md, Part 1b (verify against the cloud anyway)"],
            ["Incident history and hardening", "same file, addenda at the end"],
            ["Invoice sync / reports", "QBO_INVOICE_SYNC.md / QBO_REPORTS.md"],
            ["gcloud commands, lockout playbook", "GCLOUD_CHEATSHEET.md section 7b"],
            ["Non-engineer guide, onboarding a client", "CLICKUP_TEAM_GUIDE.md"],
            ["Credentials, token mechanics", "CREDENTIAL_HANDOVER.md, TOKENS.md"],
            ["What each client's QBO holds", "CLIENT_REVENUE_PROFILES.md, KAYA_SCORECARD_FINDINGS.md"],
            ["BigQuery DDL", "TABLE_SCHEMA_INVOICE_SYNC.md, TABLE_SCHEMA_QBO_REPORTS.md"],
            ["Scorecard components and their queries", "SCORECARDS.md"],
            ["History of changes", "CHANGELOG.md (repo root)"],
        ])

    secrets = table(
        ["Company", "Client id", "Client secret", "Refresh token"],
        [
            ["PCS", "qbo-client-id", "qbo-client-secret", "qbo-refresh-token"],
            ["QSM", "qsm-qbo-client-id", "qsm-qbo-client-secret", "qsm-qbo-refresh-token"],
            ["Kaya", "kaya-qbo-client-id", "kaya-qbo-client-secret", "kaya-qbo-refresh-token"],
            ["ODF", "odf-qbo-client-id", "odf-qbo-client-secret", "odf-qbo-refresh-token"],
        ])

    return f"""<div class="ref">
<div class="block"><h2>Project reference</h2><p class="lede">Everything needed to understand and operate the QuickBooks to BigQuery project in one place.</p>{facts}</div>
<div class="block"><h2>Architecture</h2>{arch}</div>
<div class="block"><h2>Clients</h2>{clients}</div>
<div class="two"><div class="block"><h2>Rules that must hold</h2>{invariants}</div><div class="block"><h2>If tokens fail: recovery order</h2>{runbook}{commands}</div></div>
<div class="two"><div class="block"><h2>Secrets</h2>{secrets}</div><div class="block"><h2>Where to read more</h2>{docs}</div></div>
</div>"""


# ---------------------------------------------------------------- assembly

CSS = """
/* QuickBooks tab: reuses the hub's board classes; only the few additions live here */
#s-qbo .fig { cursor: default; } #s-qbo .fig:hover { border-color: var(--line); }
#s-qbo .hbar span { color: var(--ink); } #s-qbo .hbar i { opacity: .55; }
#s-qbo .stage { min-width: 0; } #s-qbo .stage b { overflow-wrap: anywhere; }
#s-qbo .tat i { min-width: 0; font-size: 10.5px; overflow: hidden; }
#s-qbo .panel ul.plain li { line-height: 1.5; }
#s-qbo .panel .btn { cursor: pointer; }
#s-qbo .qv[hidden] { display: none; }
#s-qbo details.how { margin-top: 12px; border-top: 1px solid var(--line); padding-top: 8px; }
#s-qbo details.how summary { cursor: pointer; font-size: 12px; color: var(--mut, inherit); }
#s-qbo details.how pre.code { max-height: 260px; overflow: auto; margin: 4px 0 10px; }
#s-qbo button.lk { margin-top: 12px; background: none; border: 1px solid var(--line); border-radius: 6px;
  padding: 5px 10px; font: inherit; font-size: 12px; color: inherit; cursor: pointer; }
#s-qbo button.lk:hover { border-color: currentColor; }
"""

JS = """
(() => {
  const root = document.getElementById("s-qbo"); if (!root) return;
  const show = k => {
    root.querySelectorAll(".qv").forEach(v => v.hidden = v.dataset.qv !== k);
    root.querySelectorAll("#qbo-seg button").forEach(b => b.setAttribute("aria-pressed", b.dataset.qv === k));
  };
  root.querySelector("#qbo-seg").addEventListener("click", e => { const b = e.target.closest("button"); if (b) show(b.dataset.qv); });
  root.addEventListener("click", e => {
    const b = e.target.closest("[data-copy]"); if (!b) return;
    const pre = b.closest(".codebar").nextElementSibling;
    const done = () => { const t = b.textContent; b.textContent = "Copied"; setTimeout(() => b.textContent = t, 1200); };
    try { navigator.clipboard.writeText(pre.textContent).then(done, () => {}); } catch (err) {}
  });
  show("health");
})();
// Build sheets open in the hub's modal: BUILDERS, code() and the [data-open] handler
// are declared by the hub's main script, which runs after this one.
window.addEventListener("load", () => {
  const el = document.getElementById("qbo-sheets");
  if (!el || typeof BUILDERS === "undefined") return;
  const S = JSON.parse(el.textContent);
  const part = p => p.q ? code(p.q, "sql", p.p) : p.h;
  BUILDERS.qbo = id => S[id] && { title: S[id].title, sub: S[id].sub,
    tabs: S[id].tabs.map(([label, parts]) => [label, () => parts.map(part).join("")]) };
});
"""


ATLAS = Path(__file__).resolve().parents[2] / "docs" / "hub" / "qbo_atlas.html"


def atlas_view() -> str:
    """The six-diagram QBO Pipeline Atlas. It is a complete page with its own styles, so it goes in an
    iframe (srcdoc): its CSS cannot leak into the hub and the hub's cannot break it."""
    page = ATLAS.read_text(encoding="utf-8")
    return ('<div class="ref"><div class="block">'
            '<p class="lede">The whole QuickBooks system in six diagrams: fleet topology, credential boundaries, '
            'the token-rotation window, the 24-hour reuse timeline, truncate against MERGE, and Kaya\'s views. '
            'Source: <code>docs/hub/qbo_atlas.html</code>.</p>'
            f'<iframe title="QBO Pipeline Atlas" sandbox="allow-same-origin" srcdoc="{html.escape(page, quote=True)}" '
            'style="width:100%;height:900px;border:1px solid var(--line);border-radius:8px;background:#fff" '
            'onload="try{this.style.height=(this.contentDocument.documentElement.scrollHeight+24)+\'px\'}catch(e){}"></iframe>'
            '</div></div>')


def render_tab(data: dict) -> str:
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    kaya_lede = (f'Scorecard for {CLIENTS["kaya"]["name"]}, read through the Marketing Dashboard views. Figures are live from BigQuery as of {built}. '
                 'Every card has a <b>Build sheet</b> (tables, columns, SQL, reference amounts, Looker steps) and a <b>Get it from BigQuery</b> drawer.')
    odf_lede = (f'Scorecard for {CLIENTS["odf"]["name"]}. Reports only: ODF has no invoices. Figures are live from BigQuery as of {built}. '
                'Every card has a <b>Build sheet</b> (tables, columns, SQL, reference amounts, Looker steps) and a <b>Get it from BigQuery</b> drawer.')
    legend = '<div class="legend"><span class="lf">Read with care</span></div>'
    views = [
        ("health", "Health", health_view()),
        ("kaya", "Kaya scorecard", f'<div class="ref"><div class="block"><p class="lede">{kaya_lede}</p>{legend}{kaya_board(data["kaya"])}</div></div>'),
        ("odf", "ODF scorecard", f'<div class="ref"><div class="block"><p class="lede">{odf_lede}</p>{legend}{odf_board(data["odf"])}</div></div>'),
        ("ref", "Project reference", reference_view()),
        ("atlas", "Pipeline atlas", atlas_view()),
    ]
    seg = "".join(f'<button data-qv="{k}" aria-pressed="false">{esc(l)}</button>' for k, l, _ in views)
    body = "".join(f'<div class="qv" data-qv="{k}" hidden>{h}</div>' for k, _, h in views)
    sheets_json = json.dumps(sheets(data), default=str).replace("</", "<\\/")
    return (f'{START}<style>{CSS}</style>'
            f'<section id="s-qbo" data-tab="qbo" hidden>'
            f'<div class="vb-tools" style="margin-bottom:16px"><div class="seg" id="qbo-seg">{seg}</div></div>'
            f'{body}</section>'
            f'<script type="application/json" id="qbo-sheets">{sheets_json}</script>'
            f'<script>{JS}</script>{END}')


def inject(page: str, tab: str) -> str:
    if START in page:
        page = re.sub(re.escape(START) + ".*?" + re.escape(END) + "\n?", lambda m: "", page, flags=re.S)
        page = page.replace('["qbo", "QuickBooks", ""], ', "").replace(
            '  $("#stats").hidden = k === "qbo";\n', "")
    anchor = '  <section id="s-history"'
    for needle in (anchor, '["platform", "Schedules & probe", ""]', '  $("#q").disabled = '):
        if page.count(needle) != 1:
            sys.exit(f"hub page changed shape: expected exactly one {needle!r}, found {page.count(needle)}")
    page = page.replace(anchor, tab + "\n" + anchor)
    page = page.replace('["platform", "Schedules & probe", ""]', '["platform", "Schedules & probe", ""], ["qbo", "QuickBooks", ""]')
    page = page.replace('  $("#q").disabled = ', '  $("#stats").hidden = k === "qbo";\n  $("#q").disabled = ')
    return page


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub", required=True, help="the hub page's HTML")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    client = bigquery.Client(project=BQ_PROJECT)
    data = gather(client)
    with open(args.hub, encoding="utf-8") as fh:
        page = fh.read()
    page = inject(page, render_tab(data))
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"wrote {args.out} ({len(page):,} bytes)")


if __name__ == "__main__":
    main()
