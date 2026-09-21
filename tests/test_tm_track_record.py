"""First TM email opens on the sender's track record ("placed 50+ <role> in
<industry>") and one follow-up repeats it (Mike, 2026-09-21)."""
import flowdrip_app as fa


def _camp(*bodies):
    return {"emails": [
        {"name": f"Step {i + 1} - x", "body": b, "subject": "s",
         "step_type": fa.ST.EMAIL_AUTO}
        for i, b in enumerate(bodies)]}


def test_line_reads_naturally():
    assert fa._tm_track_record_line("Track and Trace Specialist", "Logistics & Supply Chain") == (
        "I'm reaching out because I've recently placed 50+ track and trace "
        "specialists in logistics and supply chain, and I thought I could be a "
        "resource for you.")
    assert "50+ AP specialists in accounting" in fa._tm_track_record_line(
        "AP Specialist", "Accounting")
    assert "50+ payroll secretaries," in fa._tm_track_record_line("Payroll Secretary", "")


def test_rule_is_tm_only_and_carries_the_line():
    r = fa._tm_track_record_rule("tm_threebythree", "Dispatcher", "Logistics")
    assert fa._tm_track_record_line("Dispatcher", "Logistics") in r
    assert "Model 1" in r and "No other email uses the number" in r
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
    assert "50+" not in b3


def test_backstop_leaves_model_copy_alone_and_is_idempotent():
    first = ("Hi {FirstName},<br><br>I'm reaching out because I've recently "
             "placed 50+ dispatchers in logistics. Have you ever considered "
             "offshore staff augmentation?")
    third = "Hi {FirstName},<br><br>Those 50+ placements taught me a lot."
    c = _camp(first, "Hi {FirstName},<br><br>Second.", third)
    for _ in range(2):
        fa._tm_ensure_track_record("tm_threebythree", c, "Dispatcher", "Logistics")
    assert [e["body"] for e in c["emails"]] == [
        first, "Hi {FirstName},<br><br>Second.", third]


def test_not_applied_outside_thrivemodal():
    c = _camp("Hi {FirstName},<br><br>Hello.", "Hi {FirstName},<br><br>Bye.")
    fa._tm_ensure_track_record("fivebyfive", c, "Dispatcher", "Logistics")
    assert "50+" not in c["emails"][0]["body"]


def test_offshore_line_goes_after_the_opener_question_not_above_it():
    body = ("Hi {FirstName},<br><br>I'm reaching out because I've recently "
            "placed 50+ dispatchers in logistics, and I thought I could be a "
            "resource for you. Have you ever considered offshore staff "
            "augmentation? What would your team focus on?")
    c = _camp(body, "Hi {FirstName},<br><br>Once a month.")
    fa._tm_ensure_offshore_and_monthly(c)
    fa._tm_ensure_track_record("tm_threebythree", c, "Dispatcher", "Logistics")
    b = c["emails"][0]["body"]
    assert b.startswith("Hi {FirstName},<br><br>I'm reaching out because")
    assert b.index("augmentation?") < b.index(fa._TM_OFFSHORE_LINE) < b.index("What would")
    assert b.count("50+") == 1
