"""HTTP surface: seed route, OAuth endpoints, /mcp JSON-RPC.
Spec: docs/superpowers/specs/2026-07-21-pipelineblast-app-connector-design.md
Plan: docs/superpowers/plans/2026-07-21-pipelineblast-app-connector.md
"""
import json

import pytest
import flowdrip_app as fa
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient


def _client():
    return TestClient(Starlette(routes=[
        Route("/api/v1/master/import", fa.api_master_import, methods=["POST"]),
        Route("/oauth/register", fa.oauth_register, methods=["POST"]),
        Route("/oauth/authorize", fa.oauth_authorize_get, methods=["GET"]),
        Route("/oauth/authorize", fa.oauth_authorize_post, methods=["POST"]),
        Route("/oauth/token", fa.oauth_token, methods=["POST"]),
        Route("/.well-known/oauth-authorization-server", fa.oauth_metadata, methods=["GET"]),
        Route("/.well-known/oauth-protected-resource", fa.oauth_resource_metadata, methods=["GET"]),
        Route("/mcp", fa.api_mcp, methods=["POST"]),
    ]))


@pytest.fixture()
def bdc_db(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, "_bdc_db_path", lambda: tmp_path / "bd.db")


@pytest.fixture()
def api_key(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, "_api_keys_path", lambda: tmp_path / "api_keys.json")
    return fa._mint_api_key("mike@arena.com")


# ── Task 4: seed route ─────────────────────────────────────────────
def test_master_import_requires_super_admin(bdc_db, api_key, monkeypatch):
    monkeypatch.setattr(fa, "_is_super_admin", lambda e=None: False)
    r = _client().post("/api/v1/master/import", content="Company\nAcme\n",
                       headers={"Authorization": f"Bearer {api_key}"})
    assert r.status_code == 403


def test_master_import_requires_key(bdc_db):
    r = _client().post("/api/v1/master/import", content="Company\nAcme\n")
    assert r.status_code == 401


def test_master_import_seeds(bdc_db, api_key, monkeypatch):
    monkeypatch.setattr(fa, "_is_super_admin", lambda e=None: True)
    csv_body = "Company,City,Type,Week Surfaced,Date,Status\nAcme Co,Denver,GC,w,d,s\n"
    r = _client().post("/api/v1/master/import", content=csv_body,
                       headers={"Authorization": f"Bearer {api_key}"})
    assert r.status_code == 200 and r.json() == {"added": 1, "skipped": 0}


