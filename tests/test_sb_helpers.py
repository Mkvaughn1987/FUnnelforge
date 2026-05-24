"""Pure-function tests for the AI Guided Sequence Builder helpers.

The Sequence Builder lives mostly in flowdrip_app.py's UI layer, but
its add/remove/reorder/prompt-building logic is broken out as pure
functions so we can test it without a NiceGUI harness.

Spec: docs/superpowers/specs/2026-05-23-ai-guided-sequence-builder-design.md
"""
import flowdrip_app as fa


def test_appstate_has_sequence_builder_fields():
    """AppState must initialize all six sb_* fields so a fresh
    session can render p_seq_builder without AttributeError."""
    s = fa.AppState()
    assert s.sb_goal == ""
    assert s.sb_audience == ""
    assert s.sb_tone == "consultative"
    assert s.sb_steps == []
    assert s.sb_generating is False
    assert s.sb_error == ""


def test_sb_add_step_appends_with_new_id():
    """_sb_add_step appends a new step and assigns it a unique id."""
    steps = []
    fa._sb_add_step(steps, "email")
    assert len(steps) == 1
    assert steps[0]["type"] == "email"
    assert steps[0]["delay_days"] == 0      # first step is Day 0 by default
    assert steps[0]["input"] == ""
    assert isinstance(steps[0]["id"], str) and len(steps[0]["id"]) >= 8
    # Adding a second step defaults delay_days to 1 (one day after prev)
    fa._sb_add_step(steps, "linkedin")
    assert len(steps) == 2
    assert steps[1]["type"] == "linkedin"
    assert steps[1]["delay_days"] == 1
    # IDs must be unique across appends
    assert steps[0]["id"] != steps[1]["id"]


def test_sb_add_step_rejects_unknown_type():
    """Only the five known step types are valid."""
    steps = []
    import pytest
    with pytest.raises(ValueError):
        fa._sb_add_step(steps, "fax")


def test_sb_remove_step_by_id():
    """_sb_remove_step removes the entry with the matching id and
    returns True; missing-id returns False without mutating."""
    steps = []
    fa._sb_add_step(steps, "email")
    fa._sb_add_step(steps, "call")
    _id_to_remove = steps[0]["id"]
    assert fa._sb_remove_step(steps, _id_to_remove) is True
    assert len(steps) == 1
    assert steps[0]["type"] == "call"
    assert fa._sb_remove_step(steps, "no-such-id") is False
    assert len(steps) == 1


def test_sb_move_step_reorders():
    """_sb_move_step reorders by moving an entry to a new index."""
    steps = []
    for _t in ("email", "linkedin", "call"):
        fa._sb_add_step(steps, _t)
    _email_id = steps[0]["id"]
    # Move email from index 0 to index 2 (end)
    fa._sb_move_step(steps, _email_id, 2)
    assert [st["type"] for st in steps] == ["linkedin", "call", "email"]
    # Move call to index 0
    _call_id = steps[1]["id"]
    fa._sb_move_step(steps, _call_id, 0)
    assert [st["type"] for st in steps] == ["call", "linkedin", "email"]
    # Bad id → no-op
    fa._sb_move_step(steps, "no-such-id", 0)
    assert [st["type"] for st in steps] == ["call", "linkedin", "email"]


def test_sb_step_label_per_type():
    """_sb_step_label returns a user-facing tag like 'Email · Day 2'."""
    assert fa._sb_step_label({"type": "email", "delay_days": 0}) == "Email · Day 0"
    assert fa._sb_step_label({"type": "linkedin", "delay_days": 2}) == "LinkedIn · Day 2"
    assert fa._sb_step_label({"type": "call", "delay_days": 5}) == "Call · Day 5"
    assert fa._sb_step_label({"type": "sms", "delay_days": 1}) == "SMS · Day 1"
    assert fa._sb_step_label({"type": "task", "delay_days": 3}) == "Task · Day 3"


def test_sb_build_prompt_includes_brief_and_steps():
    """Prompt must surface goal, audience, tone, and each step's
    input verbatim so Claude has the user's intent to work from."""
    steps = []
    fa._sb_add_step(steps, "email")
    steps[0]["input"] = "warm opening that mentions their Bisnow feature"
    fa._sb_add_step(steps, "linkedin")
    steps[1]["input"] = "short connection — reference the email I sent"
    prompt = fa._sb_build_prompt(
        goal="Pitch a senior PM candidate",
        audience="VPs of Construction in CO",
        tone="consultative",
        steps=steps,
    )
    # Brief surfaces
    assert "Pitch a senior PM candidate" in prompt
    assert "VPs of Construction in CO" in prompt
    assert "consultative" in prompt.lower()
    # Steps surface verbatim
    assert "warm opening that mentions their Bisnow feature" in prompt
    assert "short connection — reference the email I sent" in prompt
    # The mode-detection instruction must be present so Claude knows
    # to either write fresh OR polish drafted copy.
    assert "INSTRUCTIONS" in prompt.upper()
    assert "DRAFTED COPY" in prompt.upper()


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
    assert _e0["time"] == "9:00 AM"   # default propagated
    _e1 = out["emails"][1]
    assert _e1["step_type"] == "linkedin"
    assert _e1.get("subject", "") == ""  # LinkedIn has no subject
    assert _e1["time"] == "9:00 AM"   # default for missing time field


def test_sb_parse_campaign_handles_malformed_input():
    """Parser must not crash on non-JSON; returns a stub campaign so
    the caller can show an error without an exception."""
    out = fa._sb_parse_campaign("this is not json")
    assert out == {} or out.get("emails") == []
