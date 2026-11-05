"""Create my own campaign (2026-11-04): the user's own steps become the
campaign, "My words" steps go out exactly as typed, only "AI polish" steps
are touched, and a saved own style launches the same way over the API/MCP."""
import inspect

import own_campaign as oc


def _steps():
    return [
        {"type": "email", "delay_days": 0, "subject": "Hi {FirstName}",
         "input": "Hi {FirstName}, I recruit CPAs.", "voice": "mine",
         "_drafting": False, "ai_prompt": "x"},
        {"type": "email", "delay_days": 3, "subject": "",
         "input": "Two people for {Company}:\n\n{Candidates}", "voice": "polish"},
        {"type": "call", "delay_days": 2, "input": "Call {FirstName}.", "voice": "mine"},
    ]


def _cards():
    return [{"label": "Travis K.", "ref": "Ref #1042", "role": "Senior Accountant",
             "bullets": ["Big 4 audit", "NetSuite rollout"]}]


# ── own_campaign.py ──────────────────────────────────────────────────────

def test_my_words_go_out_exactly_as_typed():
    calls = []
    out = oc.build_emails(_steps(), _cards(),
                          polish=lambda t, k: calls.append(t) or "POLISHED {Candidates}")
    assert out[0]["body"] == "Hi {FirstName}, I recruit CPAs."
    assert out[0]["subject"] == "Hi {FirstName}"
    assert out[2]["body"] == "Call {FirstName}."
    assert calls == ["Two people for {Company}:\n\n{Candidates}"]   # polish step only


def test_candidates_token_becomes_the_list_after_polish():
    out = oc.build_emails(_steps(), _cards(), polish=lambda t, k: "Tidy. {Candidates}")
    body = out[1]["body"]
    assert body.startswith("Tidy. ")
    assert "Travis K. (Ref #1042), Senior Accountant" in body
    assert "• Big 4 audit" in body
    assert "{Candidates}" not in body


def test_polish_that_drops_the_token_keeps_the_candidates():
    out = oc.build_emails(_steps(), _cards(), polish=lambda t, k: "No token here.")
    assert "Travis K. (Ref #1042)" in out[1]["body"]


def test_polish_failure_sends_the_users_own_text():
    def boom(t, k):
        raise RuntimeError("credit balance is too low")
    out = oc.build_emails(_steps(), _cards(), polish=boom)
    assert out[1]["body"].startswith("Two people for {Company}:")
    assert "Travis K." in out[1]["body"]


def test_no_polish_function_means_users_text():
    out = oc.build_emails(_steps(), [], polish=None)
    assert out[1]["body"] == "Two people for {Company}:"


def test_followup_subject_threads_and_step_shape():
    out = oc.build_emails(_steps(), [])
    assert out[1]["subject"] == "Re: Hi {FirstName}"
    assert [e["step_type"] for e in out] == ["email_auto", "email_auto", "call"]
    assert [e["delay_days"] for e in out] == [0, 3, 2]
    assert [e["name"] for e in out] == ["Email 1", "Email 2", "Call 1"]
    assert out[2]["subject"] == ""


def test_style_steps_drop_working_fields_and_default_voice():
    saved = oc.style_steps(_steps() + [{"type": "linkedin", "input": "hi"}])
    assert set(saved[0]) == {"type", "delay_days", "subject", "input", "voice"}
    assert saved[3]["voice"] == "mine"
    assert saved[0]["delay_days"] == 0


def test_missing_content_needs_body_and_first_subject():
    st = _steps()
    assert oc.missing_content(st) == []
    st[0]["subject"] = ""
    st[2]["input"] = " "
    assert oc.missing_content(st) == [1, 3]


def test_first_email_index_prefers_the_first_followup():
    assert oc.first_email_index(_steps()) == 1
    assert oc.first_email_index([{"type": "call"}, {"type": "email"}]) == 1
    assert oc.first_email_index([{"type": "call"}]) is None


