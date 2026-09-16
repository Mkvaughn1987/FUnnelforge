"""Resume import API: POST /api/v1/candidates/import (+ count).

Both routes are thin server-to-server wrappers around ats.py's Pipeline
ingest/count - the same shared bench the in-app ATS/Pipeline tab uses.
Gated by `_ats_allowed` (only arenastaffing.net + a short allowlist may
write to or count the Pipeline via this key-authed path).

IMPORTANT: route tests mount the two handlers on a *minimal* Starlette app,
NOT flowdrip_app's real `app`. Spinning the real NiceGUI app via TestClient
starts its lifespan (leader election, email/timer threads) and pollutes every
later test in the suite. A bare app gives identical route coverage with no
side effects.
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

_SAMPLE = (
    "JANE DOE\nSenior Project Manager\nDenver, CO\njane.doe@example.com · 555-1234\n\n"
    "EXPERIENCE\nSenior Project Manager, Acme Construction, 2018-Present\n"
    "Led commercial builds, managed budgets and subcontractor schedules.\n"
    "SKILLS: scheduling, budgeting, OSHA, Procore.\n"
)


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
    """A minimal Starlette app hosting ONLY the two candidate routes, so the
    real NiceGUI app (and its startup side effects) never boot."""
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    app = Starlette(routes=[
        Route("/api/v1/candidates/import", fa.api_import_candidates,
              methods=["POST"]),
        Route("/api/v1/candidates/count", fa.api_candidates_count,
              methods=["GET"]),
    ])
    return TestClient(app)


# ── import route ────────────────────────────────────────────────────────────

def test_import_route_rejects_missing_key(ats_mod, _keys):
    r = _client().post("/api/v1/candidates/import",
                       files=[("files", ("a.pdf", b"data", "application/pdf"))])
    assert r.status_code == 401


def test_import_route_rejects_non_ats_allowed_caller(ats_mod, _keys):
    key = fa._mint_api_key(_OTHER_TENANT)
    r = _client().post(
        "/api/v1/candidates/import",
        headers={"X-API-Key": key},
        files=[("files", ("jane.txt", _SAMPLE.encode("utf-8"), "text/plain"))],
    )
    assert r.status_code == 403


def test_import_route_happy_path(ats_mod, _keys):
    key = fa._mint_api_key(_ALLOWED_OWNER)
    r = _client().post(
        "/api/v1/candidates/import",
        headers={"X-API-Key": key},
        files=[("files", ("jane.txt", _SAMPLE.encode("utf-8"), "text/plain"))],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["requested"] == 1
    assert body["added"] == 1
    assert body["updated"] == 0
    assert body["skipped"] == 0
    assert body["results"][0]["status"] == "added"
    assert body["results"][0]["name"] == "Jane Doe"

    assert ats_mod.total_count(owner=None) == 1


def test_import_route_marks_duplicate_as_skipped(ats_mod, _keys):
    key = fa._mint_api_key(_ALLOWED_OWNER)
    _client().post(
        "/api/v1/candidates/import",
        headers={"X-API-Key": key},
        files=[("files", ("jane.txt", _SAMPLE.encode("utf-8"), "text/plain"))],
    )
    r = _client().post(
        "/api/v1/candidates/import",
        headers={"X-API-Key": key},
        files=[("files", ("jane-again.txt", _SAMPLE.encode("utf-8"), "text/plain"))],
    )
    body = r.json()
    assert body["results"][0]["status"] in ("skipped", "updated")
    assert ats_mod.total_count(owner=None) == 1


def test_import_route_unreadable_file_is_skipped_not_a_batch_failure(ats_mod, _keys):
    key = fa._mint_api_key(_ALLOWED_OWNER)
    r = _client().post(
        "/api/v1/candidates/import",
        headers={"X-API-Key": key},
        files=[("files", ("blank.txt", b"hi", "text/plain"))],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["requested"] == 1
    assert body["added"] == 0
    assert body["skipped"] == 1
    assert body["results"][0]["status"] == "skipped"


# ── count route ──────────────────────────────────────────────────────────────

def test_count_endpoint_rejects_missing_key(ats_mod, _keys):
    r = _client().get("/api/v1/candidates/count")
    assert r.status_code == 401


def test_count_endpoint_rejects_non_ats_allowed_caller(ats_mod, _keys):
    key = fa._mint_api_key(_OTHER_TENANT)
    r = _client().get("/api/v1/candidates/count", headers={"X-API-Key": key})
    assert r.status_code == 403


def test_count_endpoint_returns_ats_total(ats_mod, _keys):
    ats_mod.ingest_resumes([("jane.txt", _SAMPLE.encode("utf-8"))],
                           "other.owner@arenastaffing.net", "Elizabeth", rebuild=True)

    key = fa._mint_api_key(_ALLOWED_OWNER)
    r = _client().get("/api/v1/candidates/count", headers={"X-API-Key": key})
    assert r.status_code == 200
    assert r.json() == {"total": 1}
