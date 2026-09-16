# email_sender.py — SMTP + SendGrid HTTP API email sending for DripDrop
# SMTP covers Gmail, Office 365, Yahoo, etc. SendGrid has both SMTP and an
# HTTP API — the HTTP API is preferred because DigitalOcean (and many other
# cloud hosts) block outbound SMTP ports by default for anti-spam reasons.

import base64
import json as _json
import os
import smtplib
import ssl
import urllib.request
import urllib.error
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

# Common SMTP server lookup by email domain
SMTP_SERVERS = {
    # Microsoft / Office 365
    "outlook.com":       ("smtp.office365.com", 587),
    "hotmail.com":       ("smtp.office365.com", 587),
    "live.com":          ("smtp.office365.com", 587),
    "office365.com":     ("smtp.office365.com", 587),
    # Gmail
    "gmail.com":         ("smtp.gmail.com", 587),
    "googlemail.com":    ("smtp.gmail.com", 587),
    # Yahoo
    "yahoo.com":         ("smtp.mail.yahoo.com", 587),
    # iCloud
    "icloud.com":        ("smtp.mail.me.com", 587),
    "me.com":            ("smtp.mail.me.com", 587),
    # Zoho
    "zoho.com":          ("smtp.zoho.com", 587),
}

# Default for custom domains (most companies use Office 365)
DEFAULT_SMTP = ("smtp.office365.com", 587)


def detect_smtp_server(email: str) -> tuple:
    """Auto-detect SMTP server from email domain.
    Returns (host, port).
    """
    domain = email.lower().strip().split("@")[-1] if "@" in email else ""
    if domain in SMTP_SERVERS:
        return SMTP_SERVERS[domain]
    # Most corporate domains use Office 365
    return DEFAULT_SMTP


def send_email(to: str, subject: str, html_body: str,
               from_email: str = "", from_name: str = "",
               password: str = "", smtp_host: str = "", smtp_port: int = 587,
               attachments: list = None, smtp_username: str = "",
               list_unsubscribe_mailto: str = "") -> tuple:
    """Send an email via SMTP.
    Returns (success: bool, error_message: str)

    smtp_username: Optional SMTP login username. If not set, from_email is used.
                   SendGrid requires the literal string "apikey" as the username.
    """
    if not to or not subject:
        return False, "Missing recipient or subject"
    if not from_email:
        return False, "No sender email configured"
    if not password:
        return False, "No email password configured"

    # Auto-detect SMTP server if not provided
    if not smtp_host:
        smtp_host, smtp_port = detect_smtp_server(from_email)

    # Login username defaults to from_email unless explicitly set (SendGrid uses "apikey")
    login_user = smtp_username or from_email

    try:
        # Build the email
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
        msg["To"] = to.strip()
        msg["Subject"] = subject
        if list_unsubscribe_mailto:
            msg["List-Unsubscribe"] = f"<{list_unsubscribe_mailto}>"
            # Enables Gmail/Yahoo's one-click unsubscribe UI per RFC 8058
            msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

        # Wrap body in HTML if needed
        body = _wrap_html(html_body)
        msg.attach(MIMEText(body, "html", "utf-8"))

        # Handle attachments
        if attachments:
            # Switch to mixed for attachments
            outer = MIMEMultipart("mixed")
            outer["From"] = msg["From"]
            outer["To"] = msg["To"]
            outer["Subject"] = msg["Subject"]
            if list_unsubscribe_mailto:
                outer["List-Unsubscribe"] = f"<{list_unsubscribe_mailto}>"
                outer["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
            outer.attach(MIMEText(body, "html", "utf-8"))

            for att_path in attachments:
                p = Path(att_path)
                if p.is_file():
                    part = MIMEBase("application", "octet-stream")
                    with open(p, "rb") as f:
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f'attachment; filename="{p.name}"')
                    outer.attach(part)
            msg = outer

        # Connect and send
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls(context=context)
            server.login(login_user, password)
            server.sendmail(from_email, to.strip(), msg.as_string())

        return True, ""

    except smtplib.SMTPAuthenticationError:
        return False, ("Authentication failed. Check your email and password. "
                      "For Gmail, use an App Password (not your regular password). "
                      "For Office 365, make sure SMTP is enabled for your account.")
    except smtplib.SMTPRecipientsRefused:
        return False, f"Recipient address rejected: {to}"
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {str(e)[:150]}"
    except Exception as e:
        return False, str(e)[:200]


def is_configured(email: str = "", password: str = "") -> bool:
    """Check if SMTP credentials are available."""
    return bool(email and password)


