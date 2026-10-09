# gmail_oauth.py — Gmail send via Google OAuth + Gmail API
#
# Mirrors the design of ms_email.py. Users click "Sign in with Google",
# we get an access token + refresh token through the OAuth web flow, then
# we send emails by POSTing to gmail.googleapis.com/v1/users/me/messages/send.
#
# Architecture rationale:
#   - The Gmail API send endpoint goes through Google's outbound mail
#     infrastructure. Mail leaves from the user's actual @gmail.com or
#     Workspace address with their full SPF/DKIM/DMARC and sending
#     reputation. Identical deliverability to clicking Send in Gmail itself.
#   - It runs over HTTPS port 443, so DigitalOcean's SMTP block is not
#     a problem (unlike smtp.gmail.com:587 which is blocked).
#   - No new dependencies — uses stdlib urllib for the HTTP calls and
#     stdlib email.mime to build the RFC 2822 message that Gmail expects.

import os
import json
import time
import base64
import urllib.parse
import urllib.request
import urllib.error
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

# Google app credentials (set in /opt/dripdrop/.env on the server)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "https://dripdripdrop.ai/auth/google/callback",
)

# Endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# Scopes — narrow as possible to reduce verification friction.
# - openid + email + profile let us learn the user's email + name
# - gmail.send lets us send mail on their behalf
# - gmail.readonly lets us poll their inbox for replies to campaign emails
GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def is_configured() -> bool:
    """Check if Google OAuth env vars are set."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def get_auth_url(state: str = "") -> str:
    """Generate the Google login URL. Returns the URL to redirect the user to.

    access_type=offline + prompt=consent ensures Google issues a refresh
    token. Without those params, refresh tokens are only issued on the
    very first authorization, which breaks the flow if the user re-grants
    access later.
    """
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    if state:
        params["state"] = state
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


def _post_form(url: str, data: dict, timeout: int = 30) -> dict:
    """POST form-encoded data to a Google endpoint and return the parsed JSON.
    Raises on HTTP error."""
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def exchange_code_for_token(code: str) -> dict:
    """Exchange an authorization code for access + refresh tokens.
    Returns the raw token response from Google. Caller checks for
    'access_token' to know if it succeeded."""
    try:
        return _post_form(GOOGLE_TOKEN_URL, {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"error": f"HTTP {e.code}"}
        return err
    except Exception as e:
        return {"error": "exception", "error_description": str(e)[:200]}


def refresh_access_token(refresh_token: str) -> dict:
    """Use a refresh token to get a fresh access token. Refresh tokens
    are long-lived (months/years). Returns the raw token response."""
    try:
        return _post_form(GOOGLE_TOKEN_URL, {
            "refresh_token": refresh_token,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "grant_type": "refresh_token",
        })
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"error": f"HTTP {e.code}"}
        return err
    except Exception as e:
        return {"error": "exception", "error_description": str(e)[:200]}


def get_user_profile(access_token: str) -> dict:
    """Fetch the authenticated user's email + name from Google's userinfo
    endpoint. Returns dict with 'email', 'name', 'picture'."""
    req = urllib.request.Request(
        GOOGLE_USERINFO_URL,
        method="GET",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


def _build_rfc2822_message(to: str, subject: str, html_body: str,
                            from_email: str, from_name: str = "",
                            attachments: list = None) -> str:
    """Build an RFC 2822 message and return it as a base64url-encoded string,
    which is what the Gmail API expects in the 'raw' field."""
    if attachments:
        msg = MIMEMultipart("mixed")
    else:
        msg = MIMEMultipart("alternative")
    msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    msg["To"] = to.strip()
    msg["Subject"] = subject

    # HTML body
    if "<html" not in html_body.lower():
        html_body = (
            '<html><head><meta charset="utf-8"></head>'
            '<body style="font-family:Calibri,Arial,sans-serif;font-size:11pt;color:#1E293B;">'
            f'{html_body}</body></html>'
        )

    if attachments:
        # mixed → alternative wrapper for body
        body_wrapper = MIMEMultipart("alternative")
        body_wrapper.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(body_wrapper)

        for att_path in attachments:
            try:
                p = Path(att_path)
                if not p.is_file():
                    continue
                with open(p, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{p.name}"',
                )
                msg.attach(part)
            except Exception:
                continue
    else:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    raw = msg.as_bytes()
    # Gmail API requires base64url encoding (URL-safe + no padding stripped)
    return base64.urlsafe_b64encode(raw).decode("ascii")


def send_email(access_token: str, to: str, subject: str, html_body: str,
                from_email: str = "", from_name: str = "",
                attachments: list = None) -> tuple:
    """Send an email through the Gmail API as the authenticated user.
    Returns (success: bool, error_message: str).

    Note: Gmail ignores the From: header in the raw message and always
    uses the authenticated user's address. We still set it because it
    makes the message look right in their Sent folder."""
    if not access_token:
        return False, "Not signed in with Google"
    if not to or not subject:
        return False, "Missing recipient or subject"
    if not from_email:
        # Gmail will fall back to the authenticated user's address if we
        # leave this blank, but we set it anyway for the Sent folder.
        from_email = "me"

    try:
        raw = _build_rfc2822_message(
            to=to, subject=subject, html_body=html_body,
            from_email=from_email, from_name=from_name,
            attachments=attachments,
        )
    except Exception as e:
        return False, f"Could not build message: {str(e)[:150]}"

    payload = {"raw": raw}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        GMAIL_SEND_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if 200 <= resp.status < 300:
                return True, ""
            body = resp.read().decode("utf-8", errors="replace")[:300]
            return False, f"Gmail HTTP {resp.status}: {body}"
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")[:400]
            err_json = json.loads(body)
            err = err_json.get("error", {})
            if isinstance(err, dict):
                msg = err.get("message", body)
                code = err.get("code", e.code)
                return False, f"Gmail ({code}): {msg}"
        except Exception:
            pass
        return False, f"Gmail HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"Could not reach Gmail: {e.reason}"
    except Exception as e:
        return False, f"Gmail send failed: {str(e)[:200]}"


# ─── Token storage helpers ────────────────────────────────────────────────
# Same on-disk pattern as ms_email.py: tokens live in the user's per-user
# dripdrop_config.json under the gmail_* keys. Refresh tokens are handled
# automatically by get_valid_token() — callers just call that and get back
# a fresh access token to use.

def save_tokens(config_path: Path, tokens: dict):
    """Save Gmail OAuth tokens to the user's config file."""
    cfg = {}
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    cfg["gmail_access_token"] = tokens.get("access_token", "")
    # Google only returns a refresh_token on the first consent (or when
    # prompt=consent forces a re-grant). Don't overwrite an existing
    # refresh_token with empty if Google didn't send one this time.
    if tokens.get("refresh_token"):
        cfg["gmail_refresh_token"] = tokens["refresh_token"]
    cfg["gmail_email"] = tokens.get("email", "")
    cfg["gmail_name"] = tokens.get("name", "")
    cfg["gmail_expires_at"] = tokens.get("expires_at", 0)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def load_tokens(config_path: Path) -> dict:
    """Load Gmail OAuth tokens from the user's config file. Returns empty
    dict if not configured."""
    if not config_path.exists():
        return {}
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not cfg.get("gmail_access_token") and not cfg.get("gmail_refresh_token"):
        return {}
    return {
        "access_token": cfg.get("gmail_access_token", ""),
        "refresh_token": cfg.get("gmail_refresh_token", ""),
        "email": cfg.get("gmail_email", ""),
        "name": cfg.get("gmail_name", ""),
        "expires_at": cfg.get("gmail_expires_at", 0),
    }


