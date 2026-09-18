"""GET /api/v1/campaigns (list) + GET /api/v1/campaigns/{campaign_id}
(detail) - read-only, tenant-scoped visibility into the calling account's
own launched campaigns. Lets an MCP caller see what already exists (and
find a campaign_id) before creating a new one via create_campaign.

IMPORTANT: route tests mount the handlers on a *minimal* Starlette app,
never flowdrip_app's real `app` (boots NiceGUI lifespan side effects that
pollute the whole suite) - same pattern as test_campaign_styles_api.py.
"""
import urllib.parse

import pytest

import flowdrip_app as fa

_OWNER_A = "rep.a@arenastaffing.net"
_OWNER_B = "rep.b@arenastaffing.net"

_CAMPAIGNS = {
    _OWNER_A: [
        {"_path": "/data/a1.json", "name": "Acme - Plant Manager",
         "template_key": "fourbyfour", "start_date": "2026-08-01",
         "emails": [{"subject": "s1"}, {"subject": "s2"}],
         "contacts": [{"email": "vp@acme.com"}]},
    ],
    _OWNER_B: [
        {"_path": "/data/b1.json", "name": "Beta - Senior Plant Manager",
         "template_key": "findcandidates", "start_date": "2026-08-05",
         "emails": [{"subject": "s1"}],
         "contacts": [{"email": "cand@beta.com"}]},
    ],
}

_QUEUE = {
    _OWNER_A: [
        {"campaign": "Acme - Plant Manager", "status": "sent"},
        {"campaign": "Acme - Plant Manager", "status": "pending"},
        {"campaign": "Acme - Plant Manager", "status": "pending"},
    ],
    _OWNER_B: [
        {"campaign": "Beta - Senior Plant Manager", "status": "failed"},
    ],
}


@pytest.fixture(autouse=True)
def _restore_user_ctx():
    try:
        before = fa._CURRENT_USER_EMAIL.get()
    except Exception:
        before = None
    yield
    try:
        fa._CURRENT_USER_EMAIL.set(before)
    except Exception:
        pass


@pytest.fixture
def _keys(tmp_path, monkeypatch):
    keys = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: keys)


@pytest.fixture
def _data(monkeypatch):
    """load_campaigns()/_load_queue() are keyed off whatever _CURRENT_USER_EMAIL
    the route just bound - fakes real per-tenant storage without needing a
    working _resolve_user_root() on this dev machine (see
    test_campaign_styles_api.py's _styles_paths fixture for the same caveat)."""
    def _campaigns():
        owner = fa._CURRENT_USER_EMAIL.get()
        return [dict(c) for c in _CAMPAIGNS.get(owner, [])]

    def _queue():
        owner = fa._CURRENT_USER_EMAIL.get()
        return list(_QUEUE.get(owner, []))

    monkeypatch.setattr(fa, "load_campaigns", _campaigns)
    monkeypatch.setattr(fa, "_load_queue", _queue)
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *a, **k: None)


def _client():
    # api_campaign_get takes campaign_id as its own function argument (FastAPI
    # path-param injection), not just `request` - a raw Starlette Route can't
    # call it that way, so mount on a real FastAPI app instead.
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    app = FastAPI()
    app.get("/api/v1/campaigns")(fa.api_campaigns_list)
    app.get("/api/v1/campaigns/{campaign_id}")(fa.api_campaign_get)
    return TestClient(app)


# ── campaigns_list ───────────────────────────────────────────────────────

def test_list_rejects_missing_key(_keys, _data):
    r = _client().get("/api/v1/campaigns")
    assert r.status_code == 401


def test_list_returns_only_callers_own_campaigns_with_queue_stats(_keys, _data):
    key = fa._mint_api_key(_OWNER_A)
    r = _client().get("/api/v1/campaigns", headers={"X-API-Key": key})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    c = body[0]
    assert c["campaign_id"] == "a1"
    assert c["name"] == "Acme - Plant Manager"
    assert c["template"] == "fourbyfour"
    assert c["start_date"] == "2026-08-01"
    assert c["steps"] == 2
    assert c["contacts"] == 1
    assert c["queue"] == {"pending": 2, "sent": 1, "failed": 0, "cancelled": 0}


def test_list_never_leaks_another_owners_campaigns(_keys, _data):
    key = fa._mint_api_key(_OWNER_B)
    r = _client().get("/api/v1/campaigns", headers={"X-API-Key": key})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["name"] == "Beta - Senior Plant Manager"
    assert body[0]["template"] == "findcandidates"


def test_list_empty_for_owner_with_no_campaigns(_keys, _data):
    key = fa._mint_api_key("nobody@arenastaffing.net")
    r = _client().get("/api/v1/campaigns", headers={"X-API-Key": key})
    assert r.status_code == 200
    assert r.json() == []


# ── campaign_get ─────────────────────────────────────────────────────────

def test_get_rejects_missing_key(_keys, _data):
    r = _client().get("/api/v1/campaigns/a1")
    assert r.status_code == 401


def test_get_returns_full_detail_by_campaign_id(_keys, _data):
    key = fa._mint_api_key(_OWNER_A)
    r = _client().get("/api/v1/campaigns/a1", headers={"X-API-Key": key})
    assert r.status_code == 200
    body = r.json()
    assert body["campaign_id"] == "a1"
    assert body["name"] == "Acme - Plant Manager"
    assert body["emails"] == [{"subject": "s1"}, {"subject": "s2"}]
    assert body["contacts"] == [{"email": "vp@acme.com"}]
    assert body["queue"] == {"pending": 2, "sent": 1, "failed": 0, "cancelled": 0}


def test_get_by_campaign_name_also_works(_keys, _data):
    key = fa._mint_api_key(_OWNER_A)
    name = urllib.parse.quote("Acme - Plant Manager")
    r = _client().get(f"/api/v1/campaigns/{name}", headers={"X-API-Key": key})
    assert r.status_code == 200
    assert r.json()["campaign_id"] == "a1"


def test_get_404_for_unknown_id(_keys, _data):
    key = fa._mint_api_key(_OWNER_A)
    r = _client().get("/api/v1/campaigns/nope", headers={"X-API-Key": key})
    assert r.status_code == 404


def test_get_cannot_see_other_owners_campaign_by_id(_keys, _data):
    key = fa._mint_api_key(_OWNER_A)
    r = _client().get("/api/v1/campaigns/b1", headers={"X-API-Key": key})
    assert r.status_code == 404
