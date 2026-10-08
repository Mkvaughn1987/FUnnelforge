"""Arena 5x3/5x7 run like inboxslide's Standard Outreach (three PDFs on three
emails, no résumés), and every campaign's candidate write-ups go in depth
off the real résumé (Mike, 2026-10-08).
Imports flowdrip_app lazily inside each test (per tests/conftest.py)."""
import inspect
import json


def _five_by_three():
    return {"emails": [
        {"name": f"Step {n} - x", "step_type": "email_auto", "subject": f"s{n}",
         "body": f'<div style="font-family:Aptos;">Hi {{FirstName}},<br><br>body {n}</div>',
         "delay_days": 9}
        for n in range(1, 6)]}


def _five_by_seven():
    kinds = {3: "call", 4: "linkedin", 8: "call"}
    return {"emails": [
        {"name": f"Step {n} - x", "step_type": kinds.get(n, "email_auto"),
         "subject": f"s{n}",
         "body": f'<div style="font-family:Aptos;">body {n}</div>',
         "delay_days": 9}
        for n in range(1, 11)]}


def _by_step(fa, camp):
    return {fa._fivebyfive_step_no(e["name"]): e for e in camp["emails"]}


def test_plan_matches_the_agreed_layout():
    import flowdrip_app as fa
    assert fa._SEQUENCE_PDF_PLAN["fivebythree"] == (
        (2, "market_pulse"), (3, "interview_guide"), (4, "salary_guide"))
    # 5x7 emails 2, 4 and 5 are Steps 2, 6 and 7 (calls + LinkedIn between).
    assert fa._SEQUENCE_PDF_PLAN["fivebyseven"] == (
        (2, "market_pulse"), (6, "interview_guide"), (7, "salary_guide"))


def test_5x3_lines_close_their_emails_once():
    import flowdrip_app as fa
    camp = fa._apply_fivebythree_overrides("fivebythree", _five_by_three())
    camp = fa._apply_fivebythree_overrides("fivebythree", camp)
    s = _by_step(fa, camp)
    for n, kind in fa._SEQUENCE_PDF_PLAN["fivebythree"]:
        line = fa._SEQUENCE_PDF_LINES[kind]
        assert s[n]["body"].count(line) == 1, n
        assert s[n]["body"].endswith(line + "</div>"), n
    for n in (1, 5):
        assert "I attached" not in s[n]["body"]


def test_5x7_lines_skip_calls_and_linkedin():
    import flowdrip_app as fa
    camp = fa._apply_fivebyseven_overrides("fivebyseven", _five_by_seven())
    s = _by_step(fa, camp)
    for n, kind in fa._SEQUENCE_PDF_PLAN["fivebyseven"]:
        assert s[n]["body"].count(fa._SEQUENCE_PDF_LINES[kind]) == 1
    for n in (1, 3, 4, 5, 8, 9, 10):
        assert "I attached" not in s[n]["body"]


def test_attach_pins_three_files_to_the_planned_steps(monkeypatch):
    import flowdrip_app as fa
    calls = []

    def _b(kind_id, data, company, owner_email=""):
        calls.append(kind_id)
        return f"{kind_id}_{company}.pdf" if data.get("sections") else ""
    monkeypatch.setattr(fa, "_build_named_pdf", _b)
    pdf_data = {k: {"sections": [{"h": k}]}
                for k in ("market_pulse", "interview_guide", "salary_guide",
                          "scorecard", "tenure_snapshot")}
    for ct, maker in (("fivebythree", _five_by_three),
                      ("fivebyseven", _five_by_seven)):
        calls.clear()
        camp = maker()
        got = fa._attach_sequence_pdfs(ct, camp, "Acme", pdf_data=pdf_data)
        assert calls == ["market_pulse", "interview_guide", "salary_guide"]
        assert len(got) == 3
        s = _by_step(fa, camp)
        planned = dict(fa._SEQUENCE_PDF_PLAN[ct])
        for n, em in s.items():
            if n in planned:
                assert em["attachments"] == [f"{planned[n]}_Acme.pdf"]
            else:
                assert not em.get("attachments")


def test_other_types_get_no_sequence_pdfs():
    import flowdrip_app as fa
    camp = _five_by_three()
    assert fa._attach_sequence_pdfs("fivebyfive", camp, "Acme") == []
    assert all(not e.get("attachments") for e in camp["emails"])


def test_every_path_pins_the_sequence_pdfs():
    import flowdrip_app as fa
    import sales_campaign
    api = inspect.getsource(fa._api_create_campaign_blocking)
    assert "_attach_sequence_pdfs(" in api
    assert "_build_redacted_resumes_from_cards" not in api
    assert "ff._attach_sequence_pdfs(" in inspect.getsource(sales_campaign)
    src = inspect.getsource(fa)
    assert "_camp_type_now in _SEQUENCE_PDF_TYPES" in src


def test_prompts_and_cards_never_promise_resumes():
    import flowdrip_app as fa
    import ai_prompts
    for key in ("fivebythree", "fivebyseven"):
        t = next(x for x in fa.AICB_CAMPAIGN_TYPES if x[0] == key)
        assert "redacted résumés on" not in t[4]
        assert "Mention their résumés are attached" not in t[6]
        tile = next(o for o in fa.CHOOSER_OPTIONS if o.get("key") == key)
        assert "No résumés" in tile["desc"]
    for name in ("Arena 5x3", "Arena 5x7"):
        info = ai_prompts.SEQUENCE_INFO[name]
        assert "Redacted resumes" not in [st[4] for st in info["steps"]
                                          if len(st) > 4]
        assert "No resumes" in info["about"]


