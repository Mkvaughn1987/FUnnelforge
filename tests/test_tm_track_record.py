"""First TM email opens on the sender's track record (Mike 2026-10-02: "I've
placed 100+ offshore Filipino candidates in the <industry> space ...")."""
import flowdrip_app as fa


def _camp(*bodies):
    return {"emails": [
        {"name": f"Step {i + 1} - x", "body": b, "subject": "s",
         "step_type": fa.ST.EMAIL_AUTO}
        for i, b in enumerate(bodies)]}


def test_line_reads_naturally():
    assert fa._tm_track_record_line("Track and Trace Specialist", "Logistics & Supply Chain") == (
        "I've placed 100+ offshore Filipino candidates in the logistics and "
        "supply chain space and thought I could be a resource, so I'm "
        "reaching out.")
    assert "in the accounting space" in fa._tm_track_record_line(
        "AP Specialist", "Accounting")
    assert fa._tm_track_record_line("Payroll Secretary", "") == (
        "I've placed 100+ offshore Filipino candidates and thought I could be "
        "a resource, so I'm reaching out.")


def test_rule_is_tm_only_and_carries_the_line():
    r = fa._tm_track_record_rule("tm_threebythree", "Dispatcher", "Logistics")
    assert fa._tm_track_record_line("Dispatcher", "Logistics") in r
    assert "Model 1" in r and "No other email, LinkedIn note or call uses the number" in r
    assert fa._tm_track_record_rule("fivebyfive", "Dispatcher", "Logistics") == ""


def test_backstop_adds_the_line_to_the_first_email_only():
    # Since the model-email rewrite (2026-09-21): no added question, no repeat.
    c = _camp("Hi {FirstName},<br><br>I do offshore staff augmentation.",
              "Hi {FirstName},<br><br>Second.", "Hi {FirstName},<br><br>Third.")
    fa._tm_ensure_track_record("tm_threebythree", c, "Dispatcher", "Logistics")
    b1, b2, b3 = (e["body"] for e in c["emails"])
    assert b1 == ("Hi {FirstName},<br><br>"
                  + fa._tm_track_record_line("Dispatcher", "Logistics")
                  + " I do offshore staff augmentation.")
    assert "considered" not in b1
    assert b2 == "Hi {FirstName},<br><br>Second."
    assert "100+" not in b3


def test_backstop_leaves_model_copy_alone_and_is_idempotent():
    first = ("Hi {FirstName},<br><br>I've placed 100+ offshore Filipino "
             "candidates in logistics. Have you ever considered offshore "
             "staff augmentation?")
    third = "Hi {FirstName},<br><br>Those 100+ placements taught me a lot."
    c = _camp(first, "Hi {FirstName},<br><br>Second.", third)
    for _ in range(2):
        fa._tm_ensure_track_record("tm_threebythree", c, "Dispatcher", "Logistics")
    assert [e["body"] for e in c["emails"]] == [
        first, "Hi {FirstName},<br><br>Second.", third]


def test_linkedin_note_ahead_of_the_first_email_loses_the_line():
    """Long Term Nurture opens on a LinkedIn connect; a live run put the
    track-record line on the note too. It belongs to the first email only."""
    line = fa._tm_track_record_line("Dispatcher", "Logistics")
    c = {"emails": [
        {"name": "Step 1 - LinkedIn Connect", "step_type": "linkedin",
         "body": "Hi {FirstName},<br><br>" + line + " I follow Acme. Open to connecting?"},
        {"name": "Step 2 - Capacity", "step_type": "email_auto",
         "body": "Hi {FirstName},<br><br>" + line + " We do offshore staff augmentation."},
        {"name": "Step 3 - Call 1", "step_type": "call",
         "body": "Hi {FirstName}, this is me. " + line + " Quick question."},
    ]}
    for _ in range(2):
        fa._tm_ensure_track_record("tm_twelveweek", c, "Dispatcher", "Logistics")
    assert c["emails"][0]["body"] == "Hi {FirstName},<br><br>I follow Acme. Open to connecting?"
    assert c["emails"][1]["body"].count("100+") == 1
    assert c["emails"][2]["body"] == "Hi {FirstName}, this is me. Quick question."
    assert "100+" not in c["emails"][0]["body"]
    assert "\n- No other email, LinkedIn note or call uses the number." in \
        fa._tm_track_record_rule("tm_twelveweek", "Dispatcher", "Logistics")


def test_not_applied_outside_thrivemodal():
    c = _camp("Hi {FirstName},<br><br>Hello.", "Hi {FirstName},<br><br>Bye.")
    fa._tm_ensure_track_record("fivebyfive", c, "Dispatcher", "Logistics")
    assert "100+" not in c["emails"][0]["body"]


def test_offshore_line_goes_after_the_opener_question_not_above_it():
    body = ("Hi {FirstName},<br><br>I've placed 100+ offshore Filipino "
            "candidates in the logistics space and thought I could be a "
            "resource, so I'm reaching out. Have you ever considered offshore "
            "staff augmentation? What would your team focus on?")
    c = _camp(body, "Hi {FirstName},<br><br>Once a month.")
    fa._tm_ensure_offshore_and_monthly(c)
    fa._tm_ensure_track_record("tm_threebythree", c, "Dispatcher", "Logistics")
    b = c["emails"][0]["body"]
    assert b.startswith("Hi {FirstName},<br><br>I've placed 100+")
    assert b.index("augmentation?") < b.index(fa._TM_OFFSHORE_LINE) < b.index("What would")
    assert b.count("100+") == 1


def test_slash_industry_reads_as_and():
    assert "in the freight brokerage and logistics space" in \
        fa._tm_track_record_line("Dispatcher", "Freight brokerage / logistics")


def test_choosing_the_person_becomes_candidate():
    assert fa._tm_aug_wording("Honestly, choosing the person is easy.") == (
        "Honestly, choosing the candidate is easy.")
