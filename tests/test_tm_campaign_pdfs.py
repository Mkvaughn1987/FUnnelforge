"""ThriveModal campaigns: the PDFs a campaign carries (the Sales Assets set,
one or two from the top three), where each lands in the sequence, the
refresh of saved campaigns, and the type lineup."""
import flowdrip_app as fa


def _campaign(camp_type):
    emails = []
    for n in sorted(fa._TM_STEP_SHAPE[camp_type]):
        _d, st = fa._TM_STEP_SHAPE[camp_type][n]
        emails.append({"name": f"Step {n} - x", "subject": "s",
                       "body": "Hi {FirstName},<br><br>Body.",
                       "step_type": st})
    return {"emails": emails}


# ── the PDFs ───────────────────────────────────────────────────────────────

def test_campaigns_offer_the_sales_assets_set_top_three_first():
    kinds = [k for k, *_ in fa._TM_CAMPAIGN_PDF_KINDS]
    assert kinds[:3] == ["tm_role_blueprint", "tm_cost_compare", "tm_how_it_works"]
    assert set(kinds) == {"tm_role_blueprint", "tm_cost_compare",
                          "tm_how_it_works", "interview_guide", "market_pulse"}
    for _k, _label, line in fa._TM_CAMPAIGN_PDF_KINDS:
        assert line.startswith("I've attached")


def test_old_arena_and_static_kinds_are_not_offered():
    kinds = {k for k, *_ in fa._TM_CAMPAIGN_PDF_KINDS}
    assert not kinds & {"salary_guide", "scorecard", "tenure_snapshot",
                        "tm_role_cost", "tm_logistics", "tm_twelve_questions"}


def test_clamp_keeps_two_of_the_top_three_and_drops_the_rest():
    assert fa._clamp_tm_pdf_kinds(
        ["market_pulse", "bogus", "interview_guide", "tm_cost_compare",
         "tm_cost_compare", "tm_how_it_works", "tm_role_blueprint"]) == [
        "tm_cost_compare", "tm_how_it_works"]
    assert fa._clamp_tm_pdf_kinds(None) == []
    assert fa.TM_CAMPAIGN_PDF_MIN == 1 and fa.TM_CAMPAIGN_PDF_MAX == 2
    assert fa._TM_CAMPAIGN_PDF_OFFERED == tuple(
        k for k, *_ in fa._TM_CAMPAIGN_PDF_KINDS[:3])


def test_default_is_the_types_pair_and_one_on_quick_intro():
    assert fa._tm_resolve_pdf_pick(None, "tm_threebythree") == ["tm_cost_compare"]
    assert fa._tm_resolve_pdf_pick(None, "tm_twelveweek") == [
        "tm_role_blueprint", "tm_cost_compare"]
    assert fa._tm_resolve_pdf_pick(None, "tm_stay_in_touch") == [
        "tm_cost_compare", "tm_how_it_works"]
    # An explicit pick of the top three wins.
    assert fa._tm_resolve_pdf_pick(["tm_how_it_works"], "tm_twelveweek") == [
        "tm_how_it_works"]
    # Never zero: an empty pick, or one holding only kinds campaigns no longer
    # offer, gets the default.
    assert fa._tm_resolve_pdf_pick([], "tm_twelveweek") == [
        "tm_role_blueprint", "tm_cost_compare"]
    assert fa._tm_resolve_pdf_pick(["market_pulse"], "tm_twelveweek") == [
        "tm_role_blueprint", "tm_cost_compare"]
    assert fa._tm_resolve_pdf_pick(["tm_logistics"], "tm_threebythree") == [
        "tm_cost_compare"]


