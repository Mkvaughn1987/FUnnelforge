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

    2026-05-25 — sb_goal and sb_audience removed; the per-email
    direction box (sb_special) carries the equivalent intent."""
    s = fa.AppState()
    assert not hasattr(s, "sb_goal")
    assert not hasattr(s, "sb_audience")
    assert s.sb_tone == "consultative"
    assert s.sb_counts == {
        "email": 5, "linkedin": 2, "call": 1, "sms": 0, "task": 0,
    }
    assert s.sb_span == "3 weeks"
    assert s.sb_special == ""
    assert s.sb_generating is False
    assert s.sb_error == ""


def test_sb_build_prompt_includes_tone_counts_and_span():
    """Prompt must surface tone, per-type counts, span, and special
    instructions so Claude can build the right cadence end-to-end."""
    prompt = fa._sb_build_prompt(
        tone="consultative",
        counts={"email": 5, "linkedin": 2, "call": 1, "sms": 0, "task": 0},
        span="3 weeks",
        special="Warm intro on email 1, candidate teaser on email 3, breakup on the last email",
    )
    # Tone surfaces
    assert "consultative" in prompt.lower()
    # Per-type counts surface
    assert "5" in prompt and "email" in prompt.lower()
    assert "2" in prompt and "linkedin" in prompt.lower()
    assert "1" in prompt and "call" in prompt.lower()
    # Span surfaces
    assert "3 weeks" in prompt
    # Special instructions pass through verbatim
    assert "Warm intro on email 1" in prompt
    assert "breakup on the last email" in prompt


def test_sb_build_prompt_skips_zero_count_types():
    """Types with 0 touches should not be enumerated as required
    touches — they'd just confuse the AI."""
    prompt = fa._sb_build_prompt(
        tone="direct",
        counts={"email": 3, "linkedin": 0, "call": 0, "sms": 0, "task": 0},
        span="1 week",
        special="",
    )
    assert "3" in prompt and "email" in prompt.lower()
    _lower = prompt.lower()
    assert "0 linkedin" not in _lower
    assert "0 call" not in _lower
    assert "0 sms" not in _lower
    assert "0 task" not in _lower


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
