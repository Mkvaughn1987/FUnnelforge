"""BD connector: shared master, OAuth store, TT jobs, MCP tools.
Spec: docs/superpowers/specs/2026-07-21-pipelineblast-app-connector-design.md
Plan: docs/superpowers/plans/2026-07-21-pipelineblast-app-connector.md
"""
import pytest
import flowdrip_app as fa


@pytest.fixture()
def bdc_db(tmp_path, monkeypatch):
    """Point the connector DB at a temp file."""
    monkeypatch.setattr(fa, "_bdc_db_path", lambda: tmp_path / "bd_connector.db")
    return tmp_path / "bd_connector.db"


# ── Task 1: store ──────────────────────────────────────────────────
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


# ── Task 2: normalizer ─────────────────────────────────────────────
@pytest.mark.parametrize("a,b,same", [
    ("Mortenson Construction", "mortenson construction, Inc.", True),
    ("Roche Constructors, Inc.", "Roche Constructors LLC", True),
    ("Acme Co", "Acme Company", True),
    ("Brinkmann Constructors", "Brinkman Construction", False),  # different firms
    ("PCL", "PCL Construction", False),  # bare acronym stays distinct
])
def test_bdc_norm_company(a, b, same):
    assert (fa._bdc_norm_company(a) == fa._bdc_norm_company(b)) is same


# ── Task 3: master ops ─────────────────────────────────────────────
def test_check_then_record_then_check(bdc_db):
    r = fa._bdc_check_companies(["Mortenson Construction"])
    assert r == [{"company": "Mortenson Construction", "result": "new"}]
    added = fa._bdc_record_companies(
        [{"company": "Mortenson Construction", "city": "Denver", "type": "GC",
          "week_surfaced": "2026-W30", "status": "Selected"}],
        added_by="p1@arena.com")
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


# ── Task 4: CSV seed ───────────────────────────────────────────────
SEED = ("Company,City,Type,Week Surfaced,Date,Status\n"
        "Mortenson Construction,Denver,GC,2026-W12,2026-03-16,Campaign launched + in TT\n"
        "Roche Constructors Inc,Greeley,GC,2026-W12,2026-03-16,Selected\n")


def test_seed_master_idempotent(bdc_db):
    assert fa._bdc_seed_master_from_csv(SEED) == {"added": 2, "skipped": 0}
    assert fa._bdc_seed_master_from_csv(SEED) == {"added": 0, "skipped": 2}
    assert fa._bdc_check_companies(["Mortenson Construction"])[0]["result"] == "already_worked"


# ── Task 5: OAuth primitives ───────────────────────────────────────
def test_token_mint_resolve_expire(bdc_db):
    tok = fa._bdc_mint_token("p1@arena.com", "cli1", kind="access", ttl=3600)
    assert tok.startswith("ddmcp_")
    assert fa._bdc_resolve_token(tok) == "p1@arena.com"
    expired = fa._bdc_mint_token("p1@arena.com", "cli1", kind="access", ttl=-1)
    assert fa._bdc_resolve_token(expired) is None
    assert fa._bdc_resolve_token("ddmcp_bogus") is None
    assert fa._bdc_resolve_token("") is None


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


# ── Task 10: Talent Trekker loader ─────────────────────────────────
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
        return R([])

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
