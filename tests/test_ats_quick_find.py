"""Pipeline top-bar search: find a candidate by name, email or Ref #."""
import sqlite3
import sys

import pytest

from tests.test_candidate_alias_refs_ats import _SCHEMA


@pytest.fixture
def ats(tmp_path, monkeypatch):
    db = tmp_path / "ats.db"
    con = sqlite3.connect(str(db))
    con.executescript(_SCHEMA)
    con.executemany(
        "INSERT INTO talents(id, first_name, last_name, email, owner_email) VALUES (?,?,?,?,?)",
        [(1, "John", "Smith", "js@x.com", "a@x.com"),
         (2, "Johnny", "Cash", "jc@y.com", "b@x.com"),
         (3, "Maria", "Lopez", "maria.l@z.com", "a@x.com")])
    con.commit()
    con.close()
    monkeypatch.setenv("ATS_DB_PATH", str(db))
    sys.modules.pop("ats", None)
    import ats as mod
    return mod


def _ids(rows):
    return [r["id"] for r in rows]


def test_partial_first_name_matches_everyone_on_the_team(ats):
    assert sorted(_ids(ats.quick_find("john"))) == [1, 2]


def test_every_word_must_match(ats):
    assert _ids(ats.quick_find("john smi")) == [1]


def test_email_and_ref_number(ats):
    assert _ids(ats.quick_find("maria.l@")) == [3]
    assert _ids(ats.quick_find("Ref #2"))[0] == 2


def test_one_character_returns_nothing(ats):
    assert ats.quick_find("j") == []
