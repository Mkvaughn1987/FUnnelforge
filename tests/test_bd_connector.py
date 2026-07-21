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
