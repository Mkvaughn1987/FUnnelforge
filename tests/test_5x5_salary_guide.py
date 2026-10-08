"""Arena 5x5: the salary guide on Step 6 is built and pinned on every
creation path, and nothing else in the sequence mentions an attachment.
Imports flowdrip_app lazily inside each test (per tests/conftest.py)."""
import inspect


def _emails():
    return [
        {"name": "Step 1 - Introducing Myself", "step_type": "email_auto",
         "subject": "Quick note", "body": "intro", "delay_days": 0},
        {"name": "Step 2 - Top Talent Insights spotlight", "step_type": "email_auto",
         "subject": "One person", "body": "spot", "delay_days": 3},
        {"name": "Step 3 - Follow-up Call", "step_type": "call",
         "subject": "", "body": "call", "delay_days": 0},
        {"name": "Step 4 - LinkedIn Connect", "step_type": "linkedin",
         "subject": "", "body": "li", "delay_days": 0},
        {"name": "Step 5 - Following-up bump", "step_type": "email_auto",
         "subject": "Following up", "body": "bump", "delay_days": 2},
        {"name": "Step 6 - Worth a look", "step_type": "email_auto",
         "subject": "Still think this one's worth a look", "body": "worth",
         "delay_days": 3},
        {"name": "Step 7 - Closing the loop", "step_type": "email_auto",
         "subject": "Closing the loop for now", "body": "close", "delay_days": 4},
    ]


def _fake_build(monkeypatch, fa, calls):
    def _b(kind_id, data, company, owner_email=""):
        calls.append((kind_id, company, owner_email, bool(data.get("sections"))))
        return fa._aicb_pdf_filename("Salary_Guide", company) if data.get("sections") else ""
    monkeypatch.setattr(fa, "_build_named_pdf", _b)


def test_pins_salary_guide_to_step_6_from_pdf_data(monkeypatch):
    import flowdrip_app as fa
    calls = []
    _fake_build(monkeypatch, fa, calls)
    camp = {"emails": _emails()}
    pdf_data = {"salary_guide": {"sections": [{"h": "x"}]},
                "interview_guide": {"sections": [{"h": "y"}]}}
    fname = fa._fivebyfive_attach_salary_guide(camp, "Acme Builders",
                                               pdf_data=pdf_data,
                                               owner_email="m@x.com")
    assert fname == "Salary_Guide_Acme_Builders.pdf"
    assert calls == [("salary_guide", "Acme Builders", "m@x.com", True)]
    step6 = camp["emails"][5]
    assert step6["attachments"] == [fname]
    for i, em in enumerate(camp["emails"]):
        if i != 5:
            assert not em.get("attachments")
    # idempotent
    fa._fivebyfive_attach_salary_guide(camp, "Acme Builders", pdf_data=pdf_data)
    assert step6["attachments"] == [fname]


def test_generates_when_no_pdf_data(monkeypatch):
    import flowdrip_app as fa
    calls = []
    _fake_build(monkeypatch, fa, calls)
    seen = {}

    def _gen(client, kind, ctx, research_context="", style_guide=""):
        seen["kind"] = kind
        seen["ctx"] = ctx
        return {"sections": [{"h": "pay"}]}
    monkeypatch.setattr(fa, "_generate_rich_pdf_data", _gen)
    monkeypatch.setattr(fa, "_style_guide_prompt", lambda: "")
    camp = {"emails": _emails()}
    fname = fa._fivebyfive_attach_salary_guide(
        camp, "Acme", client=object(), roles_str="Estimator",
        location_str="Denver, CO", industry="Commercial Construction")
    assert fname and camp["emails"][5]["attachments"] == [fname]
    assert seen["kind"] == "salary_guide"
    assert seen["ctx"]["positions"] == "Estimator"
    assert seen["ctx"]["company"] == "Acme"


def test_no_client_no_data_attaches_nothing(monkeypatch):
    import flowdrip_app as fa
    calls = []
    _fake_build(monkeypatch, fa, calls)
    camp = {"emails": _emails()}
    assert fa._fivebyfive_attach_salary_guide(camp, "Acme") == ""
    assert not camp["emails"][5].get("attachments")
    assert fa._fivebyfive_attach_salary_guide({"emails": []}, "Acme") == ""


def test_positional_fallback_when_step_names_drift(monkeypatch):
    import flowdrip_app as fa
    _fake_build(monkeypatch, fa, [])
    ems = _emails()
    for e in ems:
        e["name"] = e["name"].replace("Step ", "Email ")
    camp = {"emails": ems}
    fname = fa._fivebyfive_attach_salary_guide(
        camp, "Acme", pdf_data={"salary_guide": {"sections": [1]}})
    assert camp["emails"][5]["attachments"] == [fname]


def test_overrides_line_matches_the_pinned_kind():
    import flowdrip_app as fa
    assert fa._FIVEBYFIVE_PDF_KIND == "salary_guide"
    assert fa._FIVEBYFIVE_PDF_STEP == 6
    assert "salary guide" in fa._FIVEBYFIVE_SALARY_LINE.lower()
    assert "interview" not in fa._FIVEBYFIVE_SALARY_LINE.lower()
    assert "—" not in fa._FIVEBYFIVE_SALARY_LINE and "–" not in fa._FIVEBYFIVE_SALARY_LINE
    camp = {"emails": _emails()}
    fa._apply_fivebyfive_overrides("clientlookalike", camp)
    assert "salary guide" in camp["emails"][5]["body"].lower()
    assert fa._FIVEBYFIVE_PDF_TYPES == {"fivebyfive", "clientlookalike"}


def test_every_creation_path_pins_the_guide():
    import flowdrip_app as fa
    import sales_campaign as sc
    api_src = inspect.getsource(fa._api_create_campaign_blocking)
    assert "_fivebyfive_attach_salary_guide(" in api_src
    assert "_FIVEBYFIVE_PDF_TYPES" in api_src
    sc_src = inspect.getsource(sc._build_and_review)
    assert "_fivebyfive_attach_salary_guide(" in sc_src
    # Wizard: the topic match attaches nothing for the 5x5 family, then the
    # guide is pinned from the already-generated phase-1 payload.
    wiz = inspect.getsource(fa.p_ai_campaign)
    assert "_FIVEBYFIVE_PDF_TYPES" in wiz
    assert "_fivebyfive_attach_salary_guide(" in wiz
    assert wiz.index("restrict_kinds=_restrict") < wiz.index("_fivebyfive_attach_salary_guide(")


def test_build_named_pdf_refuses_unknown_kind_and_empty_data():
    import flowdrip_app as fa
    assert fa._build_named_pdf("not_a_kind", {"sections": [1]}, "Acme") == ""
    assert fa._build_named_pdf("salary_guide", {}, "Acme") == ""
    assert set(fa._AICB_PDF_KIND_META) == {k[0] for k in fa._AICB_PDF_KINDS}


def test_sequence_cards_show_the_guide():
    import ai_prompts as aip
    for name in ("Arena 5x5", "Arena Client Lookalike"):
        steps = aip.SEQUENCE_INFO[name]["steps"]
        with_pdf = [st for st in steps if len(st) > 4]
        assert len(with_pdf) == 1, name
        assert with_pdf[0][0] == 9 and with_pdf[0][4] == "Salary guide", name
    assert "salary guide" in aip.SEQUENCE_INFO["Arena 5x5"]["about"].lower()