def test_every_offered_type_places_its_default_never_first_or_call():
    for ct in fa._TM_OFFERED_TYPE_KEYS:
        camp = _campaign(ct)
        kinds = fa._tm_default_pdf_kinds(ct, camp["emails"])
        assert 1 <= len(kinds) <= 2, ct
        assert set(kinds) <= set(fa._TM_CAMPAIGN_PDF_OFFERED), ct
        placed = fa._tm_pdf_placement(ct, camp["emails"], kinds)
        assert len(placed) == min(len(kinds), len(
            fa._tm_pdf_eligible_emails(camp["emails"]))), ct
        assert len(set(placed.values())) == len(placed)
        for i in placed.values():
            assert i > 0
            assert camp["emails"][i]["step_type"] in ("email_auto", "email")


def test_pdf_lands_on_the_step_that_talks_about_it():
    names = ["Step 1 - Capacity", "Step 2 - What the role would cost",
             "Step 3 - Follow-up Call", "Step 4 - What actually transfers",
             "Step 5 - Control and commitment", "Step 6 - Close the loop"]
    emails = [{"name": n, "subject": "", "body": "Hi {FirstName},<br><br>x",
               "step_type": "call" if "Call" in n else "email_auto"}
              for n in names]
    placed = fa._tm_pdf_placement(
        "x", emails, ["tm_role_blueprint", "tm_cost_compare"])
    assert {k: emails[i]["name"] for k, i in placed.items()} == {
        "tm_cost_compare": "Step 2 - What the role would cost",
        "tm_role_blueprint": "Step 4 - What actually transfers"}
    placed = fa._tm_pdf_placement("x", emails, ["tm_how_it_works"])
    assert {k: emails[i]["name"] for k, i in placed.items()} == {
        "tm_how_it_works": "Step 5 - Control and commitment"}


def test_attach_adds_file_and_line_only_where_placed():
    camp = _campaign("tm_conversation")
    n = fa._tm_attach_campaign_pdfs(
        "tm_conversation", camp, {"tm_how_it_works": "How_We_Work_Together_X.pdf"})
    assert n == 1
    carrying = [e for e in camp["emails"] if e.get("attachments")]
    assert len(carrying) == 1 and carrying[0] is not camp["emails"][0]
    assert carrying[0]["body"].startswith("Hi {FirstName},<br><br>I've attached")
    # The unbacked-promise scrub keeps the line because the file is attached.
    assert "attached" in fa._tm_drop_unbacked_lines(carrying[0]["body"], True)


def test_nothing_built_attaches_nothing():
    camp = _campaign("tm_conversation")
    assert fa._tm_attach_campaign_pdfs("tm_conversation", camp, {}) == 0
    assert not any(e.get("attachments") for e in camp["emails"])
    assert fa._tm_attach_campaign_pdfs(
        "tm_fivebyseven", _campaign("tm_fivebyseven"), {"tm_cost_compare": ""}) == 0


def test_refresh_replaces_old_pdfs_and_is_rerunnable():
    camp = _campaign("tm_fivebyseven")
    camp["aicb_camp_type"] = "tm_fivebyseven"
    later = fa._tm_pdf_eligible_emails(camp["emails"])
    camp["emails"][later[0]]["attachments"] = ["Salary_Guide_Construction.pdf"]
    camp["emails"][later[1]]["attachments"] = ["my_upload.docx"]
    calls = []

    def fake_build(kinds, company, role, location, industry="", client=None):
        calls.append((tuple(kinds), company, role, location))
        return {k: fa._tm_campaign_pdf_filename(k, role) for k in kinds}

    for _ in range(2):
        out = fa._tm_refresh_campaign_pdfs(camp, "", "Estimator", "Denver, CO",
                                           build=fake_build)
    assert calls[-1] == (("tm_role_blueprint", "tm_cost_compare"), "",
                         "Estimator", "Denver, CO")
    atts = [a for e in camp["emails"] for a in (e.get("attachments") or [])]
    assert "Salary_Guide_Construction.pdf" not in atts
    assert "my_upload.docx" in atts  # a hand upload is never touched
    assert sorted(a for a in atts if a.endswith(".pdf")) == [
        "Offshore Role Blueprint Estimator.pdf",
        "Staffing Cost Comparison Estimator.pdf"]
    assert out["attached"] == 2
    assert not camp["emails"][0].get("attachments")
    # Running twice does not stack the "I've attached" line.
    bodies = " ".join(e["body"] for e in camp["emails"])
    assert bodies.count("I've attached") == 2


