"""Every AI Prompts run sends at most 500 emails, for everyone (Mike,
2026-10-07). 500 is also the default, and nothing typed or saved gets past
it into the prompt."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_ai_prompts_catalogue import _stub_nicegui  # noqa: E402


@pytest.fixture(scope="module")
def mods():
    _stub_nicegui()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import ai_prompts
    import staffing_prompts
    return ai_prompts, staffing_prompts


def _capped(mods):
    aip, sp = mods
    for cat in (aip.ARENA, sp.STAFFING):
        for r in cat.routines:
            if "email_cap" in r["field_by_key"]:
                yield cat, r


def test_every_cap_defaults_to_500(mods):
    found = list(_capped(mods))
    assert len(found) >= 7
    for _cat, r in found:
        assert r["field_by_key"]["email_cap"]["default"] == "500", r["key"]


@pytest.mark.parametrize("typed,want", [
    ("2000", "500"), ("501", "500"), ("500", "500"), ("250", "250"),
    ("", "500"), ("0", "1"), ("abc", "500"),
])
def test_clamp(mods, typed, want):
    aip, _ = mods
    vals = {"email_cap": typed}
    aip.clamp_email_cap(vals)
    assert vals["email_cap"] == want


def test_clamp_leaves_runs_without_a_cap_alone(mods):
    aip, _ = mods
    vals = {"companies": "9"}
    aip.clamp_email_cap(vals)
    assert vals == {"companies": "9"}


def test_prompt_never_says_more_than_500(mods):
    aip, _ = mods
    for cat, r in _capped(mods):
        vals = aip.defaults_for(r)
        vals["email_cap"] = "5000"
        p = aip.build_prompt({"routine": r["key"], "vals": vals}, cat)
        assert "5000" not in p, r["key"]
        assert "500 emails" in p, r["key"]


def test_typed_answer_is_capped(mods):
    aip, _ = mods
    r = aip.ARENA.routine_by_key["slate_campaign"]
    vals = aip.defaults_for(r)
    errors = aip.apply_answers(r, vals, {"email_cap": "900"}, aip.ARENA)
    assert not errors
    assert vals["email_cap"] == "500"


def test_every_prompt_carries_the_rule(mods):
    aip, sp = mods
    for cat in (aip.ARENA, sp.STAFFING):
        for r in cat.routines:
            p = aip.build_prompt({"routine": r["key"],
                                  "vals": aip.defaults_for(r)}, cat)
            assert "Never send more than 500 emails in one run." in p, r["key"]