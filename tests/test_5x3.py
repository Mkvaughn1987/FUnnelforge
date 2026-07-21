"""Arena 5x3 campaign + resume engine (PipelineBlast Component 1).
Import flowdrip_app lazily inside each test (per tests/conftest.py)."""


def _get(fa, key):
    for t in fa.AICB_CAMPAIGN_TYPES:
        if t[0] == key:
            return t
    return None


def test_fivebythree_registered_after_fivebyfive():
    import flowdrip_app as fa
    keys = [t[0] for t in fa.AICB_CAMPAIGN_TYPES]
    assert "fivebythree" in keys
    assert keys.index("fivebythree") == keys.index("fivebyfive") + 1
    t = _get(fa, "fivebythree")
    assert t[1] == "Arena 5×3"
    assert t[2] == "5 steps - 2 weeks"


def test_fivebythree_prompt_has_five_steps():
    import flowdrip_app as fa
    prompt = _get(fa, "fivebythree")[6]
    positions = [prompt.find(f"Step {n} -") for n in range(1, 6)]
    assert all(p != -1 for p in positions), positions
    assert positions == sorted(positions)
    assert "Step 6 -" not in prompt


def test_fivebythree_in_slate_family():
    import flowdrip_app as fa
    assert "fivebythree" in fa._ARENA_SLATE_TYPES
    assert fa._camp_is_4x4({"aicb_camp_type": "fivebythree"}) is True
    assert fa._resume_attach_indices("fivebythree", 5) == [1, 3]


def _sample_5x3_generated():
    return {"emails": [
        {"name": "Step 1 - Warm Intro", "step_type": "email_auto",
         "subject": "Quick note for Acme", "body": "Hi {FirstName},<br><br>intro",
         "delay_days": 0, "attachments": []},
        {"name": "Step 2 - Candidate Slate", "step_type": "email_auto",
         "subject": "A few candidates...", "body": "Hi {FirstName},<br><br>slate",
         "delay_days": 3, "attachments": ["Resume_Candidate_A_Redacted.pdf"]},
        {"name": "Step 3 - Interview Guide", "step_type": "email_auto",
         "subject": "An interview guide, in case it helps",
         "body": '<div style="font-family:Aptos,Calibri,Arial,sans-serif;font-size:11pt;">Hi {FirstName},<br><br>guide</div>',
         "delay_days": 9, "attachments": []},
        {"name": "Step 4 - Following up", "step_type": "email_auto",
         "subject": "Following up", "body": "Hi {FirstName},<br><br>AI DRIFT TEXT",
         "delay_days": 9, "attachments": ["Resume_Candidate_A_Redacted.pdf"]},
        {"name": "Step 5 - Closing the loop", "step_type": "email_auto",
         "subject": "Closing the loop for now", "body": "Hi {FirstName},<br><br>close",
         "delay_days": 9, "attachments": []},
    ]}


def test_5x3_overrides_noop_for_other_types():
    import flowdrip_app as fa
    data = fa._apply_fivebythree_overrides("fivebyfive", _sample_5x3_generated())
    bump = next(e for e in data["emails"] if e["name"].startswith("Step 4"))
    assert "AI DRIFT TEXT" in bump["body"]


def test_5x3_bump_verbatim_keeps_attachments_and_schedule():
    import flowdrip_app as fa
    data = fa._apply_fivebythree_overrides("fivebythree", _sample_5x3_generated())
    bump = next(e for e in data["emails"] if e["name"].startswith("Step 4"))
    assert bump["subject"] == "Following up"
    assert "AI DRIFT TEXT" not in bump["body"]
    assert "review the résumés" in bump["body"] or "look over the résumés" in bump["body"]
    # 5x3 bump RE-ATTACHES resumes — must NOT be cleared (unlike the 5x5)
    assert bump["attachments"] == ["Resume_Candidate_A_Redacted.pdf"]
    assert bump["delay_days"] == 2  # pinned from a drifted 9
    assert "—" not in bump["body"] and "–" not in bump["body"]


def test_5x3_interview_line_once_inside_div():
    import flowdrip_app as fa
    data = fa._apply_fivebythree_overrides("fivebythree", _sample_5x3_generated())
    guide = next(e for e in data["emails"] if e["name"].startswith("Step 3"))
    assert "interview guide" in guide["body"].lower()
    assert guide["body"].rstrip().endswith("</div>")
    data2 = fa._apply_fivebythree_overrides("fivebythree", data)
    guide2 = next(e for e in data2["emails"] if e["name"].startswith("Step 3"))
    assert guide2["body"].lower().count("interview guide") == 1
    # schedule pinned across all five steps
    delays = {fa._fivebyfive_step_no(e["name"]): e["delay_days"] for e in data["emails"]}
    assert delays == {1: 0, 2: 3, 3: 3, 4: 2, 5: 3}
