"""Verify the newsletter/slowdrip page split:
- PAGE_HELP['evergreen'] no longer mentions Newsletters as a section.
- PAGE_HELP['newsletters'] has a new 'Enrolling contacts' section.
- p_evergreen source no longer renders the NEWSLETTERS section.
- p_newsletters source includes a '+ Enroll' button wired to _enroll_dialog.
"""
import inspect


def test_evergreen_help_drops_newsletters_section():
    import flowdrip_app as fa
    sections = fa.PAGE_HELP["evergreen"]["sections"]
    titles = [t for (t, _body) in sections]
    assert "Newsletters" not in titles, (
        f"PAGE_HELP['evergreen'] still has a 'Newsletters' bullet: {titles}"
    )


def test_newsletters_help_adds_enrolling_contacts_section():
    import flowdrip_app as fa
    sections = fa.PAGE_HELP["newsletters"]["sections"]
    titles = [t for (t, _body) in sections]
    assert "Enrolling contacts" in titles, (
        f"PAGE_HELP['newsletters'] should have an 'Enrolling contacts' bullet, "
        f"got: {titles}"
    )
    # Verify the body explains the + Enroll button.
    body = next(b for (t, b) in sections if t == "Enrolling contacts")
    assert "+ Enroll" in body or "Enroll" in body


def test_p_newsletters_includes_enroll_button():
    """p_newsletters source must contain a '+ Enroll' button wired to
    the existing _enroll_dialog helper. Source-grep test — UI rendering
    needs a real state object, so we assert the markers exist instead
    of running the function."""
    import flowdrip_app as fa
    src = inspect.getsource(fa.p_newsletters)
    assert "+ Enroll" in src or "＋ Enroll" in src, (
        "p_newsletters must include a '+ Enroll' button label"
    )
    assert "_enroll_dialog(" in src, (
        "p_newsletters must wire its enroll button to _enroll_dialog"
    )


def test_p_evergreen_no_longer_renders_newsletters():
    """p_evergreen source must no longer contain the NEWSLETTERS section
    header, the + New Newsletter button, or the _market_refresh state
    machine that was only reachable from the now-removed Refresh button."""
    import flowdrip_app as fa
    src = inspect.getsource(fa.p_evergreen)

    # Section header marker
    assert '"NEWSLETTERS"' not in src and "'NEWSLETTERS'" not in src, (
        "p_evergreen must not render the NEWSLETTERS section header anymore"
    )
    # Creation button label that lived inside p_evergreen
    assert "+ New Newsletter" not in src, (
        "p_evergreen must not render the '+ New Newsletter' button anymore "
        "(creation moved to p_newsletters)"
    )
    # The _market_refresh_* state was only set by the Refresh button on
    # newsletter cards inside p_evergreen, and consumed by the refresh
    # panel below. Both are gone, so neither setter nor reader should
    # remain in this function.
    assert "_market_refresh_camp" not in src, (
        "p_evergreen must no longer reference _market_refresh_camp "
        "(legacy newsletter refresh state)"
    )
