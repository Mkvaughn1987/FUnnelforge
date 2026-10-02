"""AI Prompts "upload resumes from Downloads into DD & TT" run (Mike 2026-10-02).

The resume-sweep (Talent Trekker) and dripdrop-resume-load (DripDrop) skills
as one scheduled run: Wednesday and Friday, one ledger, each place tracked
separately so a person who only reached one is retried for the other.
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
    req = aip._req_from_starter(aip.STARTER_BY_ID["resume_sweep"])
    req["vals"].update(vals)
    return " ".join(aip.build_prompt(req).split())


def test_card_is_on_the_arena_and_staffing_pickers(aip):
    import staffing_prompts as sp
    assert "resume_sweep" in aip.STARTER_BY_ID
    assert "resume_sweep" in sp.STAFFING.starter_by_id
    assert "Wednesday and Friday" in aip.STARTER_BY_ID["resume_sweep"]["label"]


def test_repeats_wednesday_and_friday_on_this_computer(aip):
    p = _prompt(aip)
    assert "THEN MAKE IT REPEAT" in p
    assert "Wednesday and Friday" in p
    assert "Monday" not in p
    assert "not one that runs in the cloud" in p


def test_both_destinations_and_their_dedupe(aip):
    p = _prompt(aip)
    assert "candidates_search" in p and "import_candidates" in p
    assert "arena.talent-trekker.com" in p
    assert "Source to Resume Upload" in p
    assert "never by name" in p
    assert "3KB" in p


def test_carries_the_zoominfo_rule_like_every_prompt(aip):
    assert "ZOOMINFO" in aip.build_prompt(
        aip._req_from_starter(aip.STARTER_BY_ID["resume_sweep"]))


def test_dripdrop_only_when_tt_is_off(aip):
    p = _prompt(aip, to_tt=False)
    assert "Create Talent" not in p
    assert "talent-trekker.com" not in p
    assert "import_candidates" in p


def test_since_choices(aip):
    assert "last 7 days and say so" in _prompt(aip)
    assert "whatever its age" in _prompt(aip, since="Everything in the folder")
