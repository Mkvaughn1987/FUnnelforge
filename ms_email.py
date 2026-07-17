# ms_email.py — Microsoft Graph email sending via OAuth
# Users click "Sign in with Microsoft" → we get a token → send emails via Graph API

import os
import json
import msal
import httpx
from pathlib import Path

# Azure app credentials (set in environment)
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID", "")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET", "")
MS_TENANT_ID = os.getenv("MS_TENANT_ID", "")
MS_AUTHORITY = f"https://login.microsoftonline.com/common"
MS_SCOPES = ["Mail.Send", "Mail.Read", "User.Read"]
MS_REDIRECT_URI = os.getenv("MS_REDIRECT_URI", "https://dripdripdrop.ai/auth/microsoft/callback")
GRAPH_API = "https://graph.microsoft.com/v1.0"


def get_msal_app():
    """Create MSAL confidential client app."""
    return msal.ConfidentialClientApplication(
        MS_CLIENT_ID,
        authority=MS_AUTHORITY,
        client_credential=MS_CLIENT_SECRET,
    )


def get_auth_url(state: str = "") -> str:
    """Generate Microsoft login URL. Returns the URL to redirect user to."""
    app = get_msal_app()
    return app.get_authorization_request_url(
        scopes=MS_SCOPES,
        redirect_uri=MS_REDIRECT_URI,
        state=state,
    )


def exchange_code_for_token(code: str) -> dict:
    """Exchange authorization code for access token.
    Returns dict with access_token, refresh_token, etc.
    """
    app = get_msal_app()
    result = app.acquire_token_by_authorization_code(
        code,
        scopes=MS_SCOPES,
        redirect_uri=MS_REDIRECT_URI,
    )
    return result


def refresh_access_token(refresh_token: str) -> dict:
    """Use refresh token to get a new access token."""
    app = get_msal_app()
    result = app.acquire_token_by_refresh_token(
        refresh_token,
        scopes=MS_SCOPES,
    )
    return result


