import os
import re
import base64
import html
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail, Attachment, FileContent, FileName, FileType, Disposition, ContentId,
)

log = logging.getLogger(__name__)

# Known Plex/ODBC error signatures mapped to a plain-English hint, so a
# non-technical recipient can tell at a glance whether a failure is ours to
# fix or Plex's. Match keys are lowercase substrings checked against the
# lowercased error message. See docs/TROUBLESHOOTING.md for full detail on
# each of these — keep hints short and point there for the rest.
_KNOWN_ERROR_HINTS = [
    (
        ("session refused by service", "(2404)"),
        "Plex's ODBC service is refusing the session itself (not a network/driver "
        "problem on our side). Confirmed pattern: this means ODBC/OpenAccess SDK "
        "report access isn't enabled for this account on this Plex environment — "
        "normal Plex login can work fine while this still fails. Needs Plex Support "
        "to enable it; see docs/TROUBLESHOOTING.md.",
    ),
    (
        ("10300", "was not found in the provided configuration"),
        "The ServerDataSource name doesn't exist on this Plex host (often a "
        "test-only name used against production). Confirm the correct "
        "ServerDataSource with Plex Support — see docs/TROUBLESHOOTING.md.",
    ),
    (
        ("3059", "data source name not found"),
        "A DSN-based connection was attempted instead of driver-direct. For IAM "
        "token auth this means PLEX_ACCESS_TOKEN (or the Secret Manager token) is "
        "missing — see docs/TROUBLESHOOTING.md.",
    ),
    (
        ("token is expired", "token expired", "invalid access token"),
        "The Plex IAM access token needs to be replaced in Secret Manager — see "
        "docs/TROUBLESHOOTING.md.",
    ),
    (
        ("login failed",),
        "Likely a malformed Plex username — must be `username.company` format — "
        "see docs/TROUBLESHOOTING.md.",
    ),
]


def _classify_error(message: str) -> Optional[str]:
    """Return a plain-English hint for a known error signature, or None."""
    lower = message.lower()
    for keywords, hint in _KNOWN_ERROR_HINTS:
        if any(keyword in lower for keyword in keywords):
            return hint
    return None


def _load_template(template_name: str) -> str:
    template_path = Path(__file__).parent / "templates" / template_name
    return template_path.read_text(encoding="utf-8")


def _render_template(template: str, context: Dict[str, str]) -> str:
    rendered = template
    for key, value in context.items():
        # *_html values are pre-built (and already escaped) HTML fragments;
        # everything else is plain text and must be escaped.
        safe = value if key.endswith("_html") else html.escape(value)
        rendered = rendered.replace(f"{{{{{key}}}}}", safe)
    return rendered


def _list_to_html(items: List[str]) -> str:
    if not items:
        return "<span class=\"none-text\">None</span>"
    # Escape — ODBC error messages contain angle brackets (e.g.
    # "<ServerDataSource> not found") that would otherwise break the layout.
    rows = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"<ul class=\"events-list\">{rows}</ul>"


def _list_to_text(items: List[str]) -> str:
    if not items:
        return "None"
    return "\n".join(f"- {item}" for item in items)


def _errors_to_html(items: List[str]) -> str:
    if not items:
        return "<span class=\"none-text\">None</span>"
    rows = []
    for item in items:
        row = f"<li>{html.escape(item)}"
        hint = _classify_error(item)
        if hint:
            row += f"<span class=\"error-hint\">&#128161; {html.escape(hint)}</span>"
        row += "</li>"
        rows.append(row)
    return f"<ul class=\"events-list\">{''.join(rows)}</ul>"


def _errors_to_text(items: List[str]) -> str:
    if not items:
        return "None"
    lines = []
    for item in items:
        lines.append(f"- {item}")
        hint = _classify_error(item)
        if hint:
            lines.append(f"    -> {hint}")
    return "\n".join(lines)


# The Vox Nutrition wordmark, attached inline on every send as `cid:voxlogo`.
#
# Inline CID rather than the two obvious alternatives, both of which fail:
# a `data:` URI is stripped outright by Gmail, and a hosted https URL would
# mean making an object in the config bucket publicly readable. CID is carried
# inside the message itself, so it renders with no external fetch and no
# public asset.
#
# Converted from assets/cropped-Vox-Nutrition-Logo-1.webp — PNG because Outlook
# does not render WebP at all, and at 320px wide so it stays sharp on the
# retina displays that show it at the template's 160px.
_LOGO_PATH = Path(__file__).parent / "assets" / "vox-logo.png"
_LOGO_CID = "voxlogo"


