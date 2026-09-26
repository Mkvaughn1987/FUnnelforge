"""Connector group B (2026-09-21): the write half of Campaign Styles, saved
audiences, contact lists, sending mailboxes and bulk Clients. Each route
calls the helper its page button calls, behind the same key + gate door."""
import ast
import json
from datetime import date
from pathlib import Path

import pytest

import flowdrip_app as fa

_OWNER = "rep@thrivemodal.com"
_ROOT = Path(__file__).resolve().parent.parent

_TOOLS = ("tm_campaign_styles", "tm_contact_lists", "tm_audiences",
          "tm_mailboxes", "tm_clients")

_ROUTES = [  # (method, path, handler)
    ("get", "/api/v1/tm/campaign_styles", "api_tm_campaign_styles"),
    ("post", "/api/v1/tm/campaign_styles", "api_tm_campaign_style_update"),
    ("get", "/api/v1/tm/audiences", "api_tm_audiences"),
    ("post", "/api/v1/tm/audiences", "api_tm_audience_update"),
    ("get", "/api/v1/tm/mailboxes", "api_tm_mailboxes"),
    ("post", "/api/v1/tm/mailboxes", "api_tm_mailbox_update"),
    ("post", "/api/v1/tm/contact_lists", "api_tm_contact_list_update"),
    ("post", "/api/v1/tm/clients", "api_tm_client_update"),
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


def _app_func(name):
    for n in _tree("flowdrip_app.py").body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


@pytest.mark.parametrize("name", _TOOLS)
def test_every_tool_exists_with_a_client_method(name):
    assert name in _tool_names()
    assert name in _client_methods()


def test_the_old_styles_tool_still_exists():
    assert "my_campaign_styles" in _tool_names()
    assert "my_campaign_styles" in _client_methods()


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


def test_the_mailbox_panel_adds_through_the_shared_helper():
    src = ast.unparse(_app_func("_tm_mailbox_panel"))
    assert "_tm_add_mailbox(" in src
    assert "_TM_PRIMARY_MAILBOX_ID" not in src  # the seeding lives in the helper


# ── harness ────────────────────────────────────────────────────────────────

@pytest.fixture
def api(tmp_path, monkeypatch):
    keys = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: keys)
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *a, **k: None)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    monkeypatch.setattr(fa, "_resolve_user_root", lambda: tmp_path)
    monkeypatch.setattr(fa, "_user_campaign_styles_path",
                        lambda: tmp_path / "campaign_styles.json")
    monkeypatch.setattr(fa, "_user_contacts_dir", lambda: tmp_path / "Contacts")
    monkeypatch.setattr(fa, "_user_contacts_csv_path",
                        lambda: tmp_path / "Contacts" / "contacts.csv")
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
    return {"call": call, "tmp": tmp_path}


@pytest.mark.parametrize("method,path,handler", _ROUTES)
def test_every_route_needs_a_key(api, method, path, handler):
    assert api["call"](method, path, auth=False).status_code == 401


@pytest.mark.parametrize("method,path,handler", _ROUTES)
def test_every_route_is_404_on_arena(api, monkeypatch, method, path, handler):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    assert api["call"](method, path).status_code == 404


# ── Campaign Styles ────────────────────────────────────────────────────────

_STEPS = [{"type": "email", "content": "Warm intro about offshore staffing"},
          {"type": "call", "delay_days": 2, "content": "Quick call"},
          {"type": "linkedin", "delay_days": 3, "content": "Connect note"}]


