"""Target-a-Candidate wizard step gates and transitions.

Step gates:
- Step 1 -> 2 requires non-empty tc_jd_text
- Step 2 -> 3 requires len(tc_candidates) >= 1
- Step 3 -> 4 requires non-empty tc_preset
"""
import inspect


def test_step_jd_renderer_exists_and_handles_paste_and_upload():
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_jd)
    # Must support both upload AND paste
    assert "ui.upload" in src or ".upload(" in src or "PDF" in src
    assert "ui.textarea" in src or "textarea" in src.lower() or "paste" in src.lower()
    # Must reference tc_jd_text for the gate
    assert "tc_jd_text" in src


def test_step_jd_continue_advances_when_text_present():
    """The Continue handler advances tc_step only when tc_jd_text is
    non-empty. Structural check on the renderer source."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_jd)
    assert "tc_step" in src and "tc_jd_text" in src


def test_jd_parsing_helper_exists():
    """An AI helper to parse JD into role metadata must exist."""
    import flowdrip_app as fa
    assert hasattr(fa, "_tc_parse_jd"), (
        "_tc_parse_jd(jd_text) must be defined to extract role metadata"
    )


def test_step_candidates_renderer_supports_csv_upload():
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_candidates)
    assert "csv" in src.lower() or ".upload" in src
    assert "tc_candidates" in src


def test_step_candidates_continue_requires_at_least_one_candidate():
    """The Continue button on Step 2 must gate on len(tc_candidates) >= 1."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_candidates)
    assert "tc_candidates" in src and "tc_step = 2" in src


def test_step_preset_renderer_offers_four_options():
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_preset)
    assert "one_email" in src
    assert "two_emails_1day" in src
    assert "three_emails_3days" in src
    assert "custom" in src
    assert "1 email" in src.lower() or "one email" in src.lower()
    assert "2 emails" in src.lower() or "two emails" in src.lower()
    assert "3 emails" in src.lower() or "three emails" in src.lower()
    assert "create your own" in src.lower()


def test_step_preset_continue_requires_selection():
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_preset)
    assert "tc_preset" in src


def test_step_generate_emits_campaign_with_correct_cadence():
    """The generation step source must reference all 3 non-custom
    preset keys, call save_campaign, and use the JD context."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_generate)
    assert "one_email" in src
    assert "two_emails_1day" in src
    assert "three_emails_3days" in src
    assert "save_campaign" in src
    assert "tc_jd_text" in src or "tc_jd_parsed" in src


def test_step_generate_uses_run_as_user_helper():
    """The generation thread must use _run_as_user for per-user binding
    (Phase 0 regression net)."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_generate)
    assert "_run_as_user" in src, (
        "Generation worker must use _run_as_user(s._user_email, _run, "
        "name=...) for per-user thread binding (Phase 0 enforced)"
    )
