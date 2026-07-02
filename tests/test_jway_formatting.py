"""Organic (J's Way) newsletter formatting: bold+underlined section/candidate
headers, inline **bold** emphasis, and dashed bold-label candidate details.
"""
import flowdrip_app as fa


def _doc(**kw):
    base = {
        "intro": "Market note.",
        "key_highlights": ["Nonfarm payrolls rose by **115,000** in April"],
        "sector_strength": ["Transportation added **30,000** jobs"],
        "candidates": [{
            "label": "Candidate A", "role": "Senior CNC Machinist",
            "bullets": ["Experience: 25+ years in CNC machining",
                        "Proficiencies: Mazak, Haas"],
            "salary": "Target Salary: $33/hr.",
        }],
        "signoff": "Thank you, and I hope this was helpful!",
        "sector": "Manufacturing",
    }
    base.update(kw)
    return base


def test_section_headers_bold_and_underlined():
    html = fa._jway_render(_doc(), "there")
    assert "text-decoration:underline" in html
    assert "Sector Strength (Manufacturing):" in html


def test_labor_and_takeaway_get_sector_suffix():
    html = fa._jway_render(_doc(labor_context=["x"], takeaway=["y"]), "there")
    assert "Labor Market Context (What matters for Manufacturing):" in html
    assert "Takeaway: What This Means for Manufacturing and Skilled Trades:" in html


def test_inline_bold_markdown_converted():
    html = fa._jway_render(_doc(), "there")
    assert "<strong>115,000</strong>" in html
    assert "**" not in html  # no leftover markdown


def test_candidate_detail_is_dash_with_bold_label():
    html = fa._jway_render(_doc(), "there")
    assert "- <strong>Experience:</strong> 25+ years in CNC machining" in html


def test_candidate_name_bold_underlined():
    html = fa._jway_render(_doc(), "there")
    assert "<strong><u>Candidate A: Senior CNC Machinist</u></strong>" in html


def test_salary_bold_label():
    html = fa._jway_render(_doc(), "there")
    assert "<strong>Target Salary:</strong> $33/hr." in html


def test_warm_regards_closing():
    assert "Warm regards," in fa._jway_render(_doc(), "there")


def test_no_sector_means_no_parenthetical():
    html = fa._jway_render(_doc(sector=""), "there")
    assert "Sector Strength:" in html
    assert "(Manufacturing)" not in html
