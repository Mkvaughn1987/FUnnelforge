"""Arena 5x5 / Client Lookalike: a Market Pulse PDF rides on Step 2 beside
the salary guide on Step 6, built and pinned on every creation path (wizard,
API, Sales Campaign). The 5x5 and 5x3 prompts feature the candidates on at
least two emails: the whole slate on email 2, one line each again later
(Mike, 2026-10-14). Imports flowdrip_app lazily (per tests/conftest.py)."""
import inspect

_PREFIX = {"market_pulse": "Market_Pulse", "salary_guide": "Salary_Guide"}


def _emails():
    return [
        {"name": "Step 1 - Introducing Myself", "step_type": "email_auto",
         "subject": "Quick note", "body": "intro", "delay_days": 0},
        {"name": "Step 2 - The slate", "step_type": "email_auto",
         "subject": "A few people", "body": '<div style="font-family:Aptos;">'
         'Hi {FirstName},<br><br>slate</div>', "delay_days": 3},
        {"name": "Step 3 - Follow-up Call", "step_type": "call",
         "subject": "", "body": "call", "delay_days": 0},
        {"name": "Step 4 - LinkedIn Connect", "step_type": "linkedin",
         "subject": "", "body": "li", "delay_days": 0},
        {"name": "Step 5 - Following-up bump", "step_type": "email_auto",
         "subject": "Following up", "body": "bump", "delay_days": 2},
        {"name": "Step 6 - Worth a look", "step_type": "email_auto",
         "subject": "Still think these are worth a look",
         "body": '<div style="font-family:Aptos;">Hi {FirstName},<br><br>'
                 'worth</div>', "delay_days": 3},
        {"name": "Step 7 - Closing the loop", "step_type": "email_auto",
         "subject": "Closing the loop for now", "body": "close", "delay_days": 4},
    ]


def _fake_build(monkeypatch, fa, calls):
    def _b(kind_id, data, company, owner_email=""):
        calls.append((kind_id, company, owner_email, bool(data.get("sections"))))
        if not data.get("sections"):
            return ""
        return fa._aicb_pdf_filename(_PREFIX[kind_id], company)
    monkeypatch.setattr(fa, "_build_named_pdf", _b)


def _step(outline, n):
    i = outline.index("Step %d -" % n)
    j = outline.find("Step %d -" % (n + 1))
    return outline[i:j if j != -1 else None]


def _outline(fa, key):
    return next(t for t in fa.AICB_CAMPAIGN_TYPES if t[0] == key)[-1]


# ── Pinning ─────────────────────────────────────────────────────────────

def test_pins_market_pulse_to_step_2_from_pdf_data(monkeypatch):
    import flowdrip_app as fa
    calls = []
    _fake_build(monkeypatch, fa, calls)
    camp = {"emails": _emails()}
    pdf_data = {"market_pulse": {"sections": [{"h": "x"}]},
                "salary_guide": {"sections": [{"h": "y"}]}}
    fname = fa._fivebyfive_attach_market_pulse(camp, "Acme Builders",
                                               pdf_data=pdf_data,
                                               owner_email="m@x.com")
    assert fname == "Market_Pulse_Acme_Builders.pdf"
    assert calls == [("market_pulse", "Acme Builders", "m@x.com", True)]
    assert camp["emails"][1]["attachments"] == [fname]
    for i, em in enumerate(camp["emails"]):
        if i != 1:
            assert not em.get("attachments")
    # idempotent
    fa._fivebyfive_attach_market_pulse(camp, "Acme Builders", pdf_data=pdf_data)
    assert camp["emails"][1]["attachments"] == [fname]


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
    fname = fa._fivebyfive_attach_market_pulse(
        camp, "Acme", client=object(), roles_str="Estimator",
        location_str="Denver, CO", industry="Commercial Construction")
    assert fname and camp["emails"][1]["attachments"] == [fname]
    assert seen["kind"] == "market_pulse"
    assert seen["ctx"]["positions"] == "Estimator"
    assert seen["ctx"]["company"] == "Acme"
    assert seen["ctx"]["location"] == "Denver, CO"


