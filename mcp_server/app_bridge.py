"""Passwordless connector sign-in: the MCP server hands the browser to the
main app, where the user is already signed in, and the app hands it back
with a signed statement of who approved the connection.

    Claude -> mcp /authorize -> mcp /login  (bridge on: redirect to app)
           -> app /connector/authorize      (needs the app session; user clicks Allow)
           -> mcp /login/complete?...&sig=  (verify, mint the OAuth code)

Both processes read DRIPDROP_MCP_BRIDGE_SECRET from the same
/opt/dripdrop/.env. With no secret set the bridge is off and the connector
keeps its email/password form, so Arena's instance is unchanged.

Kept dependency-free: flowdrip_app.py imports this too.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

SIGNATURE_TTL_SECONDS = 120


def bridge_secret() -> str:
    return (os.environ.get("DRIPDROP_MCP_BRIDGE_SECRET") or "").strip()


def app_authorize_url() -> str:
    return (os.environ.get("DRIPDROP_MCP_APP_AUTHORIZE_URL") or "").strip()


def enabled() -> bool:
    return bool(bridge_secret() and app_authorize_url())


def _mac(secret: str, login_token: str, email: str, exp: int) -> str:
    msg = f"{login_token}\n{email}\n{exp}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def sign(login_token: str, email: str, now: float | None = None) -> dict:
    """Query params the app appends to the MCP's /login/complete URL."""
    secret = bridge_secret()
    if not secret:
        raise RuntimeError("DRIPDROP_MCP_BRIDGE_SECRET is not set")
    email = email.lower().strip()
    exp = int((now if now is not None else time.time()) + SIGNATURE_TTL_SECONDS)
    return {"login_token": login_token, "email": email, "exp": str(exp),
            "sig": _mac(secret, login_token, email, exp)}


def verify(login_token: str, email: str, exp: str, sig: str,
           now: float | None = None) -> bool:
    secret = bridge_secret()
    if not (secret and login_token and email and exp and sig):
        return False
    try:
        exp_i = int(exp)
    except ValueError:
        return False
    if exp_i < (now if now is not None else time.time()):
        return False
    expected = _mac(secret, login_token, email.lower().strip(), exp_i)
    return hmac.compare_digest(expected, sig)
