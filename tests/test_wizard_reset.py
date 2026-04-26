"""C2/C3: wizard state must fully reset across campaigns."""
import pytest


def test_reset_wizard_state_clears_all_aicb_and_custom(isolated_appdata):
    import flowdrip_app as fa

    s = fa.AppState()

    # Pollute with stale Campaign A data
    s.aicb_company = "Acme"
    s.aicb_website = "https://acme.example"
    s.aicb_industry = "Widgets"
    s.aicb_niche = "B2B"
    s.aicb_sel_locations = ["TX"]
    s.aicb_sel_roles = ["sales reps"]
    s.aicb_docs = {"foo": "bar"}
    s.aicb_research = "stale research"
    s.aicb_campaign = {"steps": ["leftover"]}
    s.custom_editing_idx = 2
    s.custom_steps = [{"name": "old"}]
    s.custom_name = "Old Campaign"
    s.custom_selected_type = "email"

    fa._reset_wizard_state(s)

    # Defaults
    assert s.aicb_company == ""
    assert s.aicb_website == ""
    assert s.aicb_industry == ""
    assert s.aicb_niche == ""
    assert s.aicb_sel_locations == []
    assert s.aicb_sel_roles == []
    assert s.aicb_docs == {}
    # aicb_research and aicb_campaign defaults match a fresh AppState()
    fresh = fa.AppState()
    assert s.aicb_research == fresh.aicb_research
    assert s.aicb_campaign == fresh.aicb_campaign
    assert s.custom_editing_idx == -1
    assert s.custom_steps == []
    assert s.custom_name == ""
    assert s.custom_selected_type == ""


def test_reset_wizard_state_keeps_unrelated_state(isolated_appdata):
    """Reset must NOT clear non-wizard state like the user's hub or
    nav history — only the wizard inputs."""
    import flowdrip_app as fa

    s = fa.AppState()
    s.hub = "sales"
    s.sp = "today"
    s._nav_history = [{"snapshot": "preserve me"}]

    fa._reset_wizard_state(s)

    assert s.hub == "sales"
    assert s.sp == "today"
    assert s._nav_history == [{"snapshot": "preserve me"}]


def test_reset_wizard_state_clears_all_rc_fields(isolated_appdata):
    """Regression: rc_* fields must all reset, not just rc_step and
    rc_custom_steps. Recruiting flow contamination found post-merge."""
    import flowdrip_app as fa

    s = fa.AppState()
    fresh = fa.AppState()

    # Pollute every rc_* field with stale Campaign A data
    rc_fields = [k for k in vars(fresh) if k.startswith("rc_")]
    assert len(rc_fields) >= 5, f"AppState should have several rc_* fields; found {rc_fields}"
    for name in rc_fields:
        cur = getattr(fresh, name)
        if isinstance(cur, str):
            setattr(s, name, "STALE_VALUE")
        elif isinstance(cur, list):
            setattr(s, name, ["STALE"])
        elif isinstance(cur, dict):
            setattr(s, name, {"stale": True})
        elif isinstance(cur, bool):
            setattr(s, name, not cur)
        elif isinstance(cur, int):
            setattr(s, name, 999999)
        else:
            setattr(s, name, "STALE")

    fa._reset_wizard_state(s)

    for name in rc_fields:
        expected = getattr(fresh, name)
        actual = getattr(s, name)
        assert actual == expected, (
            f"rc_* field '{name}' was not reset: "
            f"expected {expected!r}, got {actual!r}"
        )
