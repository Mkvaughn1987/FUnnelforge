"""Client alias + Ref #: ats.py side.

Every real candidate used in outreach is named by their real first name + last
initial ("Travis K.") and cited by talent id ("Ref #1042"), so a client reply
can be traced back to the Pipeline record. No made-up names.
"""
import sqlite3
import sys

import pytest

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

OWNER = "mike@arenastaffing.net"


@pytest.fixture
def ats(tmp_path, monkeypatch):
    db = tmp_path / "ats.db"
    con = sqlite3.connect(str(db))
    con.executescript(_SCHEMA)
    con.commit()
    con.close()
    monkeypatch.setenv("ATS_DB_PATH", str(db))
    sys.modules.pop("ats", None)
    import ats as mod
    return mod


def _card(**kw):
    rec = {"name": "Travis Kruse", "email": "kruse-24@hotmail.com",
           "phone": "623-235-4346", "state": "AZ",
           "current_title": "EHS Specialist II",
           "resume_text": "Travis Kruse EHS Specialist, refrigeration, OSHA."}
    rec.update(kw)
    return rec


def test_upsert_card_adds_and_returns_alias_and_ref(ats):
    res = ats.upsert_card_record(_card(), OWNER)
    assert res["status"] == "added"
    assert isinstance(res["id"], int)
    assert res["ref"] == "Ref #%d" % res["id"]
    assert res["alias"] == "Travis K."


def test_upsert_card_dedupes_on_repeat_use(ats):
    a = ats.upsert_card_record(_card(), OWNER)
    b = ats.upsert_card_record(_card(phone=""), OWNER)
    assert b["id"] == a["id"]
    assert b["alias"] == a["alias"]  # stable once minted
    c = ats.upsert_card_record(_card(email="", external_id="cw-1"), OWNER)
    assert c["id"] == a["id"]  # name+state dedupe
    d = ats.upsert_card_record(
        {"name": "Someone Else", "external_id": "cw-1", "email": "x@y.com"}, OWNER)
    assert d["id"] == a["id"]  # external_id stamped on the prior send


def test_upsert_card_without_identity_is_junk(ats):
    res = ats.upsert_card_record({"name": "Travis"}, OWNER)
    assert res["status"] == "junk" and res["id"] is None and res["ref"] == ""


@pytest.mark.parametrize("first,last,want", [
    ("Travis", "Kruse", "Travis K."), ("ian", "nguyen", "Ian N."),
    ("Mary Ann", "O'Neil", "Mary O."), ("Sarah", "", "Sarah"),
    ("", "Kruse", ""), (None, None, "")])
def test_real_name_label(ats, first, last, want):
    assert ats.real_name_label(first, last) == want


def test_alias_is_real_first_name_even_with_old_stored_alias(ats):
    t = ats.upsert_card_record(_card(), OWNER)
    con = ats._con()
    con.execute("UPDATE talents SET client_alias='Aaron M.' WHERE id=?", (t["id"],))
    con.commit()
    con.close()
    assert ats.ensure_client_alias(t["id"]) == "Travis K."
    # A client reply quoting the old made-up alias still resolves.
    assert [r["id"] for r in ats.find_by_ref_or_alias("Aaron M.")] == [t["id"]]
    assert ats.ensure_client_alias(999999) == ""


@pytest.mark.parametrize("q", ["{id}", "#{id}", "ref {id}", "Ref #{id}",
                               "REF#{id}"])
def test_search_by_ref(ats, q):
    t = ats.upsert_card_record(_card(), OWNER)
    rows = ats.keyword_search(q.format(id=t["id"]))
    assert rows and rows[0]["id"] == t["id"]


def test_search_by_alias_and_alias_with_ref(ats):
    t = ats.upsert_card_record(_card(), OWNER)
    for q in (t["alias"], t["alias"].rstrip(".").lower(),
              "%s (%s)" % (t["alias"], t["ref"])):
        rows = ats.keyword_search(q)
        assert rows and rows[0]["id"] == t["id"], q


def test_search_ref_prepends_without_dropping_keyword_hits(ats):
    # FTS ignores 1-char tokens, so give the talent a multi-digit id.
    con = ats._con()
    con.execute("INSERT INTO talents(id, first_name) VALUES(1041, 'pad')")
    con.commit()
    con.close()
    t = ats.upsert_card_record(_card(), OWNER)
    assert t["id"] == 1042
    other = ats.upsert_card_record(
        {"name": "Nina Refrig", "email": "n@x.com", "current_title": "Tech",
         "resume_text": "worked on unit %d chillers" % t["id"]}, OWNER)
    rows, meta = ats.keyword_search(str(t["id"]), with_meta=True)
    ids = [r["id"] for r in rows]
    assert ids[0] == t["id"]
    assert other["id"] in ids
    assert len(ids) == len(set(ids))
    assert "origin" in meta


def test_search_ref_respects_owner_scope(ats):
    t = ats.upsert_card_record(_card(), OWNER)
    assert ats.keyword_search("Ref #%d" % t["id"], owner="someone@else.com") == []


def test_plain_keyword_search_unchanged(ats):
    ats.upsert_card_record(_card(), OWNER)
    rows = ats.keyword_search("refrigeration")
    assert len(rows) == 1
    assert ats.keyword_search("") == []
