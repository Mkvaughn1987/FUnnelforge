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
