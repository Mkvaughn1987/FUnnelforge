"""Newsletters page list (2026-10-02 tidy): neutral rows, Enrolled / Next
issue / Created columns, secondary actions behind a ⋯ menu."""
import inspect

import flowdrip_app as fa


def test_enrolled_count_skips_removed_contacts():
    camp = {"contacts": [{"email": "a@x.com"}, {"email": "b@x.com", "removed": True},
                         {"email": "c@x.com"}]}
    assert fa._nl_enrolled_count(camp) == 2
    assert fa._nl_enrolled_count({}) == 0


def test_short_date_formats_iso_dates_and_timestamps():
    assert fa._nl_short_date("2026-09-18") == "Sep 18, 2026"
    assert fa._nl_short_date("2026-11-04T09:00:00") == "Nov 4, 2026"
    assert fa._nl_short_date("") == ""
    assert fa._nl_short_date("not a date") == ""


def test_created_label_prefers_created_date_then_fallbacks():
    assert fa._nl_created_label({"created_date": "2026-09-18"}) == "Sep 18, 2026"
    assert fa._nl_created_label({"created_at": "2026-08-01T10:00:00"}) == "Aug 1, 2026"
    assert fa._nl_created_label({"created": "2026-07-02"}) == "Jul 2, 2026"
    assert fa._nl_created_label({}) == ""


def test_page_shows_created_column_and_menu_actions():
    src = inspect.getsource(fa.p_newsletters)
    assert '"Created"' in src and "_nl_created_label(camp)" in src
    for action in ("Regenerate next issue", '"Settings"', '"Delete"'):
        assert action in src
    # Delete still goes through the confirmation dialog.
    assert "on_click=_delete_nl" in src and "def _delete_nl(" in src


def test_list_css_is_in_the_global_stylesheet():
    css = fa._nl_list_css()
    assert ".fd-nl-row" in css and "@media (max-width:900px)" in css
    assert "{_nl_list_css()}" in inspect.getsource(fa)