def test_connection(email: str, password: str,
                    smtp_host: str = "", smtp_port: int = 587,
                    smtp_username: str = "") -> tuple:
    """Test SMTP connection without sending an email.
    Returns (success: bool, message: str)
    """
    if not email or not password:
        return False, "Email and password required"

    if not smtp_host:
        smtp_host, smtp_port = detect_smtp_server(email)

    login_user = smtp_username or email
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls(context=context)
            server.login(login_user, password)
        return True, f"Connected to {smtp_host} successfully"
    except smtplib.SMTPAuthenticationError:
        return False, ("Authentication failed. Check your password. "
                      "For Gmail, you need an App Password. "
                      "For Office 365, ensure SMTP AUTH is enabled.")
    except Exception as e:
        return False, str(e)[:200]


def _wrap_html(body: str) -> str:
    """Wrap email body in a clean HTML template."""
    if "<html" in body.lower():
        return body
    return (
        '<html><head><meta charset="utf-8"></head>'
        '<body style="font-family:Calibri,Arial,sans-serif;font-size:11pt;color:#1E293B;">'
        f'{body}</body></html>'
    )


# ─── SendGrid HTTP API ────────────────────────────────────────────────────
# DigitalOcean and many other cloud hosts block outbound SMTP (port 587/465/25)
# by default for anti-spam reasons. SendGrid's HTTP API works over port 443
# which is never blocked, so this is the preferred path when the user has
# configured SendGrid.

SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"