def test_polish_prompt_keeps_merge_fields():
    p = oc.polish_prompt("Hi {FirstName}", "email", "direct")
    assert "{Candidates}" in p and "{FirstName}" in p and "direct" in p


# ── flowdrip_app wiring ──────────────────────────────────────────────────

def test_save_style_keeps_steps_and_replaces_by_name(monkeypatch):
    import flowdrip_app as fa
    store = [{"id": "old1", "name": "Other", "description": "d"}]
    monkeypatch.setattr(fa, "_load_my_campaign_styles", lambda: [dict(x) for x in store])
    monkeypatch.setattr(fa, "_save_my_campaign_styles",
                        lambda rows: store.__setitem__(slice(None), rows))
    sid = fa._own_save_style("CPA Outreach", _steps(), "direct")
    row = next(r for r in store if r["id"] == sid)
    assert row["kind"] == "own" and row["tone"] == "direct"
    assert row["steps"][0]["input"] == "Hi {FirstName}, I recruit CPAs."
    assert "Subject: Hi {FirstName}" in row["description"]
    sid2 = fa._own_save_style("CPA Outreach", _steps()[:1], "direct")
    assert sid2 == sid and len(store) == 2
    assert len(next(r for r in store if r["id"] == sid)["steps"]) == 1


def _api(monkeypatch, style):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *_: None)
    monkeypatch.setattr(fa, "_load_my_campaign_styles", lambda: [style])
    monkeypatch.setattr(fa, "_link_candidate_cards", lambda c, o, strict=True: (c, None))
    monkeypatch.setattr(fa, "_enrich_candidate_cards", lambda cl, c, role="": c)
    monkeypatch.setattr(fa, "_own_polish_text", lambda t, k, tone="", client=None: "P " + t)
    return fa


def test_api_style_id_on_own_style_sends_its_own_steps(monkeypatch):
    style = {"id": "s1", "name": "CPA Outreach", "description": "d",
             "kind": "own", "tone": "", "steps": oc.style_steps(_steps())}
    fa = _api(monkeypatch, style)
    def no_ai(*a, **k):
        raise AssertionError("own style must not be rewritten by the AI")
    monkeypatch.setattr(fa, "generate_aicb_campaign", no_ai)
    res = fa._api_create_campaign_blocking(
        object(), {"template": "byos", "style_id": "s1", "candidates": _cards()},
        "a@b.com")
    assert res["template"] == "byos"
    emails = res["emails"]
    assert emails[0]["body"] == "Hi {FirstName}, I recruit CPAs."
    assert emails[1]["body"].startswith("P Two people for {Company}:")
    assert "Travis K. (Ref #1042)" in emails[1]["body"]
    assert res["campaign_data"]["campaign_name"] == "CPA Outreach"


def test_api_style_id_on_old_style_still_uses_the_ai(monkeypatch):
    fa = _api(monkeypatch, {"id": "s2", "name": "Old", "description": "warm intro"})
    seen = {}
    def fake_gen(client, **kw):
        seen.update(kw)
        return {"emails": [{"subject": "s", "body": "b"}]}
    monkeypatch.setattr(fa, "generate_aicb_campaign", fake_gen)
    res = fa._api_create_campaign_blocking(
        object(), {"template": "byos", "style_id": "s2", "company": "Acme"}, "a@b.com")
    assert seen["byos_desc"] == "warm intro"
    assert res["emails"][0]["body"] == "b"


def test_style_id_makes_company_optional():
    import flowdrip_app as fa
    assert fa._validate_campaign_spec({"template": "byos", "style_id": "s1"}) is None
    assert "company" in fa._validate_campaign_spec({"template": "byos"})


