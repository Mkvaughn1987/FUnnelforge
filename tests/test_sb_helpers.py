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
