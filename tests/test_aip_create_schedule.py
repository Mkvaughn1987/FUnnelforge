"""The "Create a schedule" section: no checkbox, open means scheduled."""
import types

import ai_prompts as aip


def _routine():
    return aip._CAT.routine_by_key[aip._CAT.default_routine]


def _open(vals, filled=()):
    s = types.SimpleNamespace(_aip_open=None)
    req = {"vals": vals, "filled": list(filled)}
    return aip._aip_open_state(s, _routine(), req)


def test_section_is_named_create_a_schedule():
    assert aip.SECTION_NAME["repeat"] == "Create a schedule"


def test_saved_schedule_opens_the_section():
    assert _open({"repeat_on": True})["repeat"] is True


def test_no_schedule_keeps_it_shut_even_if_parse_touched_it():
    assert _open({"repeat_on": False}, filled=["repeat_on"])["repeat"] is False