def get_valid_token(config_path: Path) -> str:
    """Return a valid access token for the user, refreshing it if expired.
    Returns empty string if not connected or refresh failed."""
    tokens = load_tokens(config_path)
    if not tokens:
        return ""
    now = int(time.time())
    # Refresh if the token expires within the next 60 seconds
    if tokens.get("expires_at", 0) - now > 60:
        return tokens.get("access_token", "")
    refresh = tokens.get("refresh_token", "")
    if not refresh:
        return tokens.get("access_token", "")  # last-ditch attempt
    result = refresh_access_token(refresh)
    if "access_token" not in result:
        return ""
    new_tokens = {
        "access_token": result["access_token"],
        "refresh_token": refresh,  # Google doesn't always return a new one
        "email": tokens.get("email", ""),
        "name": tokens.get("name", ""),
        "expires_at": now + int(result.get("expires_in", 3600)),
    }
    save_tokens(config_path, new_tokens)
    return result["access_token"]


def disconnect(config_path: Path) -> bool:
    """Wipe Gmail tokens from the user's config. Returns True if anything
    was removed."""
    if not config_path.exists():
        return False
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    removed = False
    for k in ["gmail_access_token", "gmail_refresh_token",
              "gmail_email", "gmail_name", "gmail_expires_at"]:
        if k in cfg:
            cfg.pop(k, None)
            removed = True
    if removed:
        config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return removed


