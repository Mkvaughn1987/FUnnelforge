"""When a newsletter is created, the background generator should fill in
ALL N scheduled steps, not just step 0.

Also covers the 2026-05-16 fix: the in-flight banner must flip to its
success state after the FIRST issue lands, not after all N months
finish — pre-fix, a 12-month newsletter kept the spinner up for ~5 min
even though step 0 was already visible below it.
"""
import inspect


def test_gen_all_issues_calls_generator_per_step(
        isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa

    camp = {
        "name": "Big Test NL",
        "newsletter_name": "Big Test NL",
        "market_analysis": True,
        "evergreen_only": True,
        "market_sector": "construction",
        "market_region": "Denver, CO",
        "_owner_email": "tester@example.com",
        "emails": [
            {"name": f"Issue {i}", "subject": "", "body": "",
             "step_type": "email_auto"}
            for i in range(3)
        ],
    }
    fa.save_campaign(camp)

    calls = []
    def _spy(_camp, idx):
        calls.append(idx)
        return (f"S{idx}", f"B{idx}")
    monkeypatch.setattr(fa, "_generate_newsletter_content_for_step", _spy)
    # Skip the inter-issue sleep so the test runs fast.
    import time
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)

    fa._gen_all_issues_for_campaign("Big Test NL")

    assert calls == [0, 1, 2]
    saved = next(c for c in fa.load_campaigns() if c.get("name") == "Big Test NL")
    for i in range(3):
        assert saved["emails"][i]["subject"] == f"S{i}"
        assert saved["emails"][i]["body"] == f"B{i}"


def test_gen_one_issue_helper_populates_single_step(
        isolated_appdata, with_user, monkeypatch):
    """The 2026-05-16 fix introduced _gen_one_issue_for_campaign so the
    bg thread can flip _nl_first_gen_done after step 0 lands instead of
    waiting for all N months. The helper must exist and populate just
    the requested step."""
    import flowdrip_app as fa

    assert hasattr(fa, "_gen_one_issue_for_campaign"), (
        "_gen_one_issue_for_campaign(camp_name, idx) is required so the "
        "create-newsletter bg thread can flip _nl_first_gen_done after "
        "the first issue lands (not after all N months)."
    )

    camp = {
        "name": "Single Test NL",
        "newsletter_name": "Single Test NL",
        "market_analysis": True,
        "evergreen_only": True,
        "market_sector": "manufacturing",
        "market_region": "Denver, CO",
        "_owner_email": "tester@example.com",
        "emails": [
            {"name": f"Issue {i}", "subject": "", "body": "",
             "step_type": "email_auto"}
            for i in range(3)
        ],
    }
    fa.save_campaign(camp)

    calls = []
    def _spy(_camp, idx):
        calls.append(idx)
        return (f"S{idx}", f"B{idx}")
    monkeypatch.setattr(fa, "_generate_newsletter_content_for_step", _spy)

    ok = fa._gen_one_issue_for_campaign("Single Test NL", 0)

    assert ok is True
    assert calls == [0], "Helper must only generate the requested step"
    saved = next(c for c in fa.load_campaigns()
                 if c.get("name") == "Single Test NL")
    assert saved["emails"][0]["subject"] == "S0"
    assert saved["emails"][0]["body"] == "B0"
    # Other steps must remain blank
    assert saved["emails"][1]["body"] == ""
    assert saved["emails"][2]["body"] == ""


def test_first_gen_banner_renderer_unsticks_when_step0_has_content():
    """Defensive guard added 2026-05-16: if step 0 of the active
    campaign already has real content, _render_nl_first_gen_status must
    flip _nl_first_gen_done so the success card renders — even if the
    bg thread never reached its flag-flip line (server restart mid-gen,
    pre-fix flag-only-after-all-N behavior, etc.). Source-grep is fine
    here; we just need to assert the guard exists."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._render_nl_first_gen_status)
    # The guard must inspect campaign step 0's body and flip the done flag.
    assert "load_campaigns" in src, (
        "_render_nl_first_gen_status must check campaign state on disk "
        "to unstick a stale banner"
    )
    assert "_nl_first_gen_done = True" in src, (
        "Guard must flip _nl_first_gen_done = True when step 0 has content"
    )


def test_create_newsletter_generates_step0_before_tail_and_hands_off_to_banner():
    """The create-newsletter dialog must generate the first issue (step 0)
    BEFORE the long all-months sweep, then hand off to the page-level status
    banner (_nl_first_gen_camp_name) which shows the live generating state
    and the inline preview. Source-inspection is the right test here — the
    closures live inside _create_newsletter_dialog and aren't independently
    importable.

    2026-06-04: reverted the in-dialog wait/preview (the dialog card got
    destroyed by a background page re-render mid-generation — "parent element
    slot deleted" — and the preview never appeared). The page banner
    re-renders WITH the page, so it survives that."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._create_newsletter_dialog)
    # Step 0 first (for the fast preview), then the all-months sweep.
    one_idx = src.find("_gen_one_issue_for_campaign")
    all_idx = src.find("_gen_all_issues_for_campaign")
    assert one_idx >= 0 and all_idx >= 0
    assert one_idx < all_idx, (
        "Must generate step 0 (for the fast preview) before sweeping the "
        "remaining months."
    )
    # Hands off to the page-level banner, and does NOT keep the dialog open
    # to swap content (that was the fragile path).
    assert "_nl_first_gen_camp_name" in src, (
        "Dialog must hand off to the page status banner via "
        "_nl_first_gen_camp_name"
    )
    assert "card.clear()" not in src, (
        "Dialog must NOT swap its own content in place — that path was "
        "destroyed by background re-renders"
    )


def test_first_gen_banner_renders_inline_preview():
    """The page status banner must render the first issue's HTML inline
    (not just a button) so the user sees the preview where they spun the
    newsletter up."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._render_nl_first_gen_status)
    assert 'emails", []' in src or "emails" in src, (
        "banner must read the campaign's issue body to preview it"
    )
    assert "ui.html(" in src, (
        "banner must render the issue HTML inline as a preview"
    )