def test_walkthrough_state_and_entry_points():
    import flowdrip_app as fa
    s = fa.AppState()
    assert s.sb_cands == [] and s.sb_building is False and s.sb_built_camp == {}
    assert fa.CHOOSER_OPTIONS[0]["key"] == "scratch"
    assert fa.CHOOSER_OPTIONS[0]["title"] == fa.OWN_CAMPAIGN_TITLE
    side = inspect.getsource(fa._sidebar_v2)
    # one Start a Campaign button; its dialog offers both ways in, AI first
    assert "ui.label(START_CAMPAIGN_TITLE)" in side
    assert "_start_campaign_dialog(s, rf, _setup)" in side
    assert "fd-side-cta2" not in side and 'ui.label("Start with AI")' not in side
    assert fa.START_CAMPAIGN_TITLE == "Start a Campaign"
    assert [o["key"] for o in fa.START_CAMPAIGN_OPTIONS] == ["ai", "own"]
    assert fa.START_CAMPAIGN_OPTIONS[0]["tag"] == "Recommended"
    assert fa.START_CAMPAIGN_OPTIONS[1]["title"] == fa.OWN_CAMPAIGN_TITLE
    dlg = inspect.getsource(fa._start_campaign_dialog)
    assert '_sidebar_nav(s, rf, "ai_prompts", setup)' in dlg
    assert "_open_own_campaign(s, rf)" in dlg
    builder = inspect.getsource(fa.p_seq_builder)
    assert "_render_sb_start(s, rf)" in builder and "_render_sb_step_page(s, rf)" in builder
    assert "_render_sb_step3_save" in builder and "_render_sb_use" in builder
    # it opens on "Start campaign", never "Write your campaign"
    assert '"1. Start campaign"' in builder
    assert "Write your campaign" not in inspect.getsource(fa)
    start = inspect.getsource(fa._render_sb_start)
    assert '"Start campaign"' in start and "What should the first step be?" in start
    assert "_render_sb_saved(s, rf)" in start
    assert [c[0] for c in fa._SB_START_CARDS] == ["email", "call", "linkedin"]
    # one step per screen, each explained, with exactly two AI options
    page = inspect.getsource(fa._render_sb_step_page)
    assert "_SB_STEP_ABOUT[" in page and set(fa._SB_STEP_ABOUT) == {
        "email_first", "email", "call", "linkedin"}
    assert "Tell AI what you want" in page and "Polish with AI" in page
    assert "Have AI draft it" not in page and "Ask AI" not in page
    assert "What comes next?" in page and "_render_sb_cands(s, rf, step_id=_sid)" in page
    # a fill-in is asked for on the step that uses it
    assert "_draw_fills()" in page and "_own_fillin_ask(_n)" in page
    assert fa._own_fillin_ask("Competitors") == "Which competitors do you want to name?"
    assert "Client tier" in fa._own_fillin_ask("ClientTier")
    # reordering is plain buttons: the site CSP blocks CDN scripts
    assert "_move(" in page and "Sortable" not in inspect.getsource(fa)
    # one button adds candidates from the Pipeline; the summary is a choice
    cands = inspect.getsource(fa._render_sb_cands)
    assert "＋ Add candidates" in cands and '" from Pipeline"' in cands
    assert "Include a 3-bullet summary of each candidate" in cands
    assert s.sb_cand_bullets is True and s.sb_cand_open is False and s.sb_cur == 0


def test_build_hands_off_to_choose_contacts():
    import flowdrip_app as fa
    src = inspect.getsource(fa._sb_start_build)
    assert 's.loaded_view = "contacts"' in src
    save = inspect.getsource(fa._render_sb_step3_save)
    assert "_own_save_style(" in save and "Save this campaign" in save
    assert "_sb_start_build(" in save
    worker = inspect.getsource(fa._own_build_worker)
    assert "save_campaign(camp)" in worker and "_own_unique_camp_name(name)" in worker
    assert "_link_candidate_cards(cards, owner, strict=False)" in worker


def test_ai_prompts_card_only_on_dripdrop():
    import staffing_prompts
    import tm_prompts
    assert callable(staffing_prompts.STAFFING.own_campaign)
    assert tm_prompts.TM.own_campaign is None


