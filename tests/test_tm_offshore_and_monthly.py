"""ThriveModal campaigns say up front that we do offshore staff augmentation, and the
last email promises a monthly check-in (Mike, 2026-09-21)."""
import flowdrip_app as fa


def _camp(*bodies):
    return {"emails": [
        {"name": f"Step {i + 1} - x", "body": b, "subject": "s",
         "step_type": fa.ST.EMAIL_AUTO}
        for i, b in enumerate(bodies)]}


def test_missing_lines_are_added():
    c = _camp("Hi {FirstName},<br><br>What would your team do with more time?",
              "Hi {FirstName},<br><br>Middle.",
              "Hi {FirstName},<br><br>This is my last note.")
    fa._tm_ensure_offshore_and_monthly(c)
    first, mid, last = (e["body"] for e in c["emails"])
    assert first.startswith("Hi {FirstName},<br><br>" + fa._TM_OFFSHORE_LINE)
    assert "What would your team do" in first
    assert last.endswith(fa._TM_MONTHLY_LINE)
    assert mid == "Hi {FirstName},<br><br>Middle."


def test_a_question_about_offshore_staffing_is_not_saying_we_do_it():
    c = _camp("Hi {FirstName},<br><br>Have you considered offshore staff augmentation?",
              "Hi {FirstName},<br><br>Last one.")
    fa._tm_ensure_offshore_and_monthly(c)
    assert fa._TM_OFFSHORE_LINE in c["emails"][0]["body"]


def test_lines_already_there_are_left_alone():
    first = ("Hi {FirstName},<br><br>I do offshore staff augmentation for logistics "
             "companies. Quick question.")
    last = ("Hi {FirstName},<br><br>Closing this out, but I'll check in about "
            "once a month.")
    c = _camp(first, last)
    fa._tm_ensure_offshore_and_monthly(c)
    assert c["emails"][0]["body"] == first
    assert c["emails"][1]["body"] == last
    # Idempotent through the full override pass too.
    fa._tm_ensure_offshore_and_monthly(c)
    assert c["emails"][1]["body"] == last


def test_month_to_month_terms_are_not_a_check_in_promise():
    c = _camp("Hi {FirstName},<br><br>We do offshore staff augmentation.",
              "Hi {FirstName},<br><br>Month-to-month terms, monthly rate.")
    fa._tm_ensure_offshore_and_monthly(c)
    assert c["emails"][1]["body"].endswith(fa._TM_MONTHLY_LINE)


def test_calls_and_linkedin_steps_are_skipped():
    c = _camp("Hi {FirstName},<br><br>We do offshore staff augmentation.",
              "Hi {FirstName},<br><br>Final email.")
    c["emails"].append({"name": "Step 3 - Call", "body": "script",
                        "step_type": fa.ST.CALL})
    fa._tm_ensure_offshore_and_monthly(c)
    assert c["emails"][2]["body"] == "script"
    assert c["emails"][1]["body"].endswith(fa._TM_MONTHLY_LINE)


def test_the_monthly_line_survives_the_unbacked_promise_filter():
    assert fa._tm_drop_unbacked_lines(fa._TM_MONTHLY_LINE, False) == fa._TM_MONTHLY_LINE
    assert fa._tm_drop_unbacked_lines(fa._TM_OFFSHORE_LINE, False) == fa._TM_OFFSHORE_LINE


def test_overrides_apply_it_for_tm_types_only():
    c = _camp("Hi {FirstName},<br><br>Hello.", "Hi {FirstName},<br><br>Bye.")
    for i, e in enumerate(c["emails"]):
        e["name"] = f"Step {i + 1} - x"
    fa._apply_thrivemodal_overrides("tm_threebythree", c)
    assert fa._TM_OFFSHORE_LINE in c["emails"][0]["body"]
    arena = _camp("Hi {FirstName},<br><br>Hello.", "Hi {FirstName},<br><br>Bye.")
    fa._apply_thrivemodal_overrides("fivebyfive", arena)
    assert fa._TM_OFFSHORE_LINE not in arena["emails"][0]["body"]


def test_no_tm_step_still_forbids_ongoing_contact():
    for t in fa.AICB_CAMPAIGN_TYPES:
        if t[0] in fa._TM_TYPE_KEYS:
            assert "ongoing-send" not in t[6] and "ongoing sends" not in t[6], t[0]
            assert "you will stop" not in t[6], t[0]
    assert "once a month" in fa._TM_EMAIL_OPENER_RULE
    assert "offshore staff augmentation" in fa._TM_EMAIL_OPENER_RULE


def test_offshore_staffing_is_reworded_everywhere_in_tm_copy():
    c = _camp("Hi {FirstName},<br><br>We do Offshore Staffing. OFFSHORE STAFFING.",
              "Hi {FirstName},<br><br>Offshore staffing, once a month.")
    c["emails"][0]["subject"] = "Offshore staffing for you"
    fa._tm_ensure_offshore_and_monthly(c)
    b0 = c["emails"][0]["body"]
    assert "Offshore Staff Augmentation" in b0 and "OFFSHORE STAFF AUGMENTATION" in b0
    assert c["emails"][0]["subject"] == "Offshore staff augmentation for you"
    assert "Offshore staff augmentation, once" in c["emails"][1]["body"]
    # The rule names the banned phrase only to forbid it.
    assert "never 'offshore staffing'" in fa._TM_EMAIL_OPENER_RULE
    # Plug-and-play went with the model-email rewrite (2026-09-21).
    assert "plug-and-play" not in fa._TM_EMAIL_OPENER_RULE
    assert "plug-and-play" not in fa._TM_OFFSHORE_LINE


def test_tm_pdfs_say_staff_augmentation():
    data = {"title": "t", "intro": "Why offshore staffing works.",
            "sections": [{"heading": "h", "type": "bullets",
                          "items": ["Offshore staffing, done right."]}], "cta": ""}
    fa._tm_fix_pdf_labels("tm_role_blueprint", {"company": "Acme"}, data)
    assert data["intro"] == "Why offshore staff augmentation works."
    assert data["sections"][0]["items"][0] == "Offshore staff augmentation, done right."
