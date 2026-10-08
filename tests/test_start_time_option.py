""""8am tomorrow" start option: the prompt asks for tomorrow's date plus
start_time, and create_campaign moves the first email to that time."""
from datetime import date, timedelta

import ai_prompts as aip
import flowdrip_app as fa


def test_option_is_offered():
    assert "8am tomorrow" in aip.WHEN_OPTIONS


def test_default_is_8am_tomorrow():
    # Mike 2026-10-08: a run built today sends tomorrow morning unless the
    # user says otherwise. First on the menu and the default.
    assert aip.WHEN_OPTIONS[0] == "8am tomorrow"
    f = {x["key"]: x for x in aip.start_fields()}
    assert f["start_when"]["default"] == "8am tomorrow"
    r = {"fields": aip.start_fields(), "field_by_key": f}
    out = aip._start_date(r, {})
    want = _next_weekday(date.today() + timedelta(days=1))
    assert '"%s"' % want.isoformat() in out
    assert 'start_time "8:00 AM"' in out


def test_start_question_is_asked_with_the_details():
    # Mike 2026-10-08: "when would you like this to send" goes on the first
    # page, with the details, not on the sequence step.
    for f in aip.start_fields():
        assert f["section"] == "details", f["key"]
    for r in aip.ARENA.routines:
        if "start_when" in r["field_by_key"]:
            assert r["field_by_key"]["start_when"]["section"] == "details", \
                r["key"]
            assert all(f["section"] == "details" for f in r["fields"]
                       if f["key"] in aip.START_KEYS), r["key"]


def test_start_answer_stays_out_of_the_details_table():
    # The date is resolved in the numbered step; the table must not also
    # carry a relative "8am tomorrow" that reads differently on another day.
    r = aip.ARENA.routine_by_key["slate_campaign"]
    req = {"routine": r["key"], "raw": "x", "vals": {
        "industry": "packaging", "location": "Denver", "roles": "techs",
        "start_when": "8am tomorrow"}}
    p = " ".join(aip.build_prompt(req, aip.ARENA).split())
    assert "THE DETAILS" in p
    assert "When the first email goes out" not in p
    assert 'start_time "8:00 AM"' in p


def _next_weekday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def test_prompt_names_next_weekday_and_start_time():
    out = aip._start_date({"field_by_key": {}}, {"start_when": "8am tomorrow"})
    want = _next_weekday(date.today() + timedelta(days=1))
    assert '"%s"' % want.isoformat() in out
    assert 'start_time "8:00 AM"' in out


def test_pick_a_date_and_time_is_offered_instead_of_asking():
    assert "Pick a date and time" in aip.WHEN_OPTIONS
    assert not any(o.startswith("A date") for o in aip.WHEN_OPTIONS)


def test_picked_date_and_time_go_into_the_prompt():
    vals = {"start_when": "Pick a date and time", "start_on": "2026-10-07",
            "start_at": "1:00pm"}
    out = aip._start_date({"field_by_key": {}}, vals)
    assert out == '"2026-10-07" and start_time "1:00 PM"'


def test_picked_weekend_moves_to_monday():
    vals = {"start_when": "Pick a date and time", "start_on": "2026-10-10",
            "start_at": "8:00am"}  # a Saturday
    assert '"2026-10-12"' in aip._start_date({"field_by_key": {}}, vals)


def test_date_boxes_only_show_for_pick_a_date():
    f = {x["key"]: x for x in aip.start_fields()}
    r = {"field_by_key": f}
    assert not aip._visible(r, {"start_when": "Next Monday"}, f["start_on"])
    assert aip._visible(r, {"start_when": "Pick a date and time"}, f["start_on"])
    assert aip._visible(r, {"start_when": "Pick a date and time"}, f["start_at"])


def test_pick_a_date_left_blank_still_asks():
    r = {"fields": aip.start_fields(),
         "field_by_key": {x["key"]: x for x in aip.start_fields()}}
    qs = aip._open_questions(r, {"start_when": "Pick a date and time"})
    assert "What date the first email should go out" in qs
    qs = aip._open_questions(r, {"start_when": "Pick a date and time",
                                 "start_on": "2026-10-07"})
    assert "What date the first email should go out" not in qs


def test_saved_answer_with_the_old_option_never_stops_to_ask():
    # DripDrop runs end to end (Mike 2026-10-02): an old "A date I'll give"
    # answer starts on the upcoming Monday instead of asking.
    out = aip._start_date({"field_by_key": {}},
                          {"start_when": "A date I'll give the AI"})
    assert "ask me" not in out
    assert '"auto"' in out


def test_validate_accepts_and_rejects_start_time():
    base = {"template": "fourbyfour", "company": "Acme"}
    assert fa._validate_campaign_spec({**base, "start_time": "8:00 AM"}) is None
    assert fa._validate_campaign_spec({**base, "start_time": "8am"})
    assert fa._validate_campaign_spec({**base, "start_time": "13:00 PM"})


def test_apply_start_time_sets_first_email_only():
    emails = [{"step_type": "linkedin", "time": "10:00 AM"},
              {"step_type": "email_auto", "time": "9:00 AM"},
              {"step_type": "email_auto", "time": "9:00 AM"}]
    fa._apply_start_time(emails, "8:00 am")
    assert [e["time"] for e in emails] == ["10:00 AM", "8:00 AM", "9:00 AM"]


def test_apply_start_time_blank_is_a_no_op():
    emails = [{"time": "9:00 AM"}]
    fa._apply_start_time(emails, None)
    assert emails[0]["time"] == "9:00 AM"