def send_via_sendgrid_api(to: str, subject: str, html_body: str,
                           from_email: str, from_name: str = "",
                           api_key: str = "", attachments: list = None,
                           list_unsubscribe_mailto: str = "") -> tuple:
    """Send an email via the SendGrid v3 HTTP API.

    Requires a SendGrid API key that starts with 'SG.' and a verified
    sender address. Returns (success: bool, error_message: str).

    Uses only the stdlib (urllib) so no new dependencies are pulled in.
    """
    if not to or not subject:
        return False, "Missing recipient or subject"
    if not from_email:
        return False, "No sender email configured"
    if not api_key:
        return False, "No SendGrid API key configured"
    if not api_key.startswith("SG."):
        return False, "SendGrid API keys must start with 'SG.'"

    # Build the payload per SendGrid v3 spec.
    payload = {
        "personalizations": [{
            "to": [{"email": to.strip()}],
            "subject": subject,
        }],
        "from": {"email": from_email, "name": from_name} if from_name else {"email": from_email},
        "reply_to": {"email": from_email, "name": from_name} if from_name else {"email": from_email},
        "content": [{
            "type": "text/html",
            "value": _wrap_html(html_body),
        }],
    }
    if list_unsubscribe_mailto:
        payload["headers"] = {
            "List-Unsubscribe": f"<{list_unsubscribe_mailto}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }

    # Attach files (base64-encoded, per SendGrid spec)
    if attachments:
        atts = []
        for att_path in attachments:
            try:
                p = Path(att_path)
                if not p.is_file():
                    continue
                with open(p, "rb") as f:
                    raw = f.read()
                atts.append({
                    "content": base64.b64encode(raw).decode("ascii"),
                    "filename": p.name,
                    "type": "application/octet-stream",
                    "disposition": "attachment",
                })
            except Exception:
                continue
        if atts:
            payload["attachments"] = atts

    data = _json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        SENDGRID_API_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            # SendGrid returns 202 Accepted on success (not 200)
            if 200 <= resp.status < 300:
                return True, ""
            body = resp.read().decode("utf-8", errors="replace")[:200]
            return False, f"SendGrid HTTP {resp.status}: {body}"
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            body = str(e)
        # SendGrid returns structured JSON errors — pull the first message
        try:
            err_json = _json.loads(body)
            errs = err_json.get("errors", [])
            if errs and isinstance(errs, list):
                msg = errs[0].get("message", body)
                # Common errors: 'The from address does not match a verified Sender Identity'
                return False, f"SendGrid: {msg}"
        except Exception:
            pass
        return False, f"SendGrid HTTP {e.code}: {body}"
    except urllib.error.URLError as e:
        return False, f"Could not reach SendGrid: {e.reason}"
    except Exception as e:
        return False, f"SendGrid send failed: {str(e)[:200]}"


def test_sendgrid_api(api_key: str) -> tuple:
    """Verify a SendGrid API key without sending mail by hitting the
    /v3/scopes endpoint (requires read access). Returns (ok, message)."""
    if not api_key or not api_key.startswith("SG."):
        return False, "API key must start with 'SG.'"
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/scopes",
        method="GET",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if 200 <= resp.status < 300:
                return True, "SendGrid API key accepted"
            return False, f"SendGrid returned HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "SendGrid rejected the API key (401 Unauthorized)"
        return False, f"SendGrid returned HTTP {e.code}"
    except Exception as e:
        return False, f"Could not reach SendGrid: {str(e)[:150]}"


# ─── Brevo (formerly Sendinblue) HTTP API ──────────────────────────────────
# Brevo offers a permanent free tier of 300 emails/day with no credit card,
# making it the best modern replacement for SendGrid's old "free forever"
# plan now that Twilio rebranded SendGrid's free tier as a time-limited
# trial. Same HTTP-API-over-HTTPS pattern as SendGrid, so it works
# transparently behind the DigitalOcean SMTP block.
#
# Docs: https://developers.brevo.com/reference/sendtransacemail
# Free plan: https://www.brevo.com/free-plan/

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_via_brevo_api(to: str, subject: str, html_body: str,
                        from_email: str, from_name: str = "",
                        api_key: str = "", attachments: list = None,
                        list_unsubscribe_mailto: str = "") -> tuple:
    """Send an email via the Brevo v3 HTTP API.

    Requires a Brevo API key (starts with 'xkeysib-') and a verified
    sender address. Returns (success: bool, error_message: str).

    Uses only the stdlib (urllib) so no new dependencies."""
    if not to or not subject:
        return False, "Missing recipient or subject"
    if not from_email:
        return False, "No sender email configured"
    if not api_key:
        return False, "No Brevo API key configured"
    if not api_key.startswith("xkeysib-"):
        return False, "Brevo API keys must start with 'xkeysib-'"

    # Build the payload per Brevo v3 spec.
    payload = {
        "sender": {"email": from_email},
        "to": [{"email": to.strip()}],
        "subject": subject,
        "htmlContent": _wrap_html(html_body),
        "replyTo": {"email": from_email},
    }
    if from_name:
        payload["sender"]["name"] = from_name
        payload["replyTo"]["name"] = from_name

    if list_unsubscribe_mailto:
        payload["headers"] = {
            "List-Unsubscribe": f"<{list_unsubscribe_mailto}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }

    # Attachments — Brevo wants base64 + filename, max 10 MB total
    if attachments:
        atts = []
        for att_path in attachments:
            try:
                p = Path(att_path)
                if not p.is_file():
                    continue
                with open(p, "rb") as f:
                    raw = f.read()
                atts.append({
                    "content": base64.b64encode(raw).decode("ascii"),
                    "name": p.name,
                })
            except Exception:
                continue
        if atts:
            payload["attachment"] = atts

    data = _json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BREVO_API_URL,
        data=data,
        method="POST",
        headers={
            # Brevo uses a custom 'api-key' header, NOT Authorization Bearer.
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            # Brevo returns 201 Created on success
            if 200 <= resp.status < 300:
                return True, ""
            body = resp.read().decode("utf-8", errors="replace")[:200]
            return False, f"Brevo HTTP {resp.status}: {body}"
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            body = str(e)
        # Brevo returns structured JSON errors with 'message' + 'code'
        try:
            err_json = _json.loads(body)
            msg = err_json.get("message", body)
            code = err_json.get("code", "")
            if code:
                return False, f"Brevo ({code}): {msg}"
            return False, f"Brevo: {msg}"
        except Exception:
            pass
        return False, f"Brevo HTTP {e.code}: {body}"
    except urllib.error.URLError as e:
        return False, f"Could not reach Brevo: {e.reason}"
    except Exception as e:
        return False, f"Brevo send failed: {str(e)[:200]}"


def test_brevo_api(api_key: str) -> tuple:
    """Verify a Brevo API key by hitting the /v3/account endpoint.
    Returns (ok, message)."""
    if not api_key or not api_key.startswith("xkeysib-"):
        return False, "API key must start with 'xkeysib-'"
    req = urllib.request.Request(
        "https://api.brevo.com/v3/account",
        method="GET",
        headers={"api-key": api_key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if 200 <= resp.status < 300:
                return True, "Brevo API key accepted"
            return False, f"Brevo returned HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "Brevo rejected the API key (401 Unauthorized)"
        return False, f"Brevo returned HTTP {e.code}"
    except Exception as e:
        return False, f"Could not reach Brevo: {str(e)[:150]}"
