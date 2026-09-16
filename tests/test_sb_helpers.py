"""Pure-function tests for the AI Guided Sequence Builder helpers.

The Sequence Builder lives mostly in flowdrip_app.py's UI layer, but
its prompt-building and response-parsing logic is broken out as pure
functions so we can test it without a NiceGUI harness.

Spec: docs/superpowers/specs/2026-05-23-ai-guided-sequence-builder-design.md
"""
import flowdrip_app as fa


def test_appstate_has_sequence_builder_fields():
    """AppState must initialize all sb_* fields so a fresh session
    can render p_seq_builder without AttributeError.

    2026-08-27 — restored step-based design with sb_goal, sb_audience,
    sb_steps (list of dicts with id/type/delay_days/input), and related
    state fields for UI rendering."""
    s = fa.AppState()
    assert s.sb_goal == ""
    assert s.sb_audience == ""
    assert s.sb_tone == "consultative"
    assert s.sb_steps == []
    assert not hasattr(s, "sb_counts")
    assert not hasattr(s, "sb_span")
    assert not hasattr(s, "sb_special")
    assert s.sb_generating is False
    assert s.sb_error == ""
    assert s.sb_pending_camp == {}
    assert s.sb_pending_name == ""
    assert s.sb_save_as_style is False


def test_sb_build_prompt_includes_tone_goal_audience_and_steps():
    """Prompt must surface tone, goal, audience, step types, delays,
    and step-specific input so Claude can build the right sequence."""
    prompt = fa._sb_build_prompt(
        tone="consultative",
        goal="Fill a Senior DevOps role at a Denver fintech",
        audience="Passive DevOps engineers with AWS + Terraform",
        steps=[
            {"id": "s1", "type": "email", "delay_days": 0, "input": "Warm intro on my client's DevOps opening"},
            {"id": "s2", "type": "linkedin", "delay_days": 2, "input": "Connection request referencing the email"},
            {"id": "s3", "type": "call", "delay_days": 2, "input": ""},
        ],
    )
    assert "consultative" in prompt.lower()
    assert "Fill a Senior DevOps role at a Denver fintech" in prompt
    assert "Passive DevOps engineers with AWS + Terraform" in prompt
    assert "email" in prompt.lower()
    assert "linkedin" in prompt.lower()
    assert "call" in prompt.lower()
    assert "Warm intro on my client's DevOps opening" in prompt
    assert "Connection request referencing the email" in prompt


def test_sb_build_prompt_handles_blank_goal_audience_and_empty_step_input():
    """Prompt must handle empty goal/audience and step input without
    crashing or leaking sentinel values like 'None'."""
    prompt = fa._sb_build_prompt(
        tone="consultative",
        goal="",
        audience="",
        steps=[
            {"id": "s1", "type": "email", "delay_days": 0, "input": ""},
        ],
    )
    assert isinstance(prompt, str)
    assert "None" not in prompt


def test_sb_parse_campaign_normalizes_email_keys():
    """Claude returns {emails:[...]}; parser maps each item to the
    same schema queue_campaign_emails expects (step_type, subject,
    body, delay_days, time)."""
    raw = (
        '{"campaign_name":"Test Camp","synopsis":"...",'
        '"emails":['
        '{"name":"Step 1 - Intro","subject":"Hi","body":"Hi {FirstName}",'
        '"delay_days":0,"time":"9:00 AM","step_type":"email_auto"},'
        '{"name":"Step 2 - LI","body":"Connection request",'
        '"delay_days":1,"step_type":"linkedin"}'
        ']}'
    )
    out = fa._sb_parse_campaign(raw)
    assert out["campaign_name"] == "Test Camp"
    assert len(out["emails"]) == 2
    _e0 = out["emails"][0]
    assert _e0["step_type"] == "email_auto"
    assert _e0["subject"] == "Hi"
    assert "Hi {FirstName}" in _e0["body"]
    assert _e0["delay_days"] == 0
    assert _e0["time"] == "9:00 AM"
    _e1 = out["emails"][1]
    assert _e1["step_type"] == "linkedin"
    assert _e1.get("subject", "") == ""
    assert _e1["time"] == "9:00 AM"


def test_sb_parse_campaign_handles_malformed_input():
    """Parser must not crash on non-JSON; returns a stub so the
    caller can show an error without an exception."""
    out = fa._sb_parse_campaign("this is not json")
    assert out == {} or out.get("emails") == []
