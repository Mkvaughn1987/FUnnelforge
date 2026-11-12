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

# Read by Claude when the connector connects. Mike, 2026-11-12: users say
# what they want and Claude builds it; campaign types are offered as a
# multiple-choice menu rather than picked silently.
DD_INSTRUCTIONS = """You are operating DripDrop for the signed-in user. They tell you what they
want; you do it with these tools. Every page of the app has a tool.

BUILDING A CAMPAIGN - follow this order:
1. Offer the campaign types as a numbered multiple-choice menu. Call
   campaign_types and my_campaign_styles first, then show one line per
   option: number, name, length, and who it is best for. Put the user's own
   saved styles at the top of the menu, labeled "(your saved style)", and
   always end with "Custom - your own wording and steps" (template byos).
   Let the user answer with just a number. If what they asked for clearly
   fits one option, say which one you recommend and why, but still show the
   menu so they can choose.
2. Contacts - offer a second numbered menu, "Who should this go to?":
     1) One of your saved contact lists (name them: call contacts, which
        returns every list name, and show each list's size if you can)
     2) People you give me - names + emails typed or pasted, or CSV text
        (save them as a list with import_contacts so they are reusable)
     3) Your team's Arena Sales Contacts - search by company or title with
        sales_contacts action='search'
     4) Find new people with ZoomInfo - only if a ZoomInfo connector is
        available in this chat; bring them in with sales_contacts
        action='zoominfo_drop' or import_contacts
     5) Decide later - build the draft now, add contacts at launch
   Before building, run skip_check on the companies involved and tell the
   user who will be skipped (Current Clients, companies a teammate has in
   a campaign from the last 30 days, Do Not Contact) - never retry them.
   Contacts go on at launch (campaign_action action='launch' with
   contacts=[...] or list_name) or onto a running campaign with
   campaign_contacts. For template findcandidates the recipients are the
   candidates themselves (Pipeline candidates' emails work).
   Then ask only for what is still missing: role(s), location, and any
   candidates to feature.
3. Candidates: users may name Pipeline candidates ("use Vlad Shcheglov").
   Find each one with pipeline action='search' or 'get' (a name, Ref # or
   alias like "Trent K." works) and pass them to create_campaign as
   candidates [{"_pool_id": <id>}]. Every campaign type accepts them. If a
   name matches more than one person, ask which one. Emails show a client
   alias plus Ref #, never the candidate's real name.
4. Wording: if the user gives exact language, use it word for word with
   campaign_edit action='update_step' (subject/body). If they describe a
   tone, write it in that tone and offer to save it as a campaign style.
5. Always create with spec.draft=true first. Show the user every step
   (campaign_get), offer send_preview so they see the real email in their
   own inbox, and revise with campaign_edit until they approve.
6. Launch only after the user clearly says yes: campaign_action
   action='launch' with confirm=true. Launching SENDS REAL EMAIL. Report
   back the schedule and anything the result lists as skipped
   (already_worked, active_client_contacts, invalid_email).

GENERAL RULES:
- Anything that sends email, deletes, cancels, or changes many records at
  once needs the user's explicit yes in this conversation before you pass
  confirm=true. Never assume approval.
- Use the user's own words for subjects and bodies when they give them.
  Never invent statistics, client names, or placements.
- When a tool returns an error, tell the user plainly what it says and what
  you can do instead.
"""