def test_create_a_style_from_steps_as_the_builder_saves_it(api):
    c = api["call"]
    r = c("post", "/api/v1/tm/campaign_styles",
          {"action": "create", "name": "Warm 3", "steps": _STEPS, "tone": "direct"})
    assert r.status_code == 200, r.text
    new = r.json()["created"]
    want = fa._sb_compile_style_description(
        [{"type": "email", "delay_days": 0, "input": _STEPS[0]["content"]},
         {"type": "call", "delay_days": 2, "input": "Quick call"},
         {"type": "linkedin", "delay_days": 3, "input": "Connect note"}], "direct")
    assert new["description"] == want
    assert set(new) == {"id", "name", "description", "created_at"}
    stored = fa._load_my_campaign_styles()
    assert [s["name"] for s in stored] == ["Warm 3"]
    listed = c("get", "/api/v1/tm/campaign_styles").json()
    assert listed["styles"][0]["id"] == new["id"]
    assert listed["step_types"] == ["email", "call", "linkedin"]


def test_a_created_style_launches_through_style_id(api):
    """create_campaign resolves style_id against the same store."""
    r = api["call"]("post", "/api/v1/tm/campaign_styles",
                    {"action": "create", "name": "Free", "description": "Two emails"})
    sid = r.json()["created"]["id"]
    assert next(s for s in fa._load_my_campaign_styles()
                if s["id"] == sid)["description"] == "Two emails"


@pytest.mark.parametrize("body", [
    {"action": "create", "steps": _STEPS},                            # no name
    {"action": "create", "name": "X"},                                # nothing
    {"action": "create", "name": "X", "steps": []},
    {"action": "create", "name": "X", "steps": [{"type": "fax", "content": "a"}]},
    {"action": "create", "name": "X", "steps": [{"type": "email", "content": ""}]},
    {"action": "create", "name": "X", "steps": _STEPS[:1] + [
        {"type": "email", "delay_days": 0, "content": "b"}]},
    {"action": "create", "name": "X", "steps": [{"content": "a"}] * 16},
    {"action": "create", "name": "X", "steps": _STEPS, "tone": "shouty"},
    {"action": "rename", "name": "X"},
])
def test_style_create_validates_like_the_builder(api, body):
    assert api["call"]("post", "/api/v1/tm/campaign_styles", body).status_code == 400
    assert fa._load_my_campaign_styles() == []


def test_style_names_do_not_duplicate(api):
    c = api["call"]
    c("post", "/api/v1/tm/campaign_styles",
      {"action": "create", "name": "Warm", "description": "d"})
    assert c("post", "/api/v1/tm/campaign_styles",
             {"action": "create", "name": "warm", "description": "d"}).status_code == 409


def test_delete_a_style(api):
    c = api["call"]
    sid = c("post", "/api/v1/tm/campaign_styles",
            {"action": "create", "name": "A", "description": "d"}).json()["created"]["id"]
    c("post", "/api/v1/tm/campaign_styles",
      {"action": "create", "name": "B", "description": "d"})
    assert c("post", "/api/v1/tm/campaign_styles",
             {"action": "delete", "id": "nope"}).status_code == 404
    assert c("post", "/api/v1/tm/campaign_styles",
             {"action": "delete", "id": sid}).status_code == 200
    assert [s["name"] for s in fa._load_my_campaign_styles()] == ["B"]


# ── saved audiences ────────────────────────────────────────────────────────

def test_save_and_delete_an_audience(api):
    c = api["call"]
    r = c("post", "/api/v1/tm/audiences", {
        "action": "save", "name": "Denver Ops",
        "criteria": {"industries": ["Logistics", "logistics"], "junk": 1,
                     "include_unknown": True}})
    assert r.status_code == 200, r.text
    assert r.json()["saved"]["industries"] == ["Logistics"]
    assert "junk" not in r.json()["saved"]
    auds = c("get", "/api/v1/tm/audiences").json()["audiences"]
    assert [a["name"] for a in auds] == ["Denver Ops"]
    c("post", "/api/v1/tm/audiences", {"action": "save", "name": " denver  ops ",
                                        "criteria": {"seniorities": ["VP"]}})
    auds = fa.load_saved_audiences()
    assert len(auds) == 1 and auds[0]["seniorities"] == ["VP"]
    assert c("post", "/api/v1/tm/audiences",
             {"action": "delete", "name": "DENVER OPS"}).status_code == 200
    assert fa.load_saved_audiences() == []
    assert c("post", "/api/v1/tm/audiences",
             {"action": "delete", "name": "gone"}).status_code == 404


