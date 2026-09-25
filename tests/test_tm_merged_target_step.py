"""inboxslide (sales instance): Target details and Confirm are one step.

After Autofill the Target details step shows company, website, industry,
locations and a Target Positions chip picker in place, and Next goes
straight to Campaign style. Arena keeps Target details -> Confirm ->
Candidates untouched."""
import inspect

import flowdrip_app as fa


def _page_src():
    return inspect.getsource(fa.p_ai_campaign)


# ── pure chip helpers ────────────────────────────────────────────────────

def test_role_choices_posted_first_then_ticked_extras_no_dupes():
    out = fa._tm_role_choices(
        ["Dispatcher", "AP/AR Specialist", "dispatcher", " "],
        ["Data Entry Specialist", "ap/ar specialist", "Dispatcher"])
    assert out == ["Dispatcher", "AP/AR Specialist", "Data Entry Specialist"]


def test_role_choices_handles_empty():
    assert fa._tm_role_choices(None, None) == []
    assert fa._tm_role_choices([], ["Dispatcher"]) == ["Dispatcher"]


def test_toggle_role_ticks_at_end_keeping_first_pick_first():
    new, msg = fa._tm_toggle_role(["Dispatcher"], "AP/AR Specialist")
    assert (new, msg) == (["Dispatcher", "AP/AR Specialist"], None)


def test_toggle_role_unticks_case_insensitively():
    new, msg = fa._tm_toggle_role(["Dispatcher", "AP/AR Specialist"], "dispatcher")
    assert (new, msg) == (["AP/AR Specialist"], None)


def test_toggle_role_cap():
    six = [f"Role {i}" for i in range(6)]
    new, msg = fa._tm_toggle_role(six, "Role 7")
    assert new == six
    assert "Cap is 6" in msg
    # Unticking is always allowed at the cap.
    new, msg = fa._tm_toggle_role(six, "Role 0")
    assert new == six[1:] and msg is None


def test_toggle_role_blank_is_noop():
    assert fa._tm_toggle_role(["Dispatcher"], "  ") == (["Dispatcher"], None)


# ── wizard wiring (source greps: the page is one big render function) ────

def test_sales_wizard_skips_confirm_and_candidates():
    src = _page_src()
    # stale step guard
    assert "if _SALES_MODE and _wiz_step in (3, 4):" in src
    # top + bottom Next
    assert src.count("if _SALES_MODE and _nxt in (3, 4):") == 2
    # Back from Campaign style lands on Target details
    assert "if _SALES_MODE and _prev in (3, 4):" in src
    assert "_prev = 2" in src
    # progress pills
    assert "_steps = [st for st in _steps if st[0] not in (3, 4)]" in src


def test_sales_target_details_carries_company_and_positions():
    src = _page_src()
    assert 'if _SALES_MODE and _mode == "company" and _show_below_autofill:' in src
    assert 's._aicb_step2_refs["company"] = co_inp' in src
    assert "_render_tm_positions_picker(s, rf)" in src
    # Both Next buttons commit the Company field before validating.
    assert 's.aicb_company = (_refs2["company"].value or "").strip()' in src
    assert 's.aicb_company = (co_inp.value or "").strip()' in src


def test_arena_flow_untouched():
    src = _page_src()
    # Arena still shows the "next step" note and still renders Confirm.
    assert "Target roles and candidates are picked on the next step." in src
    assert "_render_step3_confirm(s, rf)" in src
    assert '(3, "Confirm")' in src
    assert "elif _wiz_step == 3:" in src


def test_positions_picker_copy():
    src = inspect.getsource(fa._render_tm_positions_picker)
    assert 'ui.label("Target Positions")' in src
    assert "hiring for right now" in src
    assert "No current postings found" in src
    assert "first tick sets the wage" in src
    assert "C['on_teal']" in src
