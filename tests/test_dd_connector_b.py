"""DD connector B (2026-11-12): the DripDrop-only pages reachable from Claude.

Pipeline, My Top 10, AI Prompts, Arena Sales Contacts + ZoomInfo Drop,
Current Clients, Arena Running Campaigns, Sales Assets, Home and the
profile/team/signature/timezone settings. One POST route per page under
/api/v1/dd/, each running the helpers its page's buttons call.

Route tests mount the handlers on a minimal Starlette app, never
flowdrip_app's real `app` (its NiceGUI lifespan pollutes the suite).
"""
import ast
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_OWNER = "rep@arenastaffing.net"
_OUTSIDER = "someone@othercompany.com"

_PAGES = {  # tool / client method -> route handler
    "pipeline": "api_dd_pipeline",
    "top10": "api_dd_top10",
    "ai_prompts": "api_dd_ai_prompts",
    "sales_contacts": "api_dd_sales_contacts",
    "clients": "api_dd_clients",
    "running_campaigns": "api_dd_running_campaigns",
    "sales_assets": "api_dd_sales_assets",
    "home": "api_dd_home",
    "profile": "api_dd_profile",
}


# ── structure ──────────────────────────────────────────────────────────────

def _tree(rel):
    return ast.parse((_ROOT / rel).read_text(encoding="utf-8"))


def _tool_names():
    out = []
    for n in ast.walk(_tree("mcp_server/dripdrop_mcp.py")):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in n.decorator_list:
                t = d.func if isinstance(d, ast.Call) else d
                if isinstance(t, ast.Attribute) and t.attr == "tool":
                    out.append(n.name)
    return out


