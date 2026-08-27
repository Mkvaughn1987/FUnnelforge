"""DripDrop MCP connector entrypoint.

Exposes DripDrop's campaign-launch and candidate-import API as MCP tools.
Each user authorizes this connector once via claude.ai Settings -> Connectors;
authorization is a normal OAuth flow that ends at DripDrop's own email/
password login (see auth_provider.py, dripdrop_login.py) - no API key is
ever typed into chat or handled by the model as text. Works identically for
interactive Cowork sessions and headless/scheduled runs, since the stored
OAuth token (not a browser session cookie) is what authenticates each call.

Run directly for local/dev (stdio or streamable-http per DRIPDROP_MCP_TRANSPORT);
in production this runs under systemd as `dripdrop-mcp.service`, fronted by
Caddy at mcp.dripdripdrop.ai (see deploy/Caddyfile).
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import anyio
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from mcp_server import dripdrop_login
from mcp_server.auth_provider import DripDropAuthProvider
from mcp_server.dripdrop_client import DripDropApiError, DripDropClient, NoApiKeyError


def _base_data_dir() -> Path:
    """Same resolution flowdrip_app.py uses (flowdrip_app.py:905-935), so
    this reads the exact users.json / api_keys.json the main app writes."""
    env = os.environ.get("DRIPDROP_DATA_DIR")
    if env:
        return Path(env)
    local_appdata = os.environ.get("LOCALAPPDATA")
    base = Path(local_appdata) if local_appdata else Path(__file__).resolve().parent
    return base / "DripDrop"


DATA_DIR = _base_data_dir()
PUBLIC_URL = os.environ.get("DRIPDROP_MCP_PUBLIC_URL", "http://127.0.0.1:8090").rstrip("/")

auth_provider = DripDropAuthProvider(data_dir=DATA_DIR, public_url=PUBLIC_URL)

mcp = MCPServer(
    name="dripdrop",
    title="DripDrop",
    description="Launch DripDrop outbound campaigns and search the shared candidate Pipeline.",
    auth_server_provider=auth_provider,
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(PUBLIC_URL),
        resource_server_url=AnyHttpUrl(PUBLIC_URL),
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["dripdrop"],
            default_scopes=["dripdrop"],
        ),
        revocation_options=RevocationOptions(enabled=True),
    ),
)


def _current_email() -> str:
    """The DripDrop account email for the caller of the current tool
    invocation, resolved from the OAuth access token's `subject` (set to the
    email in auth_provider.complete_login)."""
    token = get_access_token()
    if not token or not token.subject:
        raise RuntimeError("no authenticated DripDrop user for this request")
    return token.subject


def _login_page(login_token: str, error: str | None = None) -> str:
    error_html = f'<p style="color:#b00020">{error}</p>' if error else ""
    return f"""
    <!doctype html>
    <html>
    <head><title>Sign in to DripDrop</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      body {{ font-family: system-ui, sans-serif; max-width: 360px; margin: 80px auto; }}
      input {{ display: block; width: 100%; padding: 8px; margin: 8px 0 16px; box-sizing: border-box; }}
      button {{ width: 100%; padding: 10px; background: #4c6fff; color: #fff; border: 0; border-radius: 4px; }}
    </style>
    </head>
    <body>
      <h2>Sign in to DripDrop</h2>
      <p>Authorize this connector with your DripDrop account.</p>
      {error_html}
      <form method="post" action="/login">
        <input type="hidden" name="login_token" value="{login_token}">
        <label>Email</label>
        <input type="email" name="email" required autofocus>
        <label>Password</label>
        <input type="password" name="password" required>
        <button type="submit">Sign in</button>
      </form>
    </body>
    </html>
    """


@mcp.custom_route("/login", methods=["GET"])
async def login_form(request: Request) -> HTMLResponse:
    login_token = request.query_params.get("login_token", "")
    if not auth_provider.resolve_pending(login_token):
        return HTMLResponse("<p>This login link has expired. Please restart the authorization from Claude.</p>", status_code=400)
    return HTMLResponse(_login_page(login_token))


@mcp.custom_route("/login", methods=["POST"])
async def login_submit(request: Request):
    form = await request.form()
    login_token = str(form.get("login_token", ""))
    email = str(form.get("email", ""))
    password = str(form.get("password", ""))

    if not auth_provider.resolve_pending(login_token):
        return HTMLResponse("<p>This login link has expired. Please restart the authorization from Claude.</p>", status_code=400)

    if not dripdrop_login.authenticate(DATA_DIR, email, password):
        return HTMLResponse(_login_page(login_token, error="Incorrect email or password."), status_code=401)

    redirect_url = auth_provider.complete_login(login_token, email.lower().strip())
    if not redirect_url:
        return HTMLResponse("<p>This login link has expired. Please restart the authorization from Claude.</p>", status_code=400)
    return RedirectResponse(redirect_url, status_code=302)


@mcp.tool(
    description=(
        "Create and launch a DripDrop outbound email campaign from a spec "
        "(template, company/niche, roles, contacts). Runs as the "
        "authenticated DripDrop user; the campaign is scheduled and queued "
        "immediately, same as posting to /api/v1/campaigns."
    )
)
async def create_campaign(spec: dict) -> dict:
    """Args:
    spec: campaign spec matching DripDrop's /api/v1/campaigns body - at
        minimum {"template": <template key>, "company" or "niche": str}.
        Optional: contacts (list of {email, first_name, ...}), contacts_csv
        (raw CSV text), candidates (list of candidate cards, used by the
        fivebythree template), roles, location, industry, website, name,
        start_date (ISO date, or omitted/"auto" for the upcoming Monday),
        enroll_newsletter (newsletter name to also enroll contacts into).
    """
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.create_campaign(spec)
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


@mcp.tool(
    description=(
        "Bulk-import resume files into DripDrop's shared candidate Pipeline "
        "(the same ATS/Pipeline bench visible in-app). Each file runs the "
        "same parse+save pipeline as the in-app Bulk Import Resumes button; "
        "imports are append-only and owned by the authenticated caller."
    )
)
async def import_candidates(files: list[dict]) -> dict:
    """Args:
    files: list of {"filename": str, "content_base64": str} - one entry per
        resume (pdf/doc/docx/txt/rtf), base64-encoded file content.
    """
    import base64

    email = _current_email()
    decoded = [
        (f["filename"], base64.b64decode(f["content_base64"]))
        for f in files
    ]
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.import_candidates(decoded)
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


@mcp.tool(
    description=(
        "Count candidates in DripDrop's shared Pipeline (ATS) - a "
        "lightweight way to confirm an import landed."
    )
)
async def candidates_count() -> dict:
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.candidates_count()
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


@mcp.tool(
    description=(
        "Search DripDrop's shared candidate Pipeline (ATS) by keyword "
        "(matches name, title, employer, skills, and resume text) and/or "
        "status. Read-only, team-wide - use this to check whether a "
        "candidate for a given skill/role/location is already in the "
        "Pipeline before importing or pitching."
    )
)
async def candidates_search(q: str = "", status: str = "", limit: int = 20) -> dict:
    """Args:
    q: keyword to search for (e.g. a skill, title, or location) - optional,
        omit to just filter by status or list recent candidates.
    status: optional status filter - "active", "placed", or "on_hold".
    limit: max results to return (default 20, max 50).
    """
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.candidates_search(q=q, status=status, limit=limit)
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


@mcp.tool(
    description=(
        "List DripDrop's 10 built-in campaign templates (blitz, fourbyfour, "
        "fivebyfive, fivebythree, talentdrop, flood, sidequest, fullstream, "
        "victorycard, byos) with a description and best-for guidance for "
        "each. Read-only - use this to see what `template` values "
        "create_campaign accepts and pick the right one before launching."
    )
)
async def campaign_types() -> dict:
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.campaign_types()
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


@mcp.tool(
    description=(
        "List the authenticated DripDrop user's own saved custom \"My "
        "Campaign Styles\" (bring-your-own-style descriptions created in "
        "the app). Read-only, tenant-scoped to the caller."
    )
)
async def my_campaign_styles() -> dict:
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.my_campaign_styles()
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


def main() -> None:
    transport = os.environ.get("DRIPDROP_MCP_TRANSPORT", "streamable-http")
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        host = os.environ.get("DRIPDROP_MCP_HOST", "127.0.0.1")
        port = int(os.environ.get("DRIPDROP_MCP_PORT", "8090"))

        # mcp.run()'s public API doesn't expose transport_security, and when
        # host is a loopback address (as it is here - Caddy reverse-proxies
        # in locally) the SDK silently defaults to a TransportSecuritySettings
        # allowlist of loopback Host headers only. That rejects every real
        # request, which arrives with Host: <public domain> as forwarded by
        # Caddy. Call the lower-level run method directly so we can allowlist
        # the actual public host instead.
        public_host = urlparse(PUBLIC_URL).netloc
        transport_security = TransportSecuritySettings(
            allowed_hosts=[public_host, "127.0.0.1:*", "localhost:*"],
            allowed_origins=[PUBLIC_URL, "http://127.0.0.1:*", "http://localhost:*"],
        )
        anyio.run(
            lambda: mcp.run_streamable_http_async(
                host=host, port=port, transport_security=transport_security
            )
        )


if __name__ == "__main__":
    main()
