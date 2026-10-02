""""8am tomorrow" start option: the prompt asks for tomorrow's date plus
start_time, and create_campaign moves the first email to that time."""
from datetime import date, timedelta

import ai_prompts as aip
import flowdrip_app as fa


def test_option_is_offered():
    assert "8am tomorrow" in aip.WHEN_OPTIONS


def test_prompt_names_tomorrow_and_start_time():
    out = aip._start_date({"field_by_key": {}}, {"start_when": "8am tomorrow"})
    assert '"%s"' % (date.today() + timedelta(days=1)).isoformat() in out
    assert 'start_time "8:00 AM"' in out


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