def test_no_client_no_data_attaches_nothing(monkeypatch):
    import flowdrip_app as fa
    _fake_build(monkeypatch, fa, [])
    camp = {"emails": _emails()}
    assert fa._fivebyfive_attach_market_pulse(camp, "Acme") == ""
    assert not camp["emails"][1].get("attachments")
    assert fa._fivebyfive_attach_market_pulse({"emails": []}, "Acme") == ""


def test_positional_fallback_when_step_names_drift(monkeypatch):
    import flowdrip_app as fa
    _fake_build(monkeypatch, fa, [])
    ems = _emails()
    for e in ems:
        e["name"] = e["name"].replace("Step ", "Email ")
    camp = {"emails": ems}
    fname = fa._fivebyfive_attach_market_pulse(
        camp, "Acme", pdf_data={"market_pulse": {"sections": [1]}})
    assert camp["emails"][1]["attachments"] == [fname]


def test_both_pdfs_land_on_their_own_steps(monkeypatch):
    import flowdrip_app as fa
    calls = []
    _fake_build(monkeypatch, fa, calls)
    camp = {"emails": _emails()}
    pdf_data = {k: {"sections": [1]} for k in
                ("market_pulse", "salary_guide", "interview_guide",
                 "scorecard", "tenure_snapshot")}
    mp = fa._fivebyfive_attach_market_pulse(camp, "Acme", pdf_data=pdf_data)
    sg = fa._fivebyfive_attach_salary_guide(camp, "Acme", pdf_data=pdf_data)
    assert [c[0] for c in calls] == ["market_pulse", "salary_guide"]
    assert camp["emails"][1]["attachments"] == [mp]
    assert camp["emails"][5]["attachments"] == [sg]
    for i in (0, 2, 3, 4, 6):
        assert not camp["emails"][i].get("attachments")


# ── The line the body promises ──────────────────────────────────────────

def test_constants_match_the_pinned_kind():
    import flowdrip_app as fa
    assert fa._FIVEBYFIVE_MARKET_KIND == "market_pulse"
    assert fa._FIVEBYFIVE_MARKET_STEP == 2
    assert fa._FIVEBYFIVE_MARKET_STEP != fa._FIVEBYFIVE_PDF_STEP
    line = fa._FIVEBYFIVE_MARKET_LINE
    assert "market pulse" in line.lower()
    assert "salary" not in line.lower()
    assert "—" not in line and "–" not in line


def test_overrides_stamp_the_market_line_on_step_2_once():
    import flowdrip_app as fa
    for ct in ("fivebyfive", "clientlookalike"):
        camp = {"emails": _emails()}
        fa._apply_fivebyfive_overrides(ct, camp)
        body = camp["emails"][1]["body"]
        assert "market pulse" in body.lower(), ct
        assert body.rstrip().endswith("</div>"), ct   # inside the font div
        assert body.lower().count("market pulse") == 1
        # the salary line still lands on Step 6 only
        assert "salary guide" in camp["emails"][5]["body"].lower()
        assert "market pulse" not in camp["emails"][5]["body"].lower()
        for i in (0, 2, 3, 4, 6):
            assert "market pulse" not in camp["emails"][i]["body"].lower()
        fa._apply_fivebyfive_overrides(ct, camp)
        assert camp["emails"][1]["body"].lower().count("market pulse") == 1
    other = {"emails": _emails()}
    fa._apply_fivebyfive_overrides("fourbyfour", other)
    assert "market pulse" not in other["emails"][1]["body"].lower()


# ── Every creation path ─────────────────────────────────────────────────

def test_every_creation_path_pins_the_pulse():
    import flowdrip_app as fa
    import sales_campaign as sc
    api_src = inspect.getsource(fa._api_create_campaign_blocking)
    assert "_fivebyfive_attach_market_pulse(" in api_src
    sc_src = inspect.getsource(sc._build_and_review)
    assert "_fivebyfive_attach_market_pulse(" in sc_src
    wiz = inspect.getsource(fa.p_ai_campaign)
    assert "_fivebyfive_attach_market_pulse(" in wiz
    assert wiz.index("restrict_kinds=_restrict") < wiz.index("_fivebyfive_attach_market_pulse(")


