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


def test_industry_reads_the_name_first_then_the_niche():
    ind = fa._nl_industry
    assert ind({"name": "Kansas Manufacturing"}) == "Manufacturing"
    assert ind({"name": "Utah Manufacturing", "market_niche": "Aerospace"}) == "Manufacturing"
    assert ind({"name": "Recruitment Rundown - Package Manufacturing"}) == "Manufacturing"
    assert ind({"name": "Denver Machine Shop - Tool and Die Maker Campaign"}) == "Manufacturing"
    assert ind({"name": "Colorado Construction Rundown"}) == "Construction"
    assert ind({"name": "Utah Heavy Equipment and Construction"}) == "Construction"
    assert ind({"name": "Mission Critical Construction Rundown"}) == "Construction"
    assert ind({"name": "S+B James Healthcare Construction Campaign"}) == "Construction"
    assert ind({"name": "Kentucky Civil Engineering"}) == "Civil & Infrastructure"
    assert ind({"name": "San Diego Civil Construction Pulse"}) == "Civil & Infrastructure"
    assert ind({"name": "Denver Water/Wastewater Utility Market Campaign"}) == "Civil & Infrastructure"
    assert ind({"name": "The Montana Market Minute",
                "market_niche": "Heavy Civil Contractor"}) == "Civil & Infrastructure"
    assert ind({"name": "19six Architects - Education & Healthcare Design"}) == "Architecture & Design"
    assert ind({"name": "The Med Tech Monthly Newsletter"}) == "Healthcare"
    assert ind({"name": "Okta, Inc. - Programmer & AI Specialist Campaign"}) == "Technology"
    assert ind({"name": "Nutrien Ag Solutions - Monthly Newsletter"}) == "Agriculture & Food"
    assert ind({"name": "Offshore Accounting Talent"}) == "Accounting & Finance"
    assert ind({"name": "Freight Brokerage Brief"}) == "Logistics & Freight"
    assert ind({"name": "Arena Direct Hire Market Note"}) == "General"
    assert ind({}) == "General"


def test_industry_groups_busiest_first_general_last():
    def nl(name, n):
        return {"name": name, "contacts": [{"email": f"{i}@x.com"} for i in range(n)]}
    groups = fa._nl_industry_groups([
        nl("Arena Direct Hire Market Note", 2710), nl("Kansas Manufacturing", 109),
        nl("Colorado Construction Rundown", 569), nl("Utah Manufacturing", 35),
        nl("Western Manufacturing", 92)])
    assert [g for g, _ in groups] == ["Construction", "Manufacturing", "General"]
    assert [c["name"] for c in groups[1][1]] == [
        "Kansas Manufacturing", "Western Manufacturing", "Utah Manufacturing"]


def test_page_renders_a_headline_per_industry():
    src = inspect.getsource(fa.p_newsletters)
    assert "_nl_industry_groups(camps)" in src and "fd-nl-group-t" in src
    assert ".fd-nl-group-t" in fa._nl_list_css()
