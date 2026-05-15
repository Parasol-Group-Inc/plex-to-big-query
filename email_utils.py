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
        return "<div>None</div>"
    rows = "".join(f"<li>{item}</li>" for item in items)
    return f"<ul>{rows}</ul>"


def _list_to_text(items: List[str]) -> str:
    if not items:
        return "None"
    return "\n".join(f"- {item}" for item in items)


def send_report(report: Dict[str, object]) -> bool:
    enabled = os.environ.get("SENDGRID_ENABLED", "false").lower() == "true"
    if not enabled:
        log.info("SendGrid disabled; skipping email report.")
        return False

    api_key = os.environ.get("SENDGRID_API_KEY")
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
    status_class = "success" if status == "success" else "failed"

    events = [str(item) for item in report.get("events", [])]
    errors = [str(item) for item in report.get("errors", [])]

    context = {
        "status": status.upper(),
        "status_class": status_class,
        "start_time": str(report.get("start_time", "")),
        "end_time": str(report.get("end_time", "")),
        "duration_seconds": str(report.get("duration_seconds", "")),
        "rows_fetched": str(report.get("rows_fetched", "0")),
        "rows_written": str(report.get("rows_written", "0")),
        "events_html": _list_to_html(events),
        "errors_html": _list_to_html(errors),
    }

    html_template = _load_template(template_name)
    html_content = _render_template(html_template, context)
    text_content = (
        f"Status: {context['status']}\n"
        f"Start: {context['start_time']}\n"
        f"End: {context['end_time']}\n"
        f"Duration: {context['duration_seconds']} seconds\n"
        f"Rows fetched: {context['rows_fetched']}\n"
        f"Rows written: {context['rows_written']}\n\n"
        "What went well:\n"
        f"{_list_to_text(events)}\n\n"
        "Errors:\n"
        f"{_list_to_text(errors)}\n"
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