def test_thrivemodal_workspace_never_builds_the_old_arena_pdfs():
    """Custom Build and Fast Sprint on a ThriveModal workspace used to fall
    through to Market Pulse / Salary Guide. The gate is the playbook now."""
    src = open(fa.__file__, encoding="utf-8").read()
    assert ('_tm_campaign = ((s.aicb_camp_type or "").strip() in _TM_TYPE_KEYS\n'
            '                                    or _workspace_playbook() == '
            'PLAYBOOK_THRIVEMODAL)') in src.replace("\r\n", "\n")


# ── the lineup ─────────────────────────────────────────────────────────────

def test_offered_lineup():
    assert fa._TM_OFFERED_TYPE_KEYS == {
        "tm_fivebyseven", "tm_threebythree", "tm_conversation",
        "tm_hiring_signal", "tm_twelveweek", "tm_stay_in_touch",
        "tm_reengage", "tm_meeting_followup"}
    assert fa._TM_HIDDEN_TYPE_KEYS == {"tm_grow_client", "tm_fivethreeli"}
    for k in fa._TM_HIDDEN_TYPE_KEYS:
        assert k in {t[0] for t in fa.AICB_CAMPAIGN_TYPES}  # still registered
        assert not fa._type_visible(k, fa.PLAYBOOK_THRIVEMODAL)
    chooser = [o["key"] for o in fa.TM_CHOOSER_OPTIONS]
    assert not set(chooser) & fa._TM_HIDDEN_TYPE_KEYS
    assert set(fa._TM_OFFERED_TYPE_KEYS) <= set(chooser)
    # Saved Campaigns has its own sidebar row; the chooser does not repeat it.
    assert "saved" not in chooser and chooser[-1] == "scratch"


def test_names_say_the_situation_not_the_step_count():
    names = {t[0]: t[1] for t in fa.AICB_CAMPAIGN_TYPES}
    assert {k: names[k] for k in fa._TM_OFFERED_TYPE_KEYS} == {
        "tm_fivebyseven": "Standard Outreach",
        "tm_threebythree": "Quick Intro",
        "tm_conversation": "Priority Account Push",
        "tm_hiring_signal": "They're Hiring",
        "tm_twelveweek": "Top 25 Accounts",
        "tm_stay_in_touch": "Stay on Their Radar",
        "tm_reengage": "Revive Old Leads",
        "tm_meeting_followup": "After the Call",
    }
    cards = {o["key"]: o["title"] for o in fa.TM_CHOOSER_OPTIONS}
    for k in fa._TM_OFFERED_TYPE_KEYS:
        assert cards[k] == names[k], k
    assert cards["scratch"] == "Build Your Own"
    assert [o["key"] for o in fa.TM_CHOOSER_OPTIONS
            if o.get("recommended")] == ["tm_fivebyseven"]
    for o in fa.TM_CHOOSER_OPTIONS:
        assert o["use_when"] and o["group"] in {g for g, _ in fa._TM_CHOOSER_GROUPS}


def _shape_counts(key):
    kinds = [st for _d, st in fa._TM_STEP_SHAPE[key].values()]
    return (kinds.count(fa.ST.EMAIL_AUTO), kinds.count(fa.ST.CALL),
            kinds.count(fa.ST.LINKEDIN))


