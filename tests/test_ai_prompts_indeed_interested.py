"""AI Prompts "Indeed Interested into DD & TT" run (Mike 2026-10-10).

His indeed-to-tt run with the DripDrop half added: the first run clears a
backlog (100 by default), then it repeats on a schedule picked on the
details step (Tuesday and Thursday recommended), taking only who is new.
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
    assert "100" in aip.ARENA.tile_short["indeed_interested"]


def test_schedule_is_asked_with_the_details_not_on_its_own_step(aip):
    r = aip.ROUTINE_BY_KEY["indeed_interested"]
    assert r["no_repeat"]
    assert "repeat_on" not in r["field_by_key"]
    assert [k for k, _ in aip._aip_sections_for(r)] == ["details", "extra"]
    f = r["field_by_key"]["ind_schedule"]
    assert f["section"] == "details"
    assert f["default"].startswith("Every Tuesday and Thursday")
    assert "recommended" in f["default"]
    assert r["intro"]["details"].startswith("The first run clears a backlog")


def test_backlog_of_100_then_tuesday_and_thursday(aip):
    p = _prompt(aip)
    assert "This first run clears a backlog: stop once 100 new people" in p
    assert "Every run after this one takes only the people who are new" in p
    assert "runs every Tuesday and Thursday at 3:00pm my local time" in p
    assert "runs on this computer, not in the cloud" in p
    assert "THEN MAKE IT REPEAT" not in p
    assert "Clear a backlog first" in p


def test_other_schedules_and_just_once(aip):
    p = _prompt(aip, ind_schedule=aip.IND_SCHEDULES[1], ind_time="8:00am")
    assert "every Monday, Wednesday and Friday at 8:00am" in p
    p = _prompt(aip, ind_schedule=aip.IND_SCHEDULES[-1])
    assert "recurring task" not in p
    r = aip.ROUTINE_BY_KEY["indeed_interested"]
    assert not aip._visible(r, {"ind_schedule": aip.IND_SCHEDULES[-1]},
                            r["field_by_key"]["ind_time"])


def test_backlog_sizes(aip):
    assert "stop once 50 new people" in _prompt(aip, ind_backlog="50 people")
    p = _prompt(aip, ind_backlog="Everyone waiting")
    assert "clears the whole backlog" in p
    assert "Tell me how many that is before you start adding" in p


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


def test_owner(aip):
    assert "Owner set to Mike Vaughn" in _prompt(aip, ind_owner="Mike Vaughn")
    # "Me" typed into the box means the same as leaving it blank.
    assert "Owner set to me, the person signed in" in _prompt(aip,
                                                              ind_owner="Me")


def test_stops_on_an_indeed_warning_and_never_signs_in(aip):
    p = _prompt(aip)
    assert "stop the whole run and quote it" in p
    assert "Never type a password" in p
