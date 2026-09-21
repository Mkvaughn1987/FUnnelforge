"""Connector group C (2026-09-21): the AI Prompt page, Company Profile
(Sales Playbook, website auto-fill, team default) and Email & AI Setup.
Each route calls the helper its page calls, behind the same key + gate door."""
import ast
import inspect
import json
from pathlib import Path

import pytest

import ai_prompts as aip
import flowdrip_app as fa
import tm_prompts as tmp_mod

_OWNER = "rep@thrivemodal.com"
_ROOT = Path(__file__).resolve().parent.parent

_NEW_TOOLS = ("tm_ai_prompt", "tm_playbook")

_ROUTES = [  # (method, path, handler)
    ("get", "/api/v1/tm/ai_prompt", "api_tm_ai_prompt_runs"),
    ("post", "/api/v1/tm/ai_prompt", "api_tm_ai_prompt"),
    ("get", "/api/v1/tm/playbook", "api_tm_playbook"),
    ("post", "/api/v1/tm/playbook", "api_tm_playbook_update"),
    ("post", "/api/v1/tm/profile/autofill", "api_tm_profile_autofill"),
    ("post", "/api/v1/tm/profile/team_default", "api_tm_team_default"),
    # changed in this group
    ("get", "/api/v1/tm/saved_prompts", "api_tm_saved_prompts"),
    ("get", "/api/v1/tm/settings", "api_tm_settings"),
    ("post", "/api/v1/tm/settings", "api_tm_settings_update"),
]


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


@pytest.mark.parametrize("name", _NEW_TOOLS)
def test_every_new_tool_exists_with_a_client_method(name):
    assert name in _tool_names()
    assert name in _client_methods()


def _app_func(name):
    for n in _tree("flowdrip_app.py").body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


@pytest.mark.parametrize("method,path,handler", _ROUTES)
def test_every_route_is_registered_gated_and_keyed(method, path, handler):
    node = _app_func(handler)
    assert node is not None, handler
    decs = [ast.unparse(d) for d in node.decorator_list]
    assert f"app.{method}('{path}')" in decs, decs
    names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    assert "_is_thrivemodal" in names and "_tm_api_owner" in names
    owners = [a.value for a in ast.walk(node) if isinstance(a, ast.Assign)
              for t in a.targets if isinstance(t, ast.Name) and t.id == "owner"]
    assert len(owners) == 1 and ast.unparse(owners[0]) == "_tm_api_owner(request)"


def test_the_pages_call_the_same_helpers():
    # AI Prompt: save / delete / reopen go through the shared helpers.
    assert "save_setup(req, name)" in inspect.getsource(aip._aip_save_setup)
    assert "delete_setup(" in inspect.getsource(aip.render_saved_page)
    assert "delete_setup(" in inspect.getsource(aip._aip_setup_row)
    assert "req_from_setup(row)" in inspect.getsource(aip._open_setup)
    # Company Profile: auto-fill and team default.
    src = inspect.getsource(fa._p_profile_body)
    assert "_company_profile_from_website(url)" in src
    assert "_save_profile_as_team_default()" in src


# ── harness ────────────────────────────────────────────────────────────────

@pytest.fixture
def api(tmp_path, monkeypatch):
    keys = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: keys)
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *a, **k: None)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    monkeypatch.setattr(fa, "_resolve_user_root", lambda *a, **k: tmp_path)
    # The engine finds the app through sys.modules, which other test files
    # rebind; point every loaded copy at this one.
    import sys
    for m in {id(x): x for x in (aip, sys.modules.get("ai_prompts")) if x}.values():
        monkeypatch.setattr(m, "_ff", lambda: fa)
    cfg = {}
    monkeypatch.setattr(fa, "load_config", lambda: cfg)
    monkeypatch.setattr(fa, "save_config", lambda c: cfg.update(c))
    camps = [{"name": "Freight Notes", "evergreen_only": True},
             {"name": "Acme Outreach"}]
    monkeypatch.setattr(fa, "load_campaigns", lambda: camps)
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    app = FastAPI()
    for method, path, handler in _ROUTES:
        getattr(app, method)(path)(getattr(fa, handler))
    client = TestClient(app)
    key = fa._mint_api_key(_OWNER)

    def call(method, path, body=None, params=None, auth=True):
        h = {"X-API-Key": key} if auth else {}
        if method == "get":
            return client.get(path, params=params or {}, headers=h)
        return client.post(path, json=body or {}, headers=h)
    return {"call": call, "cfg": cfg, "tmp": tmp_path}