def test_audience_save_needs_a_name_and_object_criteria(api):
    c = api["call"]
    assert c("post", "/api/v1/tm/audiences", {"action": "save"}).status_code == 400
    assert c("post", "/api/v1/tm/audiences",
             {"action": "save", "name": "x", "criteria": ["a"]}).status_code == 400
    assert c("post", "/api/v1/tm/audiences", {"action": "x"}).status_code == 400


# ── mailboxes ──────────────────────────────────────────────────────────────

def test_add_seeds_the_primary_and_starts_warmup(api, monkeypatch):
    monkeypatch.setattr(fa, "load_config",
                        lambda: {"ms_email": "me@tm.com", "daily_send_limit": 200})
    r = api["call"]("post", "/api/v1/tm/mailboxes", {
        "action": "add", "email": "b@tm.com", "provider": "google",
        "daily_cap": 100, "warmup_days": 14})
    assert r.status_code == 200, r.text
    assert r.json()["connected"] is False and "Connect" in r.json()["next_step"]
    boxes = fa._tm_load_mailboxes()
    assert [b["id"] for b in boxes] == ["primary", fa._tm_mailbox_id("b@tm.com")]
    assert boxes[0]["email"] == "me@tm.com" and boxes[0]["warmup_days"] == 0
    assert boxes[1]["provider"] == "google" and boxes[1]["daily_cap"] == 100
    assert boxes[1]["warmup_start"] == date.today().isoformat()
    again = api["call"]("post", "/api/v1/tm/mailboxes",
                        {"action": "add", "email": "b@tm.com"})
    assert again.status_code == 409


@pytest.mark.parametrize("body", [
    {"action": "add", "email": "nope"},
    {"action": "add", "email": "a@b.com", "provider": "yahoo"},
    {"action": "add", "email": "a@b.com", "daily_cap": 1000},
    {"action": "add", "email": "a@b.com", "warmup_days": 200},
    {"action": "add", "email": "a@b.com", "daily_cap": "lots"},
    {"action": "explode"},
])
def test_mailbox_add_validates(api, body):
    assert api["call"]("post", "/api/v1/tm/mailboxes", body).status_code == 400
    assert fa._tm_load_mailboxes() == []


def test_pause_resume_and_remove(api, monkeypatch):
    monkeypatch.setattr(fa, "load_config", lambda: {})
    c = api["call"]
    c("post", "/api/v1/tm/mailboxes", {"action": "add", "email": "b@tm.com"})
    mid = fa._tm_mailbox_id("b@tm.com")
    assert c("post", "/api/v1/tm/mailboxes",
             {"action": "pause", "id": mid}).json()["paused"] is True
    assert next(b for b in fa._tm_load_mailboxes() if b["id"] == mid)["paused"]
    c("post", "/api/v1/tm/mailboxes", {"action": "resume", "email": "B@tm.com"})
    assert not next(b for b in fa._tm_load_mailboxes() if b["id"] == mid)["paused"]
    assert c("post", "/api/v1/tm/mailboxes",
             {"action": "remove", "id": "ghost"}).status_code == 404
    assert c("post", "/api/v1/tm/mailboxes",
             {"action": "remove", "id": mid}).status_code == 200
    assert [b["id"] for b in fa._tm_load_mailboxes()] == ["primary"]


