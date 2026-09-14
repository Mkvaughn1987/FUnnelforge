"""Client alias + Ref #: ats.py side.

Every real candidate used in outreach gets a stable, per-owner-unique alias
("Trent K.") and is cited by talent id ("Ref #1042"), so a client reply can be
traced back to the Pipeline record.
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
    first, initial = res["alias"].split(" ")
    assert first != "Travis"
    assert len(initial) == 2 and initial.endswith(".")


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


def test_alias_never_real_first_name_and_unique_per_owner(ats, monkeypatch):
    # Shrink the name pool so collisions are forced.
    monkeypatch.setattr(ats, "_ALIAS_FIRST_NAMES", ("Aaron", "Blake"))
    monkeypatch.setattr(ats, "_ALIAS_INITIALS", "AB")
    ids = []
    for i, fn in enumerate(["Aaron", "Carl", "Dave"]):
        ids.append(ats.upsert_card_record(
            {"name": "%s Person%d" % (fn, i), "email": "p%d@x.com" % i}, OWNER)["id"])
    aliases = [ats.ensure_client_alias(t) for t in ids]
    assert len(set(aliases)) == 3
    assert not aliases[0].startswith("Aaron")
    # A different owner may reuse the same alias.
    other = ats.upsert_card_record({"name": "Eve Other", "email": "e@x.com"},
                                   "other@arenastaffing.net")
    assert other["alias"]


def test_alias_pool_exhausted_returns_empty(ats, monkeypatch):
    monkeypatch.setattr(ats, "_ALIAS_FIRST_NAMES", ("Aaron",))
    monkeypatch.setattr(ats, "_ALIAS_INITIALS", "A")
    a = ats.upsert_card_record({"name": "Carl One", "email": "1@x.com"}, OWNER)
    b = ats.upsert_card_record({"name": "Dave Two", "email": "2@x.com"}, OWNER)
    assert a["alias"] == "Aaron A."
    assert b["alias"] == ""


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