# ── Fill-ins (2026-11-04): reusable across clients and industries ────────

def _generic():
    return [
        {"type": "email", "delay_days": 0, "subject": "{Industry} talent, {FirstName}",
         "input": "Hi {FirstName}, I place {Role} people with {Competitors}.\n\n{Candidates}"},
        {"type": "call", "delay_days": 2, "input": "Mention {CurrentClients} to {Company}."},
    ]


def test_fillins_are_the_non_merge_tokens_in_order():
    assert oc.fillins(_generic()) == ["Industry", "Role", "Competitors", "CurrentClients"]
    assert oc.fillins(_steps()) == []
    assert oc.fillin_label("CurrentClients") == "Current clients"


def test_fill_writes_values_and_leaves_merge_fields():
    out = oc.fill(_generic(), {"Industry": "HVAC", "Role": "estimator",
                               "Competitors": "Trane and Carrier",
                               "FirstName": "nope", "Candidates": "nope"})
    assert out[0]["subject"] == "HVAC talent, {FirstName}"
    assert "I place estimator people with Trane and Carrier." in out[0]["input"]
    assert "{Candidates}" in out[0]["input"] and "{CurrentClients}" in out[1]["input"]
    assert oc.missing_fillins(_generic(), {"Industry": "HVAC"}) == [
        "Role", "Competitors", "CurrentClients"]
    assert _generic()[0]["subject"].startswith("{Industry}")  # input untouched


def test_parse_detected_keeps_only_phrases_really_in_the_steps():
    steps = [{"type": "email", "subject": "HVAC hiring",
              "input": "Hi John, I work with Trane and Carrier in HVAC. {Industry}"}]
    raw = ('Here you go: [{"text": "HVAC", "name": "industry"},'
           '{"text": "Trane and Carrier", "name": "Competitors"},'
           '{"text": "Boeing", "name": "CurrentClients"},'
           '{"text": "HVAC", "name": "Industry"},'
           '{"text": "Industry", "name": "Industry"},'
           '{"text": "John", "name": "first name"}]')
    found = oc.parse_detected(raw, steps)
    assert found == [{"text": "HVAC", "name": "Industry"},
                     {"text": "Trane and Carrier", "name": "Competitors"},
                     {"text": "John", "name": "FirstName"}]
    assert oc.parse_detected("not json", steps) == []


def test_apply_detected_swaps_whole_words_and_spares_tokens():
    steps = [{"type": "email", "subject": "HVAC hiring",
              "input": "HVACR is not HVAC. Trane and Carrier, then Trane. {HVAC}"}]
    out = oc.apply_detected(steps, [{"text": "HVAC", "name": "Industry"},
                                    {"text": "Trane", "name": "Client"},
                                    {"text": "Trane and Carrier", "name": "Competitors"},
                                    {"text": "Industry", "name": "Oops"}])
    assert out[0]["subject"] == "{Industry} hiring"
    assert out[0]["input"] == ("HVACR is not {Industry}. {Competitors}, "
                               "then {Client}. {HVAC}")
    assert oc.style_fillins(out, {"Industry": "HVAC"})[0] == {
        "name": "Industry", "label": "Industry", "last": "HVAC"}


def test_detect_prompt_and_draft_rules_name_the_fillins():
    p = oc.detect_prompt(_steps())
    assert "I recruit CPAs." in p and "CurrentClients" in p and "EXACTLY" in p
    assert "{Competitors}" in oc.draft_rules() and "{Candidates}" in oc.draft_rules()