def test_mailbox_list_still_reports_budgets(api, monkeypatch):
    """Nothing connected: the primary row is there, but it can send nothing."""
    monkeypatch.setattr(fa, "_tm_analytics_sources", lambda: {"queue": []})
    r = api["call"]("get", "/api/v1/tm/mailboxes")
    body = r.json()
    assert r.status_code == 200 and body["remaining_total"] == 0
    assert body["sender"] == {"email": "", "provider": "", "connected": False}
    assert [b["id"] for b in body["mailboxes"]] == ["primary"]
    assert body["mailboxes"][0]["connected"] is False


def test_mailbox_list_shows_the_connected_gmail_with_no_registry(api, monkeypatch):
    """The bug from the field: Gmail connected, registry empty, and the tool
    said "mailboxes: []" so the agent asked the user to connect an inbox."""
    monkeypatch.setattr(fa, "_tm_analytics_sources", lambda: {"queue": [
        {"status": "sent", "sent_at": f"{date.today().isoformat()}T09:00:00"}]})
    fa.save_config({"gmail_refresh_token": "r", "gmail_access_token": "a",
                    "gmail_email": "mike@inboxslide.ai", "daily_send_limit": 100})
    assert fa._tm_load_mailboxes() == []
    body = api["call"]("get", "/api/v1/tm/mailboxes").json()
    assert body["sender"] == {"email": "mike@inboxslide.ai", "provider": "google",
                              "connected": True}
    (row,) = body["mailboxes"]
    assert row["id"] == "primary" and row["email"] == "mike@inboxslide.ai"
    assert row["connected"] is True and row["provider"] == "google"
    assert row["daily_cap"] == 100 and row["warmup_days"] == 0
    assert body["remaining_today"] == {"primary": 99}
    assert body["remaining_total"] == 99


def test_mailbox_list_stamps_connected_on_a_registered_primary(api, monkeypatch):
    monkeypatch.setattr(fa, "_tm_analytics_sources", lambda: {"queue": []})
    fa.save_config({"gmail_refresh_token": "r", "gmail_email": "mike@inboxslide.ai"})
    api["call"]("post", "/api/v1/tm/mailboxes", {"action": "add", "email": "b@tm.com"})
    rows = {b["id"]: b for b in
            api["call"]("get", "/api/v1/tm/mailboxes").json()["mailboxes"]}
    assert rows["primary"]["connected"] is True
    assert rows["primary"]["provider"] == "google"
    assert "connected" not in rows[fa._tm_mailbox_id("b@tm.com")]


@pytest.mark.parametrize("cfg,want", [
    ({}, {"email": "", "provider": "", "connected": False}),
    ({"gmail_refresh_token": "r", "gmail_email": "g@x.com"},
     {"email": "g@x.com", "provider": "google", "connected": True}),
    ({"ms_access_token": "t", "ms_email": "m@x.com"},
     {"email": "m@x.com", "provider": "microsoft", "connected": True}),
    ({"smtp_email": "s@x.com", "smtp_password": "p"},
     {"email": "s@x.com", "provider": "smtp", "connected": True}),
    ({"smtp_email": "s@x.com"}, {"email": "", "provider": "", "connected": False}),
])
def test_primary_sender_matches_the_setup_gate(cfg, want):
    assert fa._tm_primary_sender(cfg) == want


# ── contact lists ──────────────────────────────────────────────────────────

def _write_list(tmp, name, rows):
    d = tmp / "Contacts"
    d.mkdir(exist_ok=True)
    p = d / f"{name}.csv"
    fa._atomic_write_csv_text(p, fa._contacts_csv_text(rows, fa._CONTACT_COLMAP_SNAKE))
    return p


_ROWS = [{"email": "ann@x.com", "first_name": "Ann", "company": "Acme",
          "city": "Denver", "state": "CO"},
         {"email": "bo@y.com", "first_name": "Bo", "company": "Beta"}]


