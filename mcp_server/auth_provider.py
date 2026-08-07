"""OAuthAuthorizationServerProvider bridging Claude's connector OAuth flow
to DripDrop's own email/password login.

`authorize()` doesn't talk to DripDrop directly - the MCP OAuth spec expects
a provider to hand back a URL for the *browser* to land on. We hand back our
own /login page (see dripdrop_mcp.py's custom_route handlers), which prompts
for DripDrop email/password, checks them via dripdrop_login.authenticate(),
and only then mints an authorization code and redirects back to the client
(this is the "bridge to a 3rd-party OAuth/login provider" shape the SDK's
own OAuthAuthorizationServerProvider.authorize() docstring describes).

All records (registered clients, in-flight logins, codes, tokens) are flat
JSON stores under $DRIPDROP_DATA_DIR/mcp_oauth/, atomic tmp+replace writes -
see storage.py.
"""

from __future__ import annotations

import secrets
import time
from pathlib import Path

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from mcp_server.storage import JsonStore, oauth_store_dir

ACCESS_TOKEN_TTL_SECONDS = 3600
AUTH_CODE_TTL_SECONDS = 120
LOGIN_LINK_TTL_SECONDS = 300


class DripDropAuthProvider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    def __init__(self, data_dir: Path, public_url: str):
        self.data_dir = data_dir
        self.public_url = public_url.rstrip("/")
        store_dir = oauth_store_dir(data_dir)
        self.clients = JsonStore(store_dir / "clients.json")
        self.pending = JsonStore(store_dir / "pending_authorizations.json")
        self.codes = JsonStore(store_dir / "authorization_codes.json")
        self.access_tokens = JsonStore(store_dir / "access_tokens.json")
        self.refresh_tokens = JsonStore(store_dir / "refresh_tokens.json")

    # ---- Dynamic client registration ---------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        record = self.clients.get(client_id)
        if not record:
            return None
        return OAuthClientInformationFull.model_validate(record)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self.clients.put(
            client_info.client_id,
            client_info.model_dump(mode="json", exclude_none=True),
        )

    # ---- Authorization request: hand off to our own /login page -------

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        login_token = secrets.token_urlsafe(24)
        self.pending.put(login_token, {
            "client_id": client.client_id,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "code_challenge": params.code_challenge,
            "scopes": params.scopes or [],
            "state": params.state,
            "resource": params.resource,
            "expires_at": time.time() + LOGIN_LINK_TTL_SECONDS,
        })
        return f"{self.public_url}/login?login_token={login_token}"

    def resolve_pending(self, login_token: str) -> dict | None:
        """Used by the /login route to recall what authorize() stashed."""
        record = self.pending.get(login_token)
        if not record or record["expires_at"] < time.time():
            return None
        return record

    def complete_login(self, login_token: str, email: str) -> str | None:
        """Used by the /login route after a successful DripDrop password
        check. Mints a one-time authorization code bound to `email` and
        returns the URL to redirect the browser back to the client.
        Returns None if the login link is missing/expired."""
        pending = self.resolve_pending(login_token)
        if pending is None:
            return None
        self.pending.delete(login_token)

        code = secrets.token_urlsafe(32)
        self.codes.put(code, {
            "code": code,
            "client_id": pending["client_id"],
            "redirect_uri": pending["redirect_uri"],
            "redirect_uri_provided_explicitly": pending["redirect_uri_provided_explicitly"],
            "code_challenge": pending["code_challenge"],
            "scopes": pending["scopes"],
            "resource": pending["resource"],
            "subject": email,
            "expires_at": time.time() + AUTH_CODE_TTL_SECONDS,
        })
        return construct_redirect_uri(pending["redirect_uri"], code=code, state=pending["state"])

    # ---- Authorization code exchange -----------------------------------

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        record = self.codes.get(authorization_code)
        if not record or record["client_id"] != client.client_id:
            return None
        if record["expires_at"] < time.time():
            self.codes.delete(authorization_code)
            return None
        return AuthorizationCode(
            code=record["code"],
            scopes=record["scopes"],
            expires_at=record["expires_at"],
            client_id=record["client_id"],
            code_challenge=record["code_challenge"],
            redirect_uri=record["redirect_uri"],
            redirect_uri_provided_explicitly=record["redirect_uri_provided_explicitly"],
            resource=record.get("resource"),
            subject=record.get("subject"),
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        self.codes.delete(authorization_code.code)
        return self._mint_tokens(client, authorization_code.subject, authorization_code.scopes)

    # ---- Refresh ---------------------------------------------------------

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        record = self.refresh_tokens.get(refresh_token)
        if not record or record["client_id"] != client.client_id:
            return None
        return RefreshToken(
            token=record["token"],
            client_id=record["client_id"],
            scopes=record["scopes"],
            expires_at=record.get("expires_at"),
            subject=record.get("subject"),
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        # Rotate both tokens on use, per the MCP auth spec (public client).
        self.refresh_tokens.delete(refresh_token.token)
        granted_scopes = scopes or refresh_token.scopes
        return self._mint_tokens(client, refresh_token.subject, granted_scopes)

    # ---- Access token verification ---------------------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        record = self.access_tokens.get(token)
        if not record:
            return None
        if record["expires_at"] < time.time():
            self.access_tokens.delete(token)
            return None
        return AccessToken(
            token=record["token"],
            client_id=record["client_id"],
            scopes=record["scopes"],
            expires_at=record["expires_at"],
            subject=record.get("subject"),
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, AccessToken):
            self.access_tokens.delete(token.token)
        else:
            self.refresh_tokens.delete(token.token)

    # ---- shared helper -----------------------------------------------------

    def _mint_tokens(self, client: OAuthClientInformationFull, subject: str | None, scopes: list[str]) -> OAuthToken:
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        expires_at = int(time.time() + ACCESS_TOKEN_TTL_SECONDS)
        self.access_tokens.put(access_token, {
            "token": access_token,
            "client_id": client.client_id,
            "scopes": scopes,
            "expires_at": expires_at,
            "subject": subject,
        })
        self.refresh_tokens.put(refresh_token, {
            "token": refresh_token,
            "client_id": client.client_id,
            "scopes": scopes,
            "expires_at": None,
            "subject": subject,
        })
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            scope=" ".join(scopes) if scopes else None,
            refresh_token=refresh_token,
        )