def _client_methods():
    for n in ast.walk(_tree("mcp_server/dripdrop_client.py")):
        if isinstance(n, ast.ClassDef) and n.name == "DripDropClient":
            return {s.name for s in n.body
                    if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return set()


def _app_funcs(name):
    return [n for n in _tree("flowdrip_app.py").body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]


@pytest.mark.parametrize("tool,handler", sorted(_PAGES.items()))
def test_each_tool_pairs_with_a_client_method_and_a_keyed_route(tool, handler):
    assert _tool_names().count(tool) == 1
    assert tool in _client_methods()
    nodes = _app_funcs(handler)
    assert len(nodes) == 1, f"{handler} defined {len(nodes)} times"
    decs = [ast.unparse(d) for d in nodes[0].decorator_list]
    assert f"app.post('/api/v1/dd/{tool}')" in decs, decs
    calls = {ast.unparse(c.func) for c in ast.walk(nodes[0]) if isinstance(c, ast.Call)}
    assert "_ddb_route" in calls
    client_src = (_ROOT / "mcp_server" / "dripdrop_client.py").read_text(encoding="utf-8")
    assert f'self._ddb_post("{tool}"' in client_src


def test_ddb_route_resolves_the_owner_from_the_key_only():
    node = _app_funcs("_ddb_route")[0]
    owners = [ast.unparse(a.value) for a in ast.walk(node) if isinstance(a, ast.Assign)
              for t in a.targets if isinstance(t, ast.Tuple)
              and any(isinstance(e, ast.Name) and e.id == "owner" for e in t.elts)]
    assert owners == ["_dd_api_owner(request)"]


def test_routes_sit_in_the_b_section_and_mcp_code_where_agent_a_is_not():
    app_src = (_ROOT / "flowdrip_app.py").read_text(encoding="utf-8")
    b = app_src.index("# === DD connector B: DripDrop-only pages ===")
    a = app_src.index("# === DD connector A")
    end = app_src.index('@app.get("/api/v1/sales_runs/pending")')
    for handler in _PAGES.values():
        assert a < b < app_src.index(f"async def {handler}(") < end
    mcp_src = (_ROOT / "mcp_server" / "dripdrop_mcp.py").read_text(encoding="utf-8")
    for tool in _PAGES:
        assert mcp_src.index(f"async def {tool}(") < mcp_src.index("async def sales_runs_pending(")
    cl_src = (_ROOT / "mcp_server" / "dripdrop_client.py").read_text(encoding="utf-8")
    assert cl_src.index("async def profile(") < cl_src.index("async def sales_runs_pending(")


def test_destructive_and_sending_tools_say_so():
    src = (_ROOT / "mcp_server" / "dripdrop_mcp.py").read_text(encoding="utf-8")
    for tool in ("pipeline", "top10", "clients", "ai_prompts", "profile"):
        seg = src[src.index(f"async def {tool}(") - 3000: src.index(f"async def {tool}(")]
        assert "confirm=true" in seg, tool
    seg = src[src.index("async def ai_prompts(") - 2500: src.index("async def ai_prompts(")]
    assert "SENDS REAL" in seg


# ── harness ────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS talents (
  id INTEGER PRIMARY KEY,
  first_name TEXT, last_name TEXT, email TEXT, phone TEXT,
  city TEXT, state TEXT, current_title TEXT, current_employer TEXT,
  years_experience TEXT, seniority TEXT, skills TEXT, summary TEXT,
  status TEXT DEFAULT 'Candidate', source_file TEXT, resume_text TEXT,
  added_by TEXT, created_at TEXT, updated_at TEXT,
  owner_email TEXT DEFAULT '', notes TEXT DEFAULT '', work_history TEXT DEFAULT '',
  lat REAL, lng REAL
);
CREATE VIRTUAL TABLE IF NOT EXISTS talents_fts USING fts5(
  first_name, last_name, current_title, current_employer, skills,
  summary, city, state, resume_text, content='talents', content_rowid='id'
);
"""


def _safe(email):
    return email.lower().replace("@", "_at_").replace(".", "_")


@pytest.fixture
def api(with_user, tmp_path, monkeypatch):
    """flowdrip_app with keys, users and the ATS db in tmp, and per-user roots
    resolved the way server mode does (users/<safe email>)."""
    import flowdrip_app as fa
    keys = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: keys)
    base = fa._BASE_DATA_DIR

    def _root(email=None):
        email = email or fa._CURRENT_USER_EMAIL.get() or _OWNER
        return base / "users" / _safe(email)
    monkeypatch.setattr(fa, "_resolve_user_root", _root)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "")
    db = tmp_path / "ats.db"
    con = sqlite3.connect(str(db))
    con.executescript(_SCHEMA)
    con.commit()
    con.close()
    monkeypatch.setenv("ATS_DB_PATH", str(db))
    sys.modules.pop("ats", None)
    import ats
    monkeypatch.setattr(ats, "_ai_parse_resume", lambda text: {
        "first_name": "Jane", "last_name": "Doe", "email": "jane.doe@example.com",
        "phone": "555-1234", "city": "Denver", "state": "CO",
        "current_title": "Senior Project Manager", "current_employer": "Acme Construction",
        "key_skills": ["scheduling", "budgeting"], "summary": "Commercial PM.",
    })
    fa._save_users({_OWNER: {"name": "Rep One", "phone": "", "is_tenant_admin": True},
                    "mate@arenastaffing.net": {"name": "Mate Two", "phone": ""}})
    before = fa._CURRENT_USER_EMAIL.get()
    yield fa
    fa._CURRENT_USER_EMAIL.set(before)
    sys.modules.pop("ats", None)


def _client(fa):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    return TestClient(Starlette(routes=[
        Route(f"/api/v1/dd/{page}", getattr(fa, h), methods=["POST"])
        for page, h in _PAGES.items()]))


def _call(fa, page, body, key=None, owner=_OWNER):
    key = key or fa._mint_api_key(owner)
    return _client(fa).post(f"/api/v1/dd/{page}", json=body, headers={"X-API-Key": key})


@pytest.mark.parametrize("page", sorted(_PAGES))
def test_every_route_refuses_a_missing_or_bad_key(api, page):
    c = _client(api)
    assert c.post(f"/api/v1/dd/{page}", json={}).status_code == 401
    r = c.post(f"/api/v1/dd/{page}", json={}, headers={"X-API-Key": "dd_live_bogus"})
    assert r.status_code == 401


def test_pipeline_is_gated_like_the_page(api):
    r = _call(api, "pipeline", {"action": "dashboard"}, owner=_OUTSIDER)
    assert r.status_code == 403


def test_body_must_be_an_object_and_actions_are_checked(api):
    key = api._mint_api_key(_OWNER)
    r = _client(api).post("/api/v1/dd/clients", json=[1, 2], headers={"X-API-Key": key})
    assert r.status_code == 400
    r = _call(api, "clients", {"action": "explode"}, key=key)
    assert r.status_code == 400 and "action must be one of" in r.json()["error"]


# ── Pipeline ───────────────────────────────────────────────────────────────

def _load_jane(fa):
    import ats
    ats.ingest_resumes([("jane.txt", (
        "JANE DOE\nSenior Project Manager\nDenver, CO\n\n"
        "EXPERIENCE\nSenior Project Manager, Acme Construction, 2018-Present\n"
        "SKILLS: scheduling, budgeting, OSHA, Procore.\n").encode("utf-8"))],
        _OWNER, "Rep One", rebuild=True)
    return ats.recent(1)[0]["id"]


def test_pipeline_search_get_and_notes(api):
    tid = _load_jane(api)
    key = api._mint_api_key(_OWNER)
    r = _call(api, "pipeline", {"q": "project manager"}, key=key)
    assert r.status_code == 200, r.text
    hit = r.json()["candidates"][0]
    assert hit["id"] == tid and hit["ref"] == f"Ref #{tid}" and hit["name"] == "Jane Doe"
    assert "resume_text" not in hit

    r = _call(api, "pipeline", {"action": "get", "candidate_id": f"Ref #{tid}"}, key=key)
    full = r.json()["candidate"]
    assert "Procore" in full["resume_text"] and full["notes"] == ""

    r = _call(api, "pipeline", {"action": "save_notes", "candidate_id": tid,
                                "notes": "Open to Denver only."}, key=key)
    assert r.json()["candidate"]["notes"] == "Open to Denver only."
    import ats
    assert ats.get_one(tid)["notes"] == "Open to Denver only."

    r = _call(api, "pipeline", {"action": "get", "candidate_id": 999999}, key=key)
    assert r.status_code == 404


def test_pipeline_tearsheets_and_jobs(api):
    tid = _load_jane(api)
    key = api._mint_api_key(_OWNER)
    r = _call(api, "pipeline", {"action": "tearsheet_create", "name": "Denver PMs",
                                "candidate_ids": [tid]}, key=key)
    ts = r.json()["tearsheet"]
    assert ts["kind"] == "manual" and ts["count"] == 1
    r = _call(api, "pipeline", {"action": "tearsheet", "tearsheet_id": ts["id"]}, key=key)
    assert [c["id"] for c in r.json()["candidates"]] == [tid]
    r = _call(api, "pipeline", {"action": "tearsheet_remove", "tearsheet_id": ts["id"],
                                "candidate_ids": [tid]}, key=key)
    assert r.json()["tearsheet"]["count"] == 0
    # Another account's tearsheet is not reachable.
    other = api._mint_api_key("mate@arenastaffing.net")
    r = _call(api, "pipeline", {"action": "tearsheet", "tearsheet_id": ts["id"]}, key=other)
    assert r.status_code == 404
    r = _call(api, "pipeline", {"action": "tearsheet_delete", "tearsheet_id": ts["id"]}, key=key)
    assert r.status_code == 409
    r = _call(api, "pipeline", {"action": "tearsheet_delete", "tearsheet_id": ts["id"],
                                "confirm": True}, key=key)
    assert r.json()["deleted"] == "Denver PMs"
    assert _call(api, "pipeline", {"action": "tearsheets"}, key=key).json()["tearsheets"] == []

    r = _call(api, "pipeline", {"action": "job_add", "title": "Project Manager",
                                "company": "Acme", "location": "Denver, CO"}, key=key)
    jid = r.json()["job"]["id"]
    jobs = _call(api, "pipeline", {"action": "jobs"}, key=key).json()["jobs"]
    assert [j["id"] for j in jobs] == [jid]
    r = _call(api, "pipeline", {"action": "job_delete", "job_id": jid, "confirm": True}, key=key)
    assert r.status_code == 200 and r.json()["deleted"] == "Project Manager"


def test_pipeline_dashboard_and_pools(api):
    _load_jane(api)
    r = _call(api, "pipeline", {"action": "dashboard"})
    body = r.json()
    assert body["my_candidates"] == 1 and body["team_candidates"] == 1
    assert body["recently_added"][0]["name"] == "Jane Doe"
    assert "pools" in _call(api, "pipeline", {"action": "pools"}).json()


# ── My Top 10 ──────────────────────────────────────────────────────────────

def test_top10_add_edit_move_remove(api):
    key = api._mint_api_key(_OWNER)
    add = lambda name, **kw: _call(api, "top10", dict(
        {"action": "add", "company": name, "verify": False}, **kw), key=key)
    assert add("Acme Builders").status_code == 200
    r = add("Bolt Electric", roles="Superintendent")
    body = r.json()
    assert [c["company"] for c in body["top10"]] == ["Acme Builders", "Bolt Electric"]
    assert body["top10"][1]["roles"] == "Superintendent"
    assert add("Acme Builders").status_code == 409

    r = _call(api, "top10", {"action": "update", "company_id": "Bolt Electric",
                             "status": "talking", "notes": "Met at AGC"}, key=key)
    bolt = r.json()["top10"][1]
    assert bolt["status"] == "Talking" and bolt["notes"] == "Met at AGC"
    r = _call(api, "top10", {"action": "update", "company_id": bolt["id"],
                             "status": "nope"}, key=key)
    assert r.status_code == 400

    r = _call(api, "top10", {"action": "move", "company_id": bolt["id"],
                             "direction": "up"}, key=key)
    assert r.json()["top10"][0]["company"] == "Bolt Electric"
    r = _call(api, "top10", {"action": "demote", "company_id": bolt["id"]}, key=key)
    assert [c["company"] for c in r.json()["backups"]] == ["Bolt Electric"]

    assert _call(api, "top10", {"action": "remove", "company_id": bolt["id"]},
                 key=key).status_code == 409
    r = _call(api, "top10", {"action": "remove", "company_id": bolt["id"],
                             "confirm": True}, key=key)
    assert r.json()["backups"] == []
    import top_ten as _tt
    saved = _tt.load(api._top10_path(_OWNER))
    assert [c["company"] for c in saved["companies"]] == ["Acme Builders"]

    r = _call(api, "top10", {"action": "set_focus", "market": "Denver, CO",
                             "industry": "Construction"}, key=key)
    assert r.json()["focus"] == {"market": "Denver, CO", "industry": "Construction"}


def test_top10_unverified_add_comes_back_for_a_decision(api):
    # No API key on the server: the check reports an error, nothing is added.
    r = _call(api, "top10", {"action": "add", "company": "Zeta Corp"})
    body = r.json()
    assert body["added"] is False and body["check"].get("error")
    r = _call(api, "top10", {"action": "add", "company": "Zeta Corp", "add_as_typed": True})
    assert [c["company"] for c in r.json()["top10"]] == ["Zeta Corp"]


# ── AI Prompts ─────────────────────────────────────────────────────────────

def test_ai_prompts_runs_build_save_delete(api):
    key = api._mint_api_key(_OWNER)
    runs = _call(api, "ai_prompts", {}, key=key).json()["runs"]
    assert runs and all(r["questions"] is not None for r in runs)
    run = next(r for r in runs if r["questions"])
    r = _call(api, "ai_prompts", {"action": "build", "run": run["run"]}, key=key)
    assert r.status_code == 200, r.text
    assert len(r.json()["prompt"]) > 200 and "SENDS REAL EMAIL" in r.json()["note"]

    r = _call(api, "ai_prompts", {"action": "build", "run": run["run"],
                                  "answers": {"no_such_question": "x"}}, key=key)
    assert r.status_code == 400

    r = _call(api, "ai_prompts", {"action": "save", "run": run["run"], "name": "Mine"},
              key=key)
    pid = r.json()["prompt_id"]
    saved = _call(api, "ai_prompts", {"action": "saved"}, key=key).json()["saved"]
    assert [s["prompt_id"] for s in saved] == [pid]
    assert _call(api, "ai_prompts", {"action": "delete", "prompt_id": pid},
                 key=key).status_code == 409
    assert _call(api, "ai_prompts", {"action": "delete", "prompt_id": pid, "confirm": True},
                 key=key).json() == {"deleted": pid}


# ── Arena Sales Contacts + ZoomInfo Drop ──────────────────────────────────

def test_zoominfo_drop_lands_in_the_bank(api):
    key = api._mint_api_key(_OWNER)
    recs = [{"First Name": "Dana", "Last Name": "Lee", "Email": "dana@acmebuild.com",
             "Job Title": "VP Operations", "Company": "Acme Build", "Direct Phone": "303-555-0100",
             "ZoomInfo Contact ID": "123"},
            {"First Name": "Sam", "Last Name": "Ray", "Email": "sam@acmebuild.com",
             "Job Title": "Superintendent", "Company": "Acme Build",
             "ZoomInfo Contact ID": "124"}]
    r = _call(api, "sales_contacts", {"action": "zoominfo_drop", "records": recs}, key=key)
    assert r.status_code == 200, r.text
    rc = r.json()["receipt"]
    assert rc["people"] == 2 and rc["added"] == 2 and rc["new_to_team"] == 2
    again = _call(api, "sales_contacts", {"action": "zoominfo_drop", "records": recs[:1]},
                  key=key).json()["receipt"]
    assert again["added"] == 0 and again["merged"] == 1

    r = _call(api, "sales_contacts", {"q": "acme"}, key=key).json()
    assert r["matching_companies"] == 1
    assert {c["email"] for c in r["results"][0]["contacts"]} == {
        "dana@acmebuild.com", "sam@acmebuild.com"}
    prog = _call(api, "sales_contacts", {"action": "zoominfo_progress"}, key=key).json()
    assert prog["mine"]["people"] == 2 and prog["mine"]["drops"] == 2

    r = _call(api, "sales_contacts", {"action": "zoominfo_drop"}, key=key)
    assert r.status_code == 400


# ── Current Clients ───────────────────────────────────────────────────────

def test_clients_add_update_remove(api):
    key = api._mint_api_key(_OWNER)
    r = _call(api, "clients", {"action": "add", "client_name": "Acme", "domain": "@acme.com"},
              key=key)
    body = r.json()
    assert body["count"] == 1 and body["clients"][0]["domain"] == "acme.com"
    assert body["clients"][0]["website"] == "acme.com"
    r = _call(api, "clients", {"action": "add", "clients": [
        {"client_name": "Bolt", "domain": "bolt.com"}, {"client_name": "Acme", "domain": "acme.com"},
        {"domain": "nameless.com"}]}, key=key)
    body = r.json()
    assert body["count"] == 2 and len(body["errors"]) == 2

    r = _call(api, "clients", {"action": "update", "domain": "bolt.com", "notes": "Since May"},
              key=key)
    assert next(c for c in r.json()["clients"] if c["domain"] == "bolt.com")["notes"] == "Since May"
    assert _call(api, "clients", {"action": "remove", "domain": "bolt.com"},
                 key=key).status_code == 409
    r = _call(api, "clients", {"action": "remove", "domain": "bolt.com", "confirm": True}, key=key)
    assert [c["domain"] for c in r.json()["clients"]] == ["acme.com"]
    assert r.json()["removed_count"] == 1
    # The team blocklist is what launches honour.
    assert [e["domain"] for e in api.load_client_blocklist(_OWNER)] == ["acme.com"]


# ── Arena Running Campaigns ───────────────────────────────────────────────

def test_running_campaigns_lists_and_filters(api):
    cdir = api._BASE_DATA_DIR / "users" / _safe("mate@arenastaffing.net") / "Campaigns"
    cdir.mkdir(parents=True)
    (cdir / "acme.json").write_text(json.dumps({
        "name": "Denver, CO - Construction - Acme", "status": "active",
        "start_date": date.today().isoformat(), "template_key": "fourbyfour",
        "contacts": [{"email": "vp@acme.com", "company": "Acme"}]}), encoding="utf-8")
    key = api._mint_api_key(_OWNER)
    r = _call(api, "running_campaigns", {}, key=key)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matching"] == 1
    row = body["results"][0]
    assert row["company"] == "Acme" and row["campaigns"][0]["rep"] == "Mate"
    assert _call(api, "running_campaigns", {"status": "cancelled"},
                 key=key).json()["matching"] == 0
    assert _call(api, "running_campaigns", {"rep": "mate@arenastaffing.net"},
                 key=key).json()["matching"] == 1
    assert _call(api, "running_campaigns", {"status": "paused"}, key=key).status_code == 400


# ── Sales Assets ──────────────────────────────────────────────────────────

def test_sales_assets_list_validate_and_generate(api, monkeypatch):
    key = api._mint_api_key(_OWNER)
    body = _call(api, "sales_assets", {}, key=key).json()
    assert body["assets"] == [] and {k["kind"] for k in body["kinds"]} == {
        "market_pulse", "interview_guide", "salary_guide", "scorecard", "why_staffing"}
    bad = {"action": "generate", "company": "Acme", "role": "PM", "location": "Denver, CO"}
    assert _call(api, "sales_assets", dict(bad, kinds=["nope"]), key=key).status_code == 400
    assert _call(api, "sales_assets", dict(bad, kinds=["market_pulse", "scorecard",
                                                       "salary_guide", "why_staffing"]),
                 key=key).status_code == 400
    assert _call(api, "sales_assets", dict(bad, kinds=["scorecard"], role=""),
                 key=key).status_code == 400

    monkeypatch.setattr(api, "ANTHROPIC_API_KEY", "test-key")
    seen = {}

    def _fake(owner, kinds, company, role, location, *rest):
        seen.update(owner=owner, kinds=kinds)
        d = api._resolve_user_root(owner) / "PDFs"
        d.mkdir(parents=True, exist_ok=True)
        (d / "Role_Scorecard_Acme.pdf").write_bytes(b"%PDF-1.4")
        return [("scorecard", "Role Scorecard", "Role_Scorecard_Acme.pdf")], []
    monkeypatch.setattr(api, "_ddb_build_sales_pdfs", _fake)
    r = _call(api, "sales_assets", dict(bad, kinds="scorecard"), key=key)
    assert r.status_code == 200, r.text
    assert seen == {"owner": _OWNER, "kinds": ["scorecard"]}
    asset = r.json()["assets"][0]
    assert asset["path"] == "/pdfs/Role_Scorecard_Acme.pdf" and asset["kind"] == "scorecard"
    assert _call(api, "sales_assets", {}, key=key).json()["total"] == 1


# ── Home + profile ────────────────────────────────────────────────────────

def test_home_summary(api):
    r = _call(api, "home", {})
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("overdue_tasks", "tasks_today", "active_campaigns", "replies",
              "emails_queued", "active", "pipeline"):
        assert k in body


def test_profile_get_and_update(api):
    key = api._mint_api_key(_OWNER)
    body = _call(api, "profile", {}, key=key).json()
    assert body["personal"]["name"] == "Rep One"
    assert {m["email"] for m in body["team"]["members"]} == {
        _OWNER, "mate@arenastaffing.net"}

    assert _call(api, "profile", {"action": "update", "timezone": "Mars/Base"},
                 key=key).status_code == 400
    r = _call(api, "profile", {"action": "update", "timezone": "America/Chicago",
                               "signature": "Rep One\nArena", "phone": "303-555-0199",
                               "company": {"company_name": "Arena Direct Hire"}}, key=key)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["saved"]) >= {"personal", "company", "signature", "timezone"}
    assert body["timezone"] == "America/Chicago" and body["timezone_set"]
    assert body["signature"] == "Rep One\nArena"
    assert body["personal"]["phone"] == "303-555-0199"
    assert body["company"]["company_name"] == "Arena Direct Hire"
    assert _call(api, "profile", {"action": "update", "company": {"bogus": 1}},
                 key=key).status_code == 400

    assert _call(api, "profile", {"action": "set_admin", "email": "mate@arenastaffing.net",
                                  "admin": True}, key=key).status_code == 409
    r = _call(api, "profile", {"action": "set_admin", "email": "mate@arenastaffing.net",
                               "admin": True, "confirm": True}, key=key)
    assert next(m for m in r.json()["team"]["members"]
                if m["email"] == "mate@arenastaffing.net")["admin"] is True
    r = _call(api, "profile", {"action": "team_branding", "company_name": "Arena"}, key=key)
    assert r.json()["team"]["branding"]["company_name"] == "Arena"


# ── MCP side ──────────────────────────────────────────────────────────────

def test_mcp_body_and_pdf_links():
    from mcp_server import dripdrop_mcp as m
    assert m._ddb_body("search", q="pm", limit=25, mine=None, ids=[], x="") == {
        "action": "search", "q": "pm", "limit": 25}
    res = m._ddb_link_pdfs({"assets": [{"path": "/pdfs/A.pdf"}, {"path": "x"}]})
    assert res["assets"][0]["url"].endswith("/pdfs/A.pdf")
    assert "url" not in res["assets"][1]


# ── Sales Contacts: recommend for candidates (2026-11-12) ────────────────

def _drop_bank(fa, key):
    recs = [
        {"First Name": "Dana", "Last Name": "Lee", "Email": "dana@peakbuild.com",
         "Job Title": "VP Operations", "Company": "Peak Builders", "City": "Denver",
         "State": "CO"},
        {"First Name": "Sam", "Last Name": "Ray", "Email": "sam@peakbuild.com",
         "Job Title": "Receptionist", "Company": "Peak Builders", "State": "CO"},
        {"First Name": "Lou", "Last Name": "Kim", "Email": "lou@acmeconstruction.com",
         "Job Title": "Director of Project Management", "Company": "Acme Construction",
         "State": "CO"},
        {"First Name": "Ann", "Last Name": "Fox", "Email": "ann@bankco.com",
         "Job Title": "Controller", "Company": "Bank Co", "State": "NY"},
    ]
    r = _call(fa, "sales_contacts", {"action": "zoominfo_drop", "records": recs}, key=key)
    assert r.status_code == 200, r.text


def test_recommend_ranks_the_bank_for_a_pipeline_candidate_by_full_name(api):
    key = api._mint_api_key(_OWNER)
    tid = _load_jane(api)
    _drop_bank(api, key)
    r = _call(api, "sales_contacts", {"action": "recommend",
                                      "candidates": ["Jane Doe"]}, key=key)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["pool_ids"] == [tid]
    cos = [x["company"] for x in out["recommendations"]]
    # Never her own employer; the Colorado builder first.
    assert "Acme Construction" not in cos
    assert cos[0] == "Peak Builders"
    top = out["recommendations"][0]
    assert any("same state" in w for w in top["why"])
    assert top["people"][0]["email"] == "dana@peakbuild.com"
    assert "hiring authority" in top["people"][0]["why"]
    assert "pool_ids" in out["next"]


def test_recommend_takes_a_free_text_profile_without_pipeline_access(api):
    key = api._mint_api_key(_OUTSIDER)
    r = _call(api, "sales_contacts", {"action": "recommend", "candidates": [
        {"title": "Staff Accountant", "skills": "accounting, GL", "state": "NY"}]},
        key=key, owner=_OUTSIDER)
    assert r.status_code == 200, r.text
    # A Pipeline name needs Pipeline access.
    r = _call(api, "sales_contacts", {"action": "recommend", "candidates": ["Jane Doe"]},
              key=key, owner=_OUTSIDER)
    assert r.status_code == 403


def test_recommend_needs_candidates(api):
    key = api._mint_api_key(_OWNER)
    r = _call(api, "sales_contacts", {"action": "recommend"}, key=key)
    assert r.status_code == 400


def test_pipeline_get_accepts_a_full_name(api):
    key = api._mint_api_key(_OWNER)
    tid = _load_jane(api)
    r = _call(api, "pipeline", {"action": "get", "candidate_id": "jane doe"}, key=key)
    assert r.status_code == 200, r.text
    assert r.json()["candidate"]["id"] == tid
