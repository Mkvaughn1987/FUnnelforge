"""Resume import API: POST /api/v1/candidates/import (+ count).

The route is a thin server-to-server wrapper around _import_one_resume, the
same per-file core the "Bulk Import Resumes" UI worker calls. Tests pin:
  - the shared core appends to the current user's pool (added),
  - short/blank resumes are skipped (never crash the batch),
  - imports are append-only (no dedupe) - identical to the UI,
  - the route rejects a missing/invalid key with 401,
  - the route + count happy paths.

IMPORTANT: route tests mount the two handlers on a *minimal* Starlette app,
NOT flowdrip_app's real `app`. Spinning the real NiceGUI app via TestClient
starts its lifespan (leader election, email/timer threads) and pollutes every
later test in the suite. A bare app gives identical route coverage with no
side effects.
"""
import flowdrip_app as fa


def _isolate(tmp_path, monkeypatch):
    """Point pool + api-key stores + upload dir at a throwaway tmp dir and
    stub the Haiku metadata call so nothing hits the network."""
    pool = tmp_path / "candidate_pool.json"
    keys = tmp_path / "api_keys.json"
    pdfs = tmp_path / "PDFs"
    pdfs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(fa, "_user_candidate_pool_path", lambda: pool)
    monkeypatch.setattr(fa, "_api_keys_path", lambda: keys)
    monkeypatch.setattr(fa, "_user_pdf_dir", lambda: pdfs)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "test-key")

    class _Block:
        text = ('{"name":"Tim Cooper","target_role":"CNC Machinist",'
                '"location":"Denver, CO","salary":"","highlights":["a","b"]}')

    class _Msg:
        content = [_Block()]

    monkeypatch.setattr(fa, "_claude_create_with_retry",
                        lambda *a, **k: _Msg())
    return pool, keys


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


# ── shared core (used verbatim by UI + API) ────────────────────────────────

def test_import_one_resume_appends(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(fa, "_extract_resume_text",
                        lambda p: "x" * 200)  # long enough to pass the >=40 gate
    res = fa._import_one_resume(str(tmp_path / "tim.pdf"), "tim.pdf")
    assert res["status"] == "added"
    assert res["name"] == "Tim Cooper"
    assert res["candidate_id"]
    pool = fa.load_candidate_pool()
    assert len(pool) == 1
    assert pool[0]["name"] == "Tim Cooper"
    assert pool[0]["status"] == "active"


def test_import_one_resume_skips_unparseable(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(fa, "_extract_resume_text", lambda p: "")
    res = fa._import_one_resume(str(tmp_path / "blank.pdf"), "blank.pdf")
    assert res["status"] == "skipped"
    assert res["reason"] == "could not extract text"
    assert fa.load_candidate_pool() == []


def test_import_is_append_only_no_dedupe(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(fa, "_extract_resume_text", lambda p: "x" * 200)
    fa._import_one_resume(str(tmp_path / "tim.pdf"), "tim.pdf")
    fa._import_one_resume(str(tmp_path / "tim.pdf"), "tim.pdf")
    pool = fa.load_candidate_pool()
    assert len(pool) == 2  # same resume twice -> two candidates, exactly like the UI


def test_falls_back_to_filename_when_ai_fails(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(fa, "_extract_resume_text", lambda p: "x" * 200)

    def _boom(*a, **k):
        raise RuntimeError("model down")

    monkeypatch.setattr(fa, "_claude_create_with_retry", _boom)
    res = fa._import_one_resume(str(tmp_path / "Jane-Doe.pdf"), "Jane-Doe.pdf")
    assert res["status"] == "added"          # AI failure != import failure
    assert res["name"] == "Jane-Doe"          # falls back to the filename stem


# ── route (minimal app, no NiceGUI lifespan) ───────────────────────────────

def test_route_rejects_missing_key(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    r = _client().post("/api/v1/candidates/import",
                       files=[("files", ("a.pdf", b"data", "application/pdf"))])
    assert r.status_code == 401


def test_route_happy_path(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(fa, "_extract_resume_text", lambda p: "x" * 200)
    key = fa._mint_api_key("rep@arena.com")
    r = _client().post(
        "/api/v1/candidates/import",
        headers={"X-API-Key": key},
        files=[("files", ("tim.pdf", b"%PDF-1.4 fake", "application/pdf"))],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["requested"] == 1
    assert body["added"] == 1
    assert body["updated"] == 0
    assert body["results"][0]["status"] == "added"
    assert body["results"][0]["name"] == "Tim Cooper"


def test_count_endpoint(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(fa, "_extract_resume_text", lambda p: "x" * 200)
    key = fa._mint_api_key("rep@arena.com")
    fa._CURRENT_USER_EMAIL.set("rep@arena.com")
    fa._import_one_resume(str(tmp_path / "tim.pdf"), "tim.pdf")
    r = _client().get("/api/v1/candidates/count", headers={"X-API-Key": key})
    assert r.status_code == 200
    body = r.json()
    assert body["active"] == 1
    assert body["total"] == 1