@pytest.mark.parametrize("method,path,handler", _ROUTES)
def test_every_route_needs_a_key(api, method, path, handler):
    assert api["call"](method, path, auth=False).status_code == 401


@pytest.mark.parametrize("method,path,handler", _ROUTES)
def test_every_route_is_404_on_arena(api, monkeypatch, method, path, handler):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    assert api["call"](method, path).status_code == 404


# ── AI Prompt ──────────────────────────────────────────────────────────────

def test_runs_list_every_starter_and_its_questions(api):
    r = api["call"]("get", "/api/v1/tm/ai_prompt")
    assert r.status_code == 200
    runs = {x["run"]: x for x in r.json()["runs"]}
    assert set(runs) == set(tmp_mod.TM.starter_by_id)
    qs = {q["key"]: q for q in runs["signal"]["questions"]}
    assert qs["vertical"]["options"] == tmp_mod.VERTICAL_LABELS
    assert qs["vertical"]["default"] == "Logistics / 3PL"  # the starter preset
    # The newsletter question offers the user's own newsletters by name.
    assert "Freight Notes" in qs["newsletter"]["options"]
    assert "Acme Outreach" not in qs["newsletter"]["options"]
    assert r.json()["newsletters"] == ["Freight Notes"]


def test_build_writes_the_same_prompt_the_page_builds(api):
    r = api["call"]("post", "/api/v1/tm/ai_prompt", {
        "action": "build", "run": "signal",
        "answers": {"vertical": "accounting / cas firms", "location": "Texas",
                    "newsletter": "Freight Notes"},
        "instructions": ["Skip anyone in Austin."]})
    assert r.status_code == 200, r.text
    req = aip._req_from_starter(tmp_mod.TM.starter_by_id["signal"], tmp_mod.TM)
    req["vals"].update({"vertical": "Accounting / CAS firms", "location": "Texas",
                        "newsletter_mode": aip.NEWSLETTER_MODES[1],
                        "newsletter": "Freight Notes"})
    req["detail"] = ["Skip anyone in Austin."]
    assert r.json()["prompt"] == tmp_mod.build_prompt(req)
    assert '"Freight Notes" newsletter' in r.json()["prompt"]


def test_build_refuses_what_the_page_could_not_hold(api):
    c = api["call"]
    assert c("post", "/api/v1/tm/ai_prompt",
             {"action": "build", "run": "nope"}).status_code == 400
    r = c("post", "/api/v1/tm/ai_prompt",
          {"action": "build", "run": "signal", "answers": {"vertical": "Mars"}})
    assert r.status_code == 400 and "vertical must be one of" in r.json()["error"]
    assert c("post", "/api/v1/tm/ai_prompt", {
        "action": "build", "run": "signal",
        "answers": {"favourite": "x"}}).status_code == 400
    assert c("post", "/api/v1/tm/ai_prompt", {
        "action": "save", "run": "signal"}).status_code == 400  # no name


def test_a_blank_required_answer_becomes_a_question_not_an_error(api):
    r = api["call"]("post", "/api/v1/tm/ai_prompt",
                    {"action": "build", "run": "account"})
    assert r.status_code == 200
    assert "Which company" in r.json()["still_to_answer"]
    assert "I HAVEN'T DECIDED THESE" in r.json()["prompt"]


