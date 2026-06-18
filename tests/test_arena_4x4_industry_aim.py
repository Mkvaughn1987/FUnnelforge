"""The Arena 4x4 (candidate-row path) is aimed at an industry + location, not
a specific company/job posting. The prompt builder must frame outreach around
the market and must NOT carry posting/company-specific phrasing.

Spec: docs/superpowers/specs/2026-06-17-arena-4x4-industry-location-aim-design.md
"""
import flowdrip_app as fa


def test_prompt_includes_industry_and_location():
    p = fa._4x4_email_prompt("Mike", "Arena Direct Hire",
                             "Manufacturing", "Salt Lake City, UT")
    assert "Manufacturing" in p
    assert "Salt Lake City, UT" in p


def test_prompt_keeps_injection_tokens():
    """The caller fills [[HIGHLIGHTS]] and [[MARKET]] after generation, so the
    template must preserve them verbatim."""
    p = fa._4x4_email_prompt("Mike", "Arena Direct Hire",
                             "Manufacturing", "Salt Lake City, UT")
    assert "[[HIGHLIGHTS]]" in p
    assert "[[MARKET]]" in p


def test_prompt_has_no_company_posting_framing():
    """No assumption the recipient posted a req or is one specific company."""
    p = fa._4x4_email_prompt("Mike", "Arena Direct Hire",
                             "Manufacturing", "Salt Lake City, UT").lower()
    for banned in ("job posting", "actively seeking", "advertising",
                   "job link", "the live job"):
        assert banned not in p, f"prompt still carries posting framing: {banned!r}"