# ── Task 6: OAuth endpoints ────────────────────────────────────────
def test_oauth_full_flow(bdc_db, monkeypatch):
    import base64, hashlib
    c = _client()
    # 1. dynamic client registration
    r = c.post("/oauth/register", json={
        "client_name": "Claude",
        "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"]})
    assert r.status_code == 201
    cid = r.json()["client_id"]
    # 2. authorize GET renders the login form with hidden params
    verifier = "s" * 64
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    q = {"client_id": cid, "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
         "response_type": "code", "state": "xyz",
         "code_challenge": challenge, "code_challenge_method": "S256"}
    r = c.get("/oauth/authorize", params=q)
    assert r.status_code == 200 and 'name="password"' in r.text
    # 3. authorize POST with valid creds redirects back with a code
    monkeypatch.setattr(fa, "_load_users",
                        lambda: {"p1@arena.com": {"password": fa._hash_password("pw1")}})
    r = c.post("/oauth/authorize", data={**q, "email": "p1@arena.com", "password": "pw1"},
               follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("https://claude.ai/api/mcp/auth_callback?") and "state=xyz" in loc
    code = [p.split("=")[1] for p in loc.split("?")[1].split("&") if p.startswith("code=")][0]
    # 4. token exchange
    r = c.post("/oauth/token", data={"grant_type": "authorization_code", "code": code,
                                     "client_id": cid, "code_verifier": verifier,
                                     "redirect_uri": "https://claude.ai/api/mcp/auth_callback"})
    body = r.json()
    assert r.status_code == 200 and body["token_type"] == "Bearer"
    assert fa._bdc_resolve_token(body["access_token"]) == "p1@arena.com"
    # 5. refresh grant
    r = c.post("/oauth/token", data={"grant_type": "refresh_token",
                                     "refresh_token": body["refresh_token"],
                                     "client_id": cid})
    assert r.status_code == 200 and fa._bdc_resolve_token(
        r.json()["access_token"]) == "p1@arena.com"


def test_oauth_bad_password_rerenders_form(bdc_db, monkeypatch):
    monkeypatch.setattr(fa, "_load_users",
                        lambda: {"p1@arena.com": {"password": fa._hash_password("pw1")}})
    c = _client()
    cid = c.post("/oauth/register",
                 json={"redirect_uris": ["https://claude.ai/cb"]}).json()["client_id"]
    r = c.post("/oauth/authorize", data={
        "client_id": cid, "redirect_uri": "https://claude.ai/cb", "response_type": "code",
        "state": "s", "code_challenge": "c", "code_challenge_method": "S256",
        "email": "p1@arena.com", "password": "WRONG"}, follow_redirects=False)
    assert r.status_code == 200 and "try again" in r.text.lower()


def test_oauth_unregistered_redirect_uri_rejected(bdc_db):
    c = _client()
    cid = c.post("/oauth/register",
                 json={"redirect_uris": ["https://claude.ai/cb"]}).json()["client_id"]
    r = c.get("/oauth/authorize", params={"client_id": cid,
              "redirect_uri": "https://evil.example/cb", "response_type": "code",
              "code_challenge": "c", "code_challenge_method": "S256"})
    assert r.status_code == 400


def test_metadata_documents(bdc_db):
    c = _client()
    m = c.get("/.well-known/oauth-authorization-server").json()
    assert m["authorization_endpoint"].endswith("/oauth/authorize")
    assert m["code_challenge_methods_supported"] == ["S256"]
    p = c.get("/.well-known/oauth-protected-resource").json()
    assert m["issuer"] in p["authorization_servers"]


# ── Task 7: MCP JSON-RPC endpoint ──────────────────────────────────
def _rpc(c, token, method, params=None, id=1):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    body = {"jsonrpc": "2.0", "method": method}
    if id is not None:
        body["id"] = id
    if params is not None:
        body["params"] = params
    return c.post("/mcp", json=body, headers=h)


@pytest.fixture()
def mcp_token(bdc_db):
    return fa._bdc_mint_token("p1@arena.com", "cli1", "access", 3600)


def test_mcp_unauthorized_401_with_resource_metadata(bdc_db):
    r = _rpc(_client(), None, "initialize")
    assert r.status_code == 401
    assert "resource_metadata" in r.headers.get("www-authenticate", "")


def test_mcp_initialize_and_tools_list(mcp_token):
    c = _client()
    r = _rpc(c, mcp_token, "initialize",
             {"protocolVersion": "2025-06-18", "capabilities": {},
              "clientInfo": {"name": "claude", "version": "1"}})
    out = r.json()["result"]
    assert out["protocolVersion"] == "2025-06-18"
    assert out["capabilities"]["tools"] == {}
    assert out["serverInfo"]["name"] == "dripdrop"
    r = _rpc(c, mcp_token, "notifications/initialized", id=None)
    assert r.status_code == 202
    tools = {t["name"] for t in _rpc(c, mcp_token, "tools/list").json()["result"]["tools"]}
    assert tools == {"check_companies", "record_companies",
                     "launch_arena_5x3", "list_newsletters"}


def test_mcp_unknown_method_is_32601(mcp_token):
    r = _rpc(_client(), mcp_token, "resources/list")
    assert r.json()["error"]["code"] == -32601


def test_mcp_tool_call_check_companies(mcp_token):
    r = _rpc(_client(), mcp_token, "tools/call",
             {"name": "check_companies", "arguments": {"companies": ["Acme Co"]}})
    out = r.json()["result"]
    assert out["isError"] is False
    assert json.loads(out["content"][0]["text"]) == [
        {"company": "Acme Co", "result": "new"}]


def test_mcp_unknown_tool_is_error_result(mcp_token):
    r = _rpc(_client(), mcp_token, "tools/call", {"name": "nope", "arguments": {}})
    assert r.json()["result"]["isError"] is True


# ── Task 8: launch_arena_5x3 tool ──────────────────────────────────
def test_launch_tool_forces_5x3_and_updates_master(mcp_token, monkeypatch):
    seen = {}

    def fake_core(owner, spec):
        seen.update(owner=owner, spec=spec)
        return {"campaign_id": "camp1", "name": "N", "steps": 5,
                "contacts_queued": 5, "start_date": spec["start_date"],
                "schedule": [], "newsletter_enrollment": {"matched": True}}, 200

    monkeypatch.setattr(fa, "_api_campaign_core", fake_core)
    monkeypatch.setattr(fa, "_bdc_enqueue_tt", lambda *a, **k: 1)
    fa._bdc_record_companies([{"company": "Acme Co"}], added_by="p1@arena.com")
    r = _rpc(_client(), mcp_token, "tools/call", {"name": "launch_arena_5x3",
             "arguments": {"company": "Acme Co", "roles": ["PM"],
                           "start_date": "2026-07-27",
                           "contacts": [{"email": "v@acme.com"}],
                           "enroll_newsletter": "NL", "candidates": [{"x": 1}]}})
    out = json.loads(r.json()["result"]["content"][0]["text"])
    assert out["campaign_id"] == "camp1"
    assert seen["owner"] == "p1@arena.com"
    assert seen["spec"]["template"] == "fivebythree"
    assert "candidates" not in seen["spec"]          # structurally impossible
    assert fa._bdc_check_companies(["Acme Co"])[0]["status"] == "Campaign launched"


def test_launch_tool_skip_updates_master_no_tt(mcp_token, monkeypatch):
    monkeypatch.setattr(fa, "_api_campaign_core",
                        lambda o, s: ({"skipped": True, "reason": "no fit"}, 200))
    called = []
    monkeypatch.setattr(fa, "_bdc_enqueue_tt", lambda *a, **k: called.append(1))
    fa._bdc_record_companies([{"company": "Acme Co"}], added_by="p1@arena.com")
    r = _rpc(_client(), mcp_token, "tools/call", {"name": "launch_arena_5x3",
             "arguments": {"company": "Acme Co", "roles": ["PM"],
                           "start_date": "2026-07-27",
                           "contacts": [{"email": "v@acme.com"}],
                           "enroll_newsletter": "NL"}})
    out = json.loads(r.json()["result"]["content"][0]["text"])
    assert out["skipped"] is True and not called
    assert "skipped (no bench fit)" in fa._bdc_check_companies(["Acme Co"])[0]["status"]


def test_launch_tool_maps_http_errors(mcp_token, monkeypatch):
    monkeypatch.setattr(fa, "_api_campaign_core",
                        lambda o, s: ({"error": "content failed safety guard"}, 422))
    r = _rpc(_client(), mcp_token, "tools/call", {"name": "launch_arena_5x3",
             "arguments": {"company": "A", "roles": ["PM"], "start_date": "2026-07-27",
                           "contacts": [{"email": "v@a.com"}], "enroll_newsletter": "N"}})
    res = r.json()["result"]
    out = json.loads(res["content"][0]["text"])
    assert res["isError"] is True and out["retryable"] is True


# ── Task 9: list_newsletters tool ──────────────────────────────────
def test_list_newsletters_binds_user_and_filters_evergreen(mcp_token, monkeypatch):
    bound = []
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda e: bound.append(e))
    monkeypatch.setattr(fa, "load_campaigns", lambda: [
        {"name": "Recruitment Rundown - CO Construction", "evergreen_only": True},
        {"name": "Some 4x4", "evergreen_only": False}])
    r = _rpc(_client(), mcp_token, "tools/call",
             {"name": "list_newsletters", "arguments": {}})
    out = json.loads(r.json()["result"]["content"][0]["text"])
    assert out == {"newsletters": ["Recruitment Rundown - CO Construction"]}
    assert bound == ["p1@arena.com"]