def test_saved_style_lists_its_fillins_and_keeps_last_values(monkeypatch):
    import flowdrip_app as fa
    store = []
    monkeypatch.setattr(fa, "_load_my_campaign_styles", lambda: [dict(x) for x in store])
    monkeypatch.setattr(fa, "_save_my_campaign_styles",
                        lambda rows: store.__setitem__(slice(None), rows))
    sid = fa._own_save_style("Intro", _generic(), "direct",
                             values={"Industry": "HVAC", "Role": "estimators"})
    row = store[0]
    assert [f["name"] for f in row["fillins"]] == [
        "Industry", "Role", "Competitors", "CurrentClients"]
    assert row["fillins"][0]["last"] == "HVAC" and row["fillins"][2]["last"] == ""
    # editing under a new name replaces the same row and keeps old hints
    sid2 = fa._own_save_style("Intro v2", _generic()[:1], "direct",
                              values={"Role": "PMs"}, replace_id=sid)
    assert sid2 == sid and len(store) == 1 and store[0]["name"] == "Intro v2"
    assert {f["name"]: f["last"] for f in store[0]["fillins"]} == {
        "Industry": "HVAC", "Role": "PMs", "Competitors": ""}
    fa._own_remember_values(sid, {"Competitors": "Trane"})
    assert store[0]["fillins"][2]["last"] == "Trane"
    assert [r["id"] for r in fa._own_styles()] == [sid]


def test_api_own_style_asks_for_fillins_then_writes_them_in(monkeypatch):
    style = {"id": "s3", "name": "Intro", "description": "d", "kind": "own",
             "tone": "", "steps": oc.style_steps(_generic())}
    fa = _api(monkeypatch, style)
    spec = {"template": "byos", "style_id": "s3", "candidates": _cards()}
    res = fa._api_create_campaign_blocking(object(), dict(spec), "a@b.com")
    assert res["status"] == 400
    assert "Industry, Role, Competitors, CurrentClients" in res["error"]
    res = fa._api_create_campaign_blocking(object(), dict(
        spec, fill_ins={"Industry": "HVAC", "Role": "estimator",
                        "Competitors": "Trane", "CurrentClients": "two GCs"}), "a@b.com")
    emails = res["emails"]
    assert emails[0]["subject"] == "HVAC talent, {FirstName}"
    assert "I place estimator people with Trane." in emails[0]["body"]
    assert "Travis K. (Ref #1042)" in emails[0]["body"]
    assert emails[1]["body"] == "Mention two GCs to {Company}."


def test_detected_fillins_only_keep_real_phrases(monkeypatch):
    import flowdrip_app as fa

    class _Msg:
        content = [type("B", (), {"text": '[{"text": "CPAs", "name": "Role"}, '
                                          '{"text": "plumbers", "name": "Role"}]'})()]
    monkeypatch.setattr(fa, "_claude_create_with_retry", lambda *a, **k: _Msg())
    found = fa._own_detect_fillins(_steps(), client=object())
    assert found == [{"text": "CPAs", "name": "Role"}]
    out = oc.apply_detected(_steps(), found)
    assert out[0]["input"] == "Hi {FirstName}, I recruit {Role}."


def test_second_run_of_a_saved_campaign_gets_its_own_name(monkeypatch):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "load_campaigns",
                        lambda: [{"name": "Intro"}, {"name": "intro 2"}])
    assert fa._own_unique_camp_name("Intro") == "Intro 3"
    assert fa._own_unique_camp_name("Fresh") == "Fresh"


def test_a_cut_off_scan_is_a_failure_not_an_all_clear(monkeypatch):
    import pytest
    import flowdrip_app as fa

    class _Cut:
        stop_reason = "max_tokens"
        content = [type("B", (), {"text": '[{"text": "CPAs", "na'})()]

    class _Silent:
        stop_reason = "max_tokens"
        content = []
    seen = {}

    def _create(client, **kw):
        seen.update(kw)
        return _Cut()
    monkeypatch.setattr(fa, "_claude_create_with_retry", _create)
    with pytest.raises(RuntimeError):
        fa._own_detect_fillins(_steps(), client=object())
    assert seen["max_tokens"] >= 4000      # room for the model to think first
    monkeypatch.setattr(fa, "_claude_create_with_retry", lambda *a, **k: _Silent())
    with pytest.raises(RuntimeError):
        fa._own_detect_fillins(_steps(), client=object())
    import inspect
    save = inspect.getsource(fa._render_sb_step3_save)
    assert "sb_find_err" in save and "Look again" in save


