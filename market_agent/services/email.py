"""Gmail SMTP email sender."""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)

SMTP_HOST = os.getenv("MARKETAGENT_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("MARKETAGENT_SMTP_PORT", "587"))


def _smtp_user() -> str:
    return os.getenv("MARKETAGENT_SMTP_USER", "").strip()


def _smtp_password() -> str:
    return os.getenv("MARKETAGENT_SMTP_PASSWORD", "").strip()


def _default_recipient() -> str:
    return os.getenv("MARKETAGENT_SMTP_RECIPIENT", "").strip() or _smtp_user()


def is_email_configured() -> bool:
    return bool(_smtp_user() and _smtp_password())


def send_email(
    subject: str,
    html_body: str,
    *,
    recipient: str | None = None,
) -> bool:
    sender = _smtp_user()
    password = _smtp_password()
    to_addr = recipient or _default_recipient()
    if not sender or not password or not to_addr:
        log.warning("Email not configured — skipping send (subject=%s)", subject)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_addr
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender, password)
            server.sendmail(sender, [to_addr], msg.as_string())
        log.info("Email sent: %s → %s", subject, to_addr)
        return True
    except Exception:
        log.exception("Failed to send email: %s", subject)
        return False