def test_add_update_and_delete_a_contact_on_a_saved_list(api):
    p = _write_list(api["tmp"], "CPAs", _ROWS)
    c = api["call"]
    r = c("post", "/api/v1/tm/contact_lists", {
        "action": "add_contact", "list": "CPAs",
        "contact": {"Email": "Cy@Z.com", "FirstName": "Cy", "city": "Austin"}})
    assert r.status_code == 200, r.text
    rows = fa.load_contacts(p)
    assert rows[0]["email"] == "cy@z.com" and rows[0]["city"] == "Austin"
    assert rows[1]["city"] == "Denver"  # the page's columns survive the rewrite
    assert c("post", "/api/v1/tm/contact_lists", {
        "action": "add_contact", "list": "CPAs",
        "contact": {"email": "ann@x.com"}}).status_code == 409

    r = c("post", "/api/v1/tm/contact_lists", {
        "action": "update_contact", "list": "CPAs", "email": "ANN@x.com",
        "changes": {"title": "CFO", "state": "UT"}})
    assert r.status_code == 200, r.text
    ann = next(x for x in fa.load_contacts(p) if x["email"] == "ann@x.com")
    assert ann["title"] == "CFO" and ann["state"] == "UT" and ann["company"] == "Acme"
    assert c("post", "/api/v1/tm/contact_lists", {
        "action": "update_contact", "list": "CPAs", "email": "ann@x.com",
        "changes": {"email": "bo@y.com"}}).status_code == 409
    assert c("post", "/api/v1/tm/contact_lists", {
        "action": "update_contact", "list": "CPAs", "email": "ann@x.com",
        "changes": {"favourite": "x"}}).status_code == 400

    assert c("post", "/api/v1/tm/contact_lists", {
        "action": "delete_contact", "list": "CPAs",
        "email": "bo@y.com"}).status_code == 200
    assert [x["email"] for x in fa.load_contacts(p)] == ["cy@z.com", "ann@x.com"]
    assert c("post", "/api/v1/tm/contact_lists", {
        "action": "delete_contact", "list": "CPAs",
        "email": "bo@y.com"}).status_code == 404


def test_blank_list_edits_the_active_list(api):
    c = api["call"]
    r = c("post", "/api/v1/tm/contact_lists",
          {"action": "add_contact", "contact": {"email": "a@x.com"}})
    assert r.status_code == 200 and r.json()["list"] == "(active list)"
    assert [x["email"] for x in fa.load_contacts()] == ["a@x.com"]


def test_delete_list_needs_confirm_and_a_real_list(api):
    p = _write_list(api["tmp"], "Old", _ROWS)
    c = api["call"]
    assert c("post", "/api/v1/tm/contact_lists",
             {"action": "delete_list", "list": "Old"}).status_code == 400
    assert p.exists()
    assert c("post", "/api/v1/tm/contact_lists",
             {"action": "delete_list", "list": "../etc", "confirm": True}).status_code == 404
    assert c("post", "/api/v1/tm/contact_lists",
             {"action": "delete_list", "confirm": True}).status_code == 400
    assert c("post", "/api/v1/tm/contact_lists",
             {"action": "delete_list", "list": "Old", "confirm": True}).status_code == 200
    assert not p.exists()


def test_contact_lists_rejects_unknown_actions(api):
    assert api["call"]("post", "/api/v1/tm/contact_lists",
                       {"action": "rename_list"}).status_code == 400


# ── clients, in bulk ───────────────────────────────────────────────────────

def test_bulk_client_add_goes_row_by_row_like_the_upload(api, monkeypatch):
    seen = []

    def _add(d, **kw):
        seen.append((d, kw))
        return (d != "dup.com"), ("Added." if d != "dup.com" else "already on the list")
    monkeypatch.setattr(fa, "add_client_to_blocklist", _add)
    r = api["call"]("post", "/api/v1/tm/clients", {"action": "add", "clients": [
        "acme.com", {"domain": "dup.com", "name": "Dup"}, 7,
        {"domain": "beta.com", "website": "www.beta.com", "location": "CO"}]})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["added"] == 2 and b["skipped"] == 2
    assert [x["domain"] for x in b["results"]] == ["acme.com", "dup.com", "", "beta.com"]
    assert seen[0][1]["website"] == "acme.com"          # defaults to the domain
    assert seen[2][1]["website"] == "www.beta.com"
    assert all(kw["actor_email"] == _OWNER for _, kw in seen)
    assert seen[1][1]["client_name"] == "Dup"


