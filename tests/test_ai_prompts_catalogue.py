"""The AI Prompts engine after its catalogue became swappable.

ai_prompts.py once held DripDrop's routines, starters and copy as module
globals. Lifting them into a Catalogue (so inboxslide can supply its own)
must not change one byte of what the Arena page writes. The golden fixture
was generated from the pre-refactor module and is the oracle for that.
"""
import json
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "ai_prompts_golden.json"


def _stub_nicegui():
    """ai_prompts imports `ui` at module level; the engine never touches it
    outside the page functions, so any object with attribute access will do
    for the prompt tests."""
    if "nicegui" in sys.modules:
        return
    try:
        import nicegui  # noqa: F401  (the real one, if installed)
        return
    except Exception:
        pass
    ng = types.ModuleType("nicegui")

    class _Any:
        def __getattr__(self, _n):
            return _Any()

        def __call__(self, *a, **k):
            return _Any()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    ng.ui = _Any()
    sys.modules["nicegui"] = ng


@pytest.fixture(scope="module")
def aip():
    _stub_nicegui()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import importlib
    import ai_prompts
    return importlib.reload(ai_prompts)


@pytest.fixture(scope="module")
def golden():
    with open(FIXTURE, encoding="utf-8") as fh:
        cases = json.load(fh)
    assert len(cases) >= 19
    return cases


def test_golden_fixture_covers_every_routine_and_starter(aip, golden):
    names = {c["name"] for c in golden}
    for r in aip.ARENA.routines:
        assert "routine:%s" % r["key"] in names
    for st in aip.ARENA.starters:
        assert "starter:%s" % st["id"] in names


def test_arena_prompts_are_byte_identical_to_the_pre_refactor_output(aip, golden):
    bad = []
    for case in golden:
        got = aip.build_prompt(case["req"])
        if got != case["prompt"]:
            bad.append(case["name"])
    assert not bad, "prompts drifted for: %s" % ", ".join(bad)


def test_explicit_catalogue_matches_the_default(aip, golden):
    for case in golden:
        assert aip.build_prompt(case["req"], aip.ARENA) == case["prompt"]


def test_module_aliases_still_exist_and_point_at_arena(aip):
    assert aip.ROUTINES is aip.ARENA.routines
    assert aip.ROUTINE_BY_KEY is aip.ARENA.routine_by_key
    assert aip.DEFAULT_ROUTINE == aip.ARENA.default_routine == "other"
    assert aip.STANDING_RULES is aip.ARENA.standing_rules
    assert aip.UNATTENDED_RULE == aip.ARENA.unattended_rule
    assert aip.STARTERS is aip.ARENA.starters
    assert aip.STARTER_BY_ID is aip.ARENA.starter_by_id
    assert aip.SEQUENCES is aip.ARENA.sequences
    assert aip.TEMPLATE_KEY is aip.ARENA.template_key
    assert aip._CAT is aip.ARENA


def test_arena_catalogue_names_dripdrop_and_claude(aip):
    a = aip.ARENA
    assert a.product == "DripDrop"
    assert a.setups_file == "ai_prompt_setups.json"
    assert a.page_title == "AI Prompts"
    assert "Claude" in a.result_copy and "DripDrop" in a.result_copy
    assert a.result_extra is not None


def test_finalize_routines_is_idempotent(aip):
    r = {"key": "x", "name": "X", "blurb": "x", "example": "",
         "fields": [aip.F("a", "A")], "steps": [], "tools": []}
    by = aip.finalize_routines([r])
    n = len(r["fields"])
    aip.finalize_routines([r])
    assert len(r["fields"]) == n
    assert by["x"] is r
    assert "a" in r["field_by_key"]
    assert "repeat_on" in r["field_by_key"]
    assert "unattended" in r["field_by_key"]


def test_unknown_routine_falls_back_to_the_catalogue_default(aip):
    p = aip.build_prompt({"routine": "definitely-not-a-routine", "vals": {}})
    assert p.startswith("I need you to do this for me, using my DripDrop connector.")


def test_a_second_catalogue_changes_only_product_facing_text(aip):
    """A minimal foreign catalogue: the engine must read the connector name,
    default sequence and standing rules from it, not from the Arena globals."""
    r = {"key": "other", "name": "Other", "blurb": "Do the thing",
         "example": "",
         "fields": [aip.F("what", "What?", default="Do the thing")],
         "steps": ["{what}"], "tools": ["tm_audiences"]}
    by = aip.finalize_routines([r])
    cat = aip.Catalogue(
        routines=[r], routine_by_key=by, default_routine="other",
        standing_rules=["Only rule."], unattended_rule="Go alone.",
        starters=[], starter_by_id={}, sequences=["Sig"],
        template_key={"Sig": "tm_sig"}, default_sequence="Sig",
        default_template="tm_sig", setups_file="x.json",
        product="inboxslide", connector="inboxslide connector",
        assistant="Claude", page_title="AI Prompt", page_sub="sub",
        result_copy="copy", result_extra=None)
    p = aip.build_prompt({"routine": "other", "vals": {}}, cat)
    assert "using my inboxslide connector." in p
    assert "Use my inboxslide connector: tm_audiences." in p
    assert "Only rule." in p
    assert "DripDrop" not in p
    # And the default binding is untouched.
    assert aip._CAT is aip.ARENA
