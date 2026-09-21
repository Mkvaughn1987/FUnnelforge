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
from urllib.parse import urlencode, urlparse

import anyio
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import Icon
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, RedirectResponse

from mcp_server import app_bridge, dripdrop_login
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
# Same variable the app's brand layer reads, so a white-label instance's
# connector shows its own name in Claude and on the sign-in page.
BRAND = (os.environ.get("DRIPDROP_BRAND_NAME") or "DripDrop").strip() or "DripDrop"

auth_provider = DripDropAuthProvider(data_dir=DATA_DIR, public_url=PUBLIC_URL)

# Connector icon. Repo-relative PNG, unset on Arena (no icon, /favicon.ico
# stays a 404 as before). Claude shows it next to the connector name.
_ICON_REL = (os.environ.get("DRIPDROP_BRAND_ICON_LARGE") or "").strip()
ICON_PATH = (Path(__file__).resolve().parent.parent / _ICON_REL) if _ICON_REL else None
if ICON_PATH is not None and not ICON_PATH.is_file():
    ICON_PATH = None
_ICONS = [Icon(src=f"{PUBLIC_URL}/icon.png", mime_type="image/png", sizes=["512x512"])] if ICON_PATH else None

mcp = MCPServer(
    name="dripdrop",
    title=BRAND,
    icons=_ICONS,
    description=f"Launch {BRAND} outbound campaigns and search the shared candidate Pipeline.",
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
    <head><title>Sign in to {BRAND}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      body {{ font-family: system-ui, sans-serif; max-width: 360px; margin: 80px auto; }}
      input {{ display: block; width: 100%; padding: 8px; margin: 8px 0 16px; box-sizing: border-box; }}
      button {{ width: 100%; padding: 10px; background: #4c6fff; color: #fff; border: 0; border-radius: 4px; }}
    </style>
    </head>
    <body>
      <h2>Sign in to {BRAND}</h2>
      <p>Authorize this connector with your {BRAND} account.</p>
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
    pending = auth_provider.resolve_pending(login_token)
    if not pending:
        return HTMLResponse(_EXPIRED_HTML, status_code=400)
    if app_bridge.enabled():
        # Passwordless: the app confirms who is signed in (see app_bridge.py).
        client = await auth_provider.get_client(pending["client_id"])
        query = urlencode({
            "login_token": login_token,
            "client": (client.client_name if client else "") or "",
        })
        return RedirectResponse(f"{app_bridge.app_authorize_url()}?{query}", status_code=302)
    return HTMLResponse(_login_page(login_token))


if ICON_PATH is not None:
    async def _icon(request: Request) -> FileResponse:
        return FileResponse(str(ICON_PATH), media_type="image/png",
                            headers={"Cache-Control": "public, max-age=86400"})

    mcp.custom_route("/icon.png", methods=["GET"])(_icon)
    mcp.custom_route("/favicon.ico", methods=["GET"])(_icon)


_EXPIRED_HTML = "<p>This login link has expired. Please restart the authorization from Claude.</p>"


@mcp.custom_route("/login/complete", methods=["GET"])
async def login_complete(request: Request):
    """Where the app sends the browser back after the user clicks Allow."""
    q = request.query_params
    login_token = q.get("login_token", "")
    email = q.get("email", "").lower().strip()
    if not app_bridge.enabled():
        return HTMLResponse("<p>Not found.</p>", status_code=404)
    if not app_bridge.verify(login_token, email, q.get("exp", ""), q.get("sig", "")):
        return HTMLResponse("<p>This sign-in could not be verified. Please restart the authorization from Claude.</p>", status_code=400)
    if email not in dripdrop_login._load_users(DATA_DIR):
        return HTMLResponse(f"<p>No {BRAND} account found for this sign-in.</p>", status_code=403)
    redirect_url = auth_provider.complete_login(login_token, email)
    if not redirect_url:
        return HTMLResponse(_EXPIRED_HTML, status_code=400)
    return RedirectResponse(redirect_url, status_code=302)


@mcp.custom_route("/login", methods=["POST"])
async def login_submit(request: Request):
    if app_bridge.enabled():
        # The password form is not offered when the bridge is on; don't
        # accept a hand-built POST either.
        return HTMLResponse("<p>Password sign-in is disabled for this connector.</p>", status_code=403)
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


# The ThriveModal Sales Assets PDFs a campaign can attach. Mirrors
# _TM_CAMPAIGN_PDF_KINDS in flowdrip_app.py (a test keeps the two in step).
_PDF_KINDS_DOC = (
    "tm_role_blueprint (Offshore Role Blueprint: what the role covers, skills "
    "and systems, how the client oversees it), tm_cost_compare (Staffing Cost "
    "Comparison: a U.S. hire beside a dedicated professional in the "
    "Philippines), tm_how_it_works (How We Work Together: how an engagement "
    "runs from defining the role to onboarding). Every campaign carries one "
    "or two of these three."
)


@mcp.tool(
    description=(
        "Create and launch a DripDrop outbound email campaign from a spec "
        "(template, company/niche, roles, contacts). Runs as the "
        "authenticated DripDrop user; the campaign is scheduled and queued "
        "immediately, same as posting to /api/v1/campaigns. For the "
        "`findcandidates` template - the only template that emails "
        "candidates directly instead of companies - pass a job_description "
        "instead of company/niche/roles. On a ThriveModal workspace the "
        "campaign attaches Sales Assets PDFs built for its role and "
        "location: pass spec.pdfs to choose which (1 or 2) and optionally the "
        "step each goes on, or leave it out for the type's default (usually "
        "Role Blueprint + Cost Comparison). "
        "Kinds: " + _PDF_KINDS_DOC
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

        ThriveModal only - pdfs: list of PDF kinds, e.g.
        ["tm_cost_compare", "tm_how_it_works"], or of {"kind": ...,
        "step": n} to put one on step n (1-based; never step 1 or a
        call/LinkedIn step). One or two kinds. The response lists where each
        PDF landed under "pdfs"; problems come back under "pdf_notes".
        To change PDFs after launch, use tm_campaign_pdfs.
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
    "Saved audiences (the Audience filter on the campaign contacts step). "
    "action='list' (default) returns every saved audience with the criteria "
    "it filters on; use it before tm_audience_preview instead of inventing "
    "criteria. action='save' with name + criteria {industries, size_buckets, "
    "job_functions, seniorities, signal_types (lists of strings), "
    "include_unknown, require_complete_signal (true/false)} saves one; "
    "saving over an existing name replaces it. action='delete' with name "
    "removes one (ask the user first). An audience is criteria, never a list "
    "of contacts."
))
async def tm_audiences(action: str = "list", name: str = "",
                       criteria: dict | None = None) -> dict:
    if action == "list":
        return await _tm_call("tm_audiences")
    body: dict = {"action": action, "name": name}
    if criteria is not None:
        body["criteria"] = criteria
    return await _tm_call("tm_audiences", body)


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
    "Sending mailboxes. action='list' (default) returns them and how many "
    "emails each may still send TODAY; check this before promising a send "
    "volume, because a mailbox still in its warmup ramp is allowed far less "
    "than its configured daily cap, and the send loop enforces the ramp. "
    "action='add' with email, provider ('microsoft' or 'google'), daily_cap "
    "(5-500, default 250) and warmup_days (0-90, default 21) registers a new "
    "mailbox, warming up from today. Adding does NOT connect it: signing the "
    "mailbox in is an OAuth step the user does in the app in a browser "
    "(Settings > Email & AI Setup > Sending Mailboxes > Connect); tell them "
    "so. action='pause' / 'resume' / 'remove' with mailbox_id (or email) "
    "stops, restarts or drops one from the rotation; ask before removing."
))
async def tm_mailboxes(action: str = "list", email: str = "",
                       provider: str = "microsoft", daily_cap: int = 250,
                       warmup_days: int = 21, mailbox_id: str = "") -> dict:
    if action == "list":
        return await _tm_call("tm_mailboxes")
    body: dict = {"action": action, "email": email, "id": mailbox_id}
    if action == "add":
        body.update({"provider": provider, "daily_cap": daily_cap,
                     "warmup_days": warmup_days})
    return await _tm_call("tm_mailboxes", body)


@mcp.tool(description=(
    "Choose which Sales Assets PDFs an EXISTING campaign attaches, and "
    "optionally which step each rides on (ThriveModal workspaces only). The "
    "PDFs are generated fresh for the campaign's role and location and "
    "replace the campaign's current Sales Assets PDFs; files the user "
    "uploaded by hand are kept. Emails already queued and waiting to send "
    "pick up the change too. Kinds (1 or 2 per campaign): "
    + _PDF_KINDS_DOC + " Use campaigns_list / campaign_get to find the "
    "campaign_id and see its steps. Takes up to a couple of minutes."
))
async def tm_campaign_pdfs(campaign_id: str, pdfs: list, role: str = "",
                           location: str = "", industry: str = "",
                           company: str = "") -> dict:
    """Args:
    campaign_id: id from campaigns_list (or the campaign name).
    pdfs: list of kinds, e.g. ["tm_cost_compare", "tm_role_blueprint"], or
        of {"kind": ..., "step": n} to put a PDF on step n (1-based, as
        campaign_get numbers them). Never step 1, a call/LinkedIn step, or two
        PDFs on one step. Unpinned PDFs go on the step whose subject they back,
        else spread over the sequence. One or two kinds; a campaign always
        keeps at least one.
    role, location, industry, company: optional; what to build the PDFs for
        when the campaign's own values are wrong or empty.
    """
    email = _current_email()
    body = {"campaign_id": campaign_id, "pdfs": pdfs}
    for k, v in (("role", role), ("location", location),
                 ("industry", industry), ("company", company)):
        if v:
            body[k] = v
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.tm_campaign_pdfs(body)
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


# -- ThriveModal: the rest of the app (2026-09-21) --------------------------
# One tool per page, so everything the app does is reachable from Claude.
# Each maps 1:1 to a client method (test_63 pairs them).

# The app's own address, for links to PDFs. The bridge already knows it.
_APP_AUTHORIZE = os.environ.get("DRIPDROP_MCP_APP_AUTHORIZE_URL", "")
_APP_ORIGIN = ("{0.scheme}://{0.netloc}".format(urlparse(_APP_AUTHORIZE))
               if _APP_AUTHORIZE else "")


async def _tm_call(method: str, *args) -> dict:
    try:
        client = DripDropClient(DATA_DIR, _current_email())
        return await getattr(client, method)(*args)
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


def _link_pdfs(res: dict) -> dict:
    """Turn the app's /pdfs/ paths into links the user can open (they open
    in a browser where the user is signed in to the app)."""
    rows = res.get("assets") if isinstance(res.get("assets"), list) else [res]
    for r in rows:
        if isinstance(r, dict) and str(r.get("path", "")).startswith("/pdfs/"):
            r["url"] = _APP_ORIGIN + r["path"]
    return res


@mcp.tool(description=(
    "My Day: today's calls, LinkedIn touches and manual tasks from active "
    "campaigns (plus up to a week of overdue ones), with the contact's "
    "phones, LinkedIn and the call script. Pass date=YYYY-MM-DD for another "
    "day. Use tm_task_done to tick one off."
))
async def tm_my_day(date: str = "") -> dict:
    return await _tm_call("tm_my_day", date)


@mcp.tool(description=(
    "Mark My Day tasks done, exactly like the buttons in the app. One task: "
    "task_id; several: task_ids. result: 'done' (a task), 'connected' "
    "(spoke to them / LinkedIn sent), 'vm' (left a voicemail) or 'skipped' "
    "(default 'done'). undo=true puts them back. The page's bulk buttons: "
    "all_overdue=true ('Mark all overdue done'), or campaign='<name or "
    "campaign_id>' and/or channel='call'|'li'|'task' ('Mark all N done', "
    "'All LinkedIn done'), for today unless date=YYYY-MM-DD. Bulk marks "
    "give calls 'vm', LinkedIn 'connected' and tasks 'done' unless result "
    "is set. Get ids from tm_my_day. Confirm with the user before a bulk mark."
))
async def tm_task_done(task_id: str = "", result: str = "", undo: bool = False,
                       task_ids: list | None = None, all_overdue: bool = False,
                       campaign: str = "", channel: str = "",
                       date: str = "") -> dict:
    body: dict = {"task_id": task_id, "result": result, "undo": undo,
                  "all_overdue": all_overdue, "campaign": campaign,
                  "channel": channel, "date": date}
    if task_ids:
        body["task_ids"] = task_ids
    return await _tm_call("tm_task_done", body)


@mcp.tool(description=(
    "Replies: everyone who wrote back to a campaign, with their message. "
    "action='list' (default) lists them; action='scan' re-scans the user's "
    "inbox now for new replies (the app also scans every few minutes); "
    "action='draft' with email returns a suggested answer to that reply; "
    "action='followed_up' marks one handled; action='dismiss' removes it "
    "from the list. Nothing here sends email: the user answers from their "
    "own mailbox (you may also write the reply yourself), then mark it "
    "followed_up."
))
async def tm_replies(action: str = "list", email: str = "") -> dict:
    return await _tm_call("tm_replies", action, email)


@mcp.tool(description=(
    "Search the contacts on file: one saved list by name (blank = the active "
    "list), filtered by q against name, email, company and title. Also "
    "returns every saved list's name, for tm_campaign_contacts."
))
async def tm_contacts(list_name: str = "", q: str = "", limit: int = 50) -> dict:
    return await _tm_call("tm_contacts", list_name, q, limit)


@mcp.tool(description=(
    "Add contacts to an EXISTING campaign or newsletter, or remove one. "
    "action='add' with contacts=[{email, first_name, last_name, company, "
    "title, ...}] or list_name='<saved list>' queues their emails starting "
    "today; Do Not Contact, past repliers and Clients are skipped exactly as "
    "in the app. action='remove' with email stops that person's pending "
    "emails in this campaign. Adding sends real email, so confirm with the "
    "user before adding a list."
))
async def tm_campaign_contacts(campaign_id: str, action: str = "add",
                               contacts: list | None = None,
                               list_name: str = "", email: str = "") -> dict:
    body: dict = {"campaign_id": campaign_id, "action": action}
    if contacts is not None:
        body["contacts"] = contacts
    if list_name:
        body["list"] = list_name
    if email:
        body["email"] = email
    return await _tm_call("tm_campaign_contacts", body)


@mcp.tool(description=(
    "Stop, restart or delete a campaign. action: 'cancel' (stops every "
    "pending email), 'resume' (re-queues everything not yet sent; nothing "
    "already sent goes twice), 'retry_failed' (reschedules failed sends for "
    "tomorrow 9am) or 'delete' (permanent; needs confirm=true, and ask the "
    "user first)."
))
async def tm_campaign_action(campaign_id: str, action: str, confirm: bool = False) -> dict:
    return await _tm_call("tm_campaign_action",
                          {"campaign_id": campaign_id, "action": action,
                           "confirm": confirm})


@mcp.tool(description=(
    "Send one email step of a campaign to the user's own inbox as a "
    "preview, merged with their own name and carrying its attachments. "
    "step is 1-based, as campaign_get numbers the steps."
))
async def tm_send_preview(campaign_id: str, step: int = 1) -> dict:
    return await _tm_call("tm_send_preview", {"campaign_id": campaign_id, "step": step})


@mcp.tool(description=(
    "List the monthly newsletters (contacts, next issue, whether it is "
    "written yet) plus the sectors and styles a new one can use."
))
async def tm_newsletters() -> dict:
    return await _tm_call("tm_newsletters")


@mcp.tool(description=(
    "Create a monthly newsletter. sector is a key from tm_newsletters "
    "(e.g. 'logistics'); region defaults to Nationwide; start_date "
    "YYYY-MM-DD (default today); count = months (default 12); style "
    "'full_send' (with pictures) or 'j_way' (organic, text only); "
    "profiles=true adds candidate profile cards. The first issue is written "
    "in the background; enrol people afterwards with tm_campaign_contacts."
))
async def tm_newsletter_create(name: str, sector: str, region: str = "",
                               niche: str = "", start_date: str = "",
                               count: int = 12, time: str = "9:00 AM",
                               style: str = "full_send",
                               profiles: bool = True) -> dict:
    return await _tm_call("tm_newsletter_create", {
        "name": name, "sector": sector, "region": region, "niche": niche,
        "start_date": start_date, "count": count, "time": time,
        "style": style, "profiles": profiles})


@mcp.tool(description=(
    "Write a newsletter's next issue now and return its subject and text; "
    "refresh=true rewrites an issue that is already written. Emails already "
    "queued for that issue get the new copy. Takes a minute or two."
))
async def tm_newsletter_issue(campaign_id: str, refresh: bool = False) -> dict:
    return await _tm_call("tm_newsletter_issue",
                          {"campaign_id": campaign_id, "refresh": refresh})


@mcp.tool(description=(
    "Sales Assets PDFs. With no kind, lists the PDFs already in the library "
    "(newest first, each with a link) and the kinds available. With kind + "
    "role (+ company, location, industry), builds a new PDF and returns its "
    "link. Kinds: " + _PDF_KINDS_DOC + " The Sales Assets page also builds "
    "interview_guide (Interview Guide for the shortlist stage) and "
    "market_pulse (Market Pulse: industry context with sources), and "
    "kind='custom' (Create Your Own) builds a one-page PDF from description "
    "(a sentence or two on what it should be; role etc. optional). To change "
    "an existing PDF use tm_pdf_edit; to attach PDFs to a campaign use "
    "tm_campaign_pdfs."
))
async def tm_sales_assets(kind: str = "", role: str = "", company: str = "",
                          location: str = "", industry: str = "",
                          description: str = "") -> dict:
    body = None
    if kind:
        body = {"kind": kind, "role": role, "company": company,
                "location": location, "industry": industry}
        if description:
            body["description"] = description
    return _link_pdfs(await _tm_call("tm_sales_assets", body))


@mcp.tool(description=(
    "The user's Saved Prompts from the AI Prompt page. With no prompt_id, "
    "lists them; with one, returns that prompt's full text, rebuilt from its "
    "saved answers, ready to follow, plus the answers themselves. To change "
    "a saved prompt's answers, save a new one or delete one, use "
    "tm_ai_prompt."
))
async def tm_saved_prompts(prompt_id: str = "") -> dict:
    return await _tm_call("tm_saved_prompts", prompt_id)


@mcp.tool(description=(
    "Clients: companies (by email domain) that outreach never emails. "
    "action='list' (default); action='add' with domain (+ name, location, "
    "notes, website), or with clients=[domain or {domain, name, location, "
    "notes, website}, ...] to add many at once, like the Clients page's file "
    "upload (each row is reported added or skipped, e.g. already on the "
    "list); action='remove' with client_id from the list."
))
async def tm_clients(action: str = "list", domain: str = "", name: str = "",
                     location: str = "", notes: str = "", website: str = "",
                     client_id: str = "", clients: list | None = None) -> dict:
    body = None
    if action != "list":
        body = {"action": action, "domain": domain, "name": name,
                "location": location, "notes": notes, "website": website,
                "id": client_id}
        if clients is not None:
            body["clients"] = clients
    return await _tm_call("tm_clients", body)


@mcp.tool(description=(
    "Settings (Company Profile + Email & AI Setup). With no update, returns "
    "the company profile, email signature, timezone, the user's own name "
    "and phone, the newsletter personal note, the AI writing style guide, "
    "the daily send limit and whether the user is a team admin. update may "
    "hold any of {'profile': {<field>: value}, 'signature': '<text>', "
    "'timezone': 'America/Chicago', 'user': {'name', 'phone'}, "
    "'newsletter_note': '<text>', 'ai_style_guide': '<one rule per line>', "
    "'daily_send_limit': 5-500, 'restore_page_guides': true}. The allowed "
    "profile fields come back from the read; if a logo is uploaded, its "
    "colour replaces company_color, as in the app. Emails already queued "
    "keep their old signature and send times. Credentials (mailbox "
    "passwords, SMTP, OAuth sign-ins, API keys) cannot be read or changed "
    "here: the user sets those in the app in a browser. For the Sales "
    "Playbook, website auto-fill and team default use tm_playbook."
))
async def tm_settings(update: dict | None = None) -> dict:
    return await _tm_call("tm_settings", update)


@mcp.tool(description=(
    "Do Not Contact. action='list' (default, optional q filter); "
    "action='add' with email or domain (adding an email cancels its pending "
    "sends and takes it out of every campaign; a domain blocks everyone "
    "there); action='remove' with email or domain."
))
async def tm_dnc(action: str = "list", email: str = "", domain: str = "",
                 reason: str = "", q: str = "") -> dict:
    if action == "list":
        return await _tm_call("tm_dnc", None, q)
    return await _tm_call("tm_dnc", {"action": action, "email": email,
                                     "domain": domain, "reason": reason})


# ── connector group A (2026-09-21) begin ──
# ── connector group A end ──


# ── connector group B (2026-09-21) begin ──
@mcp.tool(description=(
    "My Campaign Styles: reusable campaign shapes a new campaign can be "
    "launched from (create_campaign with style_id). action='list' (default) "
    "returns the styles plus the allowed step types and tones. "
    "action='create' with name + steps, exactly what the app's Create a "
    "Campaign Style builder captures: steps=[{type: 'email'|'call'|"
    "'linkedin', delay_days: business days after the previous step (1-30; "
    "ignored on step 1), content: what that step says or should do}], at "
    "most 15, every step needs content; tone 'consultative' (default), "
    "'direct', 'casual' or 'formal'. Or pass description instead of steps "
    "for a free-form style. At launch the AI writes a fresh campaign from "
    "the style; it does not replay the text word for word. action='delete' "
    "with style_id removes one for good (ask the user first)."
))
async def tm_campaign_styles(action: str = "list", name: str = "",
                             steps: list | None = None, tone: str = "consultative",
                             description: str = "", style_id: str = "") -> dict:
    if action == "list":
        return await _tm_call("tm_campaign_styles")
    body: dict = {"action": action, "name": name, "id": style_id, "tone": tone}
    if steps is not None:
        body["steps"] = steps
    if description:
        body["description"] = description
    return await _tm_call("tm_campaign_styles", body)


@mcp.tool(description=(
    "Edit the contact lists on the Contacts page (tm_contacts reads them). "
    "list_name is a saved list's name; blank means the active list the "
    "Contacts page has open. action='add_contact' with contact={email, "
    "first_name, last_name, company, title, phone_mobile, phone_office, "
    "linkedin, city, state}; action='update_contact' with email (who) and "
    "changes={field: new value} using those same fields; "
    "action='delete_contact' with email; action='delete_list' deletes a "
    "saved list for good and needs confirm=true (ask the user first). "
    "Campaigns already running keep the contacts they were given."
))
async def tm_contact_lists(action: str, list_name: str = "", email: str = "",
                           contact: dict | None = None,
                           changes: dict | None = None,
                           confirm: bool = False) -> dict:
    body: dict = {"action": action, "list": list_name, "email": email,
                  "confirm": confirm}
    if contact is not None:
        body["contact"] = contact
    if changes is not None:
        body["changes"] = changes
    return await _tm_call("tm_contact_lists", body)
# ── connector group B end ──


# ── connector group C (2026-09-21) begin ──
@mcp.tool(description=(
    "The AI Prompt page: writes the prompt a user pastes into Claude to run "
    "an outreach job, with the ThriveModal rules built in. Nothing runs or "
    "sends here. action='runs' (default) lists the runs on offer and every "
    "question each one asks (key, options, default, required). "
    "action='build' returns the prompt text: pass run (a run id from "
    "'runs') or prompt_id (a saved prompt, to edit its answers), answers "
    "{question key: value} for anything to change from the defaults, and "
    "optional instructions (extra lines added as steps). A select question "
    "takes only one of its listed options. A required question left blank "
    "is not an error: the prompt asks the user for it (see "
    "still_to_answer). action='save' does the same and also saves it to "
    "Saved Prompts under name (a saved prompt with the same name is "
    "replaced). action='delete' removes the saved prompt prompt_id. "
    "tm_saved_prompts lists the saved ones."
))
async def tm_ai_prompt(action: str = "runs", run: str = "", prompt_id: str = "",
                       answers: dict | None = None,
                       instructions: list | None = None,
                       name: str = "") -> dict:
    body: dict = {"action": action}
    if run:
        body["run"] = run
    if prompt_id:
        body["prompt_id"] = prompt_id
    if answers:
        body["answers"] = answers
    if instructions is not None:
        body["instructions"] = instructions
    if name:
        body["name"] = name
    return await _tm_call("tm_ai_prompt", body)


@mcp.tool(description=(
    "Company Profile page: the Sales Playbook every ThriveModal campaign and "
    "sales asset is written under, plus website auto-fill and team default. "
    "action='get' (default) returns each playbook section (key, label, the "
    "text in force, whether it is the shipped default or empty, whether it "
    "can be improved) and the user's own custom sections. "
    "action='update' with sections={key: text} and/or custom_sections="
    "[{title, body}] (replaces all custom sections) saves them; an empty "
    "section is saved empty and the AI then says nothing on that topic. "
    "action='add_section' with title + body; action='remove_section' with "
    "title. action='restore' puts the shipped text back in the sections "
    "listed in sections=[keys], or in every empty section when none are "
    "listed. action='improve' with section (+ optional text to improve "
    "instead of the saved text) has the AI rewrite it without adding any "
    "fact or figure; it returns the suggestion and saves it only with "
    "apply=true - show the user the rewrite first. Proof and banned-claims "
    "sections cannot be improved. action='switch' with playbook changes the "
    "workspace playbook where the app allows it (switching away from "
    "ThriveModal turns these tools off). action='autofill' with website "
    "reads the company's site and returns the company-profile fields it "
    "found; apply=true saves them. action='team_default' copies the saved "
    "company profile and logo to the whole team (team admins only). Edit "
    "single profile fields with tm_settings."
))
async def tm_playbook(action: str = "get", sections: dict | list | None = None,
                      custom_sections: list | None = None, title: str = "",
                      body: str = "", section: str = "", text: str | None = None,
                      apply: bool = False, playbook: str = "",
                      website: str = "") -> dict:
    req: dict = {"action": action}
    if sections is not None:
        req["sections"] = sections
    if custom_sections is not None:
        req["custom_sections"] = custom_sections
    for k, v in (("title", title), ("body", body), ("section", section),
                 ("playbook", playbook), ("website", website)):
        if v:
            req[k] = v
    if text is not None:
        req["text"] = text
    if apply:
        req["apply"] = True
    return await _tm_call("tm_playbook", req)
# ── connector group C end ──


# ── connector group D (2026-09-21) begin ──
@mcp.tool(description=(
    "The cold-call briefing My Day shows for a campaign's calls: company "
    "overview, HQ and offices, open jobs, recent news and talking points, "
    "from a web search. Pass task_id (a call from tm_my_day) or "
    "campaign_id. Returns the saved one when there is one; refresh=true "
    "writes a fresh one (15-60 seconds)."
))
async def tm_call_briefing(task_id: str = "", campaign_id: str = "",
                           refresh: bool = False) -> dict:
    return await _tm_call("tm_call_briefing", {
        "task_id": task_id, "campaign_id": campaign_id, "refresh": refresh})


@mcp.tool(description=(
    "View and hand-edit a newsletter's issues, and change its settings. "
    "campaign_id from tm_newsletters. action='issues' (default) lists every "
    "issue (sent or not) and the settings; 'get_issue' returns one issue "
    "(issue=n, default the next) with its full HTML body; 'edit_issue' with "
    "issue and subject and/or body (the full HTML, edited from get_issue) "
    "saves it, stops auto-refresh overwriting it and updates emails already "
    "queued for it; issues already sent cannot be edited. 'settings' with no "
    "settings returns them; with settings={...} saves them and rewrites the "
    "next issue in the background. Settings keys: city_life (bool) plus, "
    "for ThriveModal, profiles (bool: 3 sample talent profiles per issue) "
    "and topic (what the issues are about); other workspaces use "
    "spotlights_per_issue (3 or 6) and spotlight_guidance. To have the AI "
    "rewrite an issue instead, use tm_newsletter_issue with refresh=true."
))
async def tm_newsletter_edit(campaign_id: str, action: str = "issues",
                             issue: int = 0, subject: str | None = None,
                             body: str | None = None,
                             settings: dict | None = None) -> dict:
    req: dict = {"campaign_id": campaign_id, "action": action}
    if issue:
        req["issue"] = issue
    if subject is not None:
        req["subject"] = subject
    if body is not None:
        req["body"] = body
    if isinstance(settings, dict):
        req.update({k: v for k, v in settings.items()
                    if k not in ("campaign_id", "action")})
    return await _tm_call("tm_newsletter_edit", req)


@mcp.tool(description=(
    "Edit a PDF already in the Sales Assets library, as the app's PDF "
    "editor does. file is its filename or path from tm_sales_assets. "
    "action='get' (default) returns its content: title, badge, intro, cta "
    "and sections (each {heading, type: paragraph|bullets|table|qa, items}); "
    "'update' with data={any of those} replaces them and re-renders; "
    "'revise' with instruction (e.g. 'make the intro shorter') has the AI "
    "apply it and re-renders. The file keeps its name and link, so "
    "campaigns carrying it send the new version."
))
async def tm_pdf_edit(file: str, action: str = "get", instruction: str = "",
                      data: dict | None = None) -> dict:
    req: dict = {"file": file, "action": action}
    if instruction:
        req["instruction"] = instruction
    if data is not None:
        req["data"] = data
    return _link_pdfs(await _tm_call("tm_pdf_edit", req))
# ── connector group D end ──


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
