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
        # Uncommented as each task lands (plan Tasks 5-7):
        # Route("/oauth/register", fa.oauth_register, methods=["POST"]),
        # Route("/oauth/authorize", fa.oauth_authorize_get, methods=["GET"]),
        # Route("/oauth/authorize", fa.oauth_authorize_post, methods=["POST"]),
        # Route("/oauth/token", fa.oauth_token, methods=["POST"]),
        # Route("/.well-known/oauth-authorization-server", fa.oauth_metadata, methods=["GET"]),
        # Route("/.well-known/oauth-protected-resource", fa.oauth_resource_metadata, methods=["GET"]),
        # Route("/mcp", fa.api_mcp, methods=["POST"]),
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
