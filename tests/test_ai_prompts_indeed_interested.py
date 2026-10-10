"""AI Prompts "Indeed Interested into DD & TT" run (Mike 2026-10-10).

His indeed-to-tt run with the DripDrop half added: Tuesday and Thursday,
resume-bearing Interested candidates only, deduped against each system.
"""
import sys
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
    req = aip._req_from_starter(aip.STARTER_BY_ID["indeed_interested"])
    req["vals"].update(vals)
    return " ".join(aip.build_prompt(req).split())


def test_card_is_on_the_arena_and_staffing_pickers(aip):
    import staffing_prompts as sp
    assert "indeed_interested" in aip.STARTER_BY_ID
    assert "indeed_interested" in sp.STAFFING.starter_by_id
    groups = dict(aip.ARENA.tile_groups)
    assert "indeed_interested" in groups["Daily tasks"]
    assert "indeed_interested" in aip.ARENA.tile_short


def test_repeats_tuesday_and_thursday_on_this_computer(aip):
    p = _prompt(aip)
    assert "THEN MAKE IT REPEAT" in p
    assert "Tuesday and Thursday" in p
    assert "not one that runs in the cloud" in p


def test_both_destinations_and_their_dedupe(aip):
    p = _prompt(aip)
    assert "candidates_search" in p and "import_candidates" in p
    assert "arena.talent-trekker.com" in p
    assert "Source set to Indeed" in p
    assert "Talent Rank set to 3" in p
    assert "Owner set to me" in p
    assert "last 10 digits" in p
    assert "90% match" in p
    assert "%%" not in p


def test_only_people_with_a_resume(aip):
    p = _prompt(aip)
    assert "only someone with Download resume qualifies" in p
    assert "profile only" in p


def test_talent_trekker_only_drops_the_connector(aip):
    p = _prompt(aip, ind_dest="Talent Trekker only")
    assert "import_candidates" not in p
    assert "candidates_count" not in p
    assert "DripDrop connector" not in p
    assert "TOOLS" not in p
    assert "Create Talent" in p


def test_dripdrop_only_drops_talent_trekker(aip):
    p = _prompt(aip, ind_dest="DripDrop only")
    assert "Create Talent" not in p
    assert "talent-trekker.com" not in p
    assert "import_candidates" in p
    r = aip.ROUTINE_BY_KEY["indeed_interested"]
    assert not aip._visible(r, {"ind_dest": "DripDrop only"},
                            r["field_by_key"]["ind_owner"])


def test_project_by_name_or_link(aip):
    assert "open the one called Default." in _prompt(aip)
    link = "https://resumes.indeed.com/hiring/projects/abc/"
    assert "project at %s" % link in _prompt(aip, ind_project=link)


def test_count_and_owner(aip):
    assert "who is not already in the ledger" in _prompt(aip)
    p = _prompt(aip, ind_count="25", ind_owner="Mike Vaughn")
    assert "Stop once 25 new people have been added" in p
    assert "Owner set to Mike Vaughn" in p


def test_stops_on_an_indeed_warning_and_never_signs_in(aip):
    p = _prompt(aip)
    assert "stop the whole run and quote it" in p
    assert "Never type a password" in p
