"""Quick Intro (tm_threebythree) after the 2026-10-08 walkthrough: four
emails, hourly dollars only, candidate cards on the cost email, and a close
that asks for one word."""
import re

import flowdrip_app as fa

TAG_RE = re.compile(r"\(model: ([^)]+)\)")


def _steps(key):
    t = next(x for x in fa.AICB_CAMPAIGN_TYPES if x[0] == key)
    return [s for s in t[6].split("\n") if s.startswith("Step ")]


def _camp(*bodies):
    return {"emails": [
        {"name": f"Step {i + 1} - x", "subject": "", "body": b,
         "step_type": fa.ST.EMAIL_AUTO} for i, b in enumerate(bodies)]}


# ── the sequence ───────────────────────────────────────────────────────────

def test_four_emails_capacity_economics_onboarding_close():
    tags = [TAG_RE.search(s).group(1) for s in _steps("tm_threebythree")]
    assert tags == ["Capacity", "Economics", "After the candidate joins",
                    "Close"]
    shape = fa._TM_STEP_SHAPE["tm_threebythree"]
    assert [shape[n] for n in sorted(shape)] == [
        (0, fa.ST.EMAIL_AUTO), (3, fa.ST.EMAIL_AUTO),
        (3, fa.ST.EMAIL_AUTO), (4, fa.ST.EMAIL_AUTO)]
    t = next(x for x in fa.AICB_CAMPAIGN_TYPES if x[0] == "tm_threebythree")
    assert t[2] == "4 steps - 2 weeks"
    assert fa._tm_shape_summary("tm_threebythree") == (
        "4 emails only · about 2 weeks")


def test_the_cost_step_asks_for_hourly_dollars_only():
    econ = _steps("tm_threebythree")[1]
    assert "HOURLY ONLY" in econ and "$11/hr" in econ
    assert "Never an annual salary" in econ


def test_the_card_matches_the_steps():
    card = next(o for o in fa.TM_CHOOSER_OPTIONS
                if o["key"] == "tm_threebythree")
    assert "by the hour" in card["desc"]
    assert "after the candidate joins" in card["desc"]
    assert "now, later or no" in card["desc"]


def test_cards_land_once_on_the_cost_email():
    emails = _camp("Hi {FirstName},<br><br>One.<br><br>Q1?",
                   "Hi {FirstName},<br><br>Two.<br><br>Q2?",
                   "Hi {FirstName},<br><br>Three.<br><br>Q3?",
                   "Hi {FirstName},<br><br>Four.<br><br>Q4?")["emails"]
    emails[1]["subject"] = "What would the role actually cost?"
    rounds = fa._tm_profile_rounds("tm_threebythree", emails)
    assert [(i, cnt) for i, _lead, cnt in rounds] == [(1, None)]
    # Subject not yet pinned: falls back to the second email anyway.
    emails[1]["subject"] = ""
    rounds = fa._tm_profile_rounds("tm_threebythree", emails)
    assert [i for i, _lead, _cnt in rounds] == [1]


def test_still_one_pdf_the_cost_comparison():
    assert fa._tm_resolve_pdf_pick(None, "tm_threebythree") == [
        "tm_cost_compare"]


# ── hourly dollars only ────────────────────────────────────────────────────

def test_annual_and_k_figures_go_hourly_figures_stay():
    body = ("Hi {FirstName},<br><br>A fully burdened U.S. coordinator "
            "typically runs $55,000 to $65,000 annually. A dedicated "
            "coordinator can cost up to 60 to 70 percent less. Most support "
            "staff come in under $11/hr. It scales without another $60K "
            "desk.<br><br>Want me to run the numbers?")
    out = fa._tm_hourly_dollars_only(body)
    assert "$55,000" not in out and "$60K" not in out
    assert "up to 60 to 70 percent less" in out
    assert "under $11/hr" in out
    assert out.endswith("<br><br>Want me to run the numbers?")
    # "U.S." did not split the sentence: nothing dangles.
    assert "U.S.<br>" not in out and " U.S. A " not in out


def test_hourly_ranges_and_spellings_are_hourly():
    for s in ("$9 to $11 an hour", "$9.75/hr", "$10.00 / hour", "$11 per hour",
              "$9.50-$11.00/hr", "$12 hourly"):
        assert fa._tm_hourly_dollars_only(f"Hi,<br><br>Rates run {s} all in.") \
            == f"Hi,<br><br>Rates run {s} all in."


def test_candidate_card_lines_survive():
    card = ("Here are some of the candidate profiles in our pipeline:<br><br>"
            "<b>Candidate A: Dispatcher</b> · 3 years · Est. $10.00/hr<br>"
            "• Tracks loads in McLeod<br>• Updates ETAs")
    assert fa._tm_hourly_dollars_only(card) == card


