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
        "immediately, same as posting to /api/v1/campaigns. For the "
        "`findcandidates` template - the only template that emails "
        "candidates directly instead of companies - pass a job_description "
        "instead of company/niche/roles."
    )
)
async def create_campaign(spec: dict) -> dict:
    """Args:
    spec: campaign spec matching DripDrop's /api/v1/campaigns body - at
        minimum {"template": <template key>, "company" or "niche": str},
        except for template "findcandidates" (see below). Optional: contacts
        (list of {email, first_name, ...}), contacts_csv (raw CSV text),
        candidates (list of candidate cards, used by the fivebythree
        template), roles, location, industry, website, name, start_date
        (ISO date, or omitted/"auto" for the upcoming Monday),
        enroll_newsletter (newsletter name to also enroll contacts into).

        For template "findcandidates": pass job_description (str, the full
        JD text) instead of company/niche/roles, and contacts as the
        candidates to reach (their emails). Optional cadence: "one_email"
        (default), "two_emails_1day", or "three_emails_3days".
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
        "Import candidates into DripDrop's shared Pipeline (ATS) from "
        "STRUCTURED records rather than resume files - no upload, no file "
        "bytes, no resume parsing. Use this whenever you already have the "
        "candidate's details (a job-board export, another ATS, a scraped "
        "profile) instead of a PDF, and prefer it over import_candidates "
        "when you have both: it is faster and cannot fail on an unparseable "
        "file. Give each record an external_id - the candidate's stable id "
        "in the system you got them from - and re-sending the same batch "
        "updates those rows in place instead of creating duplicates, so you "
        "never need to track what you have already sent."
    )
)
async def import_candidate_records(records: list[dict]) -> dict:
    """Args:
    records: list of candidate dicts, max 500 per call. Per record:
        external_id (str, strongly recommended - the stable id in the source
        system; it is the dedupe key), name (or first_name/last_name),
        email, phone, city, state, current_title (or title),
        current_employer (or employer), years_experience, seniority, skills
        (list or comma-separated string), summary, resume_text (the full
        resume as plain text), source (a label for where it came from).
        A record needs a first and last name plus at least one of
        title/skills/email/phone to be accepted.
    """
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.import_candidate_records(records)
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
        "List DripDrop's 11 built-in campaign templates (blitz, fourbyfour, "
        "fivebyfive, fivebythree, talentdrop, flood, sidequest, fullstream, "
        "victorycard, byos, findcandidates) with a description and best-for "
        "guidance for each. Read-only - use this to see what `template` "
        "values create_campaign accepts and pick the right one before "
        "launching."
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


@mcp.tool(
    description=(
        "List the authenticated DripDrop user's own campaigns, with the "
        "template, step count, contact count, and queue stats (pending/"
        "sent/failed/cancelled) for each. Read-only, tenant-scoped - use "
        "this to see what's already been launched before creating a new "
        "campaign, or to find a campaign_id for campaign_get."
    )
)
async def campaigns_list() -> dict:
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.campaigns_list()
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


@mcp.tool(
    description=(
        "Get full detail on one of the authenticated DripDrop user's own "
        "campaigns - all email steps (subject/body per step), contacts, "
        "and queue stats. Read-only, tenant-scoped - use campaigns_list "
        "first to find the campaign_id."
    )
)
async def campaign_get(campaign_id: str) -> dict:
    """Args:
    campaign_id: id from campaigns_list (or a campaign name).
    """
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.campaign_get(campaign_id)
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


@mcp.tool(
    description=(
        "List the Sales Campaign runs the DripDrop user has queued for you "
        "from the app's Sales Campaign page. DripDrop cannot do the sourcing "
        "itself - its ZoomInfo seat is entitled for this MCP surface, not the "
        "REST API - so it queues the target here. Each run comes back with "
        "the full target (industry, geography, roles, size band, avoid list), "
        "the already_worked dedupe keys, the contact targets, and an "
        "'instructions' field that is the literal brief: follow it. Read-only."
    )
)
async def sales_runs_pending() -> dict:
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.sales_runs_pending()
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


@mcp.tool(
    description=(
        "Write back to a queued DripDrop Sales Campaign run. Call it once "
        "with {\"status\": \"working\"} when you start, and once at the end "
        "with the companies you kept and status 'sourced'. Setting 'sourced' "
        "is what makes DripDrop write the campaigns - it matches candidates "
        "off its own bench and stops at a review screen, so do NOT call "
        "create_campaign for these companies and do not send anything."
    )
)
async def sales_run_update(run_id: str, update: dict) -> dict:
    """Args:
    run_id: the run_id from sales_runs_pending.
    update: any of -
        status: "working" (you picked it up), "sourced" (done - starts the
            build), "error" (with an "error" string saying what stopped you),
            "cancelled".
        companies: list of the companies you kept, each
            {"company": str, "state": str, "role": str, "why": str,
             "source": str, "zi_total": int,
             "contacts": [{"email", "first_name", "last_name", "title",
                           "linkedin", "state"}]}.
            Contacts are cleaned and deduped on arrival; one with no usable
            email is dropped with a reason rather than silently kept. A
            company below the contact floor is skipped at build time.
        reserves: ranked reserves, same shape, each with its demerit.
        dropped: what you dropped and why.
        claude_notes: anything the user should read on the review screen.
        schedule_result: if the run asked for a repeat, what you created.
        log: str or list of str, appended to the run's progress log.
    """
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.sales_run_update(run_id, update or {})
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


@mcp.tool(description=(
    "Import ZoomInfo contact records into a DripDrop contact list, keeping "
    "their firmographics (industry, company size, job function, seniority, "
    "hiring signal). Pass records EXACTLY as ZoomInfo returned them - do not "
    "reshape them first. Returns how many were kept, how many were added "
    "versus updated, and the reason for every record dropped. Re-importing a "
    "record that is already on the list enriches it rather than duplicating "
    "it, and a field ZoomInfo left blank never erases one already stored."
))
async def tm_import_contacts(records: list, list_name: str = "") -> dict:
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.tm_import_contacts(records, list_name)
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


@mcp.tool(description=(
    "List the saved audiences for this account, with the criteria each one "
    "filters on. Use this before tm_audience_preview to find out what the "
    "user has already defined instead of inventing criteria."
))
async def tm_audiences() -> dict:
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.tm_audiences()
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


@mcp.tool(description=(
    "Preview how many contacts an audience would reach before launching "
    "anything. Pass either {'audience': '<saved name>'} or {'criteria': "
    "{industries, size_buckets, job_functions, seniorities, signal_types, "
    "include_unknown, require_complete_signal}}, against a saved list name or "
    "inline contacts. Returns the match count, how many are already being "
    "worked in another campaign, and how many were excluded for a MISSING "
    "field rather than a wrong one - report that second number, because a "
    "small match count usually means thin data, not a bad fit."
))
async def tm_audience_preview(body: dict) -> dict:
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.tm_audience_preview(body)
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


@mcp.tool(description=(
    "Outreach results for this account: contacted, replied, reply rate, "
    "opt-outs and bounces, overall and per campaign. Optionally limit to the "
    "last N days or one campaign. There is NO open or click tracking anywhere "
    "in this product - do not report opens or clicks, and do not infer them."
))
async def tm_analytics(days: int = 0, campaign: str = "") -> dict:
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.tm_analytics(days, campaign)
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


@mcp.tool(description=(
    "The connected sending mailboxes and how many emails each may still send "
    "TODAY. Check this before promising a send volume: a mailbox still in its "
    "warmup ramp is allowed far less than its configured daily cap, and the "
    "send loop enforces the ramp, not the cap."
))
async def tm_mailboxes() -> dict:
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.tm_mailboxes()
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