def test_save_reopen_and_delete_a_prompt(api):
    c = api["call"]
    r = c("post", "/api/v1/tm/ai_prompt", {
        "action": "save", "run": "signal", "name": "Texas logistics",
        "answers": {"location": "Texas"}})
    assert r.status_code == 200, r.text
    pid = r.json()["prompt_id"]
    rows = json.loads((api["tmp"] / tmp_mod.TM.setups_file).read_text(encoding="utf-8"))
    assert rows[0]["id"] == pid and rows[0]["vals"]["location"] == "Texas"
    # Saved Prompts lists it and rebuilds it.
    lst = c("get", "/api/v1/tm/saved_prompts").json()["prompts"]
    assert [p["id"] for p in lst] == [pid]
    one = c("get", "/api/v1/tm/saved_prompts", params={"id": pid}).json()
    assert one["answers"]["location"] == "Texas" and "Texas" in one["prompt"]
    # Editing from the saved answers keeps the ones not changed.
    r = c("post", "/api/v1/tm/ai_prompt", {
        "action": "build", "prompt_id": pid, "answers": {"companies": "8"}})
    assert "Texas" in r.json()["prompt"]
    # Same name replaces rather than duplicates, as on the page.
    c("post", "/api/v1/tm/ai_prompt", {"action": "save", "run": "signal",
                                       "name": "texas LOGISTICS"})
    assert len(c("get", "/api/v1/tm/saved_prompts").json()["prompts"]) == 1
    new_id = c("get", "/api/v1/tm/saved_prompts").json()["prompts"][0]["id"]
    assert c("post", "/api/v1/tm/ai_prompt",
             {"action": "delete", "prompt_id": new_id}).status_code == 200
    assert c("post", "/api/v1/tm/ai_prompt",
             {"action": "delete", "prompt_id": new_id}).status_code == 404
    assert c("get", "/api/v1/tm/saved_prompts").json()["prompts"] == []


# ── Sales Playbook ─────────────────────────────────────────────────────────

def _defaults():
    return {k: d for k, _l, _h, d in fa.THRIVEMODAL_PLAYBOOK_FIELDS}


def test_playbook_reads_the_text_in_force(api):
    api["cfg"].update({"tm_voice": "Short.", "tm_pricing": "",
                       "tm_custom_sections": [{"title": "Obj", "body": "B"},
                                              {"title": "", "body": "x"}]})
    j = api["call"]("get", "/api/v1/tm/playbook").json()
    secs = {s["key"]: s for s in j["sections"]}
    assert len(secs) == len(fa.THRIVEMODAL_PLAYBOOK_FIELDS)
    assert secs["tm_voice"]["text"] == "Short." and not secs["tm_voice"]["is_default"]
    assert secs["tm_pricing"]["empty"]
    assert secs["tm_business"]["is_default"]
    assert secs["tm_proof"]["improvable"] is False
    assert j["custom_sections"] == [{"title": "Obj", "body": "B"}]


def test_playbook_update_add_remove_restore(api):
    c, cfg = api["call"], api["cfg"]
    assert c("post", "/api/v1/tm/playbook", {"action": "update",
             "sections": {"tm_nope": "x"}}).status_code == 400
    r = c("post", "/api/v1/tm/playbook", {"action": "update",
          "sections": {"tm_voice": "  Plain. ", "tm_pricing": ""}})
    assert r.status_code == 200
    assert cfg["tm_voice"] == "Plain." and cfg["tm_pricing"] == ""
    assert c("post", "/api/v1/tm/playbook", {"action": "add_section",
             "title": "Objections"}).status_code == 400  # needs a body
    c("post", "/api/v1/tm/playbook", {"action": "add_section",
      "title": "Objections", "body": "Price first."})
    assert cfg["tm_custom_sections"] == [{"title": "Objections", "body": "Price first."}]
    assert c("post", "/api/v1/tm/playbook", {"action": "remove_section",
             "title": "objections"}).status_code == 200
    assert cfg["tm_custom_sections"] == []
    assert c("post", "/api/v1/tm/playbook", {"action": "remove_section",
             "title": "objections"}).status_code == 404
    # Restore with no keys fills only the empty sections, like the banner.
    r = c("post", "/api/v1/tm/playbook", {"action": "restore"})
    assert r.json()["restored"] == ["tm_pricing"]
    assert cfg["tm_pricing"] == _defaults()["tm_pricing"] and cfg["tm_voice"] == "Plain."
    c("post", "/api/v1/tm/playbook", {"action": "restore", "sections": ["tm_voice"]})
    assert cfg["tm_voice"] == _defaults()["tm_voice"]


