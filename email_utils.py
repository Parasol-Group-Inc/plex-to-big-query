import os
import logging
from pathlib import Path
from typing import Dict, List

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

log = logging.getLogger(__name__)


def _load_template(template_name: str) -> str:
    template_path = Path(__file__).parent / "templates" / template_name
    return template_path.read_text(encoding="utf-8")


def _render_template(template: str, context: Dict[str, str]) -> str:
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _list_to_html(items: List[str]) -> str:
    if not items:
        return "<span class=\"none-text\">None</span>"
    rows = "".join(f"<li>{item}</li>" for item in items)
    return f"<ul class=\"events-list\">{rows}</ul>"


def _list_to_text(items: List[str]) -> str:
    if not items:
        return "None"
    return "\n".join(f"- {item}" for item in items)


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
    subject = os.environ.get("REPORT_SUBJECT", "Plex to BigQuery ETL Report")
    template_name = os.environ.get("REPORT_TEMPLATE", "report.html")

    if not api_key or not to_emails_raw or not from_email:
        log.warning("SendGrid config incomplete; skipping email report.")
        return False

    to_emails = [email.strip() for email in to_emails_raw.split(",") if email.strip()]
    if not to_emails:
        log.warning("No report recipients configured; skipping email report.")
        return False

    status = str(report.get("status", "unknown")).lower()
    status_class = "badge-success" if status == "success" else "badge-error"

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
        "logs_url": logs_url,
        "logs_url_label": logs_url_label,
        "repo_url": repo_url,
        "events_html": _list_to_html(events),
        "errors_html": _list_to_html(errors),
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
        f"ERRORS\n{_list_to_text(errors)}\n\n"
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