def test_new_shapes_match_what_was_asked_for():
    # Standard Outreach went to 7 emails (Mike, 2026-09-21), 22 business days.
    assert _shape_counts("tm_fivebyseven") == (7, 2, 1)
    assert _shape_counts("tm_threebythree") == (3, 0, 0)
    assert _shape_counts("tm_fivethreeli") == (5, 3, 1)
    assert _shape_counts("tm_stay_in_touch") == (5, 1, 0)
    # Quick Intro lands on days 0, 3 and 7.
    assert sum(d for d, _ in fa._TM_STEP_SHAPE["tm_fivebyseven"].values()) == 22
    assert sum(d for d, _ in fa._TM_STEP_SHAPE["tm_fivethreeli"].values()) == 15
    assert [d for _n, (d, _st) in sorted(
        fa._TM_STEP_SHAPE["tm_threebythree"].items())] == [0, 3, 4]
    assert round(sum(d for d, _ in fa._TM_STEP_SHAPE[
        "tm_stay_in_touch"].values()) / 5) == 12


def test_stay_on_their_radar_is_cold_unless_the_brief_says_otherwise():
    t = {x[0]: x for x in fa.AICB_CAMPAIGN_TYPES}["tm_stay_in_touch"]
    assert t[1] == "Stay on Their Radar"
    assert "cold first touch" in t[6]
    assert "unless the BRIEF says they already received outreach" in t[6]


def test_card_summary_and_week_strip_come_from_the_shape():
    assert fa._tm_shape_summary("tm_fivebyseven") == (
        "7 emails · 2 calls · 1 LinkedIn · about 4 weeks")
    assert fa._tm_shape_summary("tm_threebythree") == (
        "3 emails only · about 2 weeks")
    E, C_, L = fa.ST.EMAIL_AUTO, fa.ST.CALL, fa.ST.LINKEDIN
    assert fa._tm_shape_weeks("tm_threebythree") == [[E, E], [E]]
    assert fa._tm_shape_weeks("tm_fivebyseven") == [
        [E, E, C_, L], [E, E], [E, C_], [E, E]]
    for k in fa._TM_OFFERED_TYPE_KEYS:
        weeks = fa._tm_shape_weeks(k)
        assert len(weeks) == fa._tm_type_weeks(k), k
        assert sum(len(w) for w in weeks) == len(fa._TM_STEP_SHAPE[k]), k


def test_help_me_choose_answers_all_lead_to_offered_types():
    reached = set()
    for _q, answers in (fa._TM_HELP_Q1, fa._TM_HELP_Q2):
        for _text, nxt in answers:
            assert nxt == "q2" or nxt in fa._TM_OFFERED_TYPE_KEYS, nxt
            reached.add(nxt)
    assert reached - {"q2"} == set(fa._TM_OFFERED_TYPE_KEYS)


# ── the "didn't reply" hand-off ────────────────────────────────────────────

def test_camp_type_reads_any_of_the_three_markers():
    assert fa._tm_camp_type({"template_key": "tm_fivebyseven"}) == "tm_fivebyseven"
    assert fa._tm_camp_type({"aicb_camp_type": "tm_reengage"}) == "tm_reengage"
    assert fa._tm_camp_type({"_chooser_origin": "tm_twelveweek"}) == "tm_twelveweek"
    assert fa._tm_camp_type({"template_key": "fourbyfour"}) == ""
    assert fa._tm_camp_type(None) == ""


def test_nonresponders_skip_repliers_dnc_dupes_and_blank_emails():
    camp = {"responders": ["b@x.com", {"email": "C@x.com"}], "contacts": [
        {"email": "a@x.com", "first_name": "Ann", "company": "Acme",
         "title": "COO", "phone_office": "555"},
        {"Email": "B@x.com"},
        {"email": "c@x.com"},
        {"Email": "d@x.com", "FirstName": "Dee", "Company": "Dot"},
        {"email": "e@x.com"},
        {"email": "A@x.com"},
        {"email": ""},
        "junk",
    ]}
    rows = fa._tm_nonresponder_rows(camp, {"e@x.com"}, {"f@x.com"})
    assert [r["Email"] for r in rows] == ["a@x.com", "d@x.com"]
    assert rows[0] == {"Email": "a@x.com", "FirstName": "Ann", "LastName": "",
                       "Company": "Acme", "JobTitle": "COO", "MobilePhone": "",
                       "WorkPhone": "555", "LinkedInPage": "", "City": "",
                       "State": ""}
    assert set(rows[0]) == set(fa.CONTACT_FIELDS)
    assert fa._tm_nonresponder_rows(
        camp, set(), {"a@x.com", "d@x.com", "e@x.com"}) == []