# ── In-depth candidate write-ups ────────────────────────────────────────

def test_depth_rule_goes_into_every_candidate_block():
    import flowdrip_app as fa
    block = fa._format_candidate_block(
        [{"label": "Candidate A", "role": "PM", "bullets": ["x"]}], "fourbyfour")
    assert fa._CAND_DEPTH_RULE in block
    assert "EXACTLY 3 bullet points" not in block
    # The wizard's own block carries it too.
    assert "+ _CAND_DEPTH_RULE\n" in inspect.getsource(fa).replace("\r\n", "\n")
    for word in ("companies", "projects", "certifications", "never"):
        assert word in fa._CAND_DEPTH_RULE.lower()


class _Msg:
    def __init__(self, text):
        self.content = [type("B", (), {"text": text})()]


class _Client:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    @property
    def messages(self):
        outer = self

        class _M:
            def create(self, **kw):
                outer.calls.append(kw)
                return _Msg(outer.payload)
        return _M()


_RESUME = ("Senior Superintendent with 15 years on water and wastewater "
           "plants. Kiewit 2012-2018: $85M wastewater treatment plant "
           "expansion. PCL 2018-2024: $120M water reclamation facility. "
           "OSHA 30, Procore, P6. ") * 3


def test_enrich_replaces_bullets_from_the_real_resume(monkeypatch):
    import flowdrip_app as fa
    import ats
    monkeypatch.setattr(ats, "get_one", lambda tid: {
        "resume_text": _RESUME, "current_title": "Superintendent"})
    payload = json.dumps({"title": "Senior Superintendent", "bullets": [
        "Ran the $120M water reclamation facility for PCL",
        "Built Kiewit's $85M wastewater treatment plant expansion",
        "OSHA 30; runs schedules in P6 and Procore"]})
    client = _Client(payload)
    cards = [{"label": "Trent K.", "ref": "Ref #12", "_talent_id": 12,
              "role": "Superintendent", "bullets": ["Target role: Superintendent"]},
             {"label": "Candidate B", "role": "PM", "bullets": ["typed by hand"]}]
    out = fa._enrich_candidate_cards(client, cards, role="Superintendent")
    assert out[0]["bullets"][0] == "Ran the $120M water reclamation facility for PCL"
    assert out[0]["label"] == "Trent K." and out[0]["ref"] == "Ref #12"
    assert out[0]["_enriched"] is True
    assert out[1] == cards[1]                 # no record: untouched
    assert len(client.calls) == 1
    assert client.calls[0]["model"] == fa._CARD_ENRICH_MODEL
    # Enriched once; a second pass makes no AI call.
    fa._enrich_candidate_cards(client, out)
    assert len(client.calls) == 1


def test_enrich_keeps_card_when_resume_is_thin(monkeypatch):
    import flowdrip_app as fa
    import ats
    monkeypatch.setattr(ats, "get_one", lambda tid: {"resume_text": "short"})
    client = _Client("{}")
    cards = [{"label": "A", "_pool_id": "7", "bullets": ["keep me"]}]
    assert fa._enrich_candidate_cards(client, cards) == cards
    assert client.calls == []


def test_enrich_prompt_asks_for_depth_and_forbids_invention():
    import flowdrip_app as fa
    client = _Client(json.dumps({"title": "x", "bullets": ["a"]}))
    fa._ai_card_bullets_from_resume(client, _RESUME, role="Superintendent")
    prompt = client.calls[0]["messages"][0]["content"]
    for must in ("Name the companies", "projects", "certifications",
                 "Never invent", "most recent employer"):
        assert must in prompt


def test_generate_enriches_cards_before_the_block(monkeypatch):
    import flowdrip_app as fa
    seen = {}
    monkeypatch.setattr(fa, "_aicb_research_brief", lambda client, **kw: "brief")
    monkeypatch.setattr(fa.time, "sleep", lambda s: None)
    monkeypatch.setattr(fa, "_enrich_candidate_cards", lambda client, cards, role="": [
        dict(c, bullets=["Ran PCL's $120M water reclamation job"]) for c in cards])

    def _build(client, **kw):
        seen["block"] = kw["cand_block"]
        return {"emails": []}
    monkeypatch.setattr(fa, "_aicb_build_campaign_from_brief", _build)
    cards = [{"label": "Candidate A", "_talent_id": 3, "bullets": ["thin"]}]
    fa.generate_aicb_campaign(object(), camp_type="fivebythree",
                              candidate_cards=cards, roles=["Superintendent"])
    assert "Ran PCL's $120M water reclamation job" in seen["block"]
    assert cards[0]["bullets"] == ["Ran PCL's $120M water reclamation job"]


def test_slate_has_no_made_up_fill_cards():
    import flowdrip_app as fa
    pool = [{"id": "c1", "target_role": "PM", "resume_text": "x"}]
    cards = fa._build_slate_cards(pool, [{"id": "c1", "score": 90}], "PM")
    assert len(cards) == 1 and not cards[0].get("_synthetic")