def test_two_different_details_never_share_a_fillin():
    steps = [{"type": "email", "subject": "HVAC talent",
              "input": "We place accountants and controllers with commercial "
                       "HVAC firms. John, meet Johnny."}]
    raw = ('[{"text": "accountants", "name": "Role"},'
           '{"text": "controllers", "name": "Role"},'
           '{"text": "HVAC", "name": "Industry"},'
           '{"text": "commercial HVAC", "name": "Industry"},'
           '{"text": "John", "name": "FirstName"},'
           '{"text": "Johnny", "name": "FirstName"}]')
    found = oc.parse_detected(raw, steps)
    assert [(f["text"], f["name"]) for f in found] == [
        ("accountants", "Role"), ("controllers", "Role2"),
        ("HVAC", "Industry"), ("commercial HVAC", "Industry"),
        ("John", "FirstName"), ("Johnny", "FirstName")]
    out = oc.apply_detected(steps, found)
    assert out[0]["input"] == ("We place {Role} and {Role2} with {Industry} "
                               "firms. {FirstName}, meet {FirstName}.")
    assert oc.fillin_label("Role2") == "Role 2"
    assert oc.fillin_label("CurrentClients") == "Current clients"


# ── One step per screen (2026-11-04): candidates summary, problems, PDFs ──

def test_candidate_summary_is_three_bullets_or_none():
    cards = [{"label": "Travis K.", "ref": "Ref #1042", "role": "Senior Accountant",
              "bullets": ["one", "two", "three", "four"]}]
    on = oc.candidate_block(cards)
    assert on.count("•") == 3 and "four" not in on
    assert oc.candidate_block(cards, bullets=False) == (
        "Travis K. (Ref #1042), Senior Accountant")
    out = oc.build_emails(_steps(), cards, cand_bullets=False)
    assert "Travis K. (Ref #1042), Senior Accountant" in out[1]["body"]
    assert "•" not in out[1]["body"]


def test_step_problem_says_what_one_step_still_needs():
    st = [{"type": "call", "input": "Call {FirstName} about {Competitors}."},
          {"type": "email", "subject": "", "input": "Hi"},
          {"type": "email", "subject": "", "input": ""}]
    assert oc.step_names(st) == ["Call 1", "Email 1", "Email 2"]
    assert oc.step_problem(st, 0) == ("fillin", "Competitors")
    assert oc.step_problem(st, 0, {"Competitors": "Trane"}) is None
    assert oc.step_problem(st, 1) == "subject"      # the first email
    assert oc.step_problem(st, 2) == "body"
    st[2]["input"] = "Following up."
    assert oc.step_problem(st, 2) is None           # later emails thread


def _with_pdf():
    st = _steps()
    st[0]["pdf"] = "salary_guide"      # the first email never carries one
    st[1]["pdf"] = "salary_guide"
    st[2]["pdf"] = "market_pulse"      # a call cannot carry one
    return st + [{"type": "email", "input": "Last one.", "pdf": "not_a_kind"}]


def test_a_pdf_rides_on_any_email_but_the_first():
    st = _with_pdf()
    assert oc.pdf_plan(st) == [(1, "salary_guide")]
    assert list(oc.PDF_KINDS) == ["market_pulse", "interview_guide", "salary_guide",
                                  "scorecard", "why_staffing"]
    saved = oc.style_steps(st)
    assert [x.get("pdf") for x in saved] == [None, "salary_guide", None, None]
    # the PDF is written about a role, a place and an industry: asked like
    # any other fill-in, on the step that carries it
    assert oc.fillins(st) == ["Role", "Location", "Industry"]
    assert oc.fillins(_steps()) == []
    assert oc.step_fillins(st, 1) == ["Role", "Location", "Industry"]
    assert oc.step_fillins(st, 0) == []
    assert oc.step_problem(st, 1, {"Role": "CPAs"}) == ("fillin", "Location")


