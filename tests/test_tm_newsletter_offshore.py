"""ThriveModal newsletters are about offshore staffing: one article per issue
on a 12-month calendar, a rotating Role of the Month, server-computed Cost
Math, one objection, a customer story every third issue. Arena newsletters
must render exactly as before."""
import flowdrip_app as fa


def test_plan_rotates_with_the_send_month(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    plans = [fa._tm_newsletter_plan("Freight Brokerage", 2026 + (m > 12), (m - 1) % 12 + 1, i)
             for i, m in enumerate(range(10, 22))]
    assert len({p["angle"] for p in plans}) == 12
    assert len({p["objection"] for p in plans}) == 12
    assert all(p["vertical"] == "logistics" for p in plans)
    assert all(p["role"] in fa._TM_NL_ROLES["logistics"] for p in plans)
    assert [p["story"] for p in plans[:6]] == [False, False, True, False, False, True]


def test_every_month_has_an_angle():
    assert sorted(fa._TM_NL_ANGLES) == list(range(1, 13))


def test_prompt_is_offshore_and_keeps_the_claim_rules(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    plan = fa._tm_newsletter_plan("CPA firm", 2026, 10, 2)
    p = fa._tm_newsletter_prompt("The Ledger", "ThriveModal", "CPA Firms", "Dallas, TX",
                                 "October 2026", plan, "", "", "PLAYBOOK TEXT",
                                 'Kristy Knichel: "quote"')
    assert "OFFSHORE STAFFING" in p and plan["angle"] in p
    assert "role_of_month" not in p  # section removed 2026-09-19
    assert "up to 60-70%" in p and "round-the-clock" in p
    assert "WORD FOR WORD" in p and '"story"' in p and "PLAYBOOK TEXT" in p
    no_story = fa._tm_newsletter_prompt("x", "y", "z", "", "October 2026",
                                        dict(plan, story=False), "", "", "", "proof")
    assert '"story"' not in no_story


def test_renderer_shows_the_offshore_sections():
    html = fa._render_newsletter_html({
        "newsletter_name": "The Offshore Desk", "date": "October 2026",
        "feature": {"label": "This Month: X", "headline": "After-hours queue",
                    "paragraphs": ["Para **one**."], "takeaways": ["Do this"]},
        "role_of_month": {"title": "Track and Trace Specialist", "owns": ["Check calls"],
                          "tools": "McLeod", "stays_in_house": "Carrier relationships"},
        "cost_math": {"headline": "One role", "rows": [["Local", "$80,000"],
                      ["Offshore", "$28,000"], ["Difference", "$52,000"]], "note": "Estimate."},
        "objection": {"question": "Is our data safe?", "answer": "Here is how."},
        "story": {"text": "\"Quote.\"", "attribution": "Kristy Knichel"},
        "next_step": "Reply with one task.",
    })
    for s in ("After-hours queue", "<strong>one</strong>", "Role of the Month",
              "Track and Trace Specialist", "The Cost Math", "$52,000",
              "The Question We Hear Most", "From Our Clients", "Kristy Knichel",
              "Your Next Step"):
        assert s in html, s


def test_arena_newsletter_has_none_of_them():
    html = fa._render_newsletter_html({"newsletter_name": "Denver Report",
                                       "date": "October 2026", "intro_text": "Hi"})
    for s in ("Role of the Month", "The Cost Math", "The Question We Hear Most",
              "From Our Clients", "Your Next Step"):
        assert s not in html
    assert "Meet Your Hiring Partner" in html or "Hiring Partner" not in html


def test_squarish_logo_gets_more_height():
    assert fa._nl_logo_max_h(3.0) == 60
    assert fa._nl_logo_max_h(1.4) == 120


def test_proof_default_carries_the_verbatim_knichel_quotes():
    proof = dict((k, d) for k, _l, _h, d in fa.THRIVEMODAL_PLAYBOOK_FIELDS)["tm_proof"]
    assert "people who take ownership of their" in proof
    assert "understood the industry and could" in proof


def test_plan_outside_thrivemodal_uses_the_general_roles(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    assert fa._tm_newsletter_plan("Freight", 2026, 10, 0)["vertical"] == fa._TM_VERTICAL_GENERAL


def test_holiday_notes_switch_on_thrivemodal_only(monkeypatch):
    monkeypatch.setattr(fa, "_SALES_MODE", True)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    tm = dict((n, note) for _d, n, note in fa._holidays_for_month(2026, 12))
    assert tm["Christmas"] == fa._TM_HOLIDAY_NOTES["Christmas"]
    over = fa._holidays_for_month(2026, 12, {"12-christmas": "Mine"})
    assert over[0][2] == "Mine"
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    arena = dict((n, note) for _d, n, note in fa._holidays_for_month(2026, 12))
    assert "builds your projects" in arena["Christmas"]


def test_thrivemodal_newsletter_has_no_hero_photo(monkeypatch):
    import inspect
    monkeypatch.setattr(fa, "_SALES_MODE", True)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    assert not fa._nl_hero_enabled()
    html = fa._render_newsletter_html({"newsletter_name": "The Offshore Desk",
                                       "date": "October 2026", "location": "Dallas, TX"})
    assert 'height="180"' not in html
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    assert fa._nl_hero_enabled()
    assert "_loc_raw and _nl_hero_enabled()" in inspect.getsource(fa._render_newsletter_html)


def test_profile_rate_is_one_rate_60_percent_below_the_us_median():
    # Single rate, no range (Mike 2026-09-19): 40% of the U.S. hourly,
    # x1.08 for 5-6 years, rounded to the quarter.
    bench = fa._tm_benchmark("staff_accountant")
    hourly = bench["base"] / 2080.0
    rate = fa._tm_profile_rate(None, "Staff Accountant, 5 years experience")
    assert "-" not in rate and rate.endswith("/hr")
    assert float(rate[1:-3]) == round(hourly * 0.40 * 1.08 * 4) / 4
    assert fa._tm_profile_role("Leasing Coordinator, 5 years") == "Leasing Coordinator"


def test_cost_math_says_estimated_savings():
    import inspect
    src = inspect.getsource(fa._tm_newsletter_cost_math)
    assert '"Estimated savings"' in src and "Estimated difference" not in src


def test_json_reply_parser_prefers_last_text_block():
    from types import SimpleNamespace as NS
    msg = NS(content=[NS(text="Searching {rates} now."),
                      NS(text='```json\n{"headline": "Hi", "items": [1,],}\n```')])
    assert fa._nl_parse_json_reply(msg) == {"headline": "Hi", "items": [1]}
    assert fa._nl_parse_json_reply(NS(content=[NS(text="no json here")])) is None
