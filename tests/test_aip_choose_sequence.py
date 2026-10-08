"""AI Prompts "Choose your sequence" step: every offered Arena sequence has a
card description, nobody types a campaign name, and every per-company build
step names its campaigns "City, ST - Industry - Company"."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_ai_prompts_catalogue import _stub_nicegui  # noqa: E402


@pytest.fixture(scope="module")
def aip():
    _stub_nicegui()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import ai_prompts
    import staffing_prompts  # noqa: F401  (registers the staffing runs)
    return ai_prompts


def test_step_is_called_choose_your_sequence(aip):
    assert aip.SECTION_NAME["emails"] == "Choose your sequence"


def test_every_offered_sequence_has_a_card(aip):
    for r in aip.ARENA.routines:
        f = r["field_by_key"].get("sequence")
        if f:
            missing = [o for o in f["options"] if o not in aip.SEQUENCE_INFO]
            assert not missing, (r["key"], missing)


def test_step_days_never_go_backwards(aip):
    for name, info in aip.SEQUENCE_INFO.items():
        days = [st[0] for st in info.get("steps") or []]
        assert days == sorted(days), name
        if days:
            assert days[0] == 1, name


def test_counts_line(aip):
    assert aip.sequence_counts("Arena 4x4") == \
        "4 emails, 1 call, 1 LinkedIn, about 2½ weeks"
    assert aip.sequence_counts("Arena 5x3") == "5 emails, about 2½ weeks"
    assert aip.sequence_counts("Let the AI choose") == ""


def test_nobody_names_a_company_campaign(aip):
    for r in aip.ARENA.routines:
        if r["key"] in aip._OWN_NAME_ROUTINES:
            continue
        assert "campaign_name" not in r["field_by_key"], r["key"]


def test_build_steps_carry_the_name_rule(aip):
    for r in aip.ARENA.routines:
        if "create_campaign" not in r.get("tools", ()) \
                or r["key"] in aip._OWN_NAME_ROUTINES:
            continue
        assert any("{name_clause}" in st for st in r["steps"]), r["key"]


def test_old_saved_name_is_ignored(aip):
    req = {"routine": "sales_campaign", "raw": "", "ask_extra": [],
           "vals": {"industry": "HVAC", "location": "Colorado",
                    "roles": "service techs", "campaign_name": "my name"}}
    out = aip.build_prompt(req)
    assert "my name" not in out
    assert "<City>, <ST> - <Industry> - <Company>" in out.replace("\n", " ") \
        or "<City>, <ST> -" in out
