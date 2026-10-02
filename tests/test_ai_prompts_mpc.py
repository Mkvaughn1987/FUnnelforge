"""AI Prompts "Start with an MPC" run (Mike 2026-10-02).

The people are picked off the DripDrop Pipeline on the page, reach the
prompt with their Ref #, and the run launches the Arena 5x3 pinned to them.
"""
import sqlite3
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_ai_prompts_catalogue import _stub_nicegui  # noqa: E402


@pytest.fixture(scope="module")
def aip():
    _stub_nicegui()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import ai_prompts
    return ai_prompts


def _prompt(aip, **vals):
    req = aip._req_from_starter(aip.STARTER_BY_ID["mpc"])
    req["vals"].update(vals)
    return " ".join(aip.build_prompt(req).split())


def test_mpc_is_the_first_arena_card(aip):
    st = aip.ARENA.starters[0]
    assert st["id"] == "mpc" and st["routine"] == "mpc_campaign"
    assert "MPC" in st["label"] and st["icon"]


def test_candidates_are_picked_from_the_pipeline(aip):
    f = aip.ROUTINE_BY_KEY["mpc_campaign"]["field_by_key"]["candidates"]
    assert f["type"] == "people" and f["ask"]


def test_prompt_looks_people_up_by_ref_and_pins_them_on_a_5x3(aip):
    p = _prompt(aip, location="the Denver metro",
                candidates="Jane Doe - Estimator, Denver CO (Ref #1042)")
    assert "(Ref #1042)" in p
    assert "candidates_search using their Ref #" in p
    assert 'template "fivebythree"' in p
    assert '"_pool_id": the id from candidates_search' in p
    assert "{" not in p.replace('{"_pool_id"', "")


def test_unpicked_candidates_are_a_visible_gap(aip):
    assert "<which candidates>" in _prompt(aip)


def test_person_line_ends_with_the_ref(aip):
    row = {"id": 7, "first_name": "Jane", "last_name": "Doe",
           "current_title": "Estimator", "city": "Denver", "state": "CO"}
    assert aip._person_line(row) == "Jane Doe - Estimator, Denver CO (Ref #7)"
    assert aip._person_line({"id": 8}) == "No name (Ref #8)"
    # The stored answer is ";"-joined, so a ";" in a title cannot split it.
    assert ";" not in aip._person_line(dict(row, current_title="PM; Lead"))


def test_people_list_round_trips(aip):
    v = aip.PEOPLE_SEP.join(["A (Ref #1)", "B (Ref #2)"])
    assert aip._people_list(v) == ["A (Ref #1)", "B (Ref #2)"]
    assert aip._people_list("") == []


def _fake_ats(monkeypatch, rows):
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE talents (id INTEGER PRIMARY KEY, first_name, "
                "last_name, current_title, city, state, owner_email, "
                "resume_text)")
    con.executemany("INSERT INTO talents VALUES (?,?,?,?,?,?,?,?)", rows)

    class _Con:
        def execute(self, *a):
            return con.execute(*a)

        def close(self):
            pass

    fake = types.ModuleType("ats")
    fake._con = lambda: _Con()
    monkeypatch.setitem(sys.modules, "ats", fake)


def test_pipeline_lists_own_people_first(aip, monkeypatch):
    _fake_ats(monkeypatch, [
        (1, "Old", "Mine", "", "", "", "me@x.com", "x"),
        (2, "New", "Theirs", "", "", "", "them@x.com", "x"),
        (3, "New", "Mine", "", "", "", "Me@x.com", "x"),
    ])
    monkeypatch.setattr(aip, "_ff", lambda: types.SimpleNamespace(
        _ats_allowed=lambda e: True))
    got = aip._pipeline_people("me@x.com")
    assert got == ["New Mine (Ref #3)", "Old Mine (Ref #1)",
                   "New Theirs (Ref #2)"]


def test_no_pipeline_access_means_no_list(aip, monkeypatch):
    _fake_ats(monkeypatch, [(1, "A", "B", "", "", "", "me@x.com", "x")])
    monkeypatch.setattr(aip, "_ff", lambda: types.SimpleNamespace(
        _ats_allowed=lambda e: False))
    assert aip._pipeline_people("me@x.com") == []
    assert aip._pipeline_people("") == []
