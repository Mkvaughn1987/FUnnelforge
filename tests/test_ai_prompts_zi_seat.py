"""AI Prompts "Pull ZoomInfo contacts with my own seat" run (Mike 2026-10-02).

Users kept running out of the shared Bulk Credits and could not get the
browser half going on their own seat. The prompt has to switch pools on a
quota error, walk the Talent search, and name the cause and the fix when
something stops it rather than just stopping.
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
    req = aip._req_from_starter(aip.STARTER_BY_ID["zi_seat"])
    req["vals"].update(vals)
    return " ".join(aip.build_prompt(req).split())


def test_card_is_on_the_arena_and_staffing_pickers(aip):
    import staffing_prompts as sp
    assert "zi_seat" in aip.STARTER_BY_ID
    assert "zi_seat" in sp.STAFFING.starter_by_id
    ids = [st["id"] for st in aip.STARTERS]
    assert ids[-1] == "other" and ids[-2] == "zi_seat"


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


def test_blank_companies_makes_it_a_standing_rule(aip):
    p = _prompt(aip)
    assert "standing rule for the rest of this chat" in p
    assert "Candidate Info > Location" not in p


def test_named_companies_and_state(aip):
    p = _prompt(aip, companies="Summit Mechanical, Front Range Fab",
                zi_state="Colorado", per_company="5")
    assert "standing rule" not in p
    assert "Summit Mechanical, Front Range Fab" in p
    assert "Candidate Info > Location: Colorado." in p
    assert "up to 5 per company" in p


def test_never_types_a_password_and_names_no_assistant(aip):
    p = _prompt(aip)
    assert "Never type a password" in p
    for name in ("Claude", "ChatGPT", "GPT"):
        assert name not in p
