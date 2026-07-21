# PipelineBlast App Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Partners run PipelineBlast from the claude.ai app via a custom MCP connector on `dripdripdrop.ai` — OAuth login to their own DripDrop account, shared dedupe master, in-process 5x3 launch, automatic server-side Talent Trekker load.

**Architecture:** Everything lives in `flowdrip_app.py` (single-file deploy constraint). New pieces: one SQLite DB (`bd_connector.db`) holding the shared master + OAuth grants + TT job queue; hand-rolled OAuth 2.1 endpoints (auth-code + PKCE + dynamic client registration); a hand-rolled stateless MCP Streamable-HTTP handler at `POST /mcp` exposing 4 tools; a TT loader worker thread using Frappe token auth. Plus a `pipelineblast-app` skill zip for partners.

**Tech Stack:** Python stdlib (`sqlite3`, `hashlib`, `secrets`, `base64`), Starlette request/response objects (already used by the API routes), `requests` (already in venv) for TT calls, pytest patterns from `tests/test_campaign_api.py`. **No new dependencies.**

**Spec:** `docs/superpowers/specs/2026-07-21-pipelineblast-app-connector-design.md`

**Conventions used throughout:**
- All new server code goes in `flowdrip_app.py` in ONE contiguous block appended near the existing API routes (after `_api_enroll_newsletter`, ~L5181), prefixed `_bdc_` (BD connector) / `_mcp_` / `_oauth_` — the file has duplicate-helper shadowing danger, so grep for each new name before defining it.
- Tests go in `tests/test_bd_connector.py` (units) and `tests/test_mcp_endpoint.py` (HTTP), mirroring the fixture style of `tests/test_campaign_api.py` (import `flowdrip_app as fa`, monkeypatch path helpers to tmp_path, mount handlers with bare Starlette `Route`s + `TestClient`).
- Run tests with: `./.venv/Scripts/python -m pytest tests/test_bd_connector.py tests/test_mcp_endpoint.py -v` from repo root. Full-suite baseline: ~8 flaky pre-existing failures unrelated to this work — judge green-ness against the new files + `tests/test_campaign_api.py` (must stay green).
- Commit after every task (files: `flowdrip_app.py` + the test file touched).

---

### Task 1: SQLite store

**Files:**
- Modify: `flowdrip_app.py` (append new block after `_api_enroll_newsletter`, ~L5181)
- Test: `tests/test_bd_connector.py` (create)

- [ ] **Step 1: Write failing tests**

```python
"""BD connector: shared master, OAuth store, TT jobs, MCP tools.
Spec: docs/superpowers/specs/2026-07-21-pipelineblast-app-connector-design.md
"""
import pytest
import flowdrip_app as fa


@pytest.fixture()
def bdc_db(tmp_path, monkeypatch):
    """Point the connector DB at a temp file."""
    monkeypatch.setattr(fa, "_bdc_db_path", lambda: tmp_path / "bd_connector.db")
    return tmp_path / "bd_connector.db"


def test_bdc_db_creates_file_and_tables(bdc_db):
    with fa._bdc_db() as con:
        names = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"master", "oauth_clients", "oauth_codes",
            "oauth_tokens", "tt_jobs"} <= names
    assert bdc_db.exists()


def test_bdc_db_init_is_idempotent(bdc_db):
    with fa._bdc_db() as con:
        con.execute("INSERT INTO master (company, company_norm) VALUES ('A','a')")
    with fa._bdc_db() as con:  # re-open must not wipe
        n = con.execute("SELECT COUNT(*) FROM master").fetchone()[0]
    assert n == 1
```

- [ ] **Step 2: Run to verify failure** — `./.venv/Scripts/python -m pytest tests/test_bd_connector.py -v` → FAIL: `AttributeError: _bdc_db_path`

- [ ] **Step 3: Implement**

```python
# ─── BD Connector: partners run PipelineBlast from claude.ai ─────────────
# Spec: docs/superpowers/specs/2026-07-21-pipelineblast-app-connector-design.md
import sqlite3 as _bdc_sqlite3
from contextlib import contextmanager as _bdc_contextmanager

_BDC_SCHEMA = """
CREATE TABLE IF NOT EXISTS master (
  id INTEGER PRIMARY KEY, company TEXT NOT NULL, company_norm TEXT NOT NULL UNIQUE,
  city TEXT DEFAULT '', type TEXT DEFAULT '', week_surfaced TEXT DEFAULT '',
  date TEXT DEFAULT '', status TEXT DEFAULT '', added_by TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS oauth_clients (
  client_id TEXT PRIMARY KEY, client_name TEXT DEFAULT '',
  redirect_uris TEXT NOT NULL, created TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS oauth_codes (
  code TEXT PRIMARY KEY, client_id TEXT, email TEXT, challenge TEXT,
  redirect_uri TEXT, expires REAL);
CREATE TABLE IF NOT EXISTS oauth_tokens (
  token_hash TEXT PRIMARY KEY, kind TEXT, email TEXT, client_id TEXT,
  expires REAL, revoked INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS tt_jobs (
  id INTEGER PRIMARY KEY, company TEXT, contacts_json TEXT, owner TEXT,
  attempts INTEGER DEFAULT 0, status TEXT DEFAULT 'pending',
  next_try REAL DEFAULT 0, last_error TEXT DEFAULT '');
"""

def _bdc_db_path():
    return _BASE_DATA_DIR / "bd_connector.db"

@_bdc_contextmanager
def _bdc_db():
    con = _bdc_sqlite3.connect(_bdc_db_path(), timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(_BDC_SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()
```

- [ ] **Step 4: Run to verify pass** — same command → 2 PASS
- [ ] **Step 5: Commit** — `git add flowdrip_app.py tests/test_bd_connector.py && git commit -m "feat(connector): bd_connector.db store with master/oauth/tt_jobs tables"`

---

### Task 2: Company normalizer (loose match, server-side)

**Files:** Modify `flowdrip_app.py` (same block); Test `tests/test_bd_connector.py`

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.parametrize("a,b,same", [
    ("Mortenson Construction", "mortenson construction, Inc.", True),
    ("Roche Constructors, Inc.", "Roche Constructors LLC", True),
    ("Acme Co", "Acme Company", True),
    ("Brinkmann Constructors", "Brinkman Construction", False),  # different firms
    ("PCL", "PCL Construction", False),  # bare acronym stays distinct
])
def test_bdc_norm_company(a, b, same):
    assert (fa._bdc_norm_company(a) == fa._bdc_norm_company(b)) is same
```

- [ ] **Step 2: Run — FAIL** (`_bdc_norm_company` undefined)
- [ ] **Step 3: Implement** — deterministic + conservative: lowercase, strip punctuation, drop pure *legal* suffix tokens only (inc, llc, ltd, corp, corporation, co, company, group). Do NOT drop industry words like "construction" (that's what keeps `PCL` ≠ `PCL Construction` and Brinkmann/Brinkman distinct); the skill keeps the judgment-y variant checks client-side by passing variants into `check_companies`.

```python
_BDC_SUFFIXES = {"inc", "llc", "ltd", "corp", "corporation", "co", "company", "group"}

def _bdc_norm_company(name: str) -> str:
    toks = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split()
    while toks and toks[-1] in _BDC_SUFFIXES:
        toks.pop()
    return " ".join(toks)
