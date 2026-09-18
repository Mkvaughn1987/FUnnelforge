"""Passwordless connector sign-in (mcp_server/app_bridge.py) and the MCP
routes that use it."""

import importlib
import json
import sys

import pytest

from mcp_server import app_bridge


@pytest.fixture
def bridge_env(monkeypatch):
    monkeypatch.setenv("DRIPDROP_MCP_BRIDGE_SECRET", "s3cret-for-tests")
    monkeypatch.setenv("DRIPDROP_MCP_APP_AUTHORIZE_URL", "https://app.example/connector/authorize")


def test_disabled_without_env(monkeypatch):
    monkeypatch.delenv("DRIPDROP_MCP_BRIDGE_SECRET", raising=False)
    monkeypatch.delenv("DRIPDROP_MCP_APP_AUTHORIZE_URL", raising=False)
    assert not app_bridge.enabled()
    assert not app_bridge.verify("t", "a@b.c", "9999999999", "x")


def test_round_trip(bridge_env):
    p = app_bridge.sign("tok", " Mike@Example.com ", now=1000)
    assert p["email"] == "mike@example.com"
    assert app_bridge.verify(p["login_token"], p["email"], p["exp"], p["sig"], now=1000)


@pytest.mark.parametrize("field,value", [
    ("login_token", "other"), ("email", "eve@example.com"), ("exp", "99999999999"), ("sig", "0" * 64),
])
def test_tampering_rejected(bridge_env, field, value):
    p = app_bridge.sign("tok", "mike@example.com", now=1000)
    p[field] = value
    assert not app_bridge.verify(p["login_token"], p["email"], p["exp"], p["sig"], now=1000)


def test_expired_rejected(bridge_env):
    p = app_bridge.sign("tok", "mike@example.com", now=1000)
    later = 1000 + app_bridge.SIGNATURE_TTL_SECONDS + 1
    assert not app_bridge.verify(p["login_token"], p["email"], p["exp"], p["sig"], now=later)


def test_wrong_secret_rejected(bridge_env, monkeypatch):
    p = app_bridge.sign("tok", "mike@example.com", now=1000)
    monkeypatch.setenv("DRIPDROP_MCP_BRIDGE_SECRET", "different")
    assert not app_bridge.verify(p["login_token"], p["email"], p["exp"], p["sig"], now=1000)


# ---- MCP routes ---------------------------------------------------------

@pytest.fixture
def mcp_mod(tmp_path, monkeypatch, bridge_env):
    pytest.importorskip("mcp")
    monkeypatch.setenv("DRIPDROP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DRIPDROP_MCP_PUBLIC_URL", "https://mcp.example")
    monkeypatch.setenv("DRIPDROP_BRAND_NAME", "inboxslide")
    (tmp_path / "users.json").write_text(json.dumps({"mike@example.com": {"password": ""}}))
    sys.modules.pop("mcp_server.dripdrop_mcp", None)
    mod = importlib.import_module("mcp_server.dripdrop_mcp")
    yield mod
    sys.modules.pop("mcp_server.dripdrop_mcp", None)


def _pending(mod, token="tok"):
    import time
    mod.auth_provider.pending.put(token, {
        "client_id": "cid", "redirect_uri": "https://claude.ai/cb",
        "redirect_uri_provided_explicitly": True, "code_challenge": "c",
        "scopes": ["dripdrop"], "state": "st", "resource": None,
        "expires_at": time.time() + 300,
    })


def _client(mod):
    from starlette.testclient import TestClient
    return TestClient(mod.mcp.streamable_http_app(), base_url="https://mcp.example")


def test_brand_title(mcp_mod):
    assert mcp_mod.BRAND == "inboxslide"


def test_login_redirects_to_app(mcp_mod):
    _pending(mcp_mod)
    r = _client(mcp_mod).get("/login?login_token=tok", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://app.example/connector/authorize?login_token=tok")


def test_password_post_refused(mcp_mod):
    _pending(mcp_mod)
    r = _client(mcp_mod).post("/login", data={"login_token": "tok", "email": "mike@example.com", "password": "x"})
    assert r.status_code == 403


def test_complete_mints_code(mcp_mod):
    _pending(mcp_mod)
    p = app_bridge.sign("tok", "mike@example.com")
    r = _client(mcp_mod).get("/login/complete", params=p, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://claude.ai/cb?code=")
    assert "state=st" in r.headers["location"]


def test_complete_rejects_bad_sig(mcp_mod):
    _pending(mcp_mod)
    p = app_bridge.sign("tok", "mike@example.com")
    p["sig"] = "0" * 64
    assert _client(mcp_mod).get("/login/complete", params=p, follow_redirects=False).status_code == 400


def test_complete_rejects_unknown_user(mcp_mod):
    _pending(mcp_mod)
    p = app_bridge.sign("tok", "stranger@example.com")
    assert _client(mcp_mod).get("/login/complete", params=p, follow_redirects=False).status_code == 403