def test_improve_suggests_and_saves_only_on_apply(api, monkeypatch):
    seen = []

    async def fake(key, current):
        seen.append((key, current))
        return "Sharper."
    monkeypatch.setattr(fa, "_tm_improve_section", fake)
    c, cfg = api["call"], api["cfg"]
    r = c("post", "/api/v1/tm/playbook", {"action": "improve", "section": "tm_voice"})
    assert r.json() == {"section": "tm_voice", "suggestion": "Sharper.", "applied": False}
    assert "tm_voice" not in cfg
    assert seen[0] == ("tm_voice", _defaults()["tm_voice"])
    c("post", "/api/v1/tm/playbook", {"action": "improve", "section": "tm_voice",
                                      "text": "Mine.", "apply": True})
    assert seen[1] == ("tm_voice", "Mine.") and cfg["tm_voice"] == "Sharper."


def test_improve_refuses_locked_sections(api):
    r = api["call"]("post", "/api/v1/tm/playbook",
                    {"action": "improve", "section": "tm_proof"})
    assert r.status_code == 400 and "locked" in r.json()["error"]


def test_switch_only_where_the_app_offers_a_choice(api, monkeypatch):
    c = api["call"]
    monkeypatch.setattr(fa, "_LOCKED_PLAYBOOK", "thrivemodal")
    assert c("post", "/api/v1/tm/playbook",
             {"action": "switch", "playbook": "arena"}).status_code == 400
    monkeypatch.setattr(fa, "_LOCKED_PLAYBOOK", "")
    assert c("post", "/api/v1/tm/playbook",
             {"action": "switch", "playbook": "other"}).status_code == 400
    r = c("post", "/api/v1/tm/playbook", {"action": "switch", "playbook": "arena"})
    assert r.json()["playbook"] == "arena" and "stop working" in r.json()["note"]
    assert api["cfg"]["workspace_playbook"] == "arena"


# ── Company profile: auto-fill + team default ──────────────────────────────

def test_autofill_stages_unless_applied(api, monkeypatch):
    urls, saved = [], []
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(fa, "_company_profile_from_website",
                        lambda u: urls.append(u) or {"company_name": "Acme"})
    monkeypatch.setattr(fa, "_save_company_profile", lambda p: saved.append(p))
    c = api["call"]
    r = c("post", "/api/v1/tm/profile/autofill", {"website": "acme.com"})
    assert r.json() == {"website": "https://acme.com",
                        "found": {"company_name": "Acme"}, "applied": False}
    assert urls == ["https://acme.com"] and saved == []
    r = c("post", "/api/v1/tm/profile/autofill", {"website": "acme.com", "apply": True})
    assert r.json()["applied"] and saved[-1]["company_name"] == "Acme"
    monkeypatch.setattr(fa, "_company_profile_from_website", lambda u: None)
    assert c("post", "/api/v1/tm/profile/autofill",
             {"website": "acme.com"}).status_code == 502


def test_autofill_needs_a_site_and_an_ai_key(api, monkeypatch):
    c = api["call"]
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "")
    assert c("post", "/api/v1/tm/profile/autofill", {}).status_code == 400
    assert c("post", "/api/v1/tm/profile/autofill",
             {"website": "acme.com"}).status_code == 503


def test_team_default_is_admin_only(api, monkeypatch):
    c = api["call"]
    monkeypatch.setattr(fa, "_SERVER_MODE", True)
    monkeypatch.setattr(fa, "_is_tenant_admin", lambda email=None: False)
    assert c("post", "/api/v1/tm/profile/team_default").status_code == 403
    monkeypatch.setattr(fa, "_is_tenant_admin", lambda email=None: email == _OWNER)
    # The real helper refuses a profile without a company name.
    r = c("post", "/api/v1/tm/profile/team_default")
    assert r.status_code == 400 and "Company Name" in r.json()["error"]
    saved = []
    monkeypatch.setattr(fa, "_save_tenant_profile", lambda p, email=None: saved.append(p) or True)
    monkeypatch.setattr(fa, "_get_company_logo_path", lambda: "")
    api["cfg"]["company_name"] = "ThriveModal"
    r = c("post", "/api/v1/tm/profile/team_default")
    assert r.status_code == 200 and "thrivemodal.com" in r.json()["message"]
    assert saved[0]["company_name"] == "ThriveModal"