```

- [ ] **Step 4: Run — PASS**  •  **Step 5: Commit** `feat(connector): conservative company normalizer for shared master`

---

### Task 3: Master check / record / status ops

**Files:** Modify `flowdrip_app.py`; Test `tests/test_bd_connector.py`

- [ ] **Step 1: Write failing tests**

```python
def test_check_then_record_then_check(bdc_db):
    r = fa._bdc_check_companies(["Mortenson Construction"])
    assert r == [{"company": "Mortenson Construction", "result": "new"}]
    added = fa._bdc_record_companies(
        [{"company": "Mortenson Construction", "city": "Denver", "type": "GC",
          "week_surfaced": "2026-W30", "status": "Selected"}], added_by="p1@arena.com")
    assert added == {"added": 1, "already_worked": []}
    r2 = fa._bdc_check_companies(["mortenson construction, Inc."])[0]
    assert r2["result"] == "already_worked"
    assert r2["status"] == "Selected" and r2["added_by"] == "p1@arena.com"

def test_record_second_claim_reports_already_worked(bdc_db):
    fa._bdc_record_companies([{"company": "Acme Co"}], added_by="a@x.com")
    out = fa._bdc_record_companies([{"company": "Acme Company"}], added_by="b@x.com")
    assert out["added"] == 0 and out["already_worked"] == ["Acme Company"]

def test_update_status(bdc_db):
    fa._bdc_record_companies([{"company": "Acme Co"}], added_by="a@x.com")
    assert fa._bdc_update_status("Acme Company", "Campaign launched + in TT") is True
    assert fa._bdc_check_companies(["Acme Co"])[0]["status"] == "Campaign launched + in TT"
```

- [ ] **Step 2: Run — FAIL**
- [ ] **Step 3: Implement**

```python
def _bdc_check_companies(names: list) -> list:
    out = []
    with _bdc_db() as con:
        for n in (names or []):
            row = con.execute(
                "SELECT company, status, date, added_by FROM master WHERE company_norm=?",
                (_bdc_norm_company(n),)).fetchone()
            if row is None:
                out.append({"company": n, "result": "new"})
            else:
                out.append({"company": n, "result": "already_worked",
                            "matched": row[0], "status": row[1],
                            "date": row[2], "added_by": row[3]})
    return out

def _bdc_record_companies(rows: list, added_by: str = "") -> dict:
    added, dupes = 0, []
    today = date.today().isoformat()
    with _bdc_db() as con:  # single connection = transactional claim
        for r in (rows or []):
            name = (r.get("company") or "").strip()
            if not name:
                continue
            cur = con.execute(
                "INSERT OR IGNORE INTO master "
                "(company, company_norm, city, type, week_surfaced, date, status, added_by) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (name, _bdc_norm_company(name), r.get("city", ""), r.get("type", ""),
                 r.get("week_surfaced", ""), r.get("date") or today,
                 r.get("status", "Selected"), added_by))
            if cur.rowcount:
                added += 1
            else:
                dupes.append(name)
    return {"added": added, "already_worked": dupes}

def _bdc_update_status(company: str, status: str) -> bool:
    with _bdc_db() as con:
        cur = con.execute("UPDATE master SET status=? WHERE company_norm=?",
                          (status, _bdc_norm_company(company)))
        return cur.rowcount > 0
```

- [ ] **Step 4: Run — PASS**  •  **Step 5: Commit** `feat(connector): shared master check/record/status ops`

---

### Task 4: CSV seed import + admin route

**Files:** Modify `flowdrip_app.py`; Test `tests/test_bd_connector.py`

- [ ] **Step 1: Write failing tests**

```python
SEED = ("Company,City,Type,Week Surfaced,Date,Status\n"
        "Mortenson Construction,Denver,GC,2026-W12,2026-03-16,Campaign launched + in TT\n"
        "Roche Constructors Inc,Greeley,GC,2026-W12,2026-03-16,Selected\n")

def test_seed_master_idempotent(bdc_db):
    assert fa._bdc_seed_master_from_csv(SEED) == {"added": 2, "skipped": 0}
    assert fa._bdc_seed_master_from_csv(SEED) == {"added": 0, "skipped": 2}
    assert fa._bdc_check_companies(["Mortenson Construction"])[0]["result"] == "already_worked"
```

- [ ] **Step 2: Run — FAIL**
- [ ] **Step 3: Implement** — parse with `csv.DictReader`, map headers `Company/City/Type/Week Surfaced/Date/Status` → `_bdc_record_companies` rows (`added_by="seed"`); return added/skipped. Then the route (same auth shape as `api_create_campaign`):

```python
def _bdc_seed_master_from_csv(text: str) -> dict:
    import csv as _csv, io as _io
    rows = []
    for rec in _csv.DictReader(_io.StringIO(text or "")):
        rows.append({"company": (rec.get("Company") or "").strip(),
                     "city": (rec.get("City") or "").strip(),
                     "type": (rec.get("Type") or "").strip(),
                     "week_surfaced": (rec.get("Week Surfaced") or "").strip(),
                     "date": (rec.get("Date") or "").strip(),
                     "status": (rec.get("Status") or "").strip() or "Seeded"})
    out = _bdc_record_companies(rows, added_by="seed")
    return {"added": out["added"], "skipped": len(out["already_worked"])}

@app.post("/api/v1/master/import")
async def api_master_import(request: Request):
    """Seed/refresh the shared BD master from a CSV body. Super-admin only."""
    from starlette.responses import JSONResponse
    auth = request.headers.get("authorization", "")
    key = (auth[7:].strip() if auth.lower().startswith("bearer ")
           else request.headers.get("x-api-key", "").strip())
    owner = _resolve_api_key(key)
    if not owner:
        return JSONResponse({"error": "invalid or missing API key"}, status_code=401)
    if not _is_super_admin(owner):
        return JSONResponse({"error": "admin only"}, status_code=403)
    body = (await request.body()).decode("utf-8", "replace")
    return JSONResponse(_bdc_seed_master_from_csv(body))
```

HTTP test (in `tests/test_mcp_endpoint.py`, created here with the shared client helper — mirror `test_candidate_import_api.py`'s `_client()` pattern):

```python
"""HTTP surface: seed route, OAuth endpoints, /mcp JSON-RPC."""
import json
import pytest
import flowdrip_app as fa
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient


def _client():
    return TestClient(Starlette(routes=[
        Route("/api/v1/master/import", fa.api_master_import, methods=["POST"]),
        Route("/oauth/register", fa.oauth_register, methods=["POST"]),
        Route("/oauth/authorize", fa.oauth_authorize_get, methods=["GET"]),
        Route("/oauth/authorize", fa.oauth_authorize_post, methods=["POST"]),
        Route("/oauth/token", fa.oauth_token, methods=["POST"]),
        Route("/.well-known/oauth-authorization-server", fa.oauth_metadata, methods=["GET"]),
        Route("/.well-known/oauth-protected-resource", fa.oauth_resource_metadata, methods=["GET"]),
        Route("/mcp", fa.api_mcp, methods=["POST"]),
    ]))


@pytest.fixture()
def bdc_db(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, "_bdc_db_path", lambda: tmp_path / "bd.db")


@pytest.fixture()
def api_key(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, "_api_keys_path", lambda: tmp_path / "api_keys.json")
    return fa._mint_api_key("mike@arena.com")


def test_master_import_requires_super_admin(bdc_db, api_key, monkeypatch):
    monkeypatch.setattr(fa, "_is_super_admin", lambda e=None: False)
    r = _client().post("/api/v1/master/import", content="Company\nAcme\n",
                       headers={"Authorization": f"Bearer {api_key}"})
    assert r.status_code == 403


def test_master_import_seeds(bdc_db, api_key, monkeypatch):
    monkeypatch.setattr(fa, "_is_super_admin", lambda e=None: True)
    csv_body = "Company,City,Type,Week Surfaced,Date,Status\nAcme Co,Denver,GC,w,d,s\n"
    r = _client().post("/api/v1/master/import", content=csv_body,
                       headers={"Authorization": f"Bearer {api_key}"})
    assert r.status_code == 200 and r.json() == {"added": 1, "skipped": 0}
