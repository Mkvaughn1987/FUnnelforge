"""Back controls (2026-10-02). The top "Back a step" bar and the campaign
wizard's own Back share one rule, so a ThriveModal Review step steps back
to Target details instead of bouncing off the skipped Campaign Style step;
and in the sidebar layout the history Back names pages the way the
sidebar does."""
import flowdrip_app as fa


def _state(camp_type="", locked=False):
    s = fa.AppState()
    s.aicb_camp_type = camp_type
    s.aicb_style_locked = locked
    return s


def test_locked_tm_review_steps_back_past_style(monkeypatch):
    monkeypatch.setattr(fa, "_SALES_MODE", True)
    tm = next(iter(fa._TM_TYPE_KEYS))
    s = _state(tm, locked=True)
    # 6 (Review) -> not 5 (no style step) -> not 3/4 (sales) -> 2
    assert fa._aicb_prev_wizard_step(s, 6) == 2
    assert fa._aicb_prev_wizard_step(s, 2) == 1


def test_sales_unlocked_review_goes_to_style(monkeypatch):
    monkeypatch.setattr(fa, "_SALES_MODE", True)
    s = _state("", locked=False)
    assert fa._aicb_prev_wizard_step(s, 6) == 5
    assert fa._aicb_prev_wizard_step(s, 5) == 2


def test_arena_walks_every_step(monkeypatch):
    monkeypatch.setattr(fa, "_SALES_MODE", False)
    s = _state("fivebyfive", locked=False)
    assert [fa._aicb_prev_wizard_step(s, n) for n in (6, 5, 4, 3, 2, 1)] \
        == [5, 4, 3, 2, 1, 1]


def test_locked_fourbyfour_skips_style_on_arena(monkeypatch):
    monkeypatch.setattr(fa, "_SALES_MODE", False)
    s = _state("fourbyfour", locked=True)
    assert fa._aicb_prev_wizard_step(s, 6) == 4


def test_back_label_uses_sidebar_names(monkeypatch):
    monkeypatch.setattr(fa, "_SIDEBAR_LAYOUT", True)
    s = fa.AppState()
    s.sp = "responses"
    s._nav_history = [fa._nav_snapshot(s)]
    assert fa.nav_back_label(s) == "Back to Replies"


def test_back_label_classic_unchanged(monkeypatch):
    monkeypatch.setattr(fa, "_SIDEBAR_LAYOUT", False)
    s = fa.AppState()
    s.sp = "responses"
    s._nav_history = [fa._nav_snapshot(s)]
    assert fa.nav_back_label(s) == "Campaign Radar"


def test_sidebar_nav_records_and_clears_came_from(monkeypatch):
    s = fa.AppState()
    fa._sidebar_nav(s, lambda: None, "companies", {}, came_from="sales_dashboard")
    assert s._came_from == "sales_dashboard"
    fa._sidebar_nav(s, lambda: None, "companies", {})
    assert s._came_from == ""
