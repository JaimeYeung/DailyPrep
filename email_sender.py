import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.environ.get("GMAIL_USER", "jamesyanglh@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

# Lines containing these strings get bolded as section headers
BOLD_TRIGGERS = [
    "━━━",
    "TODAY'S SCHEDULE",
    "MEETING CONTEXT",
    "COMPANY SNAPSHOT",
    "LAST CALL SUMMARY",
    "OPEN ITEMS YOU OWE",
    "SUGGESTED TALK TRACK",
    "OBJECTION HANDLING",
    "WATCH OUT FOR",
]


def _to_html(text: str) -> str:
    html_lines = []
    for line in text.splitlines():
        escaped = (line
                   .replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;"))
        if any(trigger in line.upper() for trigger in BOLD_TRIGGERS):
            html_lines.append(f"<strong>{escaped}</strong>")
        else:
            html_lines.append(escaped)

    body_html = "<br>\n".join(html_lines)
    return f"""<html><body>
<div style="font-family: monospace; font-size: 14px; line-height: 1.6; max-width: 680px;">
{body_html}
</div>
</body></html>"""


def send_email(subject: str, body: str, to_email: str) -> bool:
    if not GMAIL_APP_PASSWORD:
        raise ValueError("GMAIL_APP_PASSWORD environment variable is not set.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = to_email

    msg.attach(MIMEText(body, "plain"))
    msg.attach(MIMEText(_to_html(body), "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)

    return True