def test_bulk_client_add_needs_a_list(api):
    c = api["call"]
    assert c("post", "/api/v1/tm/clients",
             {"action": "add", "clients": []}).status_code == 400
    assert c("post", "/api/v1/tm/clients",
             {"action": "add", "clients": "acme.com"}).status_code == 400


# ── the connector side ─────────────────────────────────────────────────────

class _FakeClient:
    calls = []

    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        async def _m(*args):
            _FakeClient.calls.append((name, args))
            return {"ok": True}
        return _m


@pytest.fixture
def mcp_mod(monkeypatch):
    mcp = pytest.importorskip("mcp_server.dripdrop_mcp")
    _FakeClient.calls = []
    monkeypatch.setattr(mcp, "DripDropClient", _FakeClient)
    monkeypatch.setattr(mcp, "_current_email", lambda: _OWNER)
    return mcp


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def _fn(tool):
    return getattr(tool, "fn", tool)


def test_tools_send_the_bodies_the_routes_read(mcp_mod):
    m = mcp_mod
    _run(_fn(m.tm_audiences)())
    _run(_fn(m.tm_audiences)(action="save", name="A", criteria={"industries": ["x"]}))
    _run(_fn(m.tm_mailboxes)())
    _run(_fn(m.tm_mailboxes)(action="pause", mailbox_id="b"))
    _run(_fn(m.tm_campaign_styles)())
    _run(_fn(m.tm_campaign_styles)(action="create", name="S", steps=_STEPS))
    _run(_fn(m.tm_contact_lists)(action="delete_contact", list_name="L", email="a@x.com"))
    _run(_fn(m.tm_clients)(action="add", clients=["a.com"]))
    c = _FakeClient.calls
    assert c[0] == ("tm_audiences", ())
    assert c[1][1][0] == {"action": "save", "name": "A",
                          "criteria": {"industries": ["x"]}}
    assert c[2] == ("tm_mailboxes", ())
    assert c[3][1][0] == {"action": "pause", "email": "", "id": "b"}
    assert c[4] == ("tm_campaign_styles", ())
    assert c[5][1][0]["steps"] == _STEPS and c[5][1][0]["action"] == "create"
    assert c[6][1][0]["list"] == "L" and c[6][1][0]["email"] == "a@x.com"
    assert c[7][1][0]["clients"] == ["a.com"]


def test_client_methods_hit_the_group_b_routes(monkeypatch):
    dc = pytest.importorskip("mcp_server.dripdrop_client")
    monkeypatch.setattr(dc, "resolve_user_api_key", lambda d, e: "k")
    cl = dc.DripDropClient(Path("."), _OWNER, base_url="http://x")
    hits = []

    async def _get(path, params=None, timeout=60.0):
        hits.append(("get", path))
        return {}

    async def _post(path, body, timeout=60.0):
        hits.append(("post", path))
        return {}
    monkeypatch.setattr(cl, "_tm_get", _get)
    monkeypatch.setattr(cl, "_tm_post", _post)
    _run(cl.tm_campaign_styles())
    _run(cl.tm_campaign_styles({"action": "delete", "id": "x"}))
    _run(cl.tm_contact_lists({"action": "delete_list"}))
    _run(cl.tm_audiences({"action": "delete", "name": "x"}))
    _run(cl.tm_mailboxes({"action": "remove", "id": "x"}))
    assert hits == [("get", "campaign_styles"), ("post", "campaign_styles"),
                    ("post", "contact_lists"), ("post", "audiences"),
                    ("post", "mailboxes")]