```

(The `_client()` routes for OAuth/mcp reference handlers built in Tasks 5–7; until those tasks land, comment those Route lines out and un-comment as each arrives.)

- [ ] **Step 4: Run — PASS**  •  **Step 5: Commit** `feat(connector): master CSV seed + super-admin import route`

---

### Task 5: OAuth token/code primitives

**Files:** Modify `flowdrip_app.py`; Test `tests/test_bd_connector.py`

- [ ] **Step 1: Write failing tests**

```python
def test_token_mint_resolve_expire(bdc_db):
    tok = fa._bdc_mint_token("p1@arena.com", "cli1", kind="access", ttl=3600)
    assert tok.startswith("ddmcp_")
    assert fa._bdc_resolve_token(tok) == "p1@arena.com"
    expired = fa._bdc_mint_token("p1@arena.com", "cli1", kind="access", ttl=-1)
    assert fa._bdc_resolve_token(expired) is None
    assert fa._bdc_resolve_token("ddmcp_bogus") is None

def test_code_roundtrip_pkce(bdc_db):
    import base64, hashlib
    verifier = "v" * 48
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    code = fa._bdc_issue_code("cli1", "p1@arena.com", challenge, "https://claude.ai/cb")
    assert fa._bdc_redeem_code(code, "cli1", verifier, "https://claude.ai/cb") == "p1@arena.com"
    assert fa._bdc_redeem_code(code, "cli1", verifier, "https://claude.ai/cb") is None  # one-shot
    code2 = fa._bdc_issue_code("cli1", "p1@arena.com", challenge, "https://claude.ai/cb")
    assert fa._bdc_redeem_code(code2, "cli1", "wrong" * 10, "https://claude.ai/cb") is None
```

- [ ] **Step 2: Run — FAIL**
- [ ] **Step 3: Implement**

```python
def _bdc_mint_token(email, client_id, kind="access", ttl=3600):
    tok = "ddmcp_" + secrets.token_urlsafe(32)
    with _bdc_db() as con:
        con.execute("INSERT INTO oauth_tokens VALUES (?,?,?,?,?,0)",
                    (hashlib.sha256(tok.encode()).hexdigest(), kind, email,
                     client_id, time.time() + ttl))
    return tok

def _bdc_resolve_token(token, kind="access"):
    if not token:
        return None
    with _bdc_db() as con:
        row = con.execute(
            "SELECT email, expires, revoked, client_id FROM oauth_tokens "
            "WHERE token_hash=? AND kind=?",
            (hashlib.sha256(token.encode()).hexdigest(), kind)).fetchone()
    if not row or row[2] or row[1] < time.time():
        return None
    return row[0] if kind == "access" else (row[0], row[3])

def _bdc_issue_code(client_id, email, challenge, redirect_uri):
    code = secrets.token_urlsafe(24)
    with _bdc_db() as con:
        con.execute("INSERT INTO oauth_codes VALUES (?,?,?,?,?,?)",
                    (code, client_id, email, challenge, redirect_uri,
                     time.time() + 300))
    return code

def _bdc_redeem_code(code, client_id, verifier, redirect_uri):
    with _bdc_db() as con:
        row = con.execute("SELECT client_id, email, challenge, redirect_uri, expires "
                          "FROM oauth_codes WHERE code=?", (code,)).fetchone()
        con.execute("DELETE FROM oauth_codes WHERE code=?", (code,))  # one-shot
    if (not row or row[0] != client_id or row[3] != redirect_uri
            or row[4] < time.time()):
        return None
    want = base64.urlsafe_b64encode(
        hashlib.sha256((verifier or "").encode()).digest()).rstrip(b"=").decode()
    return row[1] if want == row[2] else None
