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


def batch_label(kind: str) -> str:
    """'probe-1300' -> '1 PM probe', 'full-0400' -> '4 AM full run',
    'nightly' -> 'nightly test run'. Anything else is shown as it is."""
    if kind == "nightly":
        return "nightly test run"
    if kind.startswith("recovery"):
        return "re-run after a Plex outage"
    m = re.fullmatch(r"(probe|full)-(\d{2})(\d{2})", kind or "")
    if not m:
        return kind or "batch"
    hour, minute = int(m.group(2)), int(m.group(3))
    clock = f"{hour % 12 or 12}{f':{minute:02d}' if minute else ''} {'AM' if hour < 12 else 'PM'}"
    return f"{clock} {'probe' if m.group(1) == 'probe' else 'full run'}"


def _batch_note(report: Dict[str, object]) -> str:
    """Where this email sits in its batch (see main.EMAIL_ROLE), or ''."""
    role = str(report.get("email_role") or "")
    if role not in ("first", "middle", "last") or report.get("run_mode") == "retry":
        return ""
    label = batch_label(str(report.get("batch_kind") or ""))
    if role == "first":
        return (f" This is the first job of the {label}: the other jobs report in one digest "
                f"when the batch ends, and any job that fails still emails on its own.")
    return f" This job is part of the {label}; the digest at the end of the batch lists every job."


def _why_it_ran(report: Dict[str, object]) -> str:
    """One plain sentence on what triggered this run and what the probe saw,
    plus where it sits in its batch."""
    return _why_it_ran_alone(report) + _batch_note(report)


def _why_it_ran_alone(report: Dict[str, object]) -> str:
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


def _sendgrid_config():
    """(api_key, to_emails, from_email), or None when email is off or the
    config is incomplete (each case logged)."""
    enabled = os.environ.get("SENDGRID_ENABLED", "false").lower() == "true"
    if not enabled:
        log.info("SendGrid disabled; skipping email report.")
        return None

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

    if not api_key or not to_emails_raw or not from_email:
        log.warning("SendGrid config incomplete; skipping email report.")
        return None

    to_emails = [email.strip() for email in to_emails_raw.split(",") if email.strip()]
    if not to_emails:
        log.warning("No report recipients configured; skipping email report.")
        return None
    return api_key, to_emails, from_email


def _send(config, subject: str, html_content: str, text_content: str):
    """Send one message, with the inline logo, through SendGrid."""
    api_key, to_emails, from_email = config
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


def send_report(report: Dict[str, object]) -> bool:
    config = _sendgrid_config()
    if config is None:
        return False

    status = str(report.get("status", "unknown")).lower()
    no_changes = status == "no_changes"
    template_name = "probe_nochange.html" if no_changes else os.environ.get("REPORT_TEMPLATE", "report.html")

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

    _send(config, subject, html_content, text_content)
    return True


# ── Batch digest (2026-10-21) ─────────────────────────────────────────────────
# The last job of a batch (main.EMAIL_ROLE == "last") sends one email listing
# every job's latest result in the batch, read back from job_run_log. Its
# subject is the same for every digest of a day, prod or test, so a day's
# digests thread together; the batch and the environment are in the body.

_DIGEST_STATUS = {
    "success": ("OK", "#065f46", "#d1fae5"),
    "skipped": ("No changes", "#475569", "#eef2f6"),
    "partial": ("PARTIAL", "#92400e", "#fef3c7"),
    "failed":  ("FAILED", "#991b1b", "#fee2e2"),
}


def _pipeline_name(job_name: str) -> str:
    """'plex-etl-sales-orders-test' -> 'Sales Orders'."""
    name = re.sub(r"^plex-etl-", "", job_name or "?")
    name = re.sub(r"-test$", "", name)
    return name.replace("-", " ").replace("_", " ").title()


def _local_time(value, zone: ZoneInfo) -> str:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value[11:16]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo("UTC"))
        return value.astimezone(zone).strftime("%H:%M")
    return ""


def _digest_rows(runs: List[Dict[str, object]], missing: List[str], zone: ZoneInfo):
    """(html rows, text lines) for the digest's per-job table."""
    html_rows, text_lines = [], []
    for r in runs:
        status = str(r.get("status", "?"))
        label, fg, bg = _DIGEST_STATUS.get(status, (status.upper(), "#475569", "#eef2f6"))
        name = _pipeline_name(str(r.get("job_name", "")))
        rows = r.get("rows_written")
        rows_txt = f"{rows:,}" if isinstance(rows, int) and status != "skipped" else "—"
        dur = r.get("duration_seconds")
        dur_txt = f"{dur}s" if isinstance(dur, int) else ""
        when = _local_time(r.get("started_at") or r.get("logged_at"), zone)
        mode = _RUN_MODE_LABELS.get(str(r.get("run_mode", "")), str(r.get("run_mode", "")))
        failed = r.get("tables_failed") or 0
        total = r.get("tables_total")
        note_parts = []
        if r.get("detail"):
            note_parts.append(str(r["detail"]))
        elif failed:
            note_parts.append(f"{failed} of {total} table(s) failed")
        elif r.get("tables_changed"):
            note_parts.append(f"changed: {r['tables_changed']}")
        elif status == "skipped" and total:
            note_parts.append(f"{total} table(s) checked, none changed")
        note = "; ".join(note_parts)
        if len(note) > 300:
            note = note[:297] + "..."
        html_rows.append(
            f'<tr><td class="d-name">{html.escape(name)}<span class="d-sub">{html.escape(mode)}</span></td>'
            f'<td><span class="d-status" style="color:{fg};background:{bg};">{html.escape(label)}</span></td>'
            f'<td class="d-num">{html.escape(when)}</td><td class="d-num">{html.escape(dur_txt)}</td>'
            f'<td class="d-num">{html.escape(rows_txt)}</td>'
            f'<td class="d-note">{html.escape(note)}</td></tr>')
        text_lines.append(f"- {name}: {label} at {when}, {dur_txt}, rows written {rows_txt}"
                          + (f" — {note}" if note else ""))
    for job in missing:
        name = _pipeline_name(job)
        html_rows.append(
            f'<tr><td class="d-name">{html.escape(name)}</td>'
            f'<td><span class="d-status" style="color:#92400e;background:#fef3c7;">NO RESULT YET</span></td>'
            f'<td class="d-num"></td><td class="d-num"></td><td class="d-num">—</td>'
            f'<td class="d-note">Still running, or did not start: check its own email or the logs.</td></tr>')
        text_lines.append(f"- {name}: NO RESULT YET (still running, or did not start)")
    return "".join(html_rows), text_lines


_DISPATCH_NOTES = {
    "succeeded-unrecorded": "finished, but never wrote its outcome: check its own email or job_run_log",
    "lost":                 "never finished and never reported: check the Cloud Run execution",
    "dispatch-failed":      "Cloud Run refused to start it",
    "held-outage":          "held during a Plex outage, to re-run once Plex answers",
}


def _ago(value, now: datetime) -> str:
    if not isinstance(value, datetime):
        return "none in the last week"
    hours = (now - value).total_seconds() / 3600
    return f"{hours:.0f} h ago" if hours < 48 else f"{hours / 24:.0f} days ago"


