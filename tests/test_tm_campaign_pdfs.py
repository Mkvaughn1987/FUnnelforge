"""ThriveModal campaigns: the PDFs a campaign carries (the Sales Assets set,
two by default, three on long sequences), where each lands in the sequence,
the refresh of saved campaigns, and the new-business-only type lineup."""
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


def test_clamp_caps_at_three_and_drops_unknown_and_dupes():
    assert fa._clamp_tm_pdf_kinds(
        ["market_pulse", "bogus", "market_pulse", "tm_cost_compare",
         "tm_how_it_works", "tm_role_blueprint"]) == [
        "market_pulse", "tm_cost_compare", "tm_how_it_works"]
    assert fa._clamp_tm_pdf_kinds(None) == []


def test_default_is_two_and_three_on_long_sequences():
    assert fa._tm_resolve_pdf_pick(None, "tm_threebythree") == [
        "tm_role_blueprint", "tm_cost_compare"]
    assert fa._tm_resolve_pdf_pick(None, "tm_twelveweek") == [
        "tm_role_blueprint", "tm_cost_compare", "tm_how_it_works"]
    # An explicit pick wins, including an explicit "none".
    assert fa._tm_resolve_pdf_pick(["market_pulse"], "tm_twelveweek") == ["market_pulse"]
    assert fa._tm_resolve_pdf_pick([], "tm_twelveweek") == []
    # A restored draft holding only retired kinds gets the default.
    assert fa._tm_resolve_pdf_pick(["tm_logistics"], "tm_threebythree") == [
        "tm_role_blueprint", "tm_cost_compare"]


def test_every_offered_type_places_its_default_never_first_or_call():
    for ct in fa._TM_OFFERED_TYPE_KEYS:
        camp = _campaign(ct)
        kinds = fa._tm_default_pdf_kinds(ct, camp["emails"])
        assert len(kinds) >= 2, ct
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
        "x", emails, ["tm_role_blueprint", "tm_cost_compare", "tm_how_it_works"])
    assert {k: emails[i]["name"] for k, i in placed.items()} == {
        "tm_cost_compare": "Step 2 - What the role would cost",
        "tm_role_blueprint": "Step 4 - What actually transfers",
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
        "Offshore_Role_Blueprint_Estimator.pdf",
        "Staffing_Cost_Comparison_Estimator.pdf"]
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

def test_offered_lineup_is_cold_outreach_only():
    assert fa._TM_OFFERED_TYPE_KEYS == {
        "tm_conversation", "tm_fivebyseven", "tm_threebythree",
        "tm_fivethreeli", "tm_stay_in_touch", "tm_twelveweek"}
    for k in fa._TM_HIDDEN_TYPE_KEYS:
        assert k in {t[0] for t in fa.AICB_CAMPAIGN_TYPES}  # still registered
        assert not fa._type_visible(k, fa.PLAYBOOK_THRIVEMODAL)
    chooser = [o["key"] for o in fa.TM_CHOOSER_OPTIONS]
    assert not set(chooser) & fa._TM_HIDDEN_TYPE_KEYS
    assert set(fa._TM_OFFERED_TYPE_KEYS) <= set(chooser)


def _shape_counts(key):
    kinds = [st for _d, st in fa._TM_STEP_SHAPE[key].values()]
    return (kinds.count(fa.ST.EMAIL_AUTO), kinds.count(fa.ST.CALL),
            kinds.count(fa.ST.LINKEDIN))


def test_new_shapes_match_what_was_asked_for():
    assert _shape_counts("tm_fivebyseven") == (5, 1, 1)
    assert _shape_counts("tm_threebythree") == (3, 0, 0)
    assert _shape_counts("tm_fivethreeli") == (5, 3, 1)
    # Three weeks = 15 business days; the 3x3 fits inside one week.
    assert sum(d for d, _ in fa._TM_STEP_SHAPE["tm_fivebyseven"].values()) == 15
    assert sum(d for d, _ in fa._TM_STEP_SHAPE["tm_fivethreeli"].values()) == 15
    assert sum(d for d, _ in fa._TM_STEP_SHAPE["tm_threebythree"].values()) <= 5


def test_stay_in_touch_is_now_cold_nurture():
    t = {x[0]: x for x in fa.AICB_CAMPAIGN_TYPES}["tm_stay_in_touch"]
    assert t[1] == "Cold Nurture"
    assert "cold first touch" in t[6]


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
    r = fa._TM_EMAIL_OPENER_RULE
    assert "ever considered offshore staffing" in r
    assert "up to sixty to seventy percent" in r
    assert "depending on the role" in r
    assert "Never a dollar amount" in r
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