```

(`secrets`, `hashlib`, `time`, `base64` — grep first; `hashlib` and `time` are already imported at module top, add the others beside them if missing.)

- [ ] **Step 4: Run — PASS**  •  **Step 5: Commit** `feat(connector): oauth token + PKCE code primitives`

---

### Task 6: OAuth HTTP endpoints + discovery metadata

**Files:** Modify `flowdrip_app.py`; Test `tests/test_mcp_endpoint.py`

- [ ] **Step 1: Write failing tests** (uncomment the OAuth routes in `_client()`)

```python
def test_oauth_full_flow(bdc_db, monkeypatch):
    import base64, hashlib
    c = _client()
    # 1. dynamic client registration
    r = c.post("/oauth/register", json={
        "client_name": "Claude", "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"]})
    assert r.status_code == 201
    cid = r.json()["client_id"]
    # 2. authorize GET renders the login form with hidden params
    verifier = "s" * 64
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    q = {"client_id": cid, "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
         "response_type": "code", "state": "xyz",
         "code_challenge": challenge, "code_challenge_method": "S256"}
    r = c.get("/oauth/authorize", params=q)
    assert r.status_code == 200 and 'name="password"' in r.text
    # 3. authorize POST with valid creds redirects back with a code
    monkeypatch.setattr(fa, "_load_users",
                        lambda: {"p1@arena.com": {"password": fa._hash_password("pw1")}})
    r = c.post("/oauth/authorize", data={**q, "email": "p1@arena.com", "password": "pw1"},
               follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("https://claude.ai/api/mcp/auth_callback?") and "state=xyz" in loc
    code = [p.split("=")[1] for p in loc.split("?")[1].split("&") if p.startswith("code=")][0]
    # 4. token exchange
    r = c.post("/oauth/token", data={"grant_type": "authorization_code", "code": code,
                                     "client_id": cid, "code_verifier": verifier,
                                     "redirect_uri": "https://claude.ai/api/mcp/auth_callback"})
    body = r.json()
    assert r.status_code == 200 and body["token_type"] == "Bearer"
    assert fa._bdc_resolve_token(body["access_token"]) == "p1@arena.com"
    # 5. refresh grant
    r = c.post("/oauth/token", data={"grant_type": "refresh_token",
                                     "refresh_token": body["refresh_token"], "client_id": cid})
    assert r.status_code == 200 and fa._bdc_resolve_token(
        r.json()["access_token"]) == "p1@arena.com"

def test_oauth_bad_password_rerenders_form(bdc_db, monkeypatch):
    monkeypatch.setattr(fa, "_load_users",
                        lambda: {"p1@arena.com": {"password": fa._hash_password("pw1")}})
    c = _client()
    cid = c.post("/oauth/register", json={"redirect_uris": ["https://claude.ai/cb"]}).json()["client_id"]
    r = c.post("/oauth/authorize", data={
        "client_id": cid, "redirect_uri": "https://claude.ai/cb", "response_type": "code",
        "state": "s", "code_challenge": "c", "code_challenge_method": "S256",
        "email": "p1@arena.com", "password": "WRONG"}, follow_redirects=False)
    assert r.status_code == 200 and "try again" in r.text.lower()

def test_oauth_unregistered_redirect_uri_rejected(bdc_db):
    c = _client()
    cid = c.post("/oauth/register", json={"redirect_uris": ["https://claude.ai/cb"]}).json()["client_id"]
    r = c.get("/oauth/authorize", params={"client_id": cid,
              "redirect_uri": "https://evil.example/cb", "response_type": "code",
              "code_challenge": "c", "code_challenge_method": "S256"})
    assert r.status_code == 400

def test_metadata_documents(bdc_db):
    c = _client()
    m = c.get("/.well-known/oauth-authorization-server").json()
    assert m["authorization_endpoint"].endswith("/oauth/authorize")
    assert m["code_challenge_methods_supported"] == ["S256"]
    p = c.get("/.well-known/oauth-protected-resource").json()
    assert m["issuer"] in p["authorization_servers"]
```

- [ ] **Step 2: Run — FAIL**
- [ ] **Step 3: Implement** — base URL from `os.environ.get("DD_PUBLIC_BASE_URL", "https://dripdripdrop.ai")` via helper `_bdc_base_url()`. Handlers (all plain `async def(request)` + `@app.<verb>` registration so tests can Route them):

```python
def _bdc_base_url():
    return os.environ.get("DD_PUBLIC_BASE_URL", "https://dripdripdrop.ai").rstrip("/")

_OAUTH_FORM = """<!doctype html><html><body style="font-family:sans-serif;max-width:420px;margin:80px auto">
<h2>DripDrop &mdash; connect Claude</h2><p>Sign in to let Claude launch campaigns from <b>your</b> DripDrop account.</p>
{err}<form method="post" action="/oauth/authorize">
{hidden}<input name="email" type="email" placeholder="Email" required style="display:block;width:100%;margin:8px 0;padding:8px">
<input name="password" type="password" placeholder="Password" required style="display:block;width:100%;margin:8px 0;padding:8px">
<button type="submit" style="padding:8px 24px">Sign in &amp; approve</button></form></body></html>"""

def _oauth_client_redirects(client_id):
    with _bdc_db() as con:
        row = con.execute("SELECT redirect_uris FROM oauth_clients WHERE client_id=?",
                          (client_id,)).fetchone()
    return json.loads(row[0]) if row else None

@app.post("/oauth/register")
async def oauth_register(request: Request):
    from starlette.responses import JSONResponse
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_client_metadata"}, status_code=400)
    uris = body.get("redirect_uris") or []
    if not isinstance(uris, list) or not all(
            isinstance(u, str) and u.startswith("https://") for u in uris) or not uris:
        return JSONResponse({"error": "invalid_redirect_uri"}, status_code=400)
    cid = secrets.token_urlsafe(16)
    with _bdc_db() as con:
        con.execute("INSERT INTO oauth_clients VALUES (?,?,?,?)",
                    (cid, str(body.get("client_name") or ""), json.dumps(uris),
                     datetime.now().isoformat()))
    return JSONResponse({"client_id": cid, "redirect_uris": uris,
                         "token_endpoint_auth_method": "none",
                         "grant_types": ["authorization_code", "refresh_token"],
                         "response_types": ["code"]}, status_code=201)

def _oauth_hidden_fields(params):
    keep = ("client_id", "redirect_uri", "response_type", "state",
            "code_challenge", "code_challenge_method")
    esc = lambda v: (v or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
    return "".join(f'<input type="hidden" name="{k}" value="{esc(params.get(k, ""))}">'
                   for k in keep)

def _oauth_validate_authz(params):
    """Shared GET/POST validation → error string or None."""
    uris = _oauth_client_redirects(params.get("client_id", ""))
    if uris is None:
        return "unknown client_id"
    if params.get("redirect_uri") not in uris:
        return "redirect_uri not registered"
    if params.get("response_type") != "code":
        return "unsupported response_type"
    if params.get("code_challenge_method") != "S256" or not params.get("code_challenge"):
        return "PKCE S256 required"
    return None

@app.get("/oauth/authorize")
async def oauth_authorize_get(request: Request):
    from starlette.responses import HTMLResponse, JSONResponse
    p = dict(request.query_params)
    err = _oauth_validate_authz(p)
    if err:
        return JSONResponse({"error": "invalid_request", "detail": err}, status_code=400)
    return HTMLResponse(_OAUTH_FORM.format(err="", hidden=_oauth_hidden_fields(p)))

@app.post("/oauth/authorize")
async def oauth_authorize_post(request: Request):
    from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
    form = dict(await request.form())
    err = _oauth_validate_authz(form)
    if err:
        return JSONResponse({"error": "invalid_request", "detail": err}, status_code=400)
    email = (form.get("email") or "").strip().lower()
    user = _load_users().get(email)
    if not user or not _verify_password(form.get("password") or "",
                                        user.get("password", "")):
        bad = "<p style='color:#b00'>Wrong email or password &mdash; try again.</p>"
        return HTMLResponse(_OAUTH_FORM.format(err=bad,
                                               hidden=_oauth_hidden_fields(form)))
    code = _bdc_issue_code(form["client_id"], email, form["code_challenge"],
                           form["redirect_uri"])
    sep = "&" if "?" in form["redirect_uri"] else "?"
    loc = f'{form["redirect_uri"]}{sep}code={code}'
    if form.get("state"):
        loc += f'&state={form["state"]}'
    return RedirectResponse(loc, status_code=302)

@app.post("/oauth/token")
async def oauth_token(request: Request):
    from starlette.responses import JSONResponse
    form = dict(await request.form())
    grant = form.get("grant_type")
    if grant == "authorization_code":
        email = _bdc_redeem_code(form.get("code", ""), form.get("client_id", ""),
                                 form.get("code_verifier", ""),
                                 form.get("redirect_uri", ""))
        if not email:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        cid = form.get("client_id", "")
    elif grant == "refresh_token":
        got = _bdc_resolve_token(form.get("refresh_token", ""), kind="refresh")
        if not got:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        email, cid = got
    else:
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
    return JSONResponse({
        "access_token": _bdc_mint_token(email, cid, "access", ttl=3600),
        "refresh_token": _bdc_mint_token(email, cid, "refresh", ttl=90 * 86400),
        "token_type": "Bearer", "expires_in": 3600})

@app.get("/.well-known/oauth-authorization-server")
async def oauth_metadata(request: Request):
    from starlette.responses import JSONResponse
    b = _bdc_base_url()
    return JSONResponse({
        "issuer": b, "authorization_endpoint": f"{b}/oauth/authorize",
        "token_endpoint": f"{b}/oauth/token",
        "registration_endpoint": f"{b}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"]})

@app.get("/.well-known/oauth-protected-resource")
async def oauth_resource_metadata(request: Request):
    from starlette.responses import JSONResponse
    b = _bdc_base_url()
    return JSONResponse({"resource": f"{b}/mcp", "authorization_servers": [b],
                         "bearer_methods_supported": ["header"]})
```

Note: `request.form()` needs `python-multipart` only for multipart; claude.ai posts token/authorize as `application/x-www-form-urlencoded`, which Starlette parses natively. The existing import route already handles multipart, so if `python-multipart` is present anyway, fine either way.

- [ ] **Step 4: Run — PASS**  •  **Step 5: Commit** `feat(connector): oauth 2.1 endpoints (register/authorize/token) + discovery metadata`

---

### Task 7: MCP JSON-RPC endpoint

**Files:** Modify `flowdrip_app.py`; Test `tests/test_mcp_endpoint.py`

- [ ] **Step 1: Write failing tests** (uncomment the `/mcp` Route)

```python
def _rpc(c, token, method, params=None, id=1):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    body = {"jsonrpc": "2.0", "method": method}
    if id is not None:
        body["id"] = id
    if params is not None:
        body["params"] = params
    return c.post("/mcp", json=body, headers=h)

@pytest.fixture()
def mcp_token(bdc_db):
    return fa._bdc_mint_token("p1@arena.com", "cli1", "access", 3600)

def test_mcp_unauthorized_401_with_resource_metadata(bdc_db):
    r = _rpc(_client(), None, "initialize")
    assert r.status_code == 401
    assert "resource_metadata" in r.headers.get("www-authenticate", "")

def test_mcp_initialize_and_tools_list(mcp_token):
    c = _client()
    r = _rpc(c, mcp_token, "initialize",
             {"protocolVersion": "2025-06-18", "capabilities": {},
              "clientInfo": {"name": "claude", "version": "1"}})
    out = r.json()["result"]
    assert out["protocolVersion"] == "2025-06-18"
    assert out["capabilities"]["tools"] == {}
    assert out["serverInfo"]["name"] == "dripdrop"
    r = _rpc(c, mcp_token, "notifications/initialized", id=None)
    assert r.status_code == 202
    tools = {t["name"] for t in _rpc(c, mcp_token, "tools/list").json()["result"]["tools"]}
    assert tools == {"check_companies", "record_companies",
                     "launch_arena_5x3", "list_newsletters"}

def test_mcp_unknown_method_is_32601(mcp_token):
    r = _rpc(_client(), mcp_token, "resources/list")
    assert r.json()["error"]["code"] == -32601

def test_mcp_tool_call_check_companies(mcp_token):
    r = _rpc(_client(), mcp_token, "tools/call",
             {"name": "check_companies", "arguments": {"companies": ["Acme Co"]}})
    out = r.json()["result"]
    assert out["isError"] is False
    assert json.loads(out["content"][0]["text"]) == [{"company": "Acme Co", "result": "new"}]

def test_mcp_unknown_tool_is_error_result(mcp_token):
    r = _rpc(_client(), mcp_token, "tools/call", {"name": "nope", "arguments": {}})
    assert r.json()["result"]["isError"] is True
```

- [ ] **Step 2: Run — FAIL**
- [ ] **Step 3: Implement** — dispatch table `_MCP_TOOL_DEFS` (name → {description, inputSchema, fn(email, args)}). Task 7 registers only the two dedupe tools with real fns; `launch_arena_5x3` / `list_newsletters` get placeholder fns raising `NotImplementedError` here and are replaced in Tasks 8–9 (tools/list is schema-complete from day one so the tests above pass).

```python
_MCP_PROTOCOL_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18"}

def _mcp_tool_defs():
    return {
        "check_companies": {
            "description": "Check company names against the shared team BD master. "
                           "Returns per company: result 'new' or 'already_worked' "
                           "(with matched name, status, date, added_by). Pass name "
                           "variants as separate entries when unsure.",
            "inputSchema": {"type": "object", "properties": {"companies": {
                "type": "array", "items": {"type": "string"}}},
                "required": ["companies"]},
            "fn": lambda email, a: _bdc_check_companies(a.get("companies") or [])},
        "record_companies": {
            "description": "Record selected companies in the shared master (call right "
                           "after selection, before launching). Also updates status on "
                           "re-record via the status field.",
            "inputSchema": {"type": "object", "properties": {"rows": {
                "type": "array", "items": {"type": "object", "properties": {
                    "company": {"type": "string"}, "city": {"type": "string"},
                    "type": {"type": "string"}, "week_surfaced": {"type": "string"},
                    "status": {"type": "string"}}, "required": ["company"]}}},
                "required": ["rows"]},
            "fn": lambda email, a: _bdc_record_companies(a.get("rows") or [],
                                                         added_by=email)},
        "launch_arena_5x3": {
            "description": "Create + launch an Arena 5x3 campaign from YOUR DripDrop "
                           "account. The server matches the bench and attaches the 3 "
                           "redacted résumés; a {skipped:true} result means no bench "
                           "fit — record it and move on. Talent Trekker load is "
                           "queued automatically on success.",
            "inputSchema": {"type": "object", "properties": {
                "company": {"type": "string"}, "roles": {"type": "array",
                    "items": {"type": "string"}},
                "start_date": {"type": "string", "description": "YYYY-MM-DD, next business day"},
                "contacts": {"type": "array", "items": {"type": "object", "properties": {
                    "email": {"type": "string"}, "first_name": {"type": "string"},
                    "last_name": {"type": "string"}, "company": {"type": "string"},
                    "title": {"type": "string"}, "phone_office": {"type": "string"},
                    "linkedin": {"type": "string"}}, "required": ["email"]}},
                "enroll_newsletter": {"type": "string"},
                "industry": {"type": "string"}, "location": {"type": "string"},
                "name": {"type": "string"}},
                "required": ["company", "roles", "start_date", "contacts",
                             "enroll_newsletter"]},
            "fn": lambda email, a: _mcp_launch_arena_5x3(email, a)},
        "list_newsletters": {
            "description": "Exact names of YOUR ongoing newsletters (for "
                           "enroll_newsletter).",
            "inputSchema": {"type": "object", "properties": {}},
            "fn": lambda email, a: _mcp_list_newsletters(email)},
    }

def _mcp_result(id_, payload, is_error=False):
    return {"jsonrpc": "2.0", "id": id_, "result": {
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "isError": bool(is_error)}}

@app.post("/mcp")
async def api_mcp(request: Request):
    from starlette.responses import JSONResponse, Response
    auth = request.headers.get("authorization", "")
    tok = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    email = _bdc_resolve_token(tok)
    if not email:
        return JSONResponse(
            {"error": "unauthorized"}, status_code=401,
            headers={"WWW-Authenticate":
                     f'Bearer resource_metadata='
                     f'"{_bdc_base_url()}/.well-known/oauth-protected-resource"'})
    try:
        msg = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": "parse error"}})
    method, id_, params = msg.get("method", ""), msg.get("id"), msg.get("params") or {}
    if method.startswith("notifications/"):
        return Response(status_code=202)
    if method == "initialize":
        v = params.get("protocolVersion", "")
        return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": {
            "protocolVersion": v if v in _MCP_PROTOCOL_VERSIONS else "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "dripdrop", "version": "1.0.0"}}})
    if method == "ping":
        return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": {}})
    if method == "tools/list":
        tools = [{"name": n, "description": d["description"],
                  "inputSchema": d["inputSchema"]}
                 for n, d in _mcp_tool_defs().items()]
        return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": {"tools": tools}})
    if method == "tools/call":
        d = _mcp_tool_defs().get(params.get("name", ""))
        if d is None:
            return JSONResponse(_mcp_result(id_, {"error": "unknown tool"}, True))
        try:
            return JSONResponse(_mcp_result(id_, d["fn"](email,
                                                         params.get("arguments") or {})))
        except Exception as e:
            return JSONResponse(_mcp_result(id_, {"error": str(e)}, True))
    return JSONResponse({"jsonrpc": "2.0", "id": id_,
                         "error": {"code": -32601, "message": "method not found"}})
```

Placeholders for this task only (replaced in Tasks 8–9):

```python
def _mcp_launch_arena_5x3(email, args):
    raise NotImplementedError("Task 8")

def _mcp_list_newsletters(email):
    raise NotImplementedError("Task 9")
```

- [ ] **Step 4: Run — PASS**  •  **Step 5: Commit** `feat(connector): stateless MCP streamable-http endpoint with 4 tool schemas`

---

### Task 8: Extract campaign core + wire `launch_arena_5x3`

**Files:** Modify `flowdrip_app.py:5579-5710` (refactor) + connector block; Test `tests/test_mcp_endpoint.py` (+ existing `tests/test_campaign_api.py` as the regression guard)

- [ ] **Step 1: Refactor with the existing suite as the failing-test guard.** Extract everything in `api_create_campaign` after owner resolution (from `spec = await request.json()`'s validation onward, i.e. lines ~5598-5710) into:

```python
def _api_campaign_core(owner: str, spec: dict) -> tuple:
    """Validate + generate + launch a campaign for `owner`. Returns
    (payload_dict, http_status). Extracted from api_create_campaign so the
    MCP tool and the HTTP route share one code path."""
```

The route body becomes: resolve key → 401, parse JSON → 400, then `payload, status = _api_campaign_core(owner, spec)` → `JSONResponse(payload, status_code=status)`. Every `return JSONResponse(X, status_code=Y)` inside the moved block becomes `return X, Y`. Nothing else changes — same helpers, same order, same messages.

- [ ] **Step 2: Run the guard** — `./.venv/Scripts/python -m pytest tests/test_campaign_api.py -v` → all PASS (55). If anything fails, the refactor changed behavior — fix before proceeding.
- [ ] **Step 3: Commit** `refactor(api): extract _api_campaign_core from api_create_campaign (no behavior change)`
- [ ] **Step 4: Write failing tests for the tool**

```python
def test_launch_tool_forces_5x3_and_updates_master(mcp_token, monkeypatch):
    seen = {}
    def fake_core(owner, spec):
        seen.update(owner=owner, spec=spec)
        return {"campaign_id": "camp1", "name": "N", "steps": 5,
                "contacts_queued": 5, "start_date": spec["start_date"],
                "schedule": [], "newsletter_enrollment": {"matched": True}}, 200
    monkeypatch.setattr(fa, "_api_campaign_core", fake_core)
    monkeypatch.setattr(fa, "_bdc_enqueue_tt", lambda *a, **k: 1)
    fa._bdc_record_companies([{"company": "Acme Co"}], added_by="p1@arena.com")
    r = _rpc(_client(), mcp_token, "tools/call", {"name": "launch_arena_5x3",
             "arguments": {"company": "Acme Co", "roles": ["PM"],
                           "start_date": "2026-07-27",
                           "contacts": [{"email": "v@acme.com"}],
                           "enroll_newsletter": "NL", "candidates": [{"x": 1}]}})
    out = json.loads(r.json()["result"]["content"][0]["text"])
    assert out["campaign_id"] == "camp1"
    assert seen["owner"] == "p1@arena.com"
    assert seen["spec"]["template"] == "fivebythree"
    assert "candidates" not in seen["spec"]          # structurally impossible
    assert fa._bdc_check_companies(["Acme Co"])[0]["status"] == "Campaign launched"

def test_launch_tool_skip_updates_master_no_tt(mcp_token, monkeypatch):
    monkeypatch.setattr(fa, "_api_campaign_core",
                        lambda o, s: ({"skipped": True, "reason": "no fit"}, 200))
    called = []
    monkeypatch.setattr(fa, "_bdc_enqueue_tt", lambda *a, **k: called.append(1))
    fa._bdc_record_companies([{"company": "Acme Co"}], added_by="p1@arena.com")
    r = _rpc(_client(), mcp_token, "tools/call", {"name": "launch_arena_5x3",
             "arguments": {"company": "Acme Co", "roles": ["PM"],
                           "start_date": "2026-07-27",
                           "contacts": [{"email": "v@acme.com"}],
                           "enroll_newsletter": "NL"}})
    out = json.loads(r.json()["result"]["content"][0]["text"])
    assert out["skipped"] is True and not called
    assert "skipped (no bench fit)" in fa._bdc_check_companies(["Acme Co"])[0]["status"]

def test_launch_tool_maps_http_errors(mcp_token, monkeypatch):
    monkeypatch.setattr(fa, "_api_campaign_core",
                        lambda o, s: ({"error": "content failed safety guard"}, 422))
    r = _rpc(_client(), mcp_token, "tools/call", {"name": "launch_arena_5x3",
             "arguments": {"company": "A", "roles": ["PM"], "start_date": "2026-07-27",
                           "contacts": [{"email": "v@a.com"}], "enroll_newsletter": "N"}})
    res = r.json()["result"]
    out = json.loads(res["content"][0]["text"])
    assert res["isError"] is True and out["retryable"] is True
```

- [ ] **Step 5: Run — FAIL**, then implement (replaces the Task-7 placeholder):

```python
def _mcp_launch_arena_5x3(email, args):
    spec = {k: v for k, v in (args or {}).items() if k != "candidates"}
    spec["template"] = "fivebythree"
    payload, status = _api_campaign_core(email, spec)
    company = (args.get("company") or "").strip()
    if status == 200 and payload.get("skipped"):
        _bdc_update_status(company,
                           f"Selected - skipped (no bench fit): {payload.get('reason', '')}")
        return payload
    if status == 200:
        _bdc_update_status(company, "Campaign launched")
        try:
            _bdc_enqueue_tt(company, args.get("contacts") or [], email)
        except Exception as e:
            print(f"[bdc] TT enqueue failed for {company}: {e}", flush=True)
        return payload
    payload = dict(payload)
    payload["retryable"] = status in (422, 502, 503)
    raise _McpToolError(payload)

class _McpToolError(Exception):
    """Carries a JSON payload back as an isError tool result."""
    def __init__(self, payload):
        self.payload = payload
        super().__init__(str(payload))
```

And in `api_mcp`'s `tools/call` except-arm, surface the payload:

```python
        except _McpToolError as te:
            return JSONResponse(_mcp_result(id_, te.payload, True))
        except Exception as e:
            return JSONResponse(_mcp_result(id_, {"error": str(e)}, True))
```

- [ ] **Step 6: Run — PASS** (new tests + `tests/test_campaign_api.py` still green)  •  **Step 7: Commit** `feat(connector): launch_arena_5x3 tool over shared campaign core`

---

### Task 9: `list_newsletters` tool

**Files:** Modify `flowdrip_app.py`; Test `tests/test_mcp_endpoint.py`

- [ ] **Step 1: Write failing test**

```python
def test_list_newsletters_binds_user_and_filters_evergreen(mcp_token, monkeypatch):
    bound = []
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda e: bound.append(e))
    monkeypatch.setattr(fa, "load_campaigns", lambda: [
        {"name": "Recruitment Rundown - CO Construction", "evergreen_only": True},
        {"name": "Some 4x4", "evergreen_only": False}])
    r = _rpc(_client(), mcp_token, "tools/call",
             {"name": "list_newsletters", "arguments": {}})
    out = json.loads(r.json()["result"]["content"][0]["text"])
    assert out == {"newsletters": ["Recruitment Rundown - CO Construction"]}
    assert bound == ["p1@arena.com"]
