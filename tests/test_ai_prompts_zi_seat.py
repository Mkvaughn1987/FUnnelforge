"""AI Prompts "Teach Claude to Use ZoomInfo" card (Mike 2026-10-02, 2026-10-07).

Users kept running out of the shared Bulk Credits and could not get the
browser half going on their own seat. The prompt has to switch pools on a
quota error, walk the Talent search, and name the cause and the fix when
something stops it rather than just stopping.

2026-10-07: it asks nothing. The card is a lesson for the rest of the chat,
so picking it goes straight to the finished prompt, and the tile says only
who it is for.
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


def _prompt(aip):
    req = aip._req_from_starter(aip.STARTER_BY_ID["zi_seat"])
    return " ".join(aip.build_prompt(req).split())


def test_card_is_on_the_arena_and_staffing_pickers(aip):
    import staffing_prompts as sp
    assert "zi_seat" in aip.STARTER_BY_ID
    assert "zi_seat" in sp.STAFFING.starter_by_id
    ids = [st["id"] for st in aip.STARTERS]
    assert ids[-1] == "other" and ids[-2] == "zi_seat"


def test_tile_says_who_it_is_for_and_nothing_about_how(aip):
    st = aip.STARTER_BY_ID["zi_seat"]
    pitch = aip.ZI_SEAT_PITCH
    assert pitch.startswith("Is ZoomInfo giving you issues? Out of credits?")
    assert "teaches Claude or ChatGPT" in pitch
    assert len(pitch) <= 110  # the tile cap in test_aip_walkthrough
    assert st["sub"] == pitch
    assert aip.ARENA.tile_short["zi_seat"] == pitch
    for word in ("Limit exceeded", "recruiter-app", "Chrome extension"):
        assert word not in pitch


def test_asks_no_questions(aip):
    r = aip.ROUTINE_BY_KEY["zi_seat"]
    assert r["fields"] == []
    # The questions screen would hold only the empty free-text step.
    assert [k for k, _ in aip._aip_sections_for(r)] == ["extra"]
    req = aip._req_from_starter(aip.STARTER_BY_ID["zi_seat"])
    assert req["vals"] == {}
    assert aip.no_questions(req)
    assert not aip.no_questions(aip._req_from_starter(aip.STARTER_BY_ID["mpc"]))
    assert not aip.no_questions({"routine": "nope"})
    assert not aip.no_questions(None)


def test_prompt_is_a_standing_rule_with_no_details_table(aip):
    p = _prompt(aip)
    assert "THE DETAILS" not in p
    assert "I HAVEN'T DECIDED" not in p
    assert "standing rule for the rest of this chat" in p
    assert "up to 10 per company" in p
    assert "C-Level, VP, Director and Manager" in p
    assert "If the job names a state, Candidate Info > Location" in p
    assert "{" not in p and "}" not in p


def test_quota_error_switches_to_the_seat_not_a_stop(aip):
    p = _prompt(aip)
    assert "Limit exceeded" in p
    assert "switch to my own ZoomInfo seat" in p
    assert "recruiter-app.zoominfo.com" in p
    assert "Export CSV" in p
    # The pull rule is quoted in a step, so the generic ZOOMINFO section is
    # not tacked on a second time.
    assert "ZOOMINFO Any time this job" not in p


def test_says_what_to_fix_when_it_does_not_work(aip):
    p = _prompt(aip)
    assert "do not just stop" in p
    for cause in ("Chrome extension is not installed",
                  "Allow all browser actions",
                  "sign in at recruiter-app.zoominfo.com myself",
                  "ZoomInfo connector is switched off",
                  "Export is greyed out"):
        assert cause in p, cause


def test_never_types_a_password_and_names_no_assistant(aip):
    p = _prompt(aip)
    assert "Never type a password" in p
    for name in ("Claude", "ChatGPT", "GPT"):
        assert name not in p


def test_connector_describes_it_with_no_questions(aip):
    runs = {x["run"]: x for x in aip.describe_runs()}
    assert runs["zi_seat"]["questions"] == []
    assert runs["zi_seat"]["about"] == aip.ZI_SEAT_PITCH
