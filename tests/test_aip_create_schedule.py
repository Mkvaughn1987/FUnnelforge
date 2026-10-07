"""The "Create a schedule" step: no checkbox, two choices instead."""
import ai_prompts as aip


def _routine():
    return aip._CAT.routine_by_key[aip._CAT.default_routine]


def test_section_is_named_create_a_schedule():
    assert aip.SECTION_NAME["repeat"] == "Create a schedule"


def test_schedule_step_never_draws_the_checkbox():
    r = _routine()
    for on in (True, False):
        keys = [f["key"] for f in aip._step_rows(r, {"repeat_on": on},
                                                 "repeat")]
        assert "repeat_on" not in keys


def test_schedule_questions_follow_the_choice():
    r = _routine()
    keys = [f["key"] for f in aip._step_rows(r, {"repeat_on": True},
                                             "repeat")]
    assert "repeat_every" in keys


def test_step_defaults_to_the_first_section():
    secs = aip._aip_sections_for(_routine())
    assert aip._aip_step({}, secs) == secs[0][0]
    assert aip._aip_step({"step": "repeat"}, secs) == "repeat"
    assert aip._aip_step({"step": "gone"}, secs) == secs[0][0]