```

- [ ] **Step 2: Run — FAIL**, then implement (replaces placeholder; same binding pattern as the campaign route at flowdrip_app.py:5610-5614):

```python
def _mcp_list_newsletters(email):
    _CURRENT_USER_EMAIL.set(email)
    try:
        _switch_to_user_paths(email)
    except Exception:
        pass
    return {"newsletters": [c.get("name") for c in load_campaigns()
                            if c.get("evergreen_only")]}
```

- [ ] **Step 3: Run — PASS**  •  **Step 4: Commit** `feat(connector): list_newsletters tool`

---

### Task 10: Talent Trekker loader (pure function)

**Files:** Modify `flowdrip_app.py`; Test `tests/test_bd_connector.py`

- [ ] **Step 1: Write failing tests** — fake HTTP object records calls; sequence per spec (dedupe GET → create Customer if missing → create Contacts → verify GET):

```python
class _FakeTT:
    def __init__(self, existing=None):
        self.calls, self.existing = [], existing or []
    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        class R:
            status_code = 200
            def __init__(s, data): s._d = data
            def json(s): return {"data": s._d}
        if "/api/resource/Customer" in url:
            return R([{"name": e, "customer_name": e} for e in self.existing])
        return R([{"name": "c1"}] * len(kw.get("_verify", [])) or [])
    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        class R:
            status_code = 200
            def json(s): return {"data": {"name": kw["json"].get(
                "customer_name") or "contact-1"}}
        return R()