def test_a_line_dropped_whole_does_not_leave_a_triple_gap():
    body = "Hi,<br><br>It costs $4,000 a month.<br><br>Still here?"
    assert fa._tm_hourly_dollars_only(body) == "Hi,<br><br>Still here?"


def test_bodies_without_dollars_are_untouched():
    body = "Hi {FirstName},<br><br>No figures here.<br><br>Open to it?"
    assert fa._tm_hourly_dollars_only(body) is body


def test_overrides_apply_the_hourly_filter_to_tm_emails():
    c = _camp("Hi {FirstName},<br><br>We do offshore staff augmentation.",
              "Hi {FirstName},<br><br>It runs $60,000 a year. Under $11/hr "
              "here.<br><br>Numbers?")
    fa._apply_thrivemodal_overrides("tm_threebythree", c)
    assert "$60,000" not in c["emails"][1]["body"]
    assert "Under $11/hr here." in c["emails"][1]["body"]


# ── the one-word close ─────────────────────────────────────────────────────

def test_a_short_closing_question_is_replaced_with_the_one_word_ask():
    c = _camp("Hi {FirstName},<br><br>One.",
              "Hi {FirstName},<br><br>This is my last note. I'll still check "
              "in about once a month.<br><br>One role is an easy way to find "
              "out.<br><br>Open to testing one?")
    fa._tm_ensure_one_word_close("tm_threebythree", c)
    body = c["emails"][-1]["body"]
    assert body.endswith("<br><br>" + fa._TM_ONE_WORD_ASK)
    assert "Open to testing one?" not in body
    assert "once a month" in body


def test_a_close_that_already_asks_for_one_word_is_left_alone():
    body = ("Hi {FirstName},<br><br>Last note, and I'll check in once a "
            "month.<br><br>Just reply now, later or no. Any of them helps.")
    c = _camp("Hi {FirstName},<br><br>One.", body)
    fa._tm_ensure_one_word_close("tm_threebythree", c)
    assert c["emails"][-1]["body"] == body


def test_the_ask_stays_before_the_attachment_and_monthly_lines():
    pdf = "I attached the Staffing Cost Comparison for your review."
    c = _camp("Hi {FirstName},<br><br>One.",
              "Hi {FirstName},<br><br>Last note.<br><br>Still worth a look?"
              "<br><br>" + pdf + "<br><br>" + fa._TM_MONTHLY_LINE)
    fa._tm_ensure_one_word_close("tm_threebythree", c)
    assert c["emails"][-1]["body"] == (
        "Hi {FirstName},<br><br>Last note.<br><br>" + fa._TM_ONE_WORD_ASK
        + "<br><br>" + pdf + "<br><br>" + fa._TM_MONTHLY_LINE)


def test_a_long_closing_paragraph_is_kept_and_the_ask_follows():
    long_q = ("If your reps are doing track and trace instead of selling, or "
              "nights and weekends are thin, a dedicated coordinator offshore "
              "changes that without the cost of a local hire, so is there one "
              "seat you would want to price out first, or none at all?")
    c = _camp("Hi {FirstName},<br><br>One.",
              "Hi {FirstName},<br><br>Last note.<br><br>" + long_q)
    fa._tm_ensure_one_word_close("tm_threebythree", c)
    assert c["emails"][-1]["body"].endswith(
        long_q + "<br><br>" + fa._TM_ONE_WORD_ASK)


def test_other_types_keep_their_own_close():
    body = "Hi {FirstName},<br><br>Last note.<br><br>Open to one?"
    for key in ("tm_fivebyseven", "tm_conversation", "fivebyfive"):
        c = _camp("Hi {FirstName},<br><br>One.", body)
        fa._tm_ensure_one_word_close(key, c)
        assert c["emails"][-1]["body"] == body


def test_overrides_run_the_close_after_the_monthly_backstop():
    c = _camp("Hi {FirstName},<br><br>We do offshore staff augmentation.",
              "Hi {FirstName},<br><br>Final note.<br><br>Open to one?")
    fa._apply_thrivemodal_overrides("tm_threebythree", c)
    body = c["emails"][-1]["body"]
    assert body.endswith(fa._TM_ONE_WORD_ASK + "<br><br>" + fa._TM_MONTHLY_LINE)
    # Idempotent: a second pass changes nothing.
    again = {"emails": [dict(e) for e in c["emails"]]}
    fa._apply_thrivemodal_overrides("tm_threebythree", again)
    assert again["emails"][-1]["body"] == body