def _logo_attachment() -> Optional[Attachment]:
    """The inline logo, or None if it is missing.

    Deliberately never raises: a missing image must not stop a failure report
    from reaching an inbox. The template's alt text names the company, so the
    email degrades to text rather than to a broken layout.
    """
    try:
        encoded = base64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")
    except Exception as e:  # noqa: BLE001 - see docstring
        log.warning("Inline logo %s unavailable (%s); sending without it.", _LOGO_PATH, e)
        return None

    attachment = Attachment()
    attachment.file_content = FileContent(encoded)
    attachment.file_type = FileType("image/png")
    attachment.file_name = FileName("vox-logo.png")
    attachment.disposition = Disposition("inline")
    attachment.content_id = ContentId(_LOGO_CID)
    return attachment


def _local_start(report: Dict[str, object]):
    """(date 'YYYY-MM-DD', time 'HH:MM:SS', zone label) in the report's zone.

    The subject's date comes from here too: with UTC dates, an 11 PM Mountain
    run filed itself under tomorrow's thread."""
    raw = str(report.get("start_time", ""))
    zone_name = str(report.get("time_zone") or os.environ.get("REPORT_TIME_ZONE", "America/Denver"))
    try:
        local = datetime.fromisoformat(raw).astimezone(ZoneInfo(zone_name))
        return local.strftime("%Y-%m-%d"), local.strftime("%H:%M:%S"), local.strftime("%Z")
    except Exception:
        return raw[:10], raw[11:19], "UTC"


_RUN_MODE_LABELS = {
    "probe":     "Scheduled probe",
    "full":      "Scheduled full run (daily safety net)",
    "scheduled": "Scheduled run",
    "retry":     "Retry",
}


def _why_it_ran(report: Dict[str, object]) -> str:
    """One plain sentence on what triggered this run and what the probe saw."""
    mode = str(report.get("run_mode", "scheduled"))
    probe = report.get("probe") or {}
    label = _RUN_MODE_LABELS.get(mode, mode)
    status = str(report.get("status", ""))
    if status == "failed":
        return f"{label}. The run stopped before it finished; see Errors. BigQuery may still hold the previous run's data."
    if probe.get("inconclusive"):
        return f"{label}. The change probe could not be checked ({probe['inconclusive']}), so everything was extracted to be safe."
    if not probe:
        return f"{label}. Every table was extracted." if status == "success" else f"{label}. See Errors for the tables that did not load."
    checked = probe.get("sources_checked", 0)
    changed = probe.get("changed") or []
    if report.get("status") == "no_changes":
        return (f"{label}. The probe checked {checked} table(s) in {probe.get('seconds', '?')}s and "
                f"nothing has changed in Plex since the last full run, so nothing was extracted.")
    if not probe.get("may_skip"):
        if status != "success":
            return f"{label}. Every table was attempted; see Errors for the ones that did not load."
        return f"{label}. Every table was extracted. The probe recorded today's state for the next check."
    if probe.get("first_run"):
        return f"{label}. First probe for this pipeline, so everything was extracted."
    reasons = []
    if changed:
        shown = ", ".join(changed[:6]) + (f" and {len(changed) - 6} more" if len(changed) > 6 else "")
        reasons.append(f"{len(changed)} of {checked} table(s) changed in Plex ({shown})")
    if probe.get("config_changed"):
        reasons.append("the report's configuration or SQL was updated")
    return f"{label}. Extracted because " + " and ".join(reasons or ["the probe saw a change"]) + "."


def _extractions_to_html(items: List[Dict[str, object]]) -> str:
    """Compact two-column table at the bottom of the email: table, rows."""
    if not items:
        return ""
    cells = []
    for e in items:
        rows = e.get("rows")
        value = f"{rows:,}" if isinstance(rows, int) else "failed"
        style = "" if e.get("ok", True) else ' style="color:#991b1b;font-weight:bold;"'
        cells.append(f'<tr><td class="x-name">{html.escape(str(e.get("table", "?")))}</td>'
                     f'<td class="x-rows"{style}>{value}</td></tr>')
    total = sum(e["rows"] for e in items if isinstance(e.get("rows"), int))
    ok = sum(1 for e in items if e.get("ok", True))
    return (f'<tr><td colspan="2" class="section-label">Extractions &mdash; {ok} of {len(items)} tables, '
            f'{total:,} rows</td></tr>'
            f'<tr><td colspan="2" style="padding:6px 10px 10px;"><table class="x-table" role="presentation">'
            f'{"".join(cells)}</table></td></tr>')