def test_pdfs_are_built_once_per_kind_and_attached(monkeypatch):
    import flowdrip_app as fa
    st = _with_pdf()
    st[3]["pdf"] = "salary_guide"
    st.append({"type": "email", "input": "PS", "pdf": "scorecard"})
    emails = oc.build_emails(st, [])
    seen = []

    def fake(client, kind, values, owner_email=""):
        seen.append((kind, values["Role"], owner_email))
        if kind == "scorecard":
            raise RuntimeError("no credit")
        return f"{kind}.pdf"
    monkeypatch.setattr(fa, "_own_build_pdf", fake)
    missed = fa._own_attach_pdfs(emails, st, {"Role": "CPAs"}, object(), "a@b.com")
    assert seen == [("salary_guide", "CPAs", "a@b.com"), ("scorecard", "CPAs", "a@b.com")]
    assert [e["attachments"] for e in emails] == [
        [], ["salary_guide.pdf"], [], ["salary_guide.pdf"], []]
    assert missed == ["Email 4: Role Scorecard"]
    assert [c[0] for c in fa._OWN_PDF_CARDS] == list(oc.PDF_KINDS)
    page = inspect.getsource(fa._render_sb_step_page)
    assert "if _first_email:" in page and "_render_sb_pdf(s, rf, _st)" in page
    worker = inspect.getsource(fa._own_build_worker)
    assert "_own_attach_pdfs(emails, steps, values, client, owner)" in worker
    assert "if bullets:" in worker


def test_api_own_style_with_a_pdf_asks_what_it_covers(monkeypatch):
    style = {"id": "s4", "name": "Guide", "description": "d", "kind": "own",
             "tone": "", "cand_bullets": False, "steps": oc.style_steps(_with_pdf())}
    fa = _api(monkeypatch, style)
    built = []
    monkeypatch.setattr(fa, "_own_build_pdf",
                        lambda client, kind, values, owner_email="":
                        built.append(dict(values)) or "Salary_Guide_CPAs_Denver.pdf")
    def no_enrich(*a, **k):
        raise AssertionError("no summary wanted, so no résumé mining")
    monkeypatch.setattr(fa, "_enrich_candidate_cards", no_enrich)
    spec = {"template": "byos", "style_id": "s4", "candidates": _cards()}
    res = fa._api_create_campaign_blocking(object(), dict(spec), "a@b.com")
    assert res["status"] == 400 and "Role, Location, Industry" in res["error"]
    given = {"Role": "CPAs", "Location": "Denver", "Industry": "accounting"}
    res = fa._api_create_campaign_blocking(object(), dict(spec, fill_ins=given), "a@b.com")
    emails = res["emails"]
    assert emails[0]["attachments"] == []
    assert emails[1]["attachments"] == ["Salary_Guide_CPAs_Denver.pdf"]
    assert built == [given]
    assert "Travis K. (Ref #1042), Senior Accountant" in emails[1]["body"]
    assert "Big 4 audit" not in emails[1]["body"]


def test_saved_style_remembers_the_summary_choice(monkeypatch):
    import flowdrip_app as fa
    store = []
    monkeypatch.setattr(fa, "_load_my_campaign_styles", lambda: [dict(x) for x in store])
    monkeypatch.setattr(fa, "_save_my_campaign_styles",
                        lambda rows: store.__setitem__(slice(None), rows))
    fa._own_save_style("A", _steps(), "direct")
    fa._own_save_style("B", _with_pdf(), "direct", cand_bullets=False)
    assert [r["cand_bullets"] for r in store] == [True, False]
    assert store[1]["steps"][1]["pdf"] == "salary_guide"
    assert [f["name"] for f in store[1]["fillins"]] == ["Role", "Location", "Industry"]
    edit = inspect.getsource(fa._sb_open_edit)
    assert 'pdf=st.get("pdf")' in edit and "s.sb_cand_bullets" in edit
