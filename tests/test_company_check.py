"""Skip check: Current Clients and companies the team worked in the last 30
days come out before the AI spends research or ZoomInfo credits on them."""
import json
from datetime import date, timedelta

import pytest

import company_check as cc
import team_campaigns as tc

TODAY = date.today()
RECENT = (TODAY - timedelta(days=3)).isoformat()
OLD = (TODAY - timedelta(days=45)).isoformat()


def _camp(root, owner_dir, name, start, contacts, **extra):
    d = root / owner_dir / "Campaigns"
    d.mkdir(parents=True, exist_ok=True)
    camp = {"name": name, "start_date": start, "contacts": contacts}
    camp.update(extra)
    (d / (name.replace(" ", "_") + ".json")).write_text(json.dumps(camp), encoding="utf-8")


def _seed_campaigns(root):
    _camp(root, "sarah_at_arena_net", "CO - Galloway - Civil PE", RECENT, [
        {"email": "carl@gallowayus.com", "company": "Galloway & Company"}])
    _camp(root, "luke_at_arena_net", "Old Acme run", OLD, [
        {"email": "pat@acmefoods.com", "company": "Acme Foods"}])
    _camp(root, "luke_at_arena_net", "CO Newsletter", RECENT, [
        {"email": "nina@buildco.com", "company": "BuildCo"}], evergreen_only=True)


CLIENTS = [
    {"domain": "kiewit.com", "client_name": "Kiewit Corporation", "active": True},
    {"domain": "oldclient.com", "client_name": "Old Client", "active": False},
    {"domain": "xl.com", "client_name": "XL", "active": True},
]


def test_name_key_and_query_domain():
    assert cc.name_key("Galloway & Company, Inc.") == "galloway"
    assert cc.name_key("The Kiewit Corporation") == "kiewit"
    assert cc.query_domain("https://www.GallowayUS.com/about") == "gallowayus.com"
    assert cc.query_domain("@kiewit.com") == "kiewit.com"
    assert cc.query_domain("jo@mail.kiewit.com") == "mail.kiewit.com"
    assert cc.query_domain("Galloway & Company") == ""


def test_client_match_by_domain_name_and_label():
    assert cc.client_match("kiewit.com", CLIENTS)["client_name"] == "Kiewit Corporation"
    assert cc.client_match("infra.kiewit.com", CLIENTS)["domain"] == "kiewit.com"
    assert cc.client_match("Kiewit", CLIENTS)["client_name"] == "Kiewit Corporation"
    assert cc.client_match("Kiewit Infrastructure Group", CLIENTS) is not None
    # Inactive clients and partial words do not count.
    assert cc.client_match("Old Client", CLIENTS) is None
    assert cc.client_match("Kiewitz Labs", CLIENTS) is None
    # A short name only matches exactly, never inside a longer one.
    assert cc.client_match("XL", CLIENTS) is not None
    assert cc.client_match("XL Fabrication", CLIENTS) is None


def test_check_flags_team_campaigns_inside_the_window(tmp_path):
    _seed_campaigns(tmp_path)
    recs = tc.team_campaigns(tmp_path, "mike@arena.net")
    r = cc.check("Galloway", [], recs)
    assert r["verdict"] == "skip" and r["current_client"] is None
    w = r["already_worked"]
    assert w["rep"] == "Sarah" and w["campaign"] == "CO - Galloway - Civil PE"
    assert w["opens_again"] == (TODAY - timedelta(days=3) + timedelta(days=30)).isoformat()
    assert "Sarah" in r["reason"] and "opens again" in r["reason"]
    assert cc.check("gallowayus.com", [], recs)["verdict"] == "skip"
    # Past the 30 days, newsletters, and unknown companies are fine.
    assert cc.check("Acme Foods", [], recs)["verdict"] == "ok"
    assert cc.check("BuildCo", [], recs)["verdict"] == "ok"
    ok = cc.check("Nobody Inc", CLIENTS, recs)
    assert ok == {"query": "Nobody Inc", "verdict": "ok", "current_client": None,
                  "already_worked": None, "reason": ""}


def test_check_reports_both_reasons():
    rec = {"company": "Kiewit", "domains": ["kiewit.com"], "owner": "Luke",
           "campaign": "Kiewit 5x5", "started": RECENT, "status": "cancelled"}
    r = cc.check("kiewit.com", CLIENTS, [rec])
    assert r["current_client"]["client_name"] == "Kiewit Corporation"
    assert r["already_worked"]["status"] == "cancelled"
    assert r["reason"].startswith("Kiewit Corporation is a Current Client.")


# ── API ──────────────────────────────────────────────────────────────────

@pytest.fixture
def api(with_user, tmp_path, monkeypatch):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "_api_keys_path", lambda: tmp_path / "api_keys.json")
    _seed_campaigns(fa._BASE_DATA_DIR / "users")
    fa.add_client_to_blocklist("kiewit.com", "Kiewit Corporation", actor_email="mike@arena.net")
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    client = TestClient(Starlette(routes=[
        Route("/api/v1/skip_check", fa.api_skip_check, methods=["POST"]),
        Route("/api/v1/team_contacts", fa.api_team_contacts, methods=["GET"])]))
    return fa, client, {"X-API-Key": fa._mint_api_key("mike@arena.net")}


