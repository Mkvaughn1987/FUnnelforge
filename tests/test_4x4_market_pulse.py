"""Arena 4x4: the market snapshot (Market Pulse PDF) on Step 6 is built and
pinned on every creation path, and the sequence card says so.
Imports flowdrip_app lazily inside each test (per tests/conftest.py)."""
import inspect


def _emails():
    return [
        {"name": "Step 1 - Introducing Available Talent", "step_type": "email_auto",
         "subject": "Plant Manager Candidates Available", "body": "intro",
         "delay_days": 0},
        {"name": "Step 2 - Top Talent Insights", "step_type": "email_auto",
         "subject": "Top Talent Insights", "body": "facts", "delay_days": 3},
        {"name": "Step 3 - Follow-up Call", "step_type": "call",
         "subject": "", "body": "call", "delay_days": 0},
        {"name": "Step 4 - LinkedIn Connect", "step_type": "linkedin",
         "subject": "", "body": "li", "delay_days": 0},
        {"name": "Step 5 - Proven Results", "step_type": "email_auto",
         "subject": "Thoughts on This?", "body": "results", "delay_days": 4},
        {"name": "Step 6 - Market Trends & Final Note", "step_type": "email_auto",
         "subject": "Market Trends and Hiring Solutions for Plant Manager",
         "body": '<div style="font-family:Aptos;">Hi {FirstName},<br><br>'
                 'A few market updates.</div>',
         "delay_days": 4},
    ]


def _fake_build(monkeypatch, fa, calls):
    def _b(kind_id, data, company, owner_email=""):
        calls.append((kind_id, company, owner_email, bool(data.get("sections"))))
        return fa._aicb_pdf_filename("Market_Pulse", company) if data.get("sections") else ""
    monkeypatch.setattr(fa, "_build_named_pdf", _b)


def test_pins_market_pulse_to_step_6_from_pdf_data(monkeypatch):
    import flowdrip_app as fa
    calls = []
    _fake_build(monkeypatch, fa, calls)
    camp = {"emails": _emails()}
    pdf_data = {"market_pulse": {"sections": [{"h": "x"}]},
                "salary_guide": {"sections": [{"h": "y"}]}}
    fname = fa._fourbyfour_attach_market_pulse(camp, "Anomatic",
                                               pdf_data=pdf_data,
                                               owner_email="m@x.com")
    assert fname == "Market_Pulse_Anomatic.pdf"
    assert calls == [("market_pulse", "Anomatic", "m@x.com", True)]
    step6 = camp["emails"][5]
    assert step6["attachments"] == [fname]
    for i, em in enumerate(camp["emails"]):
        if i != 5:
            assert not em.get("attachments")
    # idempotent
    fa._fourbyfour_attach_market_pulse(camp, "Anomatic", pdf_data=pdf_data)
    assert step6["attachments"] == [fname]


def test_generates_when_no_pdf_data(monkeypatch):
    import flowdrip_app as fa
    _fake_build(monkeypatch, fa, [])
    seen = {}

    def _gen(client, kind, ctx, research_context="", style_guide=""):
        seen["kind"] = kind
        seen["ctx"] = ctx
        return {"sections": [{"h": "demand"}]}
    monkeypatch.setattr(fa, "_generate_rich_pdf_data", _gen)
    monkeypatch.setattr(fa, "_style_guide_prompt", lambda: "")
    camp = {"emails": _emails()}
    fname = fa._fourbyfour_attach_market_pulse(
        camp, "Anomatic", client=object(), roles_str="Plant Manager",
        location_str="New Albany, OH", industry="Packaging")
    assert fname and camp["emails"][5]["attachments"] == [fname]
    assert seen["kind"] == "market_pulse"
    assert seen["ctx"]["positions"] == "Plant Manager"
    assert seen["ctx"]["company"] == "Anomatic"
    assert seen["ctx"]["location"] == "New Albany, OH"


def test_no_client_no_data_attaches_nothing(monkeypatch):
    import flowdrip_app as fa
    _fake_build(monkeypatch, fa, [])
    camp = {"emails": _emails()}
    assert fa._fourbyfour_attach_market_pulse(camp, "Anomatic") == ""
    assert not camp["emails"][5].get("attachments")
    assert fa._fourbyfour_attach_market_pulse({"emails": []}, "Anomatic") == ""


