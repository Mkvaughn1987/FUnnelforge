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
    assert side.index('ui.label("Start with AI")') < side.index("fd-side-cta2")
    assert "_open_own_campaign(s, rf)" in side
    builder = inspect.getsource(fa.p_seq_builder)
    assert "_render_sb_step2_write" in builder and "_render_sb_step3_save" in builder
    assert "_render_sb_saved" in builder and "_render_sb_use" in builder
    # order, timing, words and candidates share one page
    write = inspect.getsource(fa._render_sb_step2_write)
    assert "sb-steps-list" in write and "_render_sb_cands_panel(s, rf" in write
    assert "Have AI draft it" in write and "Ask AI" not in write


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