# ── Settings: Company Profile + Email & AI Setup ───────────────────────────

def test_settings_read_has_the_page_values_and_no_credentials(api, monkeypatch):
    monkeypatch.setattr(fa, "_user_sig_path", lambda: api["tmp"] / "sig.txt")
    monkeypatch.setattr(fa, "_get_user_record",
                        lambda e: {"name": "Rep", "phone": "555", "password": "h"})
    api["cfg"].update({"ai_style_guide": "No dashes.", "daily_send_limit": 120,
                       "newsletter_personal_note": "Hi all",
                       "dismissed_help_strips": ["a", "b"],
                       "smtp_password": "secret"})
    j = api["call"]("get", "/api/v1/tm/settings").json()
    assert j["user"] == {"email": _OWNER, "name": "Rep", "phone": "555"}
    assert j["ai_style_guide"] == "No dashes." and j["daily_send_limit"] == 120
    assert j["newsletter_note"] == "Hi all" and j["dismissed_page_guides"] == 2
    assert "secret" not in json.dumps(j) and "password" not in json.dumps(j)


def test_settings_update_new_fields(api, monkeypatch):
    calls = []
    monkeypatch.setattr(fa, "_get_user_record", lambda e: {"name": "Rep", "phone": "1"})
    monkeypatch.setattr(fa, "_update_user_profile",
                        lambda e, **kw: calls.append((e, kw)) or True)
    c, cfg = api["call"], api["cfg"]
    assert c("post", "/api/v1/tm/settings", {"user": {"name": " "}}).status_code == 400
    assert c("post", "/api/v1/tm/settings", {"user": {"email": "x"}}).status_code == 400
    assert c("post", "/api/v1/tm/settings",
             {"daily_send_limit": "lots"}).status_code == 400
    assert calls == []
    cfg["dismissed_help_strips"] = ["x"]
    r = c("post", "/api/v1/tm/settings", {
        "user": {"phone": "555"}, "newsletter_note": " Thanks ",
        "ai_style_guide": "- No dashes", "daily_send_limit": 900,
        "restore_page_guides": True})
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == ["user", "newsletter_note", "ai_style_guide",
                                   "daily_send_limit", "page_guides"]
    assert calls == [(_OWNER, {"name": "Rep", "phone": "555"})]
    assert cfg["newsletter_personal_note"] == "Thanks"
    assert cfg["ai_style_guide"] == "- No dashes"
    assert cfg["daily_send_limit"] == 500 == r.json()["daily_send_limit"]
    assert cfg["dismissed_help_strips"] == []


# ── the connector side ─────────────────────────────────────────────────────

def test_client_routes_each_action_to_its_door(monkeypatch):
    client_mod = pytest.importorskip("mcp_server.dripdrop_client")
    seen = []

    async def get(self, path, params=None, timeout=60.0):
        seen.append(("get", path))
        return {}

    async def post(self, path, body, timeout=60.0):
        seen.append(("post", path, body.get("action")))
        return {}
    monkeypatch.setattr(client_mod.DripDropClient, "_tm_get", get)
    monkeypatch.setattr(client_mod.DripDropClient, "_tm_post", post)
    cl = object.__new__(client_mod.DripDropClient)
    import asyncio
    for body in ({}, {"action": "build"}):
        asyncio.run(cl.tm_ai_prompt(body))
    for a in ("get", "update", "autofill", "team_default"):
        asyncio.run(cl.tm_playbook({"action": a}))
    assert seen == [("get", "ai_prompt"), ("post", "ai_prompt", "build"),
                    ("get", "playbook"), ("post", "playbook", "update"),
                    ("post", "profile/autofill", "autofill"),
                    ("post", "profile/team_default", "team_default")]