def test_positional_fallback_when_step_names_drift(monkeypatch):
    import flowdrip_app as fa
    _fake_build(monkeypatch, fa, [])
    ems = _emails()
    for e in ems:
        e["name"] = e["name"].replace("Step ", "Email ")
    camp = {"emails": ems}
    fname = fa._fourbyfour_attach_market_pulse(
        camp, "Anomatic", pdf_data={"market_pulse": {"sections": [1]}})
    assert camp["emails"][5]["attachments"] == [fname]


def test_five_by_five_still_pins_its_own_guide(monkeypatch):
    """The shared pin helper must not change what the 5x5 does."""
    import flowdrip_app as fa
    calls = []

    def _b(kind_id, data, company, owner_email=""):
        calls.append(kind_id)
        return fa._aicb_pdf_filename("Salary_Guide", company)
    monkeypatch.setattr(fa, "_build_named_pdf", _b)
    ems = _emails() + [{"name": "Step 7 - Closing", "step_type": "email_auto",
                        "subject": "Closing", "body": "x", "delay_days": 4}]
    camp = {"emails": ems}
    fname = fa._fivebyfive_attach_salary_guide(
        camp, "Acme", pdf_data={"salary_guide": {"sections": [1]}})
    assert calls == ["salary_guide"]
    assert camp["emails"][5]["attachments"] == [fname]


def test_overrides_line_matches_the_pinned_kind():
    import flowdrip_app as fa
    assert fa._FOURBYFOUR_PDF_KIND == "market_pulse"
    assert fa._FOURBYFOUR_PDF_STEP == 6
    assert fa._FOURBYFOUR_PDF_TYPES == {"fourbyfour"}
    line = fa._FOURBYFOUR_MARKET_LINE
    assert "market snapshot" in line.lower()
    assert "—" not in line and "–" not in line
    camp = {"emails": _emails()}
    fa._apply_fourbyfour_overrides("fourbyfour", camp)
    body = camp["emails"][5]["body"]
    assert "market snapshot" in body.lower()
    # stamped inside the font div, once
    assert body.rstrip().endswith("</div>")
    assert body.lower().count("market snapshot") == 1
    fa._apply_fourbyfour_overrides("fourbyfour", camp)
    assert camp["emails"][5]["body"].lower().count("market snapshot") == 1
    # other steps untouched, other types untouched
    assert "market snapshot" not in camp["emails"][4]["body"].lower()
    other = {"emails": _emails()}
    fa._apply_fourbyfour_overrides("fivebyfive", other)
    assert "market snapshot" not in other["emails"][5]["body"].lower()


def test_generator_applies_the_overrides():
    import flowdrip_app as fa
    src = inspect.getsource(fa._aicb_build_campaign_from_brief)
    assert "_apply_fourbyfour_overrides(camp_type, campaign_data)" in src
    assert "_apply_fivebyfive_overrides(camp_type, campaign_data)" in src


def test_every_creation_path_pins_the_snapshot():
    import flowdrip_app as fa
    import sales_campaign as sc
    api_src = inspect.getsource(fa._api_create_campaign_blocking)
    assert "_fourbyfour_attach_market_pulse(" in api_src
    assert "_FOURBYFOUR_PDF_TYPES" in api_src
    sc_src = inspect.getsource(sc._build_and_review)
    assert "_fourbyfour_attach_market_pulse(" in sc_src
    # Wizard: the topic match attaches nothing for the 4x4, then the
    # snapshot is pinned from the already-generated phase-1 payload.
    wiz = inspect.getsource(fa.p_ai_campaign)
    assert "_FOURBYFOUR_PDF_TYPES" in wiz
    assert "_fourbyfour_attach_market_pulse(" in wiz
    assert wiz.index("restrict_kinds=_restrict") < wiz.index("_fourbyfour_attach_market_pulse(")


def test_step_6_prompt_leaves_the_attachment_to_the_code():
    import flowdrip_app as fa
    entry = next(t for t in fa.AICB_CAMPAIGN_TYPES if t[0] == "fourbyfour")
    outline = entry[-1]
    step6 = outline[outline.index("Step 6 -"):]
    assert "attach" in step6.lower()


def test_sequence_card_shows_the_snapshot():
    import ai_prompts as aip
    steps = aip.SEQUENCE_INFO["Arena 4x4"]["steps"]
    with_pdf = [st for st in steps if len(st) > 4]
    assert len(with_pdf) == 1
    assert with_pdf[0][0] == 12 and with_pdf[0][4] == "Market snapshot"
    assert "market snapshot" in aip.SEQUENCE_INFO["Arena 4x4"]["about"].lower()
