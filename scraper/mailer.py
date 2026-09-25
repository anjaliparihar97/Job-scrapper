"""Builds and sends the HTML job digest email."""
from __future__ import annotations

import logging
import os
import smtplib
from collections import defaultdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from scraper.models import JobPosting

logger = logging.getLogger(__name__)


def build_html(jobs: list[JobPosting]) -> str:
    by_company: dict[str, list[JobPosting]] = defaultdict(list)
    for job in jobs:
        by_company[job.company_display].append(job)

    sections = []
    for company, company_jobs in sorted(by_company.items()):
        rows = "\n".join(
            f"""
            <tr>
              <td style="padding:10px 8px;border-bottom:1px solid #eee;">
                <a href="{j.url}" style="color:#1a56db;text-decoration:none;font-weight:600;">
                  {_escape(j.title)}
                </a><br/>
                <span style="color:#666;font-size:13px;">{_escape(j.location) or '&nbsp;'}</span>
              </td>
            </tr>
            """
            for j in company_jobs
        )
        sections.append(
            f"""
            <h2 style="font-family:Arial,sans-serif;color:#111;font-size:18px;
                       margin:24px 0 8px;">{_escape(company)}
              <span style="color:#888;font-weight:normal;font-size:14px;">
                ({len(company_jobs)} new)
              </span>
            </h2>
            <table style="width:100%;border-collapse:collapse;
                          font-family:Arial,sans-serif;font-size:14px;">
              {rows}
            </table>
            """
        )

    body = "\n".join(sections) if sections else (
        "<p style='font-family:Arial,sans-serif;color:#555;'>"
        "No new job postings since the last check.</p>"
    )

    return f"""
    <html>
      <body style="background:#f7f7f8;padding:24px;">
        <div style="max-width:640px;margin:0 auto;background:#fff;
                    border-radius:8px;padding:24px;">
          <h1 style="font-family:Arial,sans-serif;font-size:20px;color:#111;">
            Job Digest - {datetime.now().strftime('%Y-%m-%d %H:%M')}
          </h1>
          <p style="font-family:Arial,sans-serif;color:#555;font-size:14px;">
            {len(jobs)} new position(s) found across Infineon, BASF,
            Statista and ZEISS (Germany).
          </p>
          {body}
          <p style="font-family:Arial,sans-serif;color:#999;font-size:12px;
                    margin-top:32px;">
            Sent automatically by your job-scraper-agent.
          </p>
        </div>
      </body>
    </html>
    """


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def send_digest(jobs: list[JobPosting]) -> bool:
    """Send the digest email. Returns True on success."""
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USERNAME"]
    smtp_pass = os.environ["SMTP_PASSWORD"]
    email_from = os.environ.get("EMAIL_FROM", smtp_user)
    email_to = os.environ["EMAIL_TO"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔔 {len(jobs)} new job(s) - Infineon/BASF/Statista/ZEISS"
    msg["From"] = email_from
    msg["To"] = email_to

    msg.attach(MIMEText(build_html(jobs), "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(email_from, [email_to], msg.as_string())
        logger.info("Digest email sent to %s (%d jobs)", email_to, len(jobs))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send email: %s", exc)
        return False
