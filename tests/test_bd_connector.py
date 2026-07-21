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
