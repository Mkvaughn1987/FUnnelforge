"""Every AI Prompt run sends at most 500 emails, for everyone (Mike,
2026-10-07). The email_cap boxes default to 500 and nothing typed or saved
gets past it; every ThriveModal prompt also carries the rule outright."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_tm_prompts import _stub_nicegui  # noqa: E402


@pytest.fixture(scope="module")
def mods():
    _stub_nicegui()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import ai_prompts
    import tm_prompts
    return ai_prompts, tm_prompts


@pytest.mark.parametrize("typed,want", [
    ("2000", "500"), ("501", "500"), ("500", "500"), ("150", "150"),
    ("", "500"), ("0", "1"), ("abc", "500"),
])
def test_clamp(mods, typed, want):
    aip, _ = mods
    vals = {"email_cap": typed}
    aip.clamp_email_cap(vals)
    assert vals["email_cap"] == want


def test_engine_caps_default_to_500(mods):
    aip, _ = mods
    capped = [r for r in aip.ARENA.routines if "email_cap" in r["field_by_key"]]
    assert capped
    for r in capped:
        assert r["field_by_key"]["email_cap"]["default"] == "500", r["key"]


def test_every_tm_prompt_carries_the_rule(mods):
    aip, tm = mods
    for r in tm.TM.routines:
        vals = aip.defaults_for(r)
        if "email_cap" in vals:
            vals["email_cap"] = "5000"
        p = aip.build_prompt({"routine": r["key"], "vals": vals}, tm.TM)
        assert "Never send more than 500 emails in one run." in p, r["key"]
        assert "5000" not in p, r["key"]