def _digest_health(health: Dict[str, object], zone: ZoneInfo):
    """(html, text lines, warning count) for main.batch_health()'s checks.
    Empty when every check passed."""
    now = datetime.now(ZoneInfo("UTC"))
    items = []   # (html, text)
    hours = health.get("stale_after_hours")
    for r in health.get("stale") or []:
        name = _pipeline_name(str(r.get("job_name", "")))
        msg = f"{name}: no clean run in over {hours} h (last {_ago(r.get('last_clean'), now)})"
        items.append((html.escape(msg), msg))
    build = str(health.get("build") or "")
    for r in health.get("drift") or []:
        name = _pipeline_name(str(r.get("job_name", "")))
        msg = (f"{name}: running image {r.get('build') or 'from before build tracking'}, "
               f"not {build} like this digest's sender: it missed a deploy")
        items.append((html.escape(msg), msg))
    for r in health.get("dispatch") or []:
        name = _pipeline_name(str(r.get("job_name", "")))
        outcome = str(r.get("outcome", ""))
        when = _local_time(r.get("finished_at"), zone)
        msg = f"{name} ({r.get('reason') or 'run'}, {when}): {_DISPATCH_NOTES.get(outcome, outcome)}"
        items.append((html.escape(msg), msg))
    for err in health.get("errors") or []:
        msg = f"Health check could not run: {err}"[:300]
        items.append((html.escape(msg), msg))
    if not items:
        return "", [], 0
    body = "".join(f"<li>{h}</li>" for h, _ in items)
    html_out = ('<h2 class="health-title">Health checks</h2>'
                f'<ul class="health">{body}</ul>')
    return html_out, ["Health checks:"] + [f"- {t}" for _, t in items], len(items)


def send_digest(digest: Dict[str, object]) -> bool:
    """Email one batch's digest: digest is main.collect_batch()'s result plus
    gcp_project, bq_dataset, time_zone and execution_name."""
    config = _sendgrid_config()
    if config is None:
        return False

    runs = [r for r in (digest.get("runs") or []) if isinstance(r, dict)]
    missing = [str(m) for m in (digest.get("missing") or [])]
    zone = ZoneInfo(str(digest.get("time_zone") or os.environ.get("REPORT_TIME_ZONE", "America/Denver")))
    batch_id = str(digest.get("batch_id", ""))
    label = batch_label(str(digest.get("batch_kind", "")))
    m = re.search(r"(\d{4}-\d{2}-\d{2})$", batch_id)
    batch_date = m.group(1) if m else datetime.now(zone).strftime("%Y-%m-%d")

    gcp_project = str(digest.get("gcp_project", os.environ.get("GCP_PROJECT", "")))
    bq_dataset = str(digest.get("bq_dataset", os.environ.get("BQ_DATASET", "")))
    environment = "TEST" if "test" in bq_dataset.lower() else ("PRODUCTION" if bq_dataset else "")
    env_class = "badge-env-test" if environment == "TEST" else "badge-env-prod"
    environment_badge_html = f' <span class="badge {env_class}">{html.escape(environment)}</span>' if environment else ""

    counts = {s: sum(1 for r in runs if r.get("status") == s) for s in _DIGEST_STATUS}
    unclean = counts["partial"] + counts["failed"]
    rows_written = sum(r["rows_written"] for r in runs
                       if isinstance(r.get("rows_written"), int) and r.get("status") != "skipped")
    if unclean:
        status_label, status_class = f"{unclean} job(s) need a look", "badge-error" if counts["failed"] else "badge-warning"
    elif missing:
        status_label, status_class = f"{len(missing)} job(s) without a result", "badge-warning"
    else:
        status_label, status_class = "All jobs OK", "badge-success"
    health_html, health_text, warnings = _digest_health(digest.get("health") or {}, zone)
    if warnings and status_class == "badge-success":
        status_label, status_class = f"All jobs OK, {warnings} health warning(s)", "badge-warning"

    summary = (f"{len(runs)} of {len(runs) + len(missing)} job(s) in the {label} reported: "
               f"{counts['success']} loaded, {counts['skipped']} had no changes in Plex, "
               f"{unclean} failed or ended partial.")
    if unclean:
        summary += " Each failed or partial job also sent its own email with the errors."
    if missing:
        summary += " Jobs listed as NO RESULT YET had not finished when this digest was sent."

    rows_html, rows_text = _digest_rows(runs, missing, zone)
    execution_name = str(digest.get("execution_name") or "")
    company_name = os.environ.get("COMPANY_NAME", "Vox Nutrition")
    context = {
        "batch_label": label[:1].upper() + label[1:],
        "batch_id": batch_id,
        "batch_date": batch_date,
        "status_label": status_label,
        "status_class": status_class,
        "environment_badge_html": environment_badge_html,
        "jobs": str(len(runs) + len(missing)),
        "ok": str(counts["success"]),
        "no_changes": str(counts["skipped"]),
        "unclean": str(unclean),
        "rows_written": f"{rows_written:,}",
        "summary": summary,
        "rows_html": rows_html,
        "health_html": health_html,
        "gcp_project": gcp_project,
        "bq_dataset": bq_dataset,
        "execution_name": execution_name or "local",
        "company_name": company_name,
    }
    html_content = _render_template(_load_template("digest.html"), context)
    text_content = (
        f"{context['batch_label']} — {batch_date}\n"
        + (f"Environment: {environment}\n" if environment else "")
        + f"{status_label}\n\n{summary}\n\n"
        + "\n".join(rows_text) + "\n\n"
        + ("\n".join(health_text) + "\n\n" if health_text else "")
        + f"Dataset: {gcp_project}.{bq_dataset}\n"
        f"Batch: {batch_id}\n"
    )
    subject = f"[Plex ETL] - Digest — {batch_date}"
    _send(config, subject, html_content, text_content)
    return True