def test_api_skip_check(api):
    fa, client, h = api
    assert client.post("/api/v1/skip_check", json={"companies": ["x"]}).status_code == 401
    assert client.post("/api/v1/skip_check", json={"companies": "x"}, headers=h).status_code == 400
    assert client.post("/api/v1/skip_check", json={"companies": []}, headers=h).status_code == 400
    r = client.post("/api/v1/skip_check", headers=h, json={
        "companies": ["Kiewit", "gallowayus.com", "Acme Foods", "New Co"]})
    body = r.json()
    assert r.status_code == 200 and body["skip_count"] == 2 and body["ok_count"] == 2
    assert body["ok"] == ["Acme Foods", "New Co"]
    by = {x["query"]: x for x in body["results"]}
    assert by["Kiewit"]["current_client"]["domain"] == "kiewit.com"
    assert by["gallowayus.com"]["already_worked"]["rep"] == "Sarah"
    # A bare list body works too; another team sees none of Arena's records.
    other = {"X-API-Key": fa._mint_api_key("bob@other.com")}
    r = client.post("/api/v1/skip_check", headers=other, json=["Kiewit", "Galloway"])
    assert r.json()["skip_count"] == 0


def test_api_team_contacts_carries_the_verdict(api):
    fa, client, h = api
    body = client.get("/api/v1/team_contacts?q=gallowayus.com", headers=h).json()
    assert body["verdict"] == "skip" and body["already_worked"]["rep"] == "Sarah"
    assert body["note"].startswith("Skip this company") and "pull anyone" in body["note"]
    body = client.get("/api/v1/team_contacts?q=kiewit.com", headers=h).json()
    assert body["current_client"]["client_name"] == "Kiewit Corporation"
    body = client.get("/api/v1/team_contacts?q=acmefoods.com", headers=h).json()
    assert body["verdict"] == "ok" and body["current_client"] is None
    assert "before ZoomInfo" in body["note"]


def test_create_campaign_drops_current_client_contacts(api):
    fa, _client, _h = api
    kept, skipped = fa._split_current_clients([
        {"email": "a@kiewit.com"}, {"email": "b@infra.kiewit.com"},
        {"email": "c@newco.com"}, {"Email": "d@gmail.com"}], "mike@arena.net")
    assert [c.get("email") or c.get("Email") for c in kept] == ["c@newco.com", "d@gmail.com"]
    assert len(skipped) == 2
    assert fa._client_skip_reason(skipped) == (
        "Dropped 2 contact(s) at Current Clients: Kiewit Corporation.")
    # No clients on file: nothing changes.
    kept, skipped = fa._split_current_clients([{"email": "a@kiewit.com"}], "bob@other.com")
    assert len(kept) == 1 and skipped == []


# ── connector + prompts ──────────────────────────────────────────────────

def test_connector_and_prompts_use_skip_check():
    import pathlib
    import ai_prompts as aip
    import staffing_prompts as sp
    import zoominfo_pull as zp
    root = pathlib.Path(__file__).resolve().parent.parent
    mcp_src = (root / "mcp_server" / "dripdrop_mcp.py").read_text(encoding="utf-8")
    assert "async def skip_check(companies: list[str])" in mcp_src
    assert "current_client" in mcp_src and "current_clients" in mcp_src
    from mcp_server.dripdrop_client import DripDropClient
    assert callable(getattr(DripDropClient, "skip_check", None))
    assert "skip_check" in zp.SKIP_CHECK_RULE and "Current Clients" in zp.SKIP_CHECK_RULE
    assert "verdict skip" in zp.BANK_FIRST_RULE
    assert "{" not in zp.SKIP_CHECK_RULE and "}" not in zp.SKIP_CHECK_RULE
    assert aip.ARENA.skip_rule == zp.SKIP_CHECK_RULE == sp.STAFFING.skip_rule


def test_skip_clause_adds_the_rule_only_for_arena():
    import ai_prompts as aip
    import zoominfo_pull as zp
    r = {"fields": aip.SKIP_FIELDS,
         "field_by_key": {f["key"]: f for f in aip.SKIP_FIELDS}}
    on = {"skip_worked": True, "skip_customers": True, "skip_recruiters": True}
    assert aip._skip_clause(r, on, aip.ARENA).endswith(zp.SKIP_CHECK_RULE)
    assert zp.SKIP_CHECK_RULE not in aip._skip_clause(r, on)
    only_recruiters = {"skip_worked": False, "skip_customers": False, "skip_recruiters": True}
    assert zp.SKIP_CHECK_RULE not in aip._skip_clause(r, only_recruiters, aip.ARENA)
    named = dict(on, only_these="Acme, Kiewit")
    assert aip._skip_clause(r, named, aip.ARENA).endswith(zp.SKIP_CHECK_RULE)