# ── Prompts: candidates on at least two emails ──────────────────────────

def test_5x5_prompt_sends_the_slate_twice():
    import flowdrip_app as fa
    outline = _outline(fa, "fivebyfive")
    s2, s6 = _step(outline, 2), _step(outline, 6)
    assert "WHOLE slate" in s2 and "CANDIDATE DEPTH" in s2
    assert "ONE line per candidate" in s6
    assert "spotlight ONE candidate" not in outline
    assert "Do NOT list the whole slate" not in outline
    # attachments stay the code's job on both PDF steps
    assert "attach" in s2.lower() and "attach" in s6.lower()
    # the other emails carry no candidates
    assert "Do NOT list or reference any candidates" in _step(outline, 1)
    assert "No candidates" in _step(outline, 5)


def test_5x3_prompt_sends_the_slate_twice():
    import flowdrip_app as fa
    outline = _outline(fa, "fivebythree")
    s2, s3 = _step(outline, 2), _step(outline, 3)
    assert "Present the slate" in s2 and "CANDIDATE DEPTH" in s2
    assert "ONE line per candidate" in s3
    assert "do NOT re-list the candidates" not in outline
    assert "attach" in s3.lower()
    # the 5x3's PDF plan is untouched
    assert fa._SEQUENCE_PDF_PLAN["fivebythree"] == (
        (2, "market_pulse"), (3, "interview_guide"), (4, "salary_guide"))


def test_clientlookalike_step_2_leaves_the_attachment_to_the_code():
    import flowdrip_app as fa
    outline = _outline(fa, "clientlookalike")
    assert "attach" in _step(outline, 2).lower()
    assert "attach" in _step(outline, 6).lower()


def test_weave_block_matches_the_two_email_design():
    import flowdrip_app as fa
    for ct in ("fivebyfive", "fivebythree"):
        block = fa._aicb_candidate_weave_block(ct)
        assert "Email 2" in block and "one line" in block.lower(), ct
    assert "Email 4" in fa._aicb_candidate_weave_block("fivebyfive")
    assert "Email 3" in fa._aicb_candidate_weave_block("fivebythree")
    # the 4x4 and the generic block are untouched
    assert "EVERY email" in fa._aicb_candidate_weave_block("fourbyfour")
    assert "EVERY OTHER email" in fa._aicb_candidate_weave_block("blitz")


# ── Cards and tiles ─────────────────────────────────────────────────────

def test_sequence_cards_show_both_pdfs():
    import ai_prompts as aip
    for name in ("Arena 5x5", "Arena Client Lookalike"):
        steps = aip.SEQUENCE_INFO[name]["steps"]
        with_pdf = [(st[0], st[4]) for st in steps if len(st) > 4]
        assert with_pdf == [(4, "Market pulse"), (9, "Salary guide")], name
        about = aip.SEQUENCE_INFO[name]["about"].lower()
        assert "market pulse" in about and "salary guide" in about, name
    five = aip.SEQUENCE_INFO["Arena 5x5"]
    assert "slate" in five["steps"][1][3].lower()
    assert "each candidate" in five["steps"][5][3].lower()
    assert "spotlight" not in five["about"].lower()
    three = aip.SEQUENCE_INFO["Arena 5x3"]
    assert "each candidate" in three["steps"][2][3].lower()


def test_chooser_tile_names_both_pdfs():
    import flowdrip_app as fa
    tile = next(o for o in fa.CHOOSER_OPTIONS if o.get("key") == "fivebyfive")
    desc = tile["desc"].lower()
    assert "market pulse" in desc and "salary guide" in desc
    assert "interview guide" not in desc
    entry = next(t for t in fa.AICB_CAMPAIGN_TYPES if t[0] == "fivebyfive")
    assert "market pulse" in entry[4].lower() and "salary guide" in entry[4].lower()
