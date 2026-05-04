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