# ── Label Design push alert (2026-10-27) ─────────────────────────────────────
# label_design_service/push.py sends this when a run could not push cleanly or
# changed Design & QA's labels. The push decides WHEN (once a day per problem);
# this only renders and sends.

def render_push_alert(alert: Dict[str, object]):
    """(subject, html, text) for one push alert. `alert` keys: kind (blocked |
    alarm | crash | failed | blank | labels), date, problems [{text, action,
    blocking}], label_changes [str], items [{order, name, outcome, url,
    detail}], in_view, new_rows, created, not_clean, board_id, board_name,
    run_id, gcp_project, bq_dataset, execution_name."""
    kind = str(alert.get("kind", ""))
    status_label, status_class = {
        "alarm":   ("Nothing pushed: too many new lines at once", "badge-error"),
        "crash":   ("The push stopped before finishing", "badge-error"),
        "blocked": ("Nothing created: a label would show wrong on Design & QA", "badge-error"),
        "failed":  ("Some items were not created", "badge-error"),
        "blank":   ("Created, but some fields will arrive blank on Design & QA", "badge-warning"),
        "labels":  ("New labels added to Design & QA", "badge-success"),
    }.get(kind, ("Label Design push needs a look", "badge-warning"))
    summary = {
        "alarm":   "More new lines than the safety limit appeared at once, which usually means the order-line "
                   "keys changed, not a busy day. Nothing was pushed; every run stops here until it is checked.",
        "crash":   "The push hit an error and stopped. Items created before the error are on the board and "
                   "logged; the rest will be tried again on the next run.",
        "blocked": "Before creating items, the push checks that every status label it writes has the same "
                   "colour as on Design & QA, because a board move matches labels by colour. That check "
                   "failed, so nothing was created this run. New orders wait; the next run tries again.",
        "failed":  "The push created what it could. The items below were not created, or were created "
                   "without some values; the next run retries the ones not created.",
        "blank":   "Items were created. A label could not be added to Design & QA, so when these items are "
                   "moved there the field below will arrive blank instead of showing the value.",
        "labels":  "The push added label(s) to Design & QA so that moved items keep their values. Nothing "
                   "needs doing unless the new label is unwanted.",
    }.get(kind, "")

    problems = [p for p in (alert.get("problems") or []) if isinstance(p, dict)]
    actions_html = ""
    if problems:
        lis = "".join(f'<li>{html.escape(str(p.get("text", "")))}'
                      f'<span class="what">{html.escape(str(p.get("action", "")))}</span></li>' for p in problems)
        actions_html = f'<p class="health-title"><b>What needs doing</b></p><ul class="actions">{lis}</ul>'
    changes = [str(c) for c in (alert.get("label_changes") or [])]
    changes_html = ""
    if changes:
        lis = "".join(f"<li>{html.escape(c)}</li>" for c in changes)
        changes_html = f'<p class="health-title" style="color:#215a7c;"><b>Label changes made</b></p><ul class="changes">{lis}</ul>'
    items = [i for i in (alert.get("items") or []) if isinstance(i, dict)]
    items_html = ""
    if items:
        rows = []
        for i in items:
            name = html.escape(str(i.get("name", "")))
            if i.get("url"):
                name = f'<a class="link" href="{html.escape(str(i["url"]))}">{name}</a>'
            rows.append(f'<tr><td class="d-name">{html.escape(str(i.get("order", "")))}</td><td>{name}</td>'
                        f'<td>{html.escape(str(i.get("outcome", "")))}</td>'
                        f'<td class="d-note">{html.escape(str(i.get("detail", ""))[:300])}</td></tr>')
        items_html = ('<p class="health-title" style="color:#215a7c;"><b>Items</b></p><table class="d-table">'
                      '<tr><th>Order</th><th>Item</th><th>Outcome</th><th>Detail</th></tr>' + "".join(rows) + "</table>")

    bq_dataset = str(alert.get("bq_dataset", ""))
    environment = "TEST" if "test" in bq_dataset.lower() else ("PRODUCTION" if bq_dataset else "")
    env_class = "badge-env-test" if environment == "TEST" else "badge-env-prod"
    board_id = str(alert.get("board_id", ""))
    context = {
        "alert_date": str(alert.get("date", "")),
        "gcp_project": str(alert.get("gcp_project", "")),
        "bq_dataset": bq_dataset,
        "board_name": str(alert.get("board_name") or board_id),
        "board_url": f"https://voxnutrition-company.monday.com/boards/{board_id}",
        "status_label": status_label,
        "status_class": status_class,
        "environment_badge_html": f' <span class="badge {env_class}">{html.escape(environment)}</span>' if environment else "",
        "in_view": str(alert.get("in_view", "—")),
        "new_rows": str(alert.get("new_rows", "—")),
        "created": str(alert.get("created", "—")),
        "not_clean": str(alert.get("not_clean", "—")),
        "summary": summary,
        "actions_html": actions_html,
        "changes_html": changes_html,
        "items_html": items_html,
        "run_id": str(alert.get("run_id", "")),
        "execution_name": str(alert.get("execution_name") or "local"),
        "company_name": os.environ.get("COMPANY_NAME", "Vox Nutrition"),
    }
    html_content = _render_template(_load_template("label_push_alert.html"), context)
    text = [f"Label Design push — {context['alert_date']}", status_label, "", summary, ""]
    for p in problems:
        text += [f"- {p.get('text', '')}", f"  What to do: {p.get('action', '')}"]
    if changes:
        text += ["", "Label changes made:"] + [f"- {c}" for c in changes]
    if items:
        text += ["", "Items:"] + [f"- {i.get('order', '')} {i.get('name', '')}: {i.get('outcome', '')} "
                                  f"{i.get('detail', '')} {i.get('url', '')}".rstrip() for i in items]
    text += ["", f"Board: {context['board_url']}", f"Run: {context['run_id']}"]
    subject = f"[Plex ETL] - Sales: Label Design push — {context['alert_date']}"
    return subject, html_content, "\n".join(text) + "\n"


def send_push_alert(alert: Dict[str, object]) -> bool:
    config = _sendgrid_config()
    if config is None:
        return False
    subject, html_content, text_content = render_push_alert(alert)
    _send(config, subject, html_content, text_content)
    return True
