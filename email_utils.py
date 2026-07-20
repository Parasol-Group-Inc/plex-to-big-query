import os
import html
import logging
from pathlib import Path
from typing import Dict, List, Optional

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

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
    template_name = os.environ.get("REPORT_TEMPLATE", "report.html")

    if not api_key or not to_emails_raw or not from_email:
        log.warning("SendGrid config incomplete; skipping email report.")
        return False

    to_emails = [email.strip() for email in to_emails_raw.split(",") if email.strip()]
    if not to_emails:
        log.warning("No report recipients configured; skipping email report.")
        return False

    status = str(report.get("status", "unknown")).lower()
    status_class = (
        "badge-success" if status == "success" else
        "badge-warning" if status == "partial" else
        "badge-error"
    )

    events = [str(item) for item in report.get("events", [])]
    errors = [str(item) for item in report.get("errors", [])]

    start_time_raw = str(report.get("start_time", ""))
    run_date = start_time_raw[:10] if len(start_time_raw) >= 10 else start_time_raw
    run_time = start_time_raw[11:19] if len(start_time_raw) >= 19 else start_time_raw

    gcp_project    = str(report.get("gcp_project", os.environ.get("GCP_PROJECT", "")))
    bq_dataset     = str(report.get("bq_dataset",  os.environ.get("BQ_DATASET",  "")))
    bq_table       = str(report.get("bq_table",    os.environ.get("BQ_TABLE",    "")))
    plex_view      = str(report.get("plex_view",   os.environ.get("PLEX_VIEW",   "")))
    plex_filter    = str(report.get("plex_filter", os.environ.get("PLEX_FILTER", ""))) or "none"
    plex_host      = str(report.get("plex_host",   os.environ.get("PLEX_HOST",   "")))
    execution_name = str(report.get("execution_name", os.environ.get("CLOUD_RUN_EXECUTION", "local")))
    company_name   = os.environ.get("COMPANY_NAME", "Parasol")
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

    # Subject includes report name so each pipeline gets its own Gmail thread.
    # e.g. "[Plex ETL] Work Orders Test — SUCCESS — 2026-07-14"
    # REPORT_SUBJECT env var overrides entirely when set to a non-default value.
    report_name_raw     = str(report.get("report_name", ""))
    report_name_display = report_name_raw.replace("_", " ").title() if report_name_raw else ""
    default_subject = (
        f"[Plex ETL] {report_name_display} — {status.upper()} — {run_date}"
        if report_name_display
        else f"[Plex ETL] {status.upper()} — {company_name} — {run_date}"
    )
    subject_override = os.environ.get("REPORT_SUBJECT", "")
    subject = (
        subject_override
        if subject_override and subject_override != "Plex to BigQuery ETL Report"
        else default_subject
    )

    context = {
        "status": status.upper(),
        "status_class": status_class,
        "run_date": run_date,
        "run_time": run_time,
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
    }

    html_template = _load_template(template_name)
    html_content = _render_template(html_template, context)
    text_content = (
        f"Status: {context['status']}\n"
        f"Date: {context['run_date']}  Time: {context['run_time']} UTC\n"
        f"Duration: {context['duration_seconds']} seconds\n\n"
        f"SOURCE\n"
        f"  Host:         {context['plex_host']}\n"
        f"  View/Report:  {context['plex_view']}\n"
        f"  Filter:       {context['plex_filter']}\n"
        f"  Rows fetched: {context['rows_fetched']}\n\n"
        f"DESTINATION\n"
        f"  Project:      {context['gcp_project']}\n"
        f"  Dataset:      {context['bq_dataset']}\n"
        f"  Table:        {context['bq_table']}\n"
        f"  Rows written: {context['rows_written']}\n\n"
        f"EVENTS\n{_list_to_text(events)}\n\n"
        f"ERRORS\n{_errors_to_text(errors)}\n\n"
        f"Logs:  {context['logs_url']}\n"
        f"Repo:  {context['repo_url']}\n"
    )

    message = Mail(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
        plain_text_content=text_content,
    )

    client = SendGridAPIClient(api_key)
    response = client.send(message)
    log.info("SendGrid report sent with status %s", response.status_code)
    return True
