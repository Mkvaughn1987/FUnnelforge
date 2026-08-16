"""Resume import API: POST /api/v1/candidates/import (+ count).

The route is a thin server-to-server wrapper around ats.ingest_resumes / the
same ATS Talent Pool parse+save pipeline the Upload tab uses. Tests pin:
  - a successful import lands in the key owner's ATS Talent Pool (added),
  - short/blank resumes are skipped (never crash the batch),
  - re-importing the same person merges/dedupes instead of duplicating
    (unlike the old append-only Top Candidates pool),
  - the route rejects a missing/invalid key with 401,
  - the route + count happy paths.

IMPORTANT: route tests mount the two handlers on a *minimal* Starlette app,
NOT flowdrip_app's real `app`. Spinning the real NiceGUI app via TestClient
starts its lifespan (leader election, email/timer threads) and pollutes every
later test in the suite. A bare app gives identical route coverage with no
side effects.
"""
import sqlite3
import sys

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

_OWNER = "rep@arena.com"


def _isolate(tmp_path, monkeypatch):
    """Point the ATS db + api-key store at throwaway tmp dirs and stub the
    AI resume parser so nothing hits the network."""
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
        "first_name": "Tim", "last_name": "Cooper", "email": "tim@example.com",
        "phone": "555-0100", "city": "Denver", "state": "CO",
        "current_title": "CNC Machinist", "current_employer": "",
        "key_skills": ["a", "b"], "summary": "",
    })

    keys = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: keys)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "test-key")
    return ats, keys


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


# ── route (minimal app, no NiceGUI lifespan) ───────────────────────────────

def test_route_rejects_missing_key(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    r = _client().post("/api/v1/candidates/import",
                       files=[("files", ("a.pdf", b"data", "application/pdf"))])
    assert r.status_code == 401


def test_route_happy_path(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    key = fa._mint_api_key(_OWNER)
    r = _client().post(
        "/api/v1/candidates/import",
        headers={"X-API-Key": key},
        files=[("files", ("tim.txt", ("x" * 200).encode(), "text/plain"))],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["requested"] == 1
    assert body["added"] == 1
    assert body["updated"] == 0
    assert body["results"][0]["status"] == "added"
    assert body["results"][0]["name"] == "Tim Cooper"


def test_route_skips_unparseable_file(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    key = fa._mint_api_key(_OWNER)
    r = _client().post(
        "/api/v1/candidates/import",
        headers={"X-API-Key": key},
        files=[("files", ("blank.txt", b"hi", "text/plain"))],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["added"] == 0
    assert body["results"][0]["status"] == "skipped"


def test_import_is_dedupe_not_append_only(tmp_path, monkeypatch):
    """Unlike the old Top Candidates pool, importing the same person twice
    merges/dedupes in the ATS instead of creating two records."""
    _isolate(tmp_path, monkeypatch)
    key = fa._mint_api_key(_OWNER)
    client = _client()
    for _ in range(2):
        r = client.post(
            "/api/v1/candidates/import",
            headers={"X-API-Key": key},
            files=[("files", ("tim.txt", ("x" * 200).encode(), "text/plain"))],
        )
    assert r.status_code == 200
    r2 = client.get("/api/v1/candidates/count", headers={"X-API-Key": key})
    assert r2.json()["total"] == 1


def test_count_endpoint(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    key = fa._mint_api_key(_OWNER)
    client = _client()
    client.post(
        "/api/v1/candidates/import",
        headers={"X-API-Key": key},
        files=[("files", ("tim.txt", ("x" * 200).encode(), "text/plain"))],
    )
    r = client.get("/api/v1/candidates/count", headers={"X-API-Key": key})
    assert r.status_code == 200
    body = r.json()
    assert body["active"] == 1
    assert body["total"] == 1