CFG = {"base_url": "https://arena.talent-trekker.com", "token": "k:s"}

def test_tt_load_creates_customer_and_contacts():
    http = _FakeTT()
    out = fa._tt_load_company(CFG, "Acme Co", [
        {"email": "v@acme.com", "first_name": "Val", "last_name": "P",
         "title": "VP Ops", "phone_office": "303-555-0100 ext 4"}], http=http)
    posts = [c for c in http.calls if c[0] == "POST"]
    cust = posts[0][2]["json"]
    assert cust["customer_name"] == "Acme Co"
    assert cust["custom_source_name"] == "ZoomInfo"          # exact case
    assert cust["custom_dh_branch"] == "Team Mountain Summit"
    contact = posts[1][2]["json"]
    assert contact["custom_primary_phone"] == "303-555-0100"  # ext stripped
    assert contact["links"] == [{"link_doctype": "Customer", "link_name": "Acme Co"}]
    assert contact["custom_contact_source"] == "ZoomInfo"
    assert out["customer"] == "Acme Co" and out["contacts_created"] == 1

def test_tt_load_reuses_existing_customer():
    http = _FakeTT(existing=["Acme Co"])
    fa._tt_load_company(CFG, "Acme Co", [{"email": "v@acme.com"}], http=http)
    posts = [c for c in http.calls if c[0] == "POST"]
    assert len(posts) == 1 and "Contact" in posts[0][1]      # no Customer create