# ── Inbox reply polling ───────────────────────────────────────────────────

GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"

def get_recent_inbox(access_token: str, since_minutes: int = 60,
                     max_results: int = 50) -> list:
    """Fetch recent inbox messages via Gmail API.
    Returns list of dicts with from_email, from_name, subject, body_preview,
    received_at, message_id."""
    if not access_token:
        return []

    import time as _time
    cutoff_epoch = int(_time.time()) - (since_minutes * 60)
    query = f"in:inbox after:{cutoff_epoch}"

    try:
        # Step 1: List message IDs
        list_url = f"{GMAIL_MESSAGES_URL}?q={urllib.parse.quote(query)}&maxResults={max_results}"
        req = urllib.request.Request(
            list_url, method="GET",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            list_data = json.loads(resp.read().decode("utf-8"))

        msg_ids = [m["id"] for m in list_data.get("messages", [])]
        if not msg_ids:
            return []

        # Step 2: Fetch metadata for each message
        messages = []
        for mid in msg_ids[:max_results]:
            try:
                detail_url = f"{GMAIL_MESSAGES_URL}/{mid}?format=metadata&metadataHeaders=From&metadataHeaders=Subject"
                req2 = urllib.request.Request(
                    detail_url, method="GET",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                with urllib.request.urlopen(req2, timeout=10) as resp2:
                    msg_data = json.loads(resp2.read().decode("utf-8"))

                headers = {h["name"].lower(): h["value"]
                           for h in msg_data.get("payload", {}).get("headers", [])}

                from_raw = headers.get("from", "")
                # Parse "Name <email>" format
                if "<" in from_raw and ">" in from_raw:
                    from_name = from_raw[:from_raw.index("<")].strip().strip('"')
                    from_email = from_raw[from_raw.index("<")+1:from_raw.index(">")].lower().strip()
                else:
                    from_name = ""
                    from_email = from_raw.lower().strip()

                messages.append({
                    "from_email": from_email,
                    "from_name": from_name,
                    "subject": headers.get("subject", ""),
                    "body_preview": msg_data.get("snippet", "")[:2000],
                    "received_at": msg_data.get("internalDate", ""),
                    "message_id": mid,
                    "is_read": "UNREAD" not in msg_data.get("labelIds", []),
                })
            except Exception:
                continue

        return messages

    except urllib.error.HTTPError as e:
        print(f"[Gmail Inbox] HTTP {e.code}")
        return []
    except Exception as e:
        print(f"[Gmail Inbox] Error: {e}")
        return []
