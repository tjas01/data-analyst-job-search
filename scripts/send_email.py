"""
Email digest sender - sends today's new jobs to vtejasc@gmail.com
Uses GitHub Actions SMTP secrets (SMTP_USER, SMTP_PASS, SMTP_HOST).
Falls back gracefully if no new jobs or email env vars not set.
"""

import json
import os
import smtplib
import sys
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

DATA_FILE = Path("data/jobs_latest.json")
TO_EMAIL = "vtejasc@gmail.com"
SUBJECT_PREFIX = "[Job Feed]"


def load_jobs() -> list[dict]:
    if not DATA_FILE.exists():
        print("No jobs file found.")
        return []
    with open(DATA_FILE) as f:
        data = json.load(f)
    return data.get("jobs", [])


def filter_recent(jobs: list[dict], hours: int = 25) -> list[dict]:
    """Filter jobs published within the last N hours. Falls back to all if dates are missing."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    recent = []
    undated = []
    for job in jobs:
        pub = job.get("published", "")
        if not pub:
            undated.append(job)
            continue
        try:
            # Parse ISO or RFC2822 dates
            if "T" in pub:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            else:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                recent.append(job)
        except Exception:
            undated.append(job)
    # If very few dated recent, include undated ones too
    result = recent + undated[:20]
    return result


def build_html_email(jobs: list[dict], fetched_at: str) -> str:
    source_colors = {
        "Indeed CA": "#2164f3",
        "Canada Job Bank": "#cc0000",
        "Remotive": "#0fa36a",
        "We Work Remotely": "#1a1a2e",
        "Jobicy": "#7c3aed",
        "Greenhouse": "#30a46c",
        "Lever": "#0057ff",
        "Ashby": "#e85d04",
    }

    rows = ""
    for j in jobs:
        color = source_colors.get(j["source"], "#555")
        salary = f"<br><small style='color:#555'>{j['salary']}</small>" if j.get("salary") else ""
        date_str = (j.get("published", "") or "")[:10]
        rows += f"""
        <tr>
          <td style="padding:10px 8px;border-bottom:1px solid #eee">
            <a href="{j['url']}" style="color:#1a6ef5;text-decoration:none;font-weight:600">{j['title']}</a><br>
            <small style="color:#888">{j['company']} &nbsp;|&nbsp; {j['location']}</small>
          </td>
          <td style="padding:10px 8px;border-bottom:1px solid #eee">
            <span style="background:{color};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;white-space:nowrap">{j['source']}</span>
          </td>
          <td style="padding:10px 8px;border-bottom:1px solid #eee;font-size:12px;color:#888;white-space:nowrap">
            {date_str}{salary}
          </td>
        </tr>"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#222">
  <h2 style="margin-bottom:4px">Daily Job Feed</h2>
  <p style="color:#888;font-size:13px;margin-top:0">{len(jobs)} jobs found &nbsp;|&nbsp; {fetched_at[:16]} UTC</p>
  <table width="100%" cellspacing="0" style="font-size:14px">
    <thead>
      <tr style="background:#f5f5f5">
        <th style="padding:8px;text-align:left;font-size:11px;text-transform:uppercase">Role / Company</th>
        <th style="padding:8px;text-align:left;font-size:11px;text-transform:uppercase">Source</th>
        <th style="padding:8px;text-align:left;font-size:11px;text-transform:uppercase">Date</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <p style="font-size:11px;color:#aaa;margin-top:24px">Automated digest from job-feed-aggregator. Unsubscribe by disabling the GitHub Actions workflow.</p>
</body>
</html>"""


def send_email(html: str, job_count: int, fetched_at: str):
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")

    if not smtp_user or not smtp_pass:
        print("No SMTP credentials found in environment. Skipping email.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{SUBJECT_PREFIX} {job_count} new jobs - {fetched_at[:10]}"
    msg["From"] = smtp_user
    msg["To"] = TO_EMAIL
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, TO_EMAIL, msg.as_string())
        print(f"Email sent to {TO_EMAIL} with {job_count} jobs.")
    except Exception as e:
        print(f"Email send failed: {e}")
        sys.exit(1)


def main():
    jobs = load_jobs()
    if not jobs:
        print("No jobs to send.")
        return

    with open(DATA_FILE) as f:
        meta = json.load(f)
    fetched_at = meta.get("fetched_at", datetime.now(timezone.utc).isoformat())

    recent = filter_recent(jobs, hours=25)
    print(f"Recent jobs to email: {len(recent)}")

    if not recent:
        print("No recent jobs in last 25h. No email sent.")
        return

    html = build_html_email(recent, fetched_at)
    send_email(html, len(recent), fetched_at)


if __name__ == "__main__":
    main()
