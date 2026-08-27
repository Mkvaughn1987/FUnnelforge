"""Campaign styles discovery: GET /api/v1/campaign_types + /api/v1/campaign_styles.

Both let an MCP caller see what campaign styles exist before calling
create_campaign: the 10 built-in templates (global, non-sensitive), and the
caller's own saved custom "My Campaign Styles" (BYOS descriptions, tenant-
scoped to the calling key's owner).

IMPORTANT: route tests mount the handlers on a *minimal* Starlette app, never
flowdrip_app's real `app` (boots NiceGUI lifespan side effects that pollute
the whole suite).
"""
import json

import pytest

import flowdrip_app as fa

_OWNER_A = "rep.a@arenastaffing.net"
_OWNER_B = "rep.b@arenastaffing.net"


@pytest.fixture(autouse=True)
def _restore_user_ctx():
    """The campaign_styles route binds global user context
    (_CURRENT_USER_EMAIL / _switch_to_user_paths). Snapshot + restore it so
    these tests never leak that state into the rest of the suite."""
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
def _styles_paths(tmp_path, monkeypatch):
    """_load_my_campaign_styles() reads from whichever user's paths are
    currently bound via the ambient _resolve_user_root() - but on this local
    dev machine _resolve_user_root() always falls back to the same base dir
    regardless of _CURRENT_USER_EMAIL, so real per-user isolation has to be
    faked here the same way production per-user paths work: key the file off
    the bound user email."""
    def _path():
        owner = fa._CURRENT_USER_EMAIL.get() or "anon"
        safe = owner.replace("@", "_at_").replace(".", "_")
        return tmp_path / f"{safe}_campaign_styles.json"
    monkeypatch.setattr(fa, "_user_campaign_styles_path", _path)
    return tmp_path


def _write_styles(tmp_path, owner, styles):
    safe = owner.replace("@", "_at_").replace(".", "_")
    (tmp_path / f"{safe}_campaign_styles.json").write_text(
        json.dumps(styles), encoding="utf-8")


def _client():
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    app = Starlette(routes=[
        Route("/api/v1/campaign_types", fa.api_campaign_types, methods=["GET"]),
        Route("/api/v1/campaign_styles", fa.api_campaign_styles, methods=["GET"]),
    ])
    return TestClient(app)


# ── campaign_types ──────────────────────────────────────────────────────────

def test_types_route_rejects_missing_key(_keys):
    r = _client().get("/api/v1/campaign_types")
    assert r.status_code == 401


def test_types_route_returns_all_ten_known_keys(_keys):
    key = fa._mint_api_key(_OWNER_A)
    r = _client().get("/api/v1/campaign_types", headers={"X-API-Key": key})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 10

    keys = {t["key"] for t in body}
    assert keys == {
        "blitz", "fourbyfour", "fivebyfive", "fivebythree", "talentdrop",
        "flood", "sidequest", "fullstream", "victorycard", "byos",
    }
    for t in body:
        assert set(t.keys()) == {"key", "display_name", "description", "best_for"}
        assert t["display_name"]
        assert t["description"]
        assert t["best_for"]


# ── campaign_styles ──────────────────────────────────────────────────────────

def test_styles_route_rejects_missing_key(_keys, _styles_paths):
    r = _client().get("/api/v1/campaign_styles")
    assert r.status_code == 401


def test_styles_route_returns_only_callers_own_styles(_keys, _styles_paths):
    _write_styles(_styles_paths, _OWNER_A, [
        {"id": "1", "name": "A's style", "description": "desc a", "created_at": "2026-08-01"},
    ])
    _write_styles(_styles_paths, _OWNER_B, [
        {"id": "2", "name": "B's style", "description": "desc b", "created_at": "2026-08-02"},
    ])

    key = fa._mint_api_key(_OWNER_A)
    r = _client().get("/api/v1/campaign_styles", headers={"X-API-Key": key})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["name"] == "A's style"


def test_styles_route_empty_for_user_with_none_saved(_keys, _styles_paths):
    key = fa._mint_api_key(_OWNER_B)
    r = _client().get("/api/v1/campaign_styles", headers={"X-API-Key": key})
    assert r.status_code == 200
    assert r.json() == []
