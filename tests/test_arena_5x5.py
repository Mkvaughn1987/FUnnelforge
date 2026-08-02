"""Arena 5x5 sequence — registry, family behavior, and post-gen overrides.
Imports flowdrip_app lazily inside each test (per tests/conftest.py warning)."""


def _get(fa, key):
    for t in fa.AICB_CAMPAIGN_TYPES:
        if t[0] == key:
            return t
    return None


def test_fivebyfive_registered_right_after_fourbyfour():
    import flowdrip_app as fa
    keys = [t[0] for t in fa.AICB_CAMPAIGN_TYPES]
    assert "fivebyfive" in keys
    # placed directly after the 4x4
    assert keys.index("fivebyfive") == keys.index("fourbyfour") + 1
    t = _get(fa, "fivebyfive")
    assert t[1] == "Arena 5×5"
    assert t[2] == "7 steps - 2 weeks"


def test_fivebyfive_prompt_has_seven_steps_and_delays():
    import flowdrip_app as fa
    prompt = _get(fa, "fivebyfive")[6]
    positions = [prompt.find(f"Step {n} -") for n in range(1, 8)]
    assert all(p != -1 for p in positions), positions
    assert positions == sorted(positions)
    assert "Step 8 -" not in prompt
    for needle in [
        "Step 1 - Introducing Myself (delay_days:0, step_type:email_auto)",
        "delay_days:0, step_type:call",
        "delay_days:0, step_type:linkedin",
        "Following-up bump (delay_days:2, step_type:email_auto)",
        "Worth a look (delay_days:3, step_type:email_auto)",
        "Closing the loop (delay_days:4, step_type:email_auto)",
    ]:
        assert needle in prompt, needle


def test_camp_is_4x4_includes_fivebyfive():
    import flowdrip_app as fa
    assert fa._camp_is_4x4({"aicb_camp_type": "fivebyfive"}) is True
    assert fa._camp_is_4x4({"template_key": "fivebyfive"}) is True
    assert fa._camp_is_4x4({"_chooser_origin": "fivebyfive"}) is True
    assert fa._camp_is_4x4({"aicb_camp_type": "fourbyfour"}) is True
    assert fa._camp_is_4x4({"aicb_camp_type": "talentdrop"}) is False


def test_resume_indices_and_pdf_subject_family():
    import flowdrip_app as fa
    assert fa._resume_attach_indices("fivebyfive", 5) == [1, 3]
    assert fa._resume_attach_indices("fourbyfour", 5) == [1, 3]
    assert fa._resume_attach_indices("talentdrop", 5) == [0, 2]
    camp = {"name": "Arena 5x5 - Acme (7/21)", "_chooser_origin": "fivebyfive",
            "variables": {"TargetRole": "Estimator", "CompanyName": "Acme"}}
    company, roles, location, industry = fa._pdf_campaign_subject(camp)
    assert company == "Acme"
    assert roles == "Estimator"


def _sample_generated():
    return {"emails": [
        {"name": "Step 1 - Introducing Available Talent", "step_type": "email_auto",
         "subject": "A few candidates...", "body": "Hi {FirstName},<br><br>intro",
         "delay_days": 0, "attachments": []},
        {"name": "Step 2 - Top Talent Insights spotlight", "step_type": "email_auto",
         "subject": "One person...", "body": "Hi {FirstName},<br><br>spotlight",
         "delay_days": 3, "attachments": []},
        {"name": "Step 3 - Follow-up Call", "step_type": "call",
         "subject": "", "body": "call", "delay_days": 0, "attachments": []},
        {"name": "Step 4 - LinkedIn Connect", "step_type": "linkedin",
         "subject": "", "body": "connect", "delay_days": 0, "attachments": []},
        {"name": "Step 5 - Following-up bump", "step_type": "email_auto",
         "subject": "Following up", "body": "Hi {FirstName},<br><br>AI DRIFT TEXT",
         "delay_days": 9, "attachments": []},
        {"name": "Step 6 - Worth a look", "step_type": "email_auto",
         "subject": "Still think this one's worth a look",
         "body": '<div style="font-family:Aptos,Calibri,Arial,sans-serif;font-size:11pt;">Hi {FirstName},<br><br>circle back</div>',
         "delay_days": 3, "attachments": []},
        {"name": "Step 7 - Closing the loop", "step_type": "email_auto",
         "subject": "Closing the loop for now", "body": "Hi {FirstName},<br><br>close",
         "delay_days": 4, "attachments": []},
    ]}


def test_overrides_noop_for_non_5x5():
    import flowdrip_app as fa
    data = fa._apply_fivebyfive_overrides("fourbyfour", _sample_generated())
    bump = next(e for e in data["emails"] if e["name"].startswith("Step 5"))
    assert "AI DRIFT TEXT" in bump["body"]


def test_overrides_bump_verbatim_and_schedule():
    import flowdrip_app as fa
    data = fa._apply_fivebyfive_overrides("fivebyfive", _sample_generated())
    bump = next(e for e in data["emails"] if e["name"].startswith("Step 5"))
    assert bump["subject"] == "Following up"
    assert "just a quick follow-up in case this got missed" in bump["body"]
    assert "point me to whoever owns it" in bump["body"]
    assert "AI DRIFT TEXT" not in bump["body"]
    assert bump["attachments"] == []
    assert bump["delay_days"] == 2  # pinned from a drifted 9
    assert "—" not in bump["body"] and "–" not in bump["body"]


def test_overrides_interview_line_once_inside_div():
    import flowdrip_app as fa
    data = fa._apply_fivebyfive_overrides("fivebyfive", _sample_generated())
    worth = next(e for e in data["emails"] if e["name"].startswith("Step 6"))
    assert "attached a short interview guide" in worth["body"]
    assert worth["body"].rstrip().endswith("</div>")  # line kept inside font div
    data2 = fa._apply_fivebyfive_overrides("fivebyfive", data)
    worth2 = next(e for e in data2["emails"] if e["name"].startswith("Step 6"))
    assert worth2["body"].count("attached a short interview guide") == 1
