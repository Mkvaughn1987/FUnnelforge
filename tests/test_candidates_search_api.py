"""GET /api/v1/candidates/search: MCP-facing team-wide Pipeline (ATS) search.

Replaces the old per-user "Top Candidates" pool. Auth via API key, then
gated by `_ats_allowed` (this route exposes Mike's real ATS bench, which is
only visible in-app to arenastaffing.net + a short allowlist). Backed
directly by ats.keyword_search(owner=None) - team-wide, same as the in-app
"Search my ATS/Pipeline" picker.

IMPORTANT: route tests mount the handler on a *minimal* Starlette app, never
flowdrip_app's real `app` (boots NiceGUI lifespan side effects that pollute
the whole suite).
"""
import sqlite3
import sys

import pytest

import flowdrip_app as fa

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

_ALLOWED_OWNER = "elizabeth.simonov@arenastaffing.net"
_OTHER_TENANT = "someone@othercompany.com"


@pytest.fixture
def ats_mod(tmp_path, monkeypatch):
    db = tmp_path / "ats.db"
    con = sqlite3.connect(str(db))
    con.executescript(_SCHEMA)
    con.commit()
    con.close()
    monkeypatch.setenv("ATS_DB_PATH", str(db))
    if "ats" in sys.modules:
        del sys.modules["ats"]
    import ats
    monkeypatch.setattr(ats, "_ai_parse_resume", lambda text: {
        "first_name": "Jane", "last_name": "Doe", "email": "jane.doe@example.com",
        "phone": "555-1234", "city": "Denver", "state": "CO",
        "current_title": "Senior Project Manager", "current_employer": "Acme Construction",
        "key_skills": ["scheduling", "budgeting"], "summary": "Commercial PM.",
    })
    return ats


@pytest.fixture
def _keys(tmp_path, monkeypatch):
    keys = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: keys)


def _client():
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    app = Starlette(routes=[
        Route("/api/v1/candidates/search", fa.api_candidates_search, methods=["GET"]),
    ])
    return TestClient(app)


def test_route_rejects_missing_key(ats_mod, _keys):
    r = _client().get("/api/v1/candidates/search", params={"q": "project manager"})
    assert r.status_code == 401


def test_route_rejects_non_ats_allowed_caller(ats_mod, _keys):
    key = fa._mint_api_key(_OTHER_TENANT)
    r = _client().get("/api/v1/candidates/search",
                       headers={"X-API-Key": key}, params={"q": "project manager"})
    assert r.status_code == 403


def test_route_returns_team_wide_matches(ats_mod, _keys):
    files = [("jane.txt", (
        "JANE DOE\nSenior Project Manager\nDenver, CO\n\n"
        "EXPERIENCE\nSenior Project Manager, Acme Construction, 2018-Present\n"
        "SKILLS: scheduling, budgeting, OSHA, Procore.\n"
    ).encode("utf-8"))]
    ats_mod.ingest_resumes(files, "other.owner@arenastaffing.net", "Elizabeth", rebuild=True)

    key = fa._mint_api_key(_ALLOWED_OWNER)
    r = _client().get("/api/v1/candidates/search",
                       headers={"X-API-Key": key}, params={"q": "project manager"})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["first_name"] == "Jane"
    assert body[0]["last_name"] == "Doe"


def test_empty_query_returns_empty_list(ats_mod, _keys):
    key = fa._mint_api_key(_ALLOWED_OWNER)
    r = _client().get("/api/v1/candidates/search", headers={"X-API-Key": key})
    assert r.status_code == 200
    assert r.json() == []
