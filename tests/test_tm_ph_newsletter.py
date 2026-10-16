"""ThriveModal's Organic newsletter is about the Philippines offshore market,
with the logo block top right instead of Arena's full-width banner, and never
says "nonfarm" (Mike, 2026-10-16). Arena's Organic render is unchanged."""
import flowdrip_app as fa

PH = {
    "ph": True, "company": "Thrivemodal", "month_year": "November 2026",
    "intro": "More U.S. firms are hiring in the Philippines.",
    "ph_numbers": ["IT-BPM employed **1.8M** people in 2025"],
    "ph_source_url": "https://example.org/ibpap",
    "movers": ["**A freight broker** opened a Cebu desk"],
    "role_spotlight": {"role": "AP Clerk", "what": "Processes invoices.",
                       "bullets": ["Tools: QuickBooks"], "us_wage": "$23/hr (BLS)",
                       "ph_rate": "$9-$11/hr"},
    "why_now": ["U.S. nonfarm payrolls added **29,000** jobs"],
    "quick_answer": {"question": "Is my data safe?", "answer": "Yes, with controls."},
    "candidates": [],
}


def test_ph_render_has_corner_logo_and_sections(monkeypatch):
    monkeypatch.setattr(fa, "_SALES_MODE", True)
    html = fa._jway_render(dict(PH), "Mike")
    assert "thrivemodal_logo_email.png" in html and "align='right'" in html
    assert "jway_banner.png" not in html
    assert "MARKET NOTE &middot; NOVEMBER 2026" in html and "white-space:nowrap" in html
    assert "Thrivemodal places dedicated, full-time Filipino professionals" in html
    assert ("Inside:</strong> Philippines by the Numbers &middot; Who's Moving Offshore"
            " &middot; Role Spotlight &middot; Why Now &middot; Quick Answer") in html
    assert html.index("align='right'") < html.index("Hi {FirstName},")
    assert "Role Spotlight: AP Clerk" in html and "With Thrivemodal" in html
    assert "nonfarm" not in html.lower() and "U.S. payrolls added" in html


def test_inside_line_lists_only_present_sections(monkeypatch):
    monkeypatch.setattr(fa, "_SALES_MODE", True)
    html = fa._jway_render(dict(PH, movers=[], why_now=[]), "Mike")
    assert "Who's Moving Offshore" not in html and "Why Now" not in html


def test_ph_prompt_is_about_the_philippines_and_keeps_the_rules(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    plan = fa._tm_newsletter_plan("Offshore Staffing", 2026, 11, 1)
    p = fa._jway_ph_prompt("Thrivemodal", "Offshore Staffing", "November 2026",
                           plan, 0, "", "", "PLAYBOOK TEXT")
    assert "PHILIPPINES OFFSHORE MARKET" in p and "NOT written for staffing firms" in p
    assert "small and mid-sized U.S. businesses" in p
    assert plan["role"] in p and plan["objection"] in p
    assert "up to 60-70%" in p and "retention" in p and "PLAYBOOK TEXT" in p
    assert 'Never write the word "nonfarm"' in p
    assert '"candidates":[]' in p


def test_reader_is_the_buyer_industry():
    assert fa._tm_ph_reader("Freight Brokerages") == "U.S. Freight Brokerages companies"
    assert fa._tm_ph_reader("Offshore Staffing") == "small and mid-sized U.S. businesses"


def test_arena_render_unchanged(monkeypatch):
    monkeypatch.setattr(fa, "_SALES_MODE", False)
    d = {"sector": "Manufacturing", "highlights": ["U.S. nonfarm payrolls added 29K"],
         "takeaway": ["x"]}
    html = fa._jway_render(d, "J")
    assert "nonfarm" in html  # Arena keeps its wording
    assert "for Manufacturing and Skilled Trades" in html


def test_sales_mode_drops_skilled_trades_and_nonfarm(monkeypatch):
    monkeypatch.setattr(fa, "_SALES_MODE", True)
    d = {"sector": "Offshore Staffing", "highlights": ["U.S. Nonfarm payrolls added 29K"],
         "takeaway": ["x"]}
    html = fa._jway_render(d, "J")
    assert "Skilled Trades" not in html and "nonfarm" not in html.lower()


def test_logo_is_servable():
    assert "thrivemodal_logo_email.png" in fa._STATIC_ALLOWLIST
    assert (fa._APP_DIR / "thrivemodal_logo_email.png").is_file()


def test_generator_strips_cite_tags(monkeypatch):
    import json, types
    monkeypatch.setattr(fa, "_SALES_MODE", True)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    monkeypatch.setattr(fa, "_thrivemodal_playbook_text", lambda cfg=None: "")
    monkeypatch.setattr(fa, "_tm_profile_rate", lambda client, t: "Est. $9-$11/hr")
    reply = dict(PH, ph=None, company=None, month_year=None, subject="Big year",
                 ph_numbers=['Workforce hit <cite index="10-1">1.9 million in 2025</cite>.'])
    msg = types.SimpleNamespace(content=[types.SimpleNamespace(text=json.dumps(reply))])
    monkeypatch.setattr(fa, "_claude_create_with_retry", lambda *a, **k: msg)
    subject, html = fa._generate_jway_newsletter(
        None, {}, "Market Note", "Thrivemodal", "Offshore Staffing", "", "",
        "November 2026", "Mike", 0, "", year=2026, month=11, step_idx=1)
    assert "cite" not in html and "1.9 million in 2025" in html
    assert "MARKET NOTE &middot; NOVEMBER 2026" in html and "With Thrivemodal:</strong> $9-$11/hr" in html
