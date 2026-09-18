"""ThriveModal campaigns: the Review-step PDF pick (max 2 of the six
ThriveModal sales PDFs), where each picked PDF lands in the sequence, and the
new-business-only type lineup."""
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

def test_the_six_thrivemodal_pdfs_ship_with_the_app():
    assert len(fa._TM_CAMPAIGN_PDF_KINDS) == 6
    for _k, _label, fname, line in fa._TM_CAMPAIGN_PDF_KINDS:
        p = fa._TM_CAMPAIGN_PDF_DIR / fname
        assert p.is_file(), p
        assert p.read_bytes()[:5] == b"%PDF-"
        assert line.startswith("I've attached")


def test_old_generated_kinds_are_not_offered():
    kinds = {k for k, *_ in fa._TM_CAMPAIGN_PDF_KINDS}
    assert not kinds & {"salary_guide", "scorecard", "tenure_snapshot",
                        "market_pulse", "interview_guide",
                        "tm_role_blueprint", "tm_cost_compare"}


def test_clamp_caps_at_two_and_drops_unknown_and_dupes():
    assert fa._clamp_tm_pdf_kinds(
        ["tm_logistics", "bogus", "tm_logistics", "tm_role_cost",
         "tm_how_it_works"]) == ["tm_logistics", "tm_role_cost"]
    assert fa._clamp_tm_pdf_kinds(None) == []


def test_stage_copies_the_picked_files(tmp_path):
    got = fa._tm_stage_campaign_pdfs(["tm_role_cost", "tm_twelve_questions"],
                                     dest_dir=tmp_path)
    assert got == {"tm_role_cost": "ThriveModal_What_a_Role_Really_Costs.pdf",
                   "tm_twelve_questions": "ThriveModal_Twelve_Questions.pdf"}
    for fn in got.values():
        assert (tmp_path / fn).read_bytes()[:5] == b"%PDF-"


def test_stage_leaves_out_a_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, "_TM_CAMPAIGN_PDF_DIR", tmp_path / "nowhere")
    assert fa._tm_stage_campaign_pdfs(["tm_role_cost"],
                                      dest_dir=tmp_path) == {}


def test_conversation_uses_the_step_each_pdf_backs():
    camp = _campaign("tm_conversation")
    placed = fa._tm_pdf_placement("tm_conversation", camp["emails"],
                                  ["tm_how_it_works", "tm_role_cost"])
    names = {k: camp["emails"][i]["name"] for k, i in placed.items()}
    assert names == {"tm_how_it_works": "Step 8 - x",
                     "tm_role_cost": "Step 2 - x"}


def test_every_offered_type_places_two_pdfs_never_first_or_call():
    for ct in fa._TM_OFFERED_TYPE_KEYS:
        camp = _campaign(ct)
        placed = fa._tm_pdf_placement(ct, camp["emails"],
                                      ["tm_logistics", "tm_twelve_questions"])
        assert len(placed) == 2, ct
        assert len(set(placed.values())) == 2
        for i in placed.values():
            assert i > 0
            assert camp["emails"][i]["step_type"] in ("email_auto", "email")


def test_attach_adds_file_and_line_only_where_placed():
    camp = _campaign("tm_conversation")
    n = fa._tm_attach_campaign_pdfs(
        "tm_conversation", camp, {"tm_how_it_works": "ThriveModal_How_It_Works.pdf"})
    assert n == 1
    carrying = [e for e in camp["emails"] if e.get("attachments")]
    assert [e["name"] for e in carrying] == ["Step 8 - x"]
    assert carrying[0]["body"].startswith("Hi {FirstName},<br><br>I've attached")
    # The unbacked-promise scrub keeps the line because the file is attached.
    assert "attached" in fa._tm_drop_unbacked_lines(carrying[0]["body"], True)


def test_nothing_picked_attaches_nothing():
    camp = _campaign("tm_conversation")
    assert fa._tm_attach_campaign_pdfs("tm_conversation", camp, {}) == 0
    assert not any(e.get("attachments") for e in camp["emails"])


def test_failed_stage_is_not_attached():
    camp = _campaign("tm_fivebyseven")
    assert fa._tm_attach_campaign_pdfs(
        "tm_fivebyseven", camp, {"tm_logistics": ""}) == 0


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
