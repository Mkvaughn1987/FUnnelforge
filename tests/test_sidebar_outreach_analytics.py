"""The default sidebar layout must link to Outreach Analytics (2026-10-06:
it was only in the classic SALES_NAV, so the page was unreachable)."""
import flowdrip_app as fa


def test_sidebar_has_outreach_analytics_row():
    keys = {key for _sec, rows in fa.SIDEBAR_NAV for _ik, _lbl, key in rows}
    assert "outreach_analytics" in keys


def test_outreach_analytics_row_lights_and_has_icon():
    assert fa.SIDEBAR_PAGE_ROW["outreach_analytics"] == "analytics"
    assert "analytics" in fa._SIDEBAR_ICONS
    assert fa.SIDEBAR_TITLES["outreach_analytics"] == "Outreach Analytics"