def _notes(events: List[str]) -> List[str]:
    """Only the events a reader needs; the per-table fetch/write lines are in
    the extraction table instead."""
    return [e for e in events if e.startswith(("WARNING", "ERROR"))]


def send_report(report: Dict[str, object]) -> bool:
    enabled = os.environ.get("SENDGRID_ENABLED", "false").lower() == "true"
    if not enabled:
        log.info("SendGrid disabled; skipping email report.")
        return False

    # Prefer direct env var; fall back to Secret Manager secret name pointer
    api_key = os.environ.get("SENDGRID_API_KEY")
    if not api_key:
        secret_name = os.environ.get("SECRET_SENDGRID_KEY", "sendgrid-api-key")
        gcp_project = os.environ.get("GCP_PROJECT", "")
        if gcp_project:
            try:
                from google.cloud import secretmanager as sm
                client = sm.SecretManagerServiceClient()
                name = f"projects/{gcp_project}/secrets/{secret_name}/versions/latest"
                api_key = client.access_secret_version(request={"name": name}).payload.data.decode("UTF-8")
            except Exception as e:
                log.warning("Could not fetch SendGrid key from Secret Manager: %s", e)
    to_emails_raw = os.environ.get("REPORT_TO_EMAILS", "")
    from_email = os.environ.get("REPORT_FROM_EMAIL")
    status = str(report.get("status", "unknown")).lower()
    no_changes = status == "no_changes"
    template_name = "probe_nochange.html" if no_changes else os.environ.get("REPORT_TEMPLATE", "report.html")

    if not api_key or not to_emails_raw or not from_email:
        log.warning("SendGrid config incomplete; skipping email report.")
        return False

    to_emails = [email.strip() for email in to_emails_raw.split(",") if email.strip()]
    if not to_emails:
        log.warning("No report recipients configured; skipping email report.")
        return False

    status_class = (
        "badge-success" if status == "success" else
        "badge-warning" if status == "partial" else
        "badge-neutral" if no_changes else
        "badge-error"
    )
    status_label = "NO CHANGES" if no_changes else status.upper()

    events = [str(item) for item in report.get("events", [])]
    errors = [str(item) for item in report.get("errors", [])]

    run_date, run_time, zone_label = _local_start(report)
    extractions = [e for e in (report.get("extractions") or []) if isinstance(e, dict)]
    probe = report.get("probe") or {}
    notes = _notes(events)

    gcp_project    = str(report.get("gcp_project", os.environ.get("GCP_PROJECT", "")))
    bq_dataset     = str(report.get("bq_dataset",  os.environ.get("BQ_DATASET",  "")))
    bq_table       = str(report.get("bq_table",    os.environ.get("BQ_TABLE",    "")))
    plex_view      = str(report.get("plex_view",   os.environ.get("PLEX_VIEW",   "")))
    plex_filter    = str(report.get("plex_filter", os.environ.get("PLEX_FILTER", ""))) or "none"
    plex_host      = str(report.get("plex_host",   os.environ.get("PLEX_HOST",   "")))
    execution_name = str(report.get("execution_name", os.environ.get("CLOUD_RUN_EXECUTION", "local")))
    company_name   = os.environ.get("COMPANY_NAME", "Vox Nutrition")
    repo_url       = "https://github.com/Parasol-Group-Inc/plex-to-big-query"

    region = os.environ.get("CLOUD_RUN_REGION", "us-central1")
    if execution_name and execution_name != "local":
        logs_url = (
            f"https://console.cloud.google.com/run/jobs/executions/details"
            f"/{region}/{execution_name}?project={gcp_project}"
        )
        logs_url_label = execution_name
    else:
        logs_url = (
            f"https://console.cloud.google.com/run/jobs/details"
            f"/{region}/plex-etl?project={gcp_project}"
        )
        logs_url_label = "View in Cloud Console"

    # A pipeline can produce more than one named report in a single run (e.g.
    # the work_orders pipeline also produces MFG Job Schedule and Labeling |
    # Open WO: Results) — those are peer reports sharing a pipeline, not a
    # "general" report with side extras. Each one is listed by its real
    # Reports List name in the body's "REPORTS PRODUCED" section (built from
    # reports_detail further down); the subject no longer enumerates them.
    report_category = str(report.get("report_category", ""))
    reports_detail   = report.get("reports_detail") or []

    # PRODUCTION vs TEST is deliberately kept OUT of the subject — every
    # report in a category gets exactly one subject shape regardless of
    # environment, so prod and test threads don't fork into separate-looking
    # emails. The distinction still needs to be obvious to the reader, so it
    # shows up as a badge/line in the body instead (see environment_badge_html
    # below). Derived from bq_dataset (PlexProd/PlexTest), not report_name,
    # since every real pipeline's category+display_name already made
    # report_name's "_test" suffix irrelevant to the subject.
    environment = "TEST" if "test" in bq_dataset.lower() else ("PRODUCTION" if bq_dataset else "")

    # Subject is category + pipeline: "[Plex ETL] - Sales: Orders — 2026-09-04".
    #
    # CHANGED 2026-09-04. It used to list every display_name the run produced,
    # which was fine when a pipeline made 2-3 reports and became unusable once
    # the Vox scorecard work pushed sales_orders to 22 views — the real subject
    # line ran to roughly 90 words and wrapped over four lines in Gmail,
    # burying the one word that actually identifies the email. The full report
    # list still ships in the body under "REPORTS PRODUCED", which is where a
    # reader can actually scan it.
    #
    # The pipeline name is included because category alone is NOT unique:
    # "Supply Chain" is shared by six pipelines (inventory_activity,
    # part_obsolescence, part_on_hand_inventory, purchasing_open_orders,
    # purchasing_pending_requisitions, quality_supplier_returns) and "Sales" by
    # three (sales_orders, sales_quotes, sales_returns). Category-only subjects
    # made those six arrive looking identical, with the body's report list the
    # only way to tell which pipeline had actually run — and Gmail threaded
    # them together on top of that. Category+pipeline is unique across all 24
    # jobs and still fits on one line.
    #
    # A leading category word is stripped off the pipeline name so the common
    # cases don't stutter: "Quality: Quality Nonconformance" reads as
    # "Quality: Nonconformance", "Sales: Sales Orders" as "Sales: Orders".
    # Only an exact leading word match is removed, so "Supply Chain:
    # Purchasing Open Orders" is left alone.
    #
    # run_date is kept: without it every day's run for a pipeline collapses
    # into a single ever-growing Gmail thread, which makes finding a specific
    # day's email materially harder. Drop it here if that's actually wanted.
    #
    # Deliberately NO status (SUCCESS/PARTIAL/FAILED) in the subject: a
    # pipeline can produce several peer reports in one run, and only one of
    # them failing would make an aggregate status in the subject line
    # misleading ("FAILED" reads as "nothing worked" when 2 of 3 reports are
    # fine). Status is per-run truth, not per-category truth, so it belongs
    # in the body (see status badge) where it can sit next to the actual
    # events/errors that explain it — same reasoning that already moved
    # PRODUCTION/TEST out of the subject above.
    #
    # REPORT_SUBJECT env var still overrides entirely when set to a
    # non-default value.
    report_name_raw = str(report.get("report_name", ""))
    # Strip a trailing "_test" so even a report with no category set (falling
    # back to the bare report_name) doesn't leak the environment into the
    # subject the way every real pipeline above no longer does.
    report_name_for_subject = re.sub(r"_test$", "", report_name_raw, flags=re.IGNORECASE)
    report_name_display = report_name_for_subject.replace("_", " ").title() if report_name_for_subject else ""

    # Drop a leading category word from the pipeline name ("Quality Supplier
    # Returns" under category "Quality" -> "Supplier Returns"). Exact leading
    # word only, and never down to nothing — a pipeline named exactly after its
    # category keeps its full name rather than becoming "Quality: ".
    pipeline_label = report_name_display
    if report_category and pipeline_label:
        prefix = f"{report_category} "
        if pipeline_label.lower().startswith(prefix.lower()):
            trimmed = pipeline_label[len(prefix):].strip()
            if trimmed:
                pipeline_label = trimmed

    if report_category and pipeline_label:
        subject_label = f"{report_category}: {pipeline_label}"
    else:
        # No category set on the config — fall back to the pipeline name alone.
        subject_label = report_category or pipeline_label
    default_subject = (
        f"[Plex ETL] - {subject_label} — {run_date}"
        if subject_label
        else f"[Plex ETL] - {company_name} — {run_date}"
    )
    subject_override = os.environ.get("REPORT_SUBJECT", "")
    subject = (
        subject_override
        if subject_override and subject_override != "Plex to BigQuery ETL Report"
        else default_subject
    )

    env_class = "badge-env-test" if environment == "TEST" else "badge-env-prod" if environment == "PRODUCTION" else ""
    environment_badge_html = f' <span class="badge {env_class}">{html.escape(environment)}</span>' if environment else ""

    # Peer-report breakdown — only rendered when a pipeline actually produced
    # more than one named report this run (single-view/legacy reports have
    # no reports_detail, so this section disappears rather than showing
    # "None" on every email).
    reports_detail_lines = [
        f"{r.get('display_name', '?')} — {r.get('table_name', '?')}"
        for r in reports_detail if isinstance(r, dict)
    ]
    if reports_detail_lines:
        section_label = f"Reports Produced — {report_category}" if report_category else "Reports Produced This Run"
        reports_section_html = (
            f'<tr><td colspan="2" class="section-label">{html.escape(section_label)}</td></tr>'
            f'<tr><td colspan="2" style="padding: 10px;">{_list_to_html(reports_detail_lines)}</td></tr>'
        )
        reports_section_text = f"{section_label.upper()}\n{_list_to_text(reports_detail_lines)}\n\n"
    else:
        reports_section_html = ""
        reports_section_text = ""

    context = {
        "status": status_label,
        "status_class": status_class,
        "run_date": run_date,
        "run_time": run_time,
        "zone_label": zone_label,
        "why_it_ran": _why_it_ran(report),
        "run_mode_label": _RUN_MODE_LABELS.get(str(report.get("run_mode", "scheduled")), "Run"),
        "pipeline_label": subject_label or report_name_display,
        "tables_checked": str(probe.get("sources_checked", len(extractions))),
        "probe_seconds": str(probe.get("seconds", "")),
        "table_count": str(len(extractions)),
        "extractions_html": _extractions_to_html(extractions),
        "notes_html": _list_to_html(notes) if notes else '<span class="none-text">None</span>',
        "duration_seconds": str(report.get("duration_seconds", "")),
        "rows_fetched": str(report.get("rows_fetched", "0")),
        "rows_written": str(report.get("rows_written", "0")),
        "gcp_project": gcp_project,
        "bq_dataset": bq_dataset,
        "bq_table": bq_table,
        "plex_view": plex_view,
        "plex_filter": plex_filter,
        "plex_host": plex_host,
        "execution_name": execution_name,
        "company_name": company_name,
        "logs_url": logs_url,
        "logs_url_label": logs_url_label,
        "repo_url": repo_url,
        "events_html": _list_to_html(events),
        "errors_html": _errors_to_html(errors),
        "reports_section_html": reports_section_html,
        "environment_badge_html": environment_badge_html,
    }

    html_template = _load_template(template_name)
    html_content = _render_template(html_template, context)
    environment_line = f"Environment: {environment}\n" if environment else ""
    extraction_text = "".join(
        f"  {e.get('table', '?')}: {e['rows'] if isinstance(e.get('rows'), int) else 'failed'}\n"
        for e in extractions)
    text_content = (
        f"Status: {context['status']}\n"
        f"{environment_line}"
        f"Date: {context['run_date']}  Time: {context['run_time']} {zone_label}\n"
        f"Duration: {context['duration_seconds']} seconds\n\n"
        f"{context['why_it_ran']}\n\n"
        f"ERRORS\n{_errors_to_text(errors)}\n\n"
        f"NOTES\n{_list_to_text(notes)}\n\n"
        f"{reports_section_text}"
        f"SOURCE: {context['plex_host']}  ->  DESTINATION: {context['gcp_project']}.{context['bq_dataset']}\n"
        f"Rows fetched: {context['rows_fetched']}  Rows written: {context['rows_written']}\n\n"
        + (f"EXTRACTIONS\n{extraction_text}\n" if extraction_text else "")
        + f"Logs:  {context['logs_url']}\n"
        f"Repo:  {context['repo_url']}\n"
    )

    message = Mail(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
        plain_text_content=text_content,
    )

    logo = _logo_attachment()
    if logo is not None:
        message.attachment = logo

    client = SendGridAPIClient(api_key)
    response = client.send(message)
    log.info("SendGrid report sent with status %s", response.status_code)
    return True