def get_user_profile(access_token: str) -> dict:
    """Get the signed-in user's profile (name, email)."""
    resp = httpx.get(
        f"{GRAPH_API}/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json()
    return {}


def send_email(access_token: str, to: str, subject: str, html_body: str,
               attachments: list = None) -> tuple:
    """Send email via Microsoft Graph API.
    Returns (success: bool, error: str).
    """
    if not access_token:
        return False, "Not signed in with Microsoft"
    if not to or not subject:
        return False, "Missing recipient or subject"

    # Wrap body in HTML if needed
    if "<html" not in html_body.lower():
        html_body = (
            '<html><head><meta charset="utf-8"></head>'
            '<body style="font-family:Calibri,Arial,sans-serif;font-size:11pt;color:#1E293B;">'
            f'{html_body}</body></html>'
        )

    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": html_body,
            },
            "toRecipients": [{"emailAddress": {"address": to.strip()}}],
        },
        "saveToSentItems": "true",
    }

    # Handle attachments
    if attachments:
        import base64
        att_list = []
        for att_path in attachments:
            p = Path(att_path)
            if p.is_file() and p.stat().st_size < 3 * 1024 * 1024:  # 3MB limit for inline
                with open(p, "rb") as f:
                    content = base64.b64encode(f.read()).decode()
                att_list.append({
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": p.name,
                    "contentBytes": content,
                })
        if att_list:
            payload["message"]["attachments"] = att_list

    try:
        resp = httpx.post(
            f"{GRAPH_API}/me/sendMail",
            json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        if resp.status_code == 202:
            return True, ""
        else:
            error = resp.text[:200] if resp.text else f"HTTP {resp.status_code}"
            return False, f"Graph API error: {error}"
    except Exception as e:
        return False, str(e)[:200]


def is_configured() -> bool:
    """Check if Microsoft OAuth is configured."""
    return bool(MS_CLIENT_ID and MS_CLIENT_SECRET)


# ── Token storage (per-user, saved to their config) ─────────────────────

def save_ms_tokens(config_path: Path, tokens: dict):
    """Save Microsoft tokens to user config."""
    try:
        cfg = {}
        if config_path.exists():
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
        cfg["ms_access_token"] = tokens.get("access_token", "")
        cfg["ms_refresh_token"] = tokens.get("refresh_token", "")
        cfg["ms_email"] = tokens.get("email", "")
        cfg["ms_name"] = tokens.get("name", "")
        config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[MS Auth] Failed to save tokens: {e}")


def load_ms_tokens(config_path: Path) -> dict:
    """Load Microsoft tokens from user config."""
    try:
        if config_path.exists():
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            return {
                "access_token": cfg.get("ms_access_token", ""),
                "refresh_token": cfg.get("ms_refresh_token", ""),
                "email": cfg.get("ms_email", ""),
                "name": cfg.get("ms_name", ""),
            }
    except Exception:
        pass
    return {}


def get_valid_token(config_path: Path) -> str:
    """Get a valid access token, refreshing if needed. Returns token string or ''."""
    tokens = load_ms_tokens(config_path)
    access = tokens.get("access_token", "")
    refresh = tokens.get("refresh_token", "")

    if not access and not refresh:
        return ""

    # Try the current access token
    if access:
        # Quick check — try to get user profile
        try:
            resp = httpx.get(
                f"{GRAPH_API}/me",
                headers={"Authorization": f"Bearer {access}"},
                timeout=10,
            )
            if resp.status_code == 200:
                return access
        except Exception:
            pass

    # Token expired — try refresh
    if refresh:
        result = refresh_access_token(refresh)
        if "access_token" in result:
            tokens["access_token"] = result["access_token"]
            if "refresh_token" in result:
                tokens["refresh_token"] = result["refresh_token"]
            save_ms_tokens(config_path, tokens)
            return result["access_token"]

    return ""


# ── Inbox reply polling ───────────────────────────────────────────────────
# Reads recent inbox messages via Microsoft Graph to detect replies from
# campaign contacts. Used by the server-side reply monitor.

def get_recent_inbox(access_token: str, since_minutes: int = 60,
                     max_results: int = 100) -> list:
    """Fetch recent messages via Microsoft Graph API.

    Uses `/me/messages` (all folders) rather than
    `/me/mailFolders/inbox/messages` because Exchange conversation-threading
    sometimes stamps replies with a parentFolderId other than Inbox even
    when Outlook displays them in the Inbox view. We filter in Python to:
      - exclude drafts, sent items, deleted items, junk
      - keep anything the user would perceive as "in their mailbox"
    """
    if not access_token:
        return []

    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")

    # Query /me/messages with a receivedDateTime filter. Add parentFolderId
    # to the $select so we can filter out Sent/Drafts/Deleted in Python.
    # We fetch the full `body` (not just bodyPreview) because non-delivery
    # reports carry the failed recipient + SMTP status deep in the body
    # (e.g. "Status code: 550 5.4.1"), well past the 255-char preview. The
    # Prefer header asks Graph for plain text so the NDR parser doesn't have
    # to strip HTML.
    params = (
        f"$filter=receivedDateTime ge {cutoff}"
        f"&$orderby=receivedDateTime desc"
        f"&$top={max_results}"
        f"&$select=from,subject,bodyPreview,body,receivedDateTime,id,isRead,parentFolderId,isDraft"
    )

    # Resolve the folder IDs to EXCLUDE (Sent, Drafts, Deleted, Junk,
    # Outbox, Archive) by hitting each well-known folder's path endpoint.
    # We deliberately do NOT $select `wellKnownName` on /me/mailFolders —
    # some tenants 400 on it ("Could not find a property named
    # 'wellKnownName'"), which silently disabled exclusion and let the
    # 20k+ Sent Items crowd real NDRs out of the result window. The path
    # form (/me/mailFolders/sentitems) is locale-independent and never
    # touches the custom "Undeliverable" folder, so bounces stay included.
    exclude_folder_ids = set()
    for _wk in ("sentitems", "drafts", "deleteditems", "junkemail", "outbox", "archive"):
        try:
            _r = httpx.get(
                f"{GRAPH_API}/me/mailFolders/{_wk}?$select=id",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if _r.status_code == 200:
                _fid = _r.json().get("id")
                if _fid:
                    exclude_folder_ids.add(_fid)
        except Exception:
            pass  # non-fatal — worst case that folder isn't excluded

    try:
        # Paginate a few pages so a burst of NDRs (or heavy normal mail) in
        # one window isn't truncated at $top. Normal 5-minute scans have
        # far fewer than a page and stop after the first request; only a
        # flood follows @odata.nextLink. Bounded so we never runaway.
        messages = []
        url = f"{GRAPH_API}/me/messages?{params}"
        _pages = 0
        _MAX_PAGES = 6  # up to ~600 messages/scan
        while url and _pages < _MAX_PAGES:
            resp = httpx.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    # Ask Graph for the body as plain text rather than HTML.
                    "Prefer": 'outlook.body-content-type="text"',
                },
                timeout=25,
            )
            if resp.status_code != 200:
                print(f"[MS Inbox] HTTP {resp.status_code}: {resp.text[:200]}")
                break
            data = resp.json()
            for msg in data.get("value", []):
                if msg.get("isDraft"):
                    continue
                if msg.get("parentFolderId") in exclude_folder_ids:
                    continue
                from_data = msg.get("from", {}).get("emailAddress", {})
                # Full text body (capped) so the NDR parser can read the
                # failed recipient + SMTP status; bodyPreview is ~255 chars.
                body_full = ((msg.get("body") or {}).get("content") or "")[:12000]
                messages.append({
                    "from_email": (from_data.get("address") or "").lower().strip(),
                    "from_name": from_data.get("name", ""),
                    "subject": msg.get("subject", ""),
                    "body_preview": msg.get("bodyPreview", "")[:2000],
                    "body_full": body_full,
                    "received_at": msg.get("receivedDateTime", ""),
                    "message_id": msg.get("id", ""),
                    "is_read": msg.get("isRead", False),
                })
            url = data.get("@odata.nextLink")
            _pages += 1
        return messages

    except Exception as e:
        print(f"[MS Inbox] Error: {e}")
        return []
