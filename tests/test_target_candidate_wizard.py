"""Find Candidates wizard step gates and transitions.

Renamed from "Target a Candidate" on 2026-05-12. The wizard was also
restructured from 4 steps to 3:
- Step 0: JD (OPTIONAL — can skip)
- Step 1: Cadence preset
- Step 2: Generate

The legacy "Step 2 — Candidates CSV upload" was removed entirely. Users
source candidates outside DripDrop and add them in the email editor's
contacts step after generation.
"""
import inspect


def test_step_jd_renderer_exists_and_handles_paste_and_upload():
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_jd)
    # Must support both upload AND paste
    assert "ui.upload" in src or ".upload(" in src or "PDF" in src
    assert "ui.textarea" in src or "textarea" in src.lower() or "paste" in src.lower()
    # Must reference tc_jd_text
    assert "tc_jd_text" in src


def test_step_jd_is_optional_with_skip_button():
    """The JD step is optional since 2026-05-12. The renderer must
    expose a Skip control that advances without requiring a JD."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_jd)
    # Skip button copy
    assert "Skip" in src or "skip" in src
    # Either branch advances tc_step (skip OR continue-with-jd)
    assert "tc_step = 1" in src


def test_appstate_has_tc_jd_mode_field():
    """Step 1 cleanup (2026-05-16) added a choose-one input mode.
    AppState must expose tc_jd_mode so the renderer can dispatch."""
    import flowdrip_app as fa
    s = fa.AppState()
    assert hasattr(s, "tc_jd_mode"), (
        "AppState must define tc_jd_mode (\"\" | \"upload\" | \"paste\")"
    )
    # Default must be the choice state, not pre-selected.
    assert s.tc_jd_mode == ""


def test_step_jd_renderer_dispatches_on_mode():
    """The renderer must branch on tc_jd_mode so each mode renders a
    distinct UI section."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_jd)
    # Choice + upload + paste branches all referenced.
    assert "tc_jd_mode" in src
    assert '"upload"' in src
    assert '"paste"' in src


def test_step_jd_mode_defaults_from_prior_data():
    """On revisit, the renderer must default tc_jd_mode based on prior
    state (filename → upload, text → paste). This keeps users from
    landing back on the choice cards after they've already provided a
    JD."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_jd)
    # The default-from-prior-data logic must reference both fields.
    assert "tc_jd_filename" in src
    assert "tc_jd_text" in src
    # And it must assign tc_jd_mode based on them.
    assert 'tc_jd_mode = "upload"' in src or "tc_jd_mode = 'upload'" in src
    assert 'tc_jd_mode = "paste"' in src or "tc_jd_mode = 'paste'" in src


def test_jd_parsing_helper_exists():
    """An AI helper to parse JD into role metadata must exist."""
    import flowdrip_app as fa
    assert hasattr(fa, "_tc_parse_jd"), (
        "_tc_parse_jd(jd_text) must be defined to extract role metadata"
    )


def test_candidates_step_no_longer_routed():
    """The Candidates CSV upload step was removed 2026-05-12 per user
    direction — users source candidates outside DripDrop and add them
    in the email editor afterward. The wizard dispatcher must not
    route to _tc_render_step_candidates anymore."""
    import flowdrip_app as fa
    src = inspect.getsource(fa.p_target_candidate)
    # The dispatcher should NOT call the candidates renderer.
    assert "_tc_render_step_candidates" not in src, (
        "Candidates step was removed — p_target_candidate must not "
        "route to _tc_render_step_candidates"
    )


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
    preset keys, call save_campaign, and use the JD context (when
    provided — JD is optional now)."""
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


def test_step_generate_handles_skipped_jd():
    """When the user skips the JD step, the generator must still
    produce a sequence — gracefully falling back to a generic-but-warm
    candidate-outreach prompt."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_generate)
    # Must branch on whether a JD is present so the prompt isn't built
    # with empty/missing context (would produce broken copy).
    assert "_has_jd" in src or "tc_jd_text" in src
