"""Candidate read/search API: GET /api/v1/candidates/search,
GET /api/v1/candidates/{id}, POST /api/v1/candidates/match.

All three operate on the full ATS Talent Pool (no separate "top candidates"
concept). Tests pin:
  - /search: q-mode (keyword, capped, no cursor) and browse-mode (id-keyset
    cursor pagination, real total_matched), plus the state/city/has_email/
    added_after structural filters and owner scoping.
  - /{id}: happy path (incl. "ats_" prefix), 404 for another owner's record
    or a missing id, 400 for a non-numeric id.
  - /match: happy path with a stubbed jd_extract/ai_score_fit (no network),
    the hard 25-row limit cap, min_score filtering, and cursor pagination.
  - all three reject a missing/invalid key with 401.

IMPORTANT: route tests mount handlers on a *minimal* Starlette app, not
flowdrip_app's real `app` - see test_candidate_import_api.py's docstring for
why (real app boot pollutes the rest of the suite).
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
CREATE TRIGGER IF NOT EXISTS talents_ai AFTER INSERT ON talents BEGIN
  INSERT INTO talents_fts(rowid, first_name, last_name, current_title,
    current_employer, skills, summary, city, state, resume_text)
  VALUES (new.id, new.first_name, new.last_name, new.current_title,
    new.current_employer, new.skills, new.summary, new.city, new.state,
    new.resume_text);
END;
"""

_OWNER = "rep@arena.com"
_OTHER = "other@arena.com"


def _isolate(tmp_path, monkeypatch):
    db = tmp_path / "ats.db"
    con = sqlite3.connect(str(db))
    con.executescript(_SCHEMA)
    con.commit()
    con.close()
    monkeypatch.setenv("ATS_DB_PATH", str(db))
    if "ats" in sys.modules:
        del sys.modules["ats"]
    import ats

    keys = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: keys)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "test-key")
    return ats, keys


def _insert(ats, **kw):
    con = ats._con()
    row = {
        "first_name": "Tim", "last_name": "Cooper", "email": "tim@example.com",
        "phone": "555-0100", "city": "Denver", "state": "CO",
        "current_title": "CNC Machinist", "current_employer": "Acme",
        "years_experience": "10", "seniority": "Senior",
        "skills": "cnc,lathe,welding", "summary": "Runs union crews.",
        "resume_text": "Ten years of CNC machining and welding experience.",
        "owner_email": _OWNER, "created_at": "2026-01-15T00:00:00",
        "updated_at": "2026-01-15T00:00:00",
    }
    row.update(kw)
    cols = list(row.keys())
    con.execute(
        f"INSERT INTO talents ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [row[c] for c in cols],
    )
    con.commit()
    tid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.close()
    return tid


def _client():
    # api_candidate_get takes candidate_id as a real function arg (FastAPI-style
    # path param injection, since flowdrip_app's `app` is nicegui's FastAPI
    # instance) - a plain Starlette Route can't call it, so mount on FastAPI.
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    app = FastAPI()
    app.add_api_route("/api/v1/candidates/search", fa.api_candidates_search,
                       methods=["GET"])
    app.add_api_route("/api/v1/candidates/match", fa.api_candidates_match,
                       methods=["POST"])
    app.add_api_route("/api/v1/candidates/{candidate_id}", fa.api_candidate_get,
                       methods=["GET"])
    return TestClient(app)


# ── /search ──────────────────────────────────────────────────────────────