def test_tt_load_skips_contact_without_email():
    http = _FakeTT()
    out = fa._tt_load_company(CFG, "Acme Co", [{"first_name": "NoEmail"}], http=http)
    assert out["contacts_created"] == 0

def test_tt_config_from_env(monkeypatch):
    monkeypatch.setenv("TT_API_KEY", "k")
    monkeypatch.setenv("TT_API_SECRET", "s")
    cfg = fa._tt_config()
    assert cfg == {"base_url": "https://arena.talent-trekker.com", "token": "k:s"}

def test_tt_config_missing_returns_none(monkeypatch):
    monkeypatch.delenv("TT_API_KEY", raising=False)
    monkeypatch.delenv("TT_API_SECRET", raising=False)
    assert fa._tt_config() is None
```

- [ ] **Step 2: Run — FAIL**
- [ ] **Step 3: Implement** — values from the phase-5 reference (exact field names verified live 2026-07-09):

```python
def _tt_config():
    k, s = os.environ.get("TT_API_KEY", ""), os.environ.get("TT_API_SECRET", "")
    if not (k and s):
        return None
    return {"base_url": os.environ.get("TT_BASE_URL",
                                       "https://arena.talent-trekker.com"),
            "token": f"{k}:{s}"}

def _tt_sanitize_phone(raw: str) -> str:
    m = re.match(r"[\d+()\- .]+", (raw or "").strip())
    return m.group(0).strip(" .") if m else ""

def _tt_load_company(cfg, company, contacts, http=None):
    """Push one company + its reps into Talent Trekker via Frappe REST
    (token auth). Raises on transport/HTTP failure — caller retries."""
    if http is None:
        import requests as http  # noqa — module has get/post
    base = cfg["base_url"].rstrip("/")
    hdr = {"Authorization": f"token {cfg['token']}"}
    q = json.dumps([["customer_name", "like", f"%{company}%"]])
    r = http.get(f"{base}/api/resource/Customer",
                 params={"filters": q, "fields": '["name","customer_name"]'},
                 headers=hdr, timeout=30)
    exact = next((d for d in r.json().get("data", [])
                  if (d.get("customer_name") or "").strip().lower()
                  == company.strip().lower()), None)
    if exact:
        cust_name = exact["name"]
    else:
        r = http.post(f"{base}/api/resource/Customer", headers=hdr, timeout=30, json={
            "customer_name": company, "customer_type": "Company",
            "custom_status_type": "Direct Hire",
            "custom_dh_status": "Direct Hire: Prospect",
            "custom_dh_company": "Arena Direct Hire",
            "custom_dh_branch": "Team Mountain Summit",
            "custom_source_name": "ZoomInfo"})
        cust_name = r.json()["data"]["name"]
    created = 0
    for ct in (contacts or []):
        em = (ct.get("email") or "").strip()
        if not em:
            continue
        phone = _tt_sanitize_phone(ct.get("phone_mobile")
                                   or ct.get("phone_office") or "")
        body = {"first_name": ct.get("first_name", ""),
                "last_name": ct.get("last_name", ""),
                "custom_primary_email": em, "email_id": em,
                "custom_status_type": "Direct Hire",
                "custom_contact_source": "ZoomInfo", "status": "Passive",
                "designation": ct.get("title", ""),
                "email_ids": [{"email_id": em, "is_primary": 1}],
                "links": [{"link_doctype": "Customer", "link_name": cust_name}]}
        if phone:
            body["custom_primary_phone"] = phone
            body["contact_no"] = phone
        http.post(f"{base}/api/resource/Contact", headers=hdr, timeout=30,
                  json=body)
        created += 1
        time.sleep(0.3)  # space calls per TT reliability notes
    return {"customer": cust_name, "contacts_created": created}
```

(Make the `time.sleep(0.3)` skippable in tests by keeping it — 1 contact per test = one 0.3s pause, acceptable.)

- [ ] **Step 4: Run — PASS**  •  **Step 5: Commit** `feat(connector): talent trekker loader over frappe token auth`

---

### Task 11: TT job queue + worker

**Files:** Modify `flowdrip_app.py`; Test `tests/test_bd_connector.py`

- [ ] **Step 1: Write failing tests**

```python
def test_tt_enqueue_and_process_success(bdc_db, monkeypatch):
    fa._bdc_record_companies([{"company": "Acme Co"}], added_by="p1@x.com")
    fa._bdc_enqueue_tt("Acme Co", [{"email": "v@acme.com"}], "p1@x.com")
    monkeypatch.setattr(fa, "_tt_config", lambda: {"base_url": "b", "token": "t"})
    monkeypatch.setattr(fa, "_tt_load_company",
                        lambda cfg, co, cts, http=None: {"customer": co,
                                                         "contacts_created": 1})
    assert fa._bdc_process_tt_jobs() == 1
    assert fa._bdc_check_companies(["Acme Co"])[0]["status"] == "Campaign launched + in TT"
    assert fa._bdc_process_tt_jobs() == 0                     # queue drained

def test_tt_final_failure_marks_master(bdc_db, monkeypatch):
    fa._bdc_record_companies([{"company": "Acme Co"}], added_by="p1@x.com")
    fa._bdc_enqueue_tt("Acme Co", [], "p1@x.com")
    monkeypatch.setattr(fa, "_tt_config", lambda: {"base_url": "b", "token": "t"})
    def boom(cfg, co, cts, http=None):
        raise RuntimeError("tt down")
    monkeypatch.setattr(fa, "_tt_load_company", boom)
    for _ in range(fa._BDC_TT_MAX_ATTEMPTS):
        fa._bdc_process_tt_jobs(ignore_backoff=True)
    assert fa._bdc_check_companies(["Acme Co"])[0]["status"] == "TT load failed"

def test_tt_no_config_leaves_job_pending(bdc_db, monkeypatch):
    fa._bdc_enqueue_tt("Acme Co", [], "p1@x.com")
    monkeypatch.setattr(fa, "_tt_config", lambda: None)
    assert fa._bdc_process_tt_jobs() == 0
    with fa._bdc_db() as con:
        assert con.execute("SELECT status FROM tt_jobs").fetchone()[0] == "pending"