def test_followon_note_only_when_opened_from_a_campaign():
    assert fa._tm_followon_note("") == ""
    note = fa._tm_followon_note("Acme - Standard Outreach")
    assert "'Acme - Standard Outreach'" in note and "did not reply" in note
    assert "do not mention that they did not" in note
    src = open(fa.__file__, encoding="utf-8").read()
    assert "brief=(_tm_followon_note(" in src


def test_followon_preloads_the_wizard_on_stay_on_their_radar(monkeypatch):
    class S:
        pass
    s = S()
    s._nav_history = []
    monkeypatch.setattr(fa, "_nav_snapshot", lambda st: {})
    monkeypatch.setattr(fa, "_reset_wizard_state",
                        lambda st: setattr(st, "aicb_followon_from", ""))
    rows = [{"Email": "a@x.com"}]
    fa._tm_start_followon(s, {"name": "Acme", "variables": {
        "Industry": "Logistics"}}, rows)
    assert s.aicb_camp_type == "tm_stay_in_touch" and s.aicb_style_locked
    assert s.sp == "ai_campaign" and s.aicb_wizard_step == 1
    assert s.aicb_contacts == rows and s.aicb_contacts is not rows
    assert s.aicb_followon_from == "Acme" and s.aicb_industry == "Logistics"
    assert s._nav_history == [{}]


def test_twelve_week_program_is_fifteen_touches_over_twelve_weeks():
    assert _shape_counts("tm_twelveweek") == (8, 4, 3)
    assert sorted(fa._TM_STEP_SHAPE["tm_twelveweek"]) == list(range(1, 16))
    total = sum(d for d, _ in fa._TM_STEP_SHAPE["tm_twelveweek"].values())
    assert round(total / 5) == 12
    t = {x[0]: x for x in fa.AICB_CAMPAIGN_TYPES}["tm_twelveweek"]
    # Candidates here are the KIND of person ThriveModal would recruit.
    assert "not specific people who are available" in t[6]


# ── the opener ─────────────────────────────────────────────────────────────

def test_every_thrivemodal_type_gets_the_offshore_opener():
    for k in fa._TM_TYPE_KEYS:
        assert fa._tm_opener_rule(k) == fa._TM_EMAIL_OPENER_RULE


def test_opener_keeps_the_savings_claim_inside_the_rules():
    # Since the model-email rewrite (2026-09-21) the saving is stated once,
    # in the cost email, not in every opener.
    r = fa._TM_EMAIL_OPENER_RULE
    assert "only the cost email states the saving" in r
    assert "up to sixty to seventy percent" in r
    assert "depending on the role" in r
    assert "no email ever gives a dollar amount" in r
    assert "$" not in r


def test_arena_types_never_get_the_opener(monkeypatch):
    monkeypatch.setattr(fa, "_workspace_playbook",
                        lambda *a, **k: fa.PLAYBOOK_ARENA)
    for k in ("fourbyfour", "fivebyfive", "fivebythree", "byos"):
        assert fa._tm_opener_rule(k) == ""


def test_custom_build_on_a_thrivemodal_workspace_gets_the_opener(monkeypatch):
    monkeypatch.setattr(fa, "_workspace_playbook",
                        lambda *a, **k: fa.PLAYBOOK_THRIVEMODAL)
    assert fa._tm_opener_rule("byos") == fa._TM_EMAIL_OPENER_RULE


def test_the_builder_prompt_carries_the_opener():
    src = open(fa.__file__, encoding="utf-8").read()
    assert "        _tm_opener_rule(camp_type) +" in src