def test_search_rejects_missing_key(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    r = _client().get("/api/v1/candidates/search")
    assert r.status_code == 401


def test_search_keyword_mode(tmp_path, monkeypatch):
    ats, _ = _isolate(tmp_path, monkeypatch)
    _insert(ats)
    key = fa._mint_api_key(_OWNER)
    r = _client().get("/api/v1/candidates/search", params={"q": "cnc"},
                       headers={"X-API-Key": key})
    assert r.status_code == 200
    body = r.json()
    assert body["returned"] == 1
    assert body["results"][0]["name"] == "Tim Cooper"
    assert body["results"][0]["id"] == "ats_1"
    assert body["next_cursor"] is None


def test_search_browse_mode_paginates_with_cursor(tmp_path, monkeypatch):
    ats, _ = _isolate(tmp_path, monkeypatch)
    for i in range(3):
        _insert(ats, first_name=f"Cand{i}", email=f"c{i}@example.com")
    key = fa._mint_api_key(_OWNER)
    client = _client()

    r1 = client.get("/api/v1/candidates/search", params={"limit": "2"},
                     headers={"X-API-Key": key})
    b1 = r1.json()
    assert b1["matched"] == 3
    assert b1["returned"] == 2
    assert b1["next_cursor"] is not None

    r2 = client.get("/api/v1/candidates/search",
                     params={"limit": "2", "cursor": str(b1["next_cursor"])},
                     headers={"X-API-Key": key})
    b2 = r2.json()
    assert b2["returned"] == 1
    assert b2["next_cursor"] is None


def test_search_scoped_to_key_owner(tmp_path, monkeypatch):
    ats, _ = _isolate(tmp_path, monkeypatch)
    _insert(ats, owner_email=_OWNER)
    _insert(ats, owner_email=_OTHER, first_name="Nope", email="nope@example.com")
    key = fa._mint_api_key(_OWNER)
    r = _client().get("/api/v1/candidates/search", headers={"X-API-Key": key})
    body = r.json()
    assert body["matched"] == 1
    assert body["results"][0]["name"] == "Tim Cooper"


def test_search_structural_filters(tmp_path, monkeypatch):
    ats, _ = _isolate(tmp_path, monkeypatch)
    _insert(ats, city="Denver", state="CO", email="has@example.com")
    _insert(ats, first_name="NoEmail", email="", city="Boulder", state="CO")
    key = fa._mint_api_key(_OWNER)
    client = _client()

    r = client.get("/api/v1/candidates/search",
                    params={"city": "Boulder"}, headers={"X-API-Key": key})
    assert r.json()["matched"] == 1
    assert r.json()["results"][0]["name"] == "NoEmail Cooper"

    r = client.get("/api/v1/candidates/search",
                    params={"has_email": "false"}, headers={"X-API-Key": key})
    assert r.json()["matched"] == 1

    r = client.get("/api/v1/candidates/search",
                    params={"added_after": "2099-01-01"}, headers={"X-API-Key": key})
    assert r.json()["matched"] == 0


# ── /{id} ────────────────────────────────────────────────────────────────

def test_get_rejects_missing_key(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    r = _client().get("/api/v1/candidates/ats_1")
    assert r.status_code == 401


def test_get_happy_path_with_and_without_prefix(tmp_path, monkeypatch):
    ats, _ = _isolate(tmp_path, monkeypatch)
    tid = _insert(ats)
    key = fa._mint_api_key(_OWNER)
    client = _client()

    r = client.get(f"/api/v1/candidates/ats_{tid}", headers={"X-API-Key": key})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == f"ats_{tid}"
    assert body["resume_text"] == "Ten years of CNC machining and welding experience."
    assert body["skills"] == ["cnc", "lathe", "welding"]

    r2 = client.get(f"/api/v1/candidates/{tid}", headers={"X-API-Key": key})
    assert r2.status_code == 200
    assert r2.json()["id"] == f"ats_{tid}"


def test_get_404s_for_other_owner_and_missing(tmp_path, monkeypatch):
    ats, _ = _isolate(tmp_path, monkeypatch)
    tid = _insert(ats, owner_email=_OTHER)
    key = fa._mint_api_key(_OWNER)
    client = _client()

    r = client.get(f"/api/v1/candidates/ats_{tid}", headers={"X-API-Key": key})
    assert r.status_code == 404

    r2 = client.get("/api/v1/candidates/ats_99999", headers={"X-API-Key": key})
    assert r2.status_code == 404


def test_get_400s_for_non_numeric_id(tmp_path, monkeypatch):
    ats, _ = _isolate(tmp_path, monkeypatch)
    key = fa._mint_api_key(_OWNER)
    r = _client().get("/api/v1/candidates/ats_not-a-number",
                       headers={"X-API-Key": key})
    assert r.status_code == 400


# ── /match ───────────────────────────────────────────────────────────────

def _stub_match_ai(monkeypatch, ats, scores=None):
    """No-network stand-ins for jd_extract/ai_score_fit, mirroring
    test_candidate_import_api.py's _ai_parse_resume stub."""
    monkeypatch.setattr(ats, "jd_extract", lambda jd_text: {
        "title": "CNC Machinist", "must_have_skills": ["cnc"],
        "nice_to_have": [], "location": "", "seniority": "",
    })
    scores = scores or {}

    def _fake_score(intent, resume_text):
        return scores.get(resume_text, (75, "solid fit"))
    monkeypatch.setattr(ats, "ai_score_fit", _fake_score)


def test_match_rejects_missing_key(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    r = _client().post("/api/v1/candidates/match", json={"job_description": "cnc machinist"})
    assert r.status_code == 401


def test_match_requires_job_description(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    key = fa._mint_api_key(_OWNER)
    r = _client().post("/api/v1/candidates/match", json={},
                        headers={"X-API-Key": key})
    assert r.status_code == 400


def test_match_503_when_ai_not_configured(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "")
    key = fa._mint_api_key(_OWNER)
    r = _client().post("/api/v1/candidates/match",
                        json={"job_description": "cnc machinist"},
                        headers={"X-API-Key": key})
    assert r.status_code == 503


def test_match_happy_path(tmp_path, monkeypatch):
    ats, _ = _isolate(tmp_path, monkeypatch)
    _stub_match_ai(monkeypatch, ats)
    _insert(ats)
    key = fa._mint_api_key(_OWNER)
    r = _client().post("/api/v1/candidates/match",
                        json={"job_description": "Need a CNC machinist"},
                        headers={"X-API-Key": key})
    assert r.status_code == 200
    body = r.json()
    assert body["total_matched"] == 1
    assert len(body["results"]) == 1
    result = body["results"][0]
    assert result["candidate_id"] == "ats_1"
    assert result["match_score"] == 75
    assert result["match_reasons"]
    assert result["resume_text"]


def test_match_limit_hard_capped_at_25(tmp_path, monkeypatch):
    ats, _ = _isolate(tmp_path, monkeypatch)
    _stub_match_ai(monkeypatch, ats)
    for i in range(3):
        _insert(ats, first_name=f"Cand{i}", email=f"c{i}@example.com")
    key = fa._mint_api_key(_OWNER)
    r = _client().post("/api/v1/candidates/match",
                        json={"job_description": "cnc machinist", "limit": 999},
                        headers={"X-API-Key": key})
    assert r.status_code == 200
    # only 3 candidates exist, but confirms the request didn't reject/clamp-error
    assert len(r.json()["results"]) == 3


def test_match_min_score_filters_results(tmp_path, monkeypatch):
    ats, _ = _isolate(tmp_path, monkeypatch)
    strong = "Ten years of CNC machining and welding experience."
    weak = "Some CNC exposure in a class once."
    _stub_match_ai(monkeypatch, ats, scores={strong: (90, "great"), weak: (20, "meh")})
    _insert(ats, resume_text=strong, email="strong@example.com")
    _insert(ats, resume_text=weak, first_name="Weak", email="weak@example.com")
    key = fa._mint_api_key(_OWNER)
    r = _client().post("/api/v1/candidates/match",
                        json={"job_description": "cnc machinist", "min_score": 50},
                        headers={"X-API-Key": key})
    body = r.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["match_score"] == 90


def test_match_cursor_pagination(tmp_path, monkeypatch):
    ats, _ = _isolate(tmp_path, monkeypatch)
    _stub_match_ai(monkeypatch, ats)
    for i in range(3):
        _insert(ats, first_name=f"Cand{i}", email=f"c{i}@example.com")
    key = fa._mint_api_key(_OWNER)
    client = _client()

    r1 = client.post("/api/v1/candidates/match",
                      json={"job_description": "cnc machinist", "limit": 2},
                      headers={"X-API-Key": key})
    b1 = r1.json()
    assert len(b1["results"]) == 2
    assert b1["next_cursor"] is not None

    r2 = client.post("/api/v1/candidates/match",
                      json={"job_description": "cnc machinist", "limit": 2,
                            "cursor": b1["next_cursor"]},
                      headers={"X-API-Key": key})
    b2 = r2.json()
    assert len(b2["results"]) == 1
    seen_ids = {r["candidate_id"] for r in b1["results"]} | {r["candidate_id"] for r in b2["results"]}
    assert len(seen_ids) == 3