```

- [ ] **Step 2: Run — FAIL**
- [ ] **Step 3: Implement**

```python
_BDC_TT_MAX_ATTEMPTS = 5

def _bdc_enqueue_tt(company, contacts, owner):
    with _bdc_db() as con:
        con.execute("INSERT INTO tt_jobs (company, contacts_json, owner) "
                    "VALUES (?,?,?)", (company, json.dumps(contacts or []), owner))
    return 1

def _bdc_process_tt_jobs(ignore_backoff=False):
    """Run due pending TT jobs once. Returns jobs completed successfully."""
    cfg = _tt_config()
    if cfg is None:
        return 0
    now = time.time()
    with _bdc_db() as con:
        rows = con.execute(
            "SELECT id, company, contacts_json, attempts FROM tt_jobs "
            "WHERE status='pending'" +
            ("" if ignore_backoff else " AND next_try<=?"),
            () if ignore_backoff else (now,)).fetchall()
    done = 0
    for jid, company, cts_json, attempts in rows:
        try:
            _tt_load_company(cfg, company, json.loads(cts_json))
            with _bdc_db() as con:
                con.execute("UPDATE tt_jobs SET status='done' WHERE id=?", (jid,))
            _bdc_update_status(company, "Campaign launched + in TT")
            done += 1
        except Exception as e:
            attempts += 1
            final = attempts >= _BDC_TT_MAX_ATTEMPTS
            with _bdc_db() as con:
                con.execute(
                    "UPDATE tt_jobs SET attempts=?, status=?, next_try=?, "
                    "last_error=? WHERE id=?",
                    (attempts, "failed" if final else "pending",
                     time.time() + min(3600, 60 * 2 ** attempts), str(e)[:500], jid))
            if final:
                _bdc_update_status(company, "TT load failed")
                print(f"[bdc] TT load FAILED for {company}: {e}", flush=True)
    return done

def _bdc_start_tt_worker():
    """Daemon thread: drain TT jobs every 60s. Started once at server startup."""
    import threading
    def loop():
        while True:
            try:
                _bdc_process_tt_jobs()
            except Exception as e:
                print(f"[bdc] tt worker error: {e}", flush=True)
            time.sleep(60)
    t = threading.Thread(target=loop, daemon=True, name="bdc-tt-worker")
    t.start()
    return t
```

Startup wiring: find where the app starts its existing background work (grep `app.on_startup` / the queue-processor start near the `ui.run(` call at the bottom of `flowdrip_app.py`) and add `_bdc_start_tt_worker()` beside it, guarded the same way the other server-mode-only threads are guarded (`_SERVER_MODE`), so importing the module in tests spawns nothing.

- [ ] **Step 4: Run — PASS**  •  **Step 5: Commit** `feat(connector): tt job queue + retry worker, wired at server startup`

---

### Task 12: `pipelineblast-app` skill package

**Files:**
- Create: `C:\Users\mkvau\claude\skills-build\pipelineblast-app\SKILL.md`
- Create: `...\pipelineblast-app\references\{source-companies.md, zoominfo-contacts.md, dedupe-master.md, dripdrop-campaign.md, tt-verification.md}`
- No server code, no tests — verification is a zip-contents listing.

- [ ] **Step 1: Copy unchanged phases** — `source-companies.md` and `zoominfo-contacts.md` copied verbatim from `C:\Users\mkvau\.claude\skills\pipelineblast\references\`.
- [ ] **Step 2: Write `SKILL.md`** — from the existing pipelineblast SKILL.md with: name `pipelineblast` (same trigger phrases), description noting v1.0-app and that it REQUIRES the DripDrop, ZoomInfo, and Indeed connectors; phase list where Phase 5 is "verify TT results"; a "version: app-1.0" line in the description for support triage.
- [ ] **Step 3: Write `dedupe-master.md`** — same policy text (loose match, append-before-campaigns, false-skip-is-cheaper), mechanics replaced: call `check_companies` with the company name plus any suspected variants; treat any `already_worked` as skip; after selection call `record_companies` with city/type/week/status.
- [ ] **Step 4: Write `dripdrop-campaign.md`** — from the current 5x3 API reference with: Method 1 = the `launch_arena_5x3` tool (same field semantics table, same skip-response rules, same weekday verification); call `list_newsletters` first to resolve `enroll_newsletter` exactly, and if none fits the run's market, STOP and flag Mike (launches hold until the newsletter exists); all XHR/browser-tab mechanics deleted; retry rules keyed on the tool's `retryable` flag. Method 2 (UI wizard) deleted — partners have no browser access to the app.
- [ ] **Step 5: Write `tt-verification.md`** — the CRM load is automatic server-side after each launch; the skill's Phase 5 is: report per-company TT status from the master (`Campaign launched + in TT` vs `TT load failed`), flag failures to Mike, never attempt manual CRM writes.
- [ ] **Step 6: Zip** — `powershell Compress-Archive -Path C:\Users\mkvau\claude\skills-build\pipelineblast-app\* -DestinationPath C:\Users\mkvau\claude\skills-build\pipelineblast-app.zip -Force`, then list the archive contents to verify all 6 files present.
- [ ] **Step 7: Commit** the skill source folder if it's inside a repo; otherwise done (skills-build is outside FunnelForge — no commit).

---

### Task 13: Full verification + rollout notes

- [ ] **Step 1: Full new-suite run** — `./.venv/Scripts/python -m pytest tests/test_bd_connector.py tests/test_mcp_endpoint.py tests/test_campaign_api.py -v` → all green.
- [ ] **Step 2: Broader regression** — `./.venv/Scripts/python -m pytest tests/ -x -q --ignore=tests/test_live_ai.py`; compare failures against the known ~8 flaky baseline; anything NEW gets fixed before calling it done.
- [ ] **Step 3: Syntax gate for deploy** — `./.venv/Scripts/python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read())"` → no output.
- [ ] **Step 4: Commit any stragglers; do NOT deploy.** Deploy is explicitly deferred: this rides `feat/5x3-campaign`, which must NOT go to prod until the Component-2 matching source is repointed to the ATS (both routines are disabled for exactly this reason). Rollout order when that lands: (1) deploy branch; (2) `pip` nothing — no new deps; (3) set `TT_API_KEY`/`TT_API_SECRET` (+ optional `TT_BASE_URL`, `DD_PUBLIC_BASE_URL`) in the server environment; (4) seed the master: `POST /api/v1/master/import` with Mike's key + the current `companies_master.csv` body; (5) Mike adds `https://dripdripdrop.ai/mcp` as a custom connector on his own claude.ai account, uploads the zip, runs ONE real end-to-end campaign; (6) only then send partners `docs/pipelineblast-partner-setup.md` + the zip + their DripDrop invites.

---

## Self-Review (done at planning time)

- **Spec coverage:** MCP endpoint ✓ (T7), OAuth ✓ (T5-6), 4 tools ✓ (T7-9), shared master SQLite + seed ✓ (T1-4), server-side TT ✓ (T10-11), skill zip ✓ (T12), rollout gates ✓ (T13). Spec's "MCP SDK" line amended to hand-rolled (no-new-deps constraint) — spec updated 2026-07-21.
- **Placeholder scan:** Task-7 `NotImplementedError` fns are explicit cross-task seams replaced in T8/T9, not TBDs.
- **Type consistency:** `_api_campaign_core(owner, spec) -> (dict, int)` used identically in T8 route + tool; `_bdc_check_companies` result shape consistent across T3/T7/T8 tests; `_tt_config()` dict shape consistent across T10/T11.