mcp = MCPServer(
    name="dripdrop",
    title="DripDrop",
    description="Run DripDrop from Claude: build and launch campaigns, work the Pipeline, tasks, replies, newsletters and every other page.",
    instructions=DD_INSTRUCTIONS,
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
        "immediately, same as posting to /api/v1/campaigns. Contacts at "
        "Current Clients, at companies a teammate put in a campaign in the "
        "last 30 days, or on anyone's Do Not Contact list are dropped: the "
        "reply says \"skipped\" with a reason when nobody is left, and "
        "\"current_clients\" / \"already_worked\" name who was dropped - "
        "report those, do not retry them. Run skip_check first to avoid "
        "this. For the "
        "`findcandidates` template - the only template that emails "
        "candidates directly instead of companies - describe the opening "
        "(role, client, confidential, location, pay, selling_points, "
        "job_description) instead of company/niche/roles. With "
        "spec.draft=true nothing is queued: the campaign is written and "
        "saved as a draft so you can show the user the emails "
        "(campaign_get), change them (campaign_edit) and launch it with "
        "campaign_action action='launch' once they agree - use this "
        "whenever the user has not already approved the copy."
    )
)
async def create_campaign(spec: dict) -> dict:
    """Args:
    spec: campaign spec matching DripDrop's /api/v1/campaigns body - at
        minimum {"template": <template key>, "company" or "niche": str},
        except for template "findcandidates" (see below). Optional: contacts
        (list of {email, first_name, last_name, company, title, linkedin,
        phone_mobile, phone_office} - for ZoomInfo contacts always include
        both numbers when present, so they stay on file), contacts_csv (raw
        CSV text),
        candidates (list of candidate cards; every template accepts them,
        and fivebythree/fivebyseven pick from the Pipeline when none are
        given - each real person needs "_pool_id" (the
        id from candidates_search) or "name" plus "email" or "phone"
        (optionally "resume_text", "external_id"); people not yet in the
        Pipeline are added. Emails cite them by a stable client alias and
        Ref # (e.g. "Trent K. (Ref #1042)"); real names never reach the
        email. Mark AI-written sample profiles "_synthetic": true), roles, location, industry, website, name,
        industry_category (for company campaigns, always set it: the one
        label below that best describes what THIS company does, judged
        company by company, not from the run's search terms - "Manufacturing",
        "Civil & Engineering", "Heavy Equipment & Rental", "Mechanical
        Contracting", "Electrical Contracting", "Healthcare Construction",
        "Data Center / Mission Critical", "General Contracting",
        "Construction" (a builder that fits none of the construction labels
        above), "Healthcare", "Architecture & Design", "Technology",
        "Logistics & Freight", "Energy", "Accounting & Finance", "Real
        Estate", "Automotive", "Other"), start_date
        (ISO date, or omitted/"auto" for the upcoming Monday), start_time
        (clock time like "8:00 AM" for the first email; omit to keep the
        template's time),
        enroll_newsletter (newsletter name to also enroll contacts into),
        style_id (the id of one of the user's saved styles from
        my_campaign_styles, with template "byos"; company/niche are then
        optional. A style of kind "own" goes out in the user's own words
        and puts any candidates where its {Candidates} spot is),
        fill_ins (dict, for a kind "own" style that lists "fillins" in
        my_campaign_styles: what changes per client, e.g. {"Industry":
        "commercial HVAC", "Competitors": "Trane and Carrier"}. Ask the
        user for each one every time; never reuse the "last" value or
        make one up),
        draft (bool, default false - true saves the campaign as a draft
        and queues nothing; launch it later with campaign_action).

        For template "findcandidates": contacts are the candidates to
        reach (their business emails, with company, title and both phone
        numbers). Describe the opening instead of company/niche/roles:
        role (str, the title), client (str, the hiring company),
        confidential (bool, default true - the emails never name the
        client; false names it), location (str, where the job is), pay
        (str, as the recruiter would say it), selling_points (list of
        strings - why someone would move), job_description (str, optional
        full JD text). Optional cadence: "one_email" (default),
        "two_emails_1day", "three_emails_3days", or "three_emails_1week"
        (days 0, 3 and 7 - the one to use for passive candidates). name
        defaults to "Find Candidates - <role>".
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
        "List DripDrop's built-in campaign templates (blitz, fourbyfour, "
        "fivebyfive, fivebythree, fivebyseven, clientlookalike, talentdrop, "
        "flood, sidequest, fullstream, victorycard, byos, findcandidates) "
        "with a description and best-for "
        "guidance and length for each. Read-only. When a user wants a "
        "campaign, show these to them as a numbered multiple-choice menu "
        "(name, length, best for), with their saved styles from "
        "my_campaign_styles at the top and 'Custom - your own wording' last, "
        "and let them pick by number before calling create_campaign."
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
        "the app). Read-only, tenant-scoped to the caller. A style with "
        "kind \"own\" was made with Create my own campaign: its steps are "
        "the user's own emails, call scripts and LinkedIn messages. Launch "
        "any style with create_campaign, template \"byos\" and its id as "
        "style_id; an own style then sends the user's words as written "
        "(only steps they marked \"polish\" are lightly tidied), so do not "
        "rewrite or summarise them. An own style with \"fillins\" is "
        "reused across clients: ask the user for each fill-in (its "
        "\"last\" value is only a reminder of the previous run) and pass "
        "them to create_campaign as fill_ins, keyed by name."
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
        "Shared Arena Contacts: the people the user's whole team has already "
        "reached at a company, from every campaign and uploaded list, all "
        "time. Pass a company name or email domain. Anyone who replied not "
        "interested or is on a Do Not Contact list is already left out, and "
        "people who replied are flagged. It also says whether the company is "
        "off limits: verdict \"skip\" with current_client (a Current Client) "
        "or already_worked (a teammate's campaign in the last 30 days) means "
        "drop the company and pull nobody. CHECK THIS BEFORE ZOOMINFO: use these "
        "contacts first and only pull from ZoomInfo for companies that come "
        "back empty or need more people. Read-only, team-scoped."
    )
)
async def team_contacts(company_or_domain: str, limit: int = 50) -> dict:
    """Args:
    company_or_domain: company name ("Galloway") or email domain ("gallowayus.com").
    limit: max people per company (default 50, max 200).
    """
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.team_contacts(company_or_domain, limit)
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


@mcp.tool(
    description=(
        "Skip check: pass every company on your target list at once (names "
        "or email domains) and get back which to drop before any research "
        "or ZoomInfo pull - Current Clients, and companies anyone on the "
        "team put in an outbound campaign in the last 30 days (cancelled "
        "ones too), with the rep, campaign and the date it opens again. "
        "Run it right after you have a list of companies. DripDrop refuses "
        "to launch at these companies anyway, so skipping them early saves "
        "credits. Read-only, team-scoped."
    )
)
async def skip_check(companies: list[str]) -> dict:
    """Args:
    companies: company names ("Galloway & Company") or email domains
        ("gallowayus.com"), up to 300.
    """
    email = _current_email()
    try:
        client = DripDropClient(DATA_DIR, email)
        return await client.skip_check(companies)
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


# ── DD connector B: the DripDrop-only pages ──────────────────────────────
# One tool per page, each mirroring that page's buttons through
# /api/v1/dd/<page>. Anything destructive refuses without confirm=true.

_DDB_APP_ORIGIN = os.environ.get("DRIPDROP_APP_ORIGIN", "https://dripdripdrop.ai").rstrip("/")


async def _ddb_call(method: str, body: dict) -> dict:
    try:
        client = DripDropClient(DATA_DIR, _current_email())
        return await getattr(client, method)(body)
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


def _ddb_body(action: str, **fields) -> dict:
    """The request body: the action plus every field the caller set."""
    body = {"action": action}
    for k, v in fields.items():
        if v is None or v == "" or v == [] or v == {}:
            continue
        body[k] = v
    return body


def _ddb_link_pdfs(res: dict) -> dict:
    """Turn the app's /pdfs/ paths into links the user can open (in a
    browser where they are signed in to DripDrop)."""
    for r in res.get("assets") or [] if isinstance(res, dict) else []:
        if isinstance(r, dict) and str(r.get("path", "")).startswith("/pdfs/"):
            r["url"] = _DDB_APP_ORIGIN + r["path"]
    return res


@mcp.tool(description=(
    "Pipeline (the /ats candidate database, Arena accounts only). Mirrors the "
    "Pipeline page. action: "
    "'search' (default; q = keywords, a Ref # or a name; optional location "
    "'City, ST' + radius_mi (default 50), added_within_days, mine=true for only "
    "the user's own uploads, strict=true for every-word matching); "
    "'jd_match' (jd_text = a job description, AI picks the search terms; "
    "location/radius_mi optional); 'find' (q = part of a name or email, like the "
    "top-bar Quick Find); 'get' (candidate_id = Ref #: the full record with "
    "contact details, summary, recruiter notes and resume text); 'save_notes' "
    "(candidate_id + notes: REPLACES the Recruiter Notes, so get first and send "
    "the whole text); 'dashboard' (the user's pool by industry, state and role, "
    "recently added); 'pools' (the team's top 20 role x state pools) and 'pool' "
    "(role + state from pools); 'tearsheets', 'tearsheet' (tearsheet_id: its "
    "candidates), 'tearsheet_create' (name; with query it is a smart saved "
    "search, otherwise a hand-picked list, optionally seeded with candidate_ids), "
    "'tearsheet_add' / 'tearsheet_remove' (tearsheet_id + candidate_ids), "
    "'tearsheet_delete' (tearsheet_id, confirm=true); 'jobs', 'job_add' (title, "
    "company, location, jd_text), 'job_matches' (job_id), 'job_delete' (job_id, "
    "confirm=true); 'companies' (companies reached in the user's campaigns, with "
    "contacts; q filters) and 'company_insight' (company: a short web-researched "
    "summary, cached). The page has no status or tag editor, so neither does this. "
    "To pitch candidates use create_campaign with their Ref #s; to load resumes use "
    "import_candidates / import_candidate_records."
))
async def pipeline(action: str = "search", q: str = "", candidate_id: str = "",
                   candidate_ids: list | None = None, notes: str | None = None,
                   location: str = "", radius_mi: int = 0, added_within_days: int = 0,
                   mine: bool = False, strict: bool = False, jd_text: str = "",
                   role: str = "", state: str = "", tearsheet_id: int = 0,
                   name: str = "", query: str = "", job_id: int = 0, title: str = "",
                   company: str = "", refresh: bool = False, limit: int = 25,
                   confirm: bool = False) -> dict:
    body = _ddb_body(action, q=q, candidate_id=candidate_id, candidate_ids=candidate_ids,
                     location=location, radius_mi=radius_mi or None,
                     added_within_days=added_within_days or None, mine=mine or None,
                     strict=strict or None, jd_text=jd_text, role=role, state=state,
                     tearsheet_id=tearsheet_id or None, name=name, query=query,
                     job_id=job_id or None, title=title, company=company,
                     refresh=refresh or None, limit=limit, confirm=confirm or None)
    if notes is not None:
        body["notes"] = notes
    return await _ddb_call("pipeline", body)


@mcp.tool(description=(
    "My Top 10: the user's private list of ten target companies plus ten backups, "
    "each with new job postings, hiring signals, status and any teammate campaign "
    "there. Mirrors the My Top 10 page. action: 'view' (default; fills an empty "
    "list from the user's own outreach the first time and starts a background "
    "re-check of stale postings/signals); 'add' (company = name or website; it is "
    "looked up on the web first and saved under its real name - if the check "
    "cannot confirm it you get the check back and can retry or pass "
    "add_as_typed=true; to='backup' adds to the backups, default is the top 10, "
    "which bumps the last one to backups; optional roles, notes); 'update' "
    "(company_id + any of name, website, city, state, industry, roles, status, "
    "notes); 'remove' (company_id, confirm=true); 'move' (company_id, direction "
    "up/down); 'promote' (backup -> top 10) / 'demote' (company_id); 'set_focus' "
    "(market e.g. 'Denver, CO', industry) then 'fill' to top the list up from "
    "the user's outreach in that focus; 'recheck' (company_ids, default all ten: "
    "postings + signals refresh in the background, view again in a minute or "
    "two); 'check_pipeline' (company_ids, default all ten: how many Pipeline "
    "candidates fit each company's newest posting, Arena accounts only). "
    "company_id also accepts the company's name."
))
async def top10(action: str = "view", company: str = "", company_id: str = "",
                company_ids: list | None = None, to: str = "", add_as_typed: bool = False,
                verify: bool = True, name: str = "", website: str = "", city: str = "",
                state: str = "", industry: str = "", roles: str = "", status: str = "",
                notes: str | None = None, direction: str = "", market: str = "",
                confirm: bool = False) -> dict:
    body = _ddb_body(action, company=company, company_id=company_id,
                     company_ids=company_ids, to=to, add_as_typed=add_as_typed or None,
                     name=name, website=website, city=city, state=state,
                     industry=industry, roles=roles, status=status, direction=direction,
                     market=market, confirm=confirm or None)
    if not verify:
        body["verify"] = False
    if notes is not None:
        body["notes"] = notes
    return await _ddb_call("top10", body)


@mcp.tool(description=(
    "AI Prompts page: the job cards (find new business by hiring signals, client "
    "look-alikes, MPC, slate, find candidates, LinkedIn adds, resume sweep, Indeed "
    "Interested, ZoomInfo help, anything else) and the questions each asks. "
    "action: 'runs' (default: every card with its questions, options and "
    "defaults); 'build' (run = a card id from runs, answers = {question key: "
    "answer}, optional instructions = extra lines; or prompt_id to reuse a saved "
    "one) returns the finished brief, exactly the text the page would hand you; "
    "'save' (same as build plus name: keeps it under Saved Prompts); 'saved' "
    "(list them); 'delete' (prompt_id, confirm=true). Building does not send "
    "anything. The brief is your instructions: carry it out with the other "
    "DripDrop tools. Whatever it launches through create_campaign SENDS REAL "
    "EMAIL, so confirm the campaigns with the user before launching them."
))
async def ai_prompts(action: str = "runs", run: str = "", answers: dict | None = None,
                     instructions: list | None = None, prompt_id: str = "",
                     name: str = "", confirm: bool = False) -> dict:
    return await _ddb_call("ai_prompts", _ddb_body(
        action, run=run, answers=answers, instructions=instructions,
        prompt_id=prompt_id, name=name, confirm=confirm or None))


@mcp.tool(description=(
    "Arena Sales Contacts: the team's contact bank - everyone any teammate has "
    "reached in a campaign or uploaded list, grouped by company (people who said "
    "no or are on a Do Not Contact list are left out). Mirrors that page and its "
    "ZoomInfo Drop panel. action: 'search' (default; filters q (company, person, "
    "title, email or city), rep (teammate email), state, industry, "
    "replied_only=true; sort newest/oldest/name/name_desc/person/person_desc/most; "
    "limit, offset) returns companies with their people plus the filter counts; "
    "'zoominfo_drop' saves ZoomInfo people into the user's 'ZoomInfo Archive' "
    "contact list so they join the bank and nobody pays for them again - pass "
    "records (a list of people, ZoomInfo field names are fine: First Name, Last "
    "Name, Email, Job Title, Company, Direct Phone, Mobile Phone, LinkedIn, City, "
    "State, ...) or csv_text (a ZoomInfo CSV export) - and returns the receipt "
    "(added, merged, new to the team); 'zoominfo_progress' (the user's archive and "
    "who on the team has dropped files). For one company's people plus its skip "
    "verdict use team_contacts."
))
async def sales_contacts(action: str = "search", q: str = "", rep: str = "",
                         state: str = "", industry: str = "", replied_only: bool = False,
                         sort: str = "", limit: int = 25, offset: int = 0,
                         records: list | None = None, csv_text: str = "",
                         filename: str = "") -> dict:
    return await _ddb_call("sales_contacts", _ddb_body(
        action, q=q, rep=rep, state=state, industry=industry,
        replied_only=replied_only or None, sort=sort, limit=limit, offset=offset or None,
        records=records, csv_text=csv_text, filename=filename))


@mcp.tool(description=(
    "Current Clients: the team's list of client companies, by email domain. "
    "Nobody at these domains is ever put in a new campaign (skip_check and "
    "create_campaign both honour it). Mirrors the Current Clients page. action: "
    "'list' (default; q filters); 'add' (client_name + domain, optional website, "
    "location, notes - or clients = a list of those to add several); 'update' "
    "(client_id or domain, then client_name, website, location or notes); "
    "'remove' (client_id or domain, confirm=true: campaigns can reach that "
    "company again, so check with the user first)."
))
async def clients(action: str = "list", client_name: str = "", domain: str = "",
                  website: str | None = None, location: str | None = None,
                  notes: str | None = None, client_id: str = "",
                  clients: list | None = None, q: str = "",
                  confirm: bool = False) -> dict:
    body = _ddb_body(action, client_name=client_name, domain=domain, client_id=client_id,
                     clients=clients, q=q, confirm=confirm or None)
    for k, v in (("website", website), ("location", location), ("notes", notes)):
        if v is not None:
            body[k] = v
    return await _ddb_call("clients", body)


@mcp.tool(description=(
    "Arena Running Campaigns: every company anyone on the team has put in an "
    "outbound campaign in the last 30 days (cancelled included), with each "
    "campaign's rep, type, start date and the date the company opens up again. "
    "New campaigns skip these companies. Mirrors that page and its filters: rep "
    "(teammate email), state, industry, campaign_type (a template key such as "
    "fourbyfour), status running/cancelled, q (company, rep, campaign, geography "
    "or roles), sort newest/opens/name, limit. action 'list' (default) or "
    "'sort_industries' (the page's 'Sort them with AI' button: files companies "
    "with no industry into one). For a yes/no on specific companies use skip_check."
))
async def running_campaigns(action: str = "list", rep: str = "", state: str = "",
                            industry: str = "", campaign_type: str = "", status: str = "",
                            q: str = "", sort: str = "", limit: int = 50) -> dict:
    return await _ddb_call("running_campaigns", _ddb_body(
        action, rep=rep, state=state, industry=industry, campaign_type=campaign_type,
        status=status, q=q, sort=sort, limit=limit))


@mcp.tool(description=(
    "Sales Assets: branded PDFs to attach to outreach. action 'list' (default) "
    "returns the user's PDF library newest first, each with a link, and the kinds "
    "available. action 'generate' builds up to 3 at once, like the page: kinds "
    "(any of market_pulse, interview_guide, salary_guide, scorecard, "
    "why_staffing), company (or the market), role, location - all required - "
    "plus optional industry, website, experience_level. Each PDF researches the "
    "web, so a batch takes a few minutes. Returns each PDF with its link (opens "
    "where the user is signed in to DripDrop). The page's Create Your Own custom "
    "PDF is not available here."
))
async def sales_assets(action: str = "list", kinds: list | None = None,
                       company: str = "", role: str = "", location: str = "",
                       industry: str = "", website: str = "",
                       experience_level: str = "") -> dict:
    return _ddb_link_pdfs(await _ddb_call("sales_assets", _ddb_body(
        action, kinds=kinds, company=company, role=role, location=location,
        industry=industry, website=website, experience_level=experience_level)))


@mcp.tool(description=(
    "Home page summary: overdue tasks, tasks today and tomorrow, active "
    "campaigns (sent, pending, next send), reply count and the latest replies, "
    "emails queued, setup status and (Arena accounts) Pipeline size. Read-only. "
    "Use it to answer 'how am I doing' or 'what's on today'; the task, reply "
    "and campaign tools have the detail."
))
async def home() -> dict:
    return await _ddb_call("home", {"action": "get"})


@mcp.tool(description=(
    "The user's My Profile, Team, Signature and Timezone settings. action 'get' "
    "(default) returns all of them: name, phone, company profile (read-only when "
    "it comes from the team's profile), email signature, timezone, newsletter "
    "note, team members and team branding. action 'update' changes any of: name, "
    "phone, company (an object of company_name, company_website, "
    "company_industry, company_description, company_phone, company_linkedin, "
    "company_address, company_tagline, company_color), signature (the full "
    "email signature text, replaces it), timezone (IANA, e.g. America/Chicago - "
    "every send time is in it), newsletter_note. Team admins only: "
    "'team_branding' (company_name, company_color, company_website, "
    "company_tagline for the whole team) and 'set_admin' (email, admin "
    "true/false, confirm=true). Mailboxes, AI setup and Do Not Contact are "
    "separate settings tools."
))
async def profile(action: str = "get", name: str | None = None, phone: str | None = None,
                  company: dict | None = None, signature: str | None = None,
                  timezone: str | None = None, newsletter_note: str | None = None,
                  company_name: str | None = None, company_color: str | None = None,
                  company_website: str | None = None, company_tagline: str | None = None,
                  email: str = "", admin: bool | None = None,
                  confirm: bool = False) -> dict:
    body = _ddb_body(action, email=email, confirm=confirm or None)
    for k, v in (("name", name), ("phone", phone), ("company", company),
                 ("signature", signature), ("timezone", timezone),
                 ("newsletter_note", newsletter_note), ("company_name", company_name),
                 ("company_color", company_color), ("company_website", company_website),
                 ("company_tagline", company_tagline), ("admin", admin)):
        if v is not None:
            body[k] = v
    return await _ddb_call("profile", body)


@mcp.tool(
    description=(
        "List the Sales Campaign runs the DripDrop user has queued for you "
        "from the app's Sales Campaign page. DripDrop cannot do the sourcing "
        "itself - its ZoomInfo seat is entitled for this MCP surface, not the "
        "REST API - so it queues the target here. Each run comes back with "
        "the full target (industry, geography, roles, size band, avoid list), "
        "the already_worked dedupe keys, the contact targets, and an "
        "'instructions' field that is the literal brief: follow it. Calling "
        "it also queues retry runs for companies an earlier run parked while "
        "ZoomInfo was out of credits, once their two-day wait is up; a retry "
        "run's brief says so and only asks for contacts."
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
        "create_campaign for these companies and do not send anything. "
        "For an AI Prompts job (run_id starting 'job_') it is different: "
        "claim it with {\"status\": \"working\"}, do the job exactly as its "
        "instructions say, then post {\"status\": \"done\", \"result\": "
        "\"...\"} or {\"status\": \"error\", \"error\": \"...\"}."
    )
)
async def sales_run_update(run_id: str, update: dict) -> dict:
    """Args:
    run_id: the run_id from sales_runs_pending.
    update: any of -
        status: "working" (you picked it up), "sourced" (done - starts the
            build), "error" (with an "error" string saying what stopped you),
            "cancelled". An AI Prompts job ("job_" run_id) takes "working",
            "done", "error" or "cancelled", never "sourced".
        result: AI Prompts jobs only - with status "done", what you did in
            plain words: every company, contact, campaign or file you made
            or changed, and every judgement call. The user reads it on the
            AI Prompts page.
        companies: list of the companies you kept, each
            {"company": str, "state": str, "role": str, "why": str,
             "source": str, "zi_total": int,
             "contacts": [{"email", "first_name", "last_name", "title",
                           "linkedin", "state", "phone_mobile",
                           "phone_office", "paid_by"}]}.
            paid_by is "bulk" (connector Bulk Credits) or "seat" (the
            user's own ZoomInfo Talent credits). phone_mobile is the
            ZoomInfo mobile and phone_office the work line - send both
            whenever ZoomInfo has them so they stay on file.
            Contacts are cleaned and deduped on arrival; one with no usable
            email is dropped with a reason rather than silently kept. A
            company below the contact floor is skipped at build time.
        reserves: ranked reserves, same shape, each with its demerit.
        dropped: what you dropped and why.
        parked: companies you could not get contacts for because both
            ZoomInfo credit pools were out - same shape as a company, plus
            "waiting_reason" (the exact error). DripDrop retries them in two
            days on its own. Never put these in companies or dropped.
        credits: one line on what each credit pool did, e.g. "Bulk: 34
            reveals, then Limit exceeded. Seat: 41 reveals."
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


# -- DD connector A: shared pages (2026-11-12) ------------------------------
# Today's Tasks, Replies, Contacts, campaign contacts / lifecycle / editing,
# send preview, Newsletters, Outreach Analytics, Settings, the sending inbox,
# Do Not Contact and My Campaign Styles. Each tool is one page's buttons.


async def _conn_a_call(method: str, *args) -> dict:
    try:
        client = DripDropClient(DATA_DIR, _current_email())
        return await getattr(client, method)(*args)
    except NoApiKeyError as e:
        return {"error": str(e)}
    except DripDropApiError as e:
        return {"error": str(e.body), "status_code": e.status_code}


@mcp.tool(description=(
    "Today's Tasks page: the calls, LinkedIn touches and manual tasks due "
    "today from active campaigns (plus up to a week of overdue ones, "
    "flagged overdue), with the contact's phones, LinkedIn, the call "
    "script, the campaign and its campaign_id. Pass date=YYYY-MM-DD for "
    "another day. Tick one off with task_done; get the cold-call briefing "
    "for a call with call_briefing. Read-only."
))
async def my_day(date: str = "") -> dict:
    return await _conn_a_call("my_day", date)


@mcp.tool(description=(
    "Mark Today's Tasks done, exactly like the buttons on the page. One "
    "task: task_id; several: task_ids (ids from my_day). result: 'done' "
    "(a task), 'connected' (spoke to them / LinkedIn sent), 'vm' (left a "
    "voicemail) or 'skipped' (default 'done'). undo=true puts them back. "
    "The page's bulk buttons: all_overdue=true ('Mark all overdue as "
    "done'), or campaign='<name or campaign_id>' and/or channel='call'|"
    "'li'|'task' ('Mark all N done'), for today unless date=YYYY-MM-DD. "
    "Bulk marks give calls 'vm', LinkedIn 'connected' and tasks 'done' "
    "unless result is set, and need confirm=true: say how many tasks it "
    "will clear and ask the user first."
))
async def task_done(task_id: str = "", result: str = "", undo: bool = False,
                    task_ids: list | None = None, all_overdue: bool = False,
                    campaign: str = "", channel: str = "", date: str = "",
                    confirm: bool = False) -> dict:
    body: dict = {"task_id": task_id, "result": result, "undo": undo,
                  "all_overdue": all_overdue, "campaign": campaign,
                  "channel": channel, "date": date, "confirm": confirm}
    if task_ids:
        body["task_ids"] = task_ids
    return await _conn_a_call("task_done", body)


@mcp.tool(description=(
    "The cold-call briefing Today's Tasks shows above a campaign's calls: "
    "company overview, HQ and offices, open jobs, recent news and talking "
    "points, from a web search. Pass task_id (a call from my_day) or "
    "campaign_id (from campaigns_list). Returns the saved one when there is "
    "one; refresh=true writes a fresh one (the card's Refresh, 15-60 "
    "seconds). Sends nothing."
))
async def call_briefing(task_id: str = "", campaign_id: str = "",
                        refresh: bool = False) -> dict:
    return await _conn_a_call("call_briefing", {
        "task_id": task_id, "campaign_id": campaign_id, "refresh": refresh})


@mcp.tool(description=(
    "Replies page: everyone who wrote back to a campaign, with their "
    "message. action='list' (default) lists them; 'scan' is Scan Now (re-"
    "reads the user's inbox for new replies; the app also scans every few "
    "minutes); 'draft' with email is Draft Reply (an AI-suggested answer to "
    "that reply); 'followed_up' with email is 'I Responded' (marks it "
    "handled); 'dismiss' with email removes a false positive from the list. "
    "Nothing here sends email: the user answers from their own mailbox, "
    "then mark it followed_up."
))
async def replies(action: str = "list", email: str = "") -> dict:
    return await _conn_a_call("replies", action, email)


@mcp.tool(description=(
    "Contacts page: search the contacts in one saved list by name (blank = "
    "the list the Contacts page has open), filtered by q against name, "
    "email, company and title. Also returns every saved list's name, for "
    "campaign_contacts, campaign_action launch or create_campaign. Edit "
    "lists with contact_lists; save new ones with import_contacts. Read-only."
))
async def contacts(list_name: str = "", q: str = "", limit: int = 50) -> dict:
    return await _conn_a_call("contacts", list_name, q, limit)


@mcp.tool(description=(
    "Save contacts as a named list on the Contacts page (what Import New "
    "Contact List does with a CSV). contacts=[{email, first_name, "
    "last_name, company, title, phone_mobile, phone_office, linkedin, city, "
    "state}] (ZoomInfo-style camelCase keys are understood too); list_name "
    "is the list to save into. If the list exists the contacts are merged "
    "in: a known email is enriched (a blank field never erases a stored "
    "one), a new one is added. Nobody is emailed; enrol the list with "
    "campaign_contacts or create_campaign."
))
async def import_contacts(contacts: list, list_name: str) -> dict:
    return await _conn_a_call("import_contacts", contacts, list_name)


@mcp.tool(description=(
    "Edit the contact lists on the Contacts page (contacts reads them). "
    "list_name is a saved list's name; blank means the list the Contacts "
    "page has open. action='add_contact' with contact={email, first_name, "
    "last_name, company, title, phone_mobile, phone_office, linkedin, city, "
    "state}; action='update_contact' with email (who) and changes={field: "
    "new value} using those same fields; action='delete_contact' with "
    "email; action='delete_list' deletes a saved list permanently and needs "
    "confirm=true (ask the user first). Campaigns already running keep the "
    "contacts they were given."
))
async def contact_lists(action: str, list_name: str = "", email: str = "",
                        contact: dict | None = None,
                        changes: dict | None = None,
                        confirm: bool = False) -> dict:
    body: dict = {"action": action, "list": list_name, "email": email,
                  "confirm": confirm}
    if contact is not None:
        body["contact"] = contact
    if changes is not None:
        body["changes"] = changes
    return await _conn_a_call("contact_lists", body)


@mcp.tool(description=(
    "Add contacts to an EXISTING running campaign or newsletter (the "
    "campaign card's '+ Add Contacts'), or take one out. action='add' with "
    "contacts=[{email, first_name, last_name, company, title, ...}] or "
    "list_name='<saved list from contacts>' queues their emails starting "
    "today: this SENDS REAL EMAIL, so tell the user who and how many, ask, "
    "then pass confirm=true. Do Not Contact, past repliers and Current "
    "Clients are skipped exactly as in the app. action='remove' with email "
    "stops that person's pending emails in this campaign (no confirm "
    "needed). campaign_id from campaigns_list or newsletters."
))
async def campaign_contacts(campaign_id: str, action: str = "add",
                            contacts: list | None = None,
                            list_name: str = "", email: str = "",
                            confirm: bool = False) -> dict:
    body: dict = {"campaign_id": campaign_id, "action": action, "confirm": confirm}
    if contacts is not None:
        body["contacts"] = contacts
    if list_name:
        body["list"] = list_name
    if email:
        body["email"] = email
    return await _conn_a_call("campaign_contacts", body)


@mcp.tool(description=(
    "Run a campaign-level action, as the campaign page's buttons do "
    "(campaign_id from campaigns_list). action: 'cancel' (stops every "
    "pending email; needs confirm=true, ask first); 'resume' (re-queues "
    "everything not yet sent; nothing already sent goes twice, but it does "
    "restart sending, so check with the user); 'retry_failed' (reschedules "
    "failed sends); 'delete' (permanent; needs confirm=true, ask the user "
    "first); 'duplicate' (a copy with no contacts that has not launched; "
    "returns its campaign_id); 'launch' (queues a draft from "
    "create_campaign draft=true, or a duplicate, and SENDS REAL EMAIL: show "
    "the user the steps (campaign_get) and who it goes to, ask, then pass "
    "confirm=true; start_date YYYY-MM-DD, today or later, default today; "
    "optional name, contacts=[{email, first_name, ...}] or list_name to set "
    "who it goes to, enroll_newsletter to also enrol them in a newsletter. "
    "If some contacts work at the team's Current Clients the launch is "
    "refused with the list; ask the user and pass active_clients='skip' or "
    "'send_all'); 'graduate_responders' (the Contacts tab's 'Graduate to "
    "Slow Drip': enrols everyone who replied or was removed into the "
    "newsletter newsletter_id from newsletters, or only the contact given "
    "as email; their newsletter emails start going out)."
))
async def campaign_action(campaign_id: str, action: str, confirm: bool = False,
                          start_date: str = "", name: str = "",
                          contacts: list | None = None, list_name: str = "",
                          active_clients: str = "",
                          enroll_newsletter: str = "",
                          newsletter_id: str = "", email: str = "") -> dict:
    body: dict = {"campaign_id": campaign_id, "action": action,
                  "confirm": confirm}
    for k, v in (("start_date", start_date), ("name", name),
                 ("list", list_name), ("active_clients", active_clients),
                 ("enroll_newsletter", enroll_newsletter),
                 ("newsletter_id", newsletter_id), ("email", email)):
        if v:
            body[k] = v
    if contacts is not None:
        body["contacts"] = contacts
    return await _conn_a_call("campaign_action", body)


@mcp.tool(description=(
    "Edit a campaign's steps, as the campaign editor does. Steps are "
    "1-based, as campaign_get numbers them. action: 'update_step' (step + "
    "any of subject, body (HTML, email steps), note (the script of a call, "
    "LinkedIn or task step), delay_days (days after the previous step), "
    "send_time ('9:00 AM', quarter hours), send_date (YYYY-MM-DD, '' to "
    "clear; later dated steps move with it)); 'add_step' (step_type email|"
    "call|linkedin|task|sms, position = where it lands, default last, plus "
    "optional subject/body/note/delay_days/send_time); 'delete_step' (step); "
    "'move_step' (step, to_position); 'rename' (name; only before launch); "
    "'ai_rewrite' (Rewrite with AI: step + instruction such as 'make it "
    "shorter'; returns the rewritten body, apply=true saves it, "
    "remember=true also adds the instruction to the user's AI style "
    "guide); 'remember_style' (step + edited_body, and original_body if the "
    "step already holds the edit: the AI learns writing rules from the "
    "user's edit for every future email; apply=true also saves "
    "edited_body); 'remove_attachment' (step + attachment file name). If "
    "the campaign is running, its pending emails are re-queued to match "
    "(nothing already sent goes twice) and the result says how many "
    "changed, so confirm edits to a running campaign with the user first. "
    "Steps cannot be added, removed or reordered after a campaign has sent "
    "email: duplicate it with campaign_action instead."
))
async def campaign_edit(campaign_id: str, action: str, step: int = 0,
                        subject: str | None = None, body: str | None = None,
                        note: str | None = None,
                        delay_days: int | None = None, send_time: str = "",
                        send_date: str | None = None,
                        step_type: str = "email", position: int = 0,
                        to_position: int = 0, name: str = "",
                        instruction: str = "", apply: bool = False,
                        remember: bool = False,
                        original_body: str | None = None,
                        edited_body: str | None = None,
                        attachment: str = "") -> dict:
    req: dict = {"campaign_id": campaign_id, "action": action,
                 "apply": apply, "remember": remember}
    for k, v in (("step", step), ("position", position),
                 ("to_position", to_position), ("send_time", send_time),
                 ("name", name), ("instruction", instruction),
                 ("attachment", attachment)):
        if v:
            req[k] = v
    for k, v in (("subject", subject), ("body", body), ("note", note),
                 ("delay_days", delay_days), ("send_date", send_date),
                 ("original_body", original_body),
                 ("edited_body", edited_body)):
        if v is not None:
            req[k] = v
    if action == "add_step":
        req["type"] = step_type
    return await _conn_a_call("campaign_edit", req)


@mcp.tool(description=(
    "Send one email step of a campaign to the user's OWN inbox as a test "
    "(the editor's Send Test), merged with their own name and carrying its "
    "attachments; the subject is marked [PREVIEW]. Only the user receives "
    "it. step is 1-based, as campaign_get numbers the steps."
))
async def send_preview(campaign_id: str, step: int = 1) -> dict:
    return await _conn_a_call("send_preview", {"campaign_id": campaign_id, "step": step})


@mcp.tool(description=(
    "Newsletters page: the monthly newsletters (Slow Drips) with contacts, "
    "next issue and whether it is written yet, plus the sectors (industry "
    "keys with their niches) and styles a new one can use. campaign_id here "
    "feeds newsletter_issue, newsletter_edit, campaign_contacts (to enrol "
    "people) and campaign_action graduate_responders. Read-only."
))
async def newsletters() -> dict:
    return await _conn_a_call("newsletters")


@mcp.tool(description=(
    "Create a monthly newsletter, as the Newsletters page's Create dialog "
    "does. sector is a key from newsletters (e.g. 'construction'); niche "
    "optional (one of that sector's niches or free text); region is "
    "required (e.g. 'Denver, CO'); start_date YYYY-MM-DD (default the next "
    "first Thursday), then the same day each month; count = months "
    "(default 12); time ('9:00 AM'); style 'j_way' (organic, text only; "
    "the default) or 'full_send' (with pictures); spotlights_per_issue 3 or "
    "6 candidate spotlights, spotlight_guidance (who to feature); "
    "city_life (full_send only). The first issue is written in the "
    "background; nobody is enrolled, so nothing sends until people are "
    "added with campaign_contacts."
))
async def newsletter_create(name: str, sector: str, region: str, niche: str = "",
                            start_date: str = "", count: int = 12,
                            time: str = "9:00 AM", style: str = "j_way",
                            spotlights_per_issue: int = 3,
                            spotlight_guidance: str = "",
                            city_life: bool = True) -> dict:
    return await _conn_a_call("newsletter_create", {
        "name": name, "sector": sector, "region": region, "niche": niche,
        "start_date": start_date, "count": count, "time": time,
        "style": style, "spotlights_per_issue": spotlights_per_issue,
        "spotlight_guidance": spotlight_guidance, "city_life": city_life})


@mcp.tool(description=(
    "Write a newsletter's next issue now and return its subject and text; "
    "refresh=true rewrites one already written (the card's Refresh Next "
    "Email). Emails already queued for that issue get the new copy, and it "
    "goes out on its scheduled date to everyone enrolled. Takes a minute "
    "or two."
))
async def newsletter_issue(campaign_id: str, refresh: bool = False) -> dict:
    return await _conn_a_call("newsletter_issue",
                              {"campaign_id": campaign_id, "refresh": refresh})


@mcp.tool(description=(
    "View and hand-edit a newsletter's issues, and change its settings "
    "(the card's View / Edit and Settings). campaign_id from newsletters. "
    "action='issues' (default) lists every issue (sent or not) and the "
    "settings; 'get_issue' returns one issue (issue=n, default the next) "
    "with its full HTML body; 'edit_issue' with issue and subject and/or "
    "body (the full HTML, edited from get_issue) saves it, stops "
    "auto-refresh overwriting it and updates emails already queued for it; "
    "issues already sent cannot be edited. 'settings' with no settings "
    "returns them; with settings={spotlights_per_issue: 3|6, "
    "spotlight_guidance: '<who to feature>', city_life: bool (Full style "
    "only)} saves them and rewrites the next issue in the background. To "
    "have the AI rewrite an issue instead, use newsletter_issue refresh=true."
))
async def newsletter_edit(campaign_id: str, action: str = "issues",
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
    return await _conn_a_call("newsletter_edit", req)


@mcp.tool(description=(
    "Outreach Analytics page: emails sent, pending, failed, people reached, "
    "replies and reply rate (replies / people reached), opt-outs and "
    "bounces - totals, then one row per campaign type (Arena 4x4, 5x5, "
    "Newsletters...) with each email in the sequence and the campaigns run "
    "as that type. days=N limits to the last N days (default all time); "
    "campaign='<name or campaign_id>' adds that campaign's per-email table "
    "with who was sent each email. There is NO open or click tracking: do "
    "not report or infer opens or clicks. Read-only."
))
async def analytics(days: int = 0, campaign: str = "") -> dict:
    return await _conn_a_call("analytics", days, campaign)


@mcp.tool(description=(
    "Settings: My Profile, Signature, Timezone and Email & AI Setup. With "
    "no update, returns the company profile, email signature, timezone, the "
    "user's own name and phone, the newsletter personal note, the AI "
    "writing style guide, the daily send limit, whether the company profile "
    "is set by the team owner, and whether the user is a team admin. update "
    "may hold any of {'profile': {<field>: value}, 'signature': '<text>', "
    "'timezone': 'America/Denver', 'user': {'name', 'phone'}, "
    "'newsletter_note': '<text>', 'ai_style_guide': '<one rule per line>', "
    "'daily_send_limit': 5-500, 'restore_page_guides': true}. The allowed "
    "profile fields come back from the read; a teammate cannot change a "
    "profile the team owner sets, and the owner's change updates the "
    "team's. Emails already queued keep their old signature and send "
    "times. Credentials (mailbox sign-ins, SMTP, API keys) cannot be read "
    "or changed here: the user sets those in the app."
))
async def settings(update: dict | None = None) -> dict:
    return await _conn_a_call("settings", update)


@mcp.tool(description=(
    "The sending inbox (Email & AI Setup): which inbox is connected "
    "(provider microsoft / google / smtp / sendgrid / brevo, and its "
    "address), the daily send limit, how many emails went out today and "
    "how many may still go today. Check remaining_today before promising a "
    "send volume. If sender.connected is false nothing can send; the user "
    "connects an inbox in the app (it is a sign-in, not something this "
    "connector can do). Change the daily limit with settings. Read-only."
))
async def mailboxes() -> dict:
    return await _conn_a_call("mailboxes")


@mcp.tool(description=(
    "Do Not Contact page. action='list' (default, optional q filter on "
    "email, domain, name or company); action='add' with email (plus "
    "optional name, company, reason) cancels that person's pending sends "
    "and takes them out of every campaign; action='add' with domain (Block "
    "Domain, plus optional company) blocks everyone at that domain and "
    "cancels their pending sends; action='remove' with email or domain "
    "takes it off the list (it does not re-queue anything)."
))
async def dnc(action: str = "list", email: str = "", domain: str = "",
              name: str = "", company: str = "", reason: str = "",
              q: str = "") -> dict:
    if action == "list":
        return await _conn_a_call("dnc", None, q)
    return await _conn_a_call("dnc", {"action": action, "email": email,
                                      "domain": domain, "name": name,
                                      "company": company, "reason": reason})


@mcp.tool(description=(
    "Create or delete one of the user's campaign styles (list them with "
    "my_campaign_styles). action='create' with name + steps, what the "
    "Create a Campaign Style builder captures: steps=[{type: 'email'|"
    "'call'|'linkedin', delay_days: business days after the previous step "
    "(1-30; ignored on step 1), content: what that step says or should "
    "do}], at most 15, every step needs content; tone 'consultative' "
    "(default), 'direct', 'casual' or 'formal'. Or pass description "
    "instead of steps for a free-form style (Save as Campaign Style). At "
    "launch (create_campaign template 'byos' with style_id) the AI writes "
    "a fresh campaign from the style; it does not replay the text word for "
    "word. action='delete' with style_id removes one permanently: ask the "
    "user, then pass confirm=true."
))
async def campaign_styles(action: str, name: str = "", steps: list | None = None,
                          tone: str = "consultative", description: str = "",
                          style_id: str = "", confirm: bool = False) -> dict:
    body: dict = {"action": action, "name": name, "id": style_id, "tone": tone,
                  "confirm": confirm}
    if steps is not None:
        body["steps"] = steps
    if description:
        body["description"] = description
    return await _conn_a_call("campaign_styles", body)


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
