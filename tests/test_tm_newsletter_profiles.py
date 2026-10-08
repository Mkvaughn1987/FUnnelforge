"""Sales-instance newsletters: the optional 3 AI sample talent profiles.

They must be labelled as samples, carry no pay figure, and leave Arena's
candidate spotlights untouched."""
import inspect
import json
import re

import flowdrip_app as fa


def test_full_send_block_asks_for_three_unpaid_samples():
    ins, schema = fa._tm_spotlight_prompt_block("Freight Brokerage", 3, "")
    assert "SAMPLE TALENT PROFILES" in ins and "composite" in ins
    assert "no pay, salary" in ins and "virtual assistant" in ins
    assert schema.count('"name": "Profile ') == 3
    assert '"salary_ask": ""' in schema
    assert fa._tm_spotlight_prompt_block("x", 0) == ("", "")


def test_recommendations_steer_the_profiles():
    ins, _ = fa._tm_spotlight_prompt_block("CPA Firms", 3, "staff accountants")
    assert "staff accountants" in ins


def test_organic_prompt_adds_profiles_only_when_asked():
    off = fa._jway_sales_prompt("Freight", "Freight Brokerage", "Dallas, TX",
                                "October 2026", "Pat", "Acme")
    on = fa._jway_sales_prompt("Freight", "Freight Brokerage", "Dallas, TX",
                               "October 2026", "Pat", "Acme", 3, "")
    assert '"candidates":[]' in off and "never include candidate profiles" in off
    assert on.count('"label":"Profile ') == 3
    assert '"salary":""' in on and "never include candidate profiles" not in on


def test_arena_spotlights_unchanged():
    ins, schema = fa._spotlight_prompt_block("construction", 3, [], "")
    assert "CANDIDATE SPOTLIGHTS" in ins and "salary_ask" in schema


def test_renderers_label_profiles_as_samples_on_sales_instances():
    src = inspect.getsource(fa._jway_render)
    assert "_TM_PROFILES_HEADING" in src
    assert fa._TM_PROFILES_HEADING == "Candidate Profiles"
    assert not hasattr(fa, "_TM_PROFILES_NOTE")


def test_dialogs_offer_the_toggle_and_save_three_or_zero():
    create = inspect.getsource(fa._create_newsletter_dialog)
    assert "_spotlight_count = 3 if _tm_profiles_in.value else 0" in create
    settings = inspect.getsource(fa._edit_newsletter_settings_dialog)
    assert "_new_count = 3 if _tm_prof_in.value else 0" in settings


# ── AI candidate profiles inside ThriveModal campaigns ─────────────────────

class _Msg:
    def __init__(self, text):
        # A thinking block first, as Sonnet 5 sends it.
        self.content = [type("T", (), {"type": "thinking", "thinking": "..."})(),
                        type("B", (), {"type": "text", "text": text})()]


def _fake_model(monkeypatch, payload, seen=None):
    def create(client, **kw):
        if seen is not None:
            seen.append(kw["messages"][0]["content"])
        return _Msg(json.dumps(payload))
    monkeypatch.setattr(fa, "_claude_create_with_retry", create)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda: True)
    monkeypatch.setattr(fa, "_tm_profile_rate",
                        lambda client, t: "$10.25/hr" if "Track" in t else "")


_THREE = {"profiles": [
    {"title": "Track and Trace Specialist", "years": 5,
     "bullets": ["Works in McLeod and DAT daily",
                 "Runs after-hours check calls for U.S. brokerages",
                 "Updates shippers on exceptions before they ask"]},
    {"title": "freight billing and audit specialist", "years": 3,
     "bullets": ["Audits carrier invoices against rate confirmations",
                 "Paid $22/hr at last job"]},   # pay bullet dropped -> 1 left
    {"title": "Load Planner", "years": 12,
     "bullets": ["Builds loads in Descartes", "Balances lanes by equipment type"]},
    {"title": "Wizard of Logistics", "years": 4,  # not an allowed title
     "bullets": ["a", "b"]},
]}


def test_profiles_are_at_least_three():
    assert [fa._clamp_ai_profiles(v) for v in (None, 0, "2", 4, 9, "x")] == [
        3, 3, 3, 4, 5, 3]
    assert fa.AppState().aicb_tm_profiles == 3


def test_generated_profiles_are_clean_and_priced_from_wage_data(monkeypatch):
    seen = []
    _fake_model(monkeypatch, _THREE, seen)
    out = fa._tm_generate_campaign_profiles(
        None, 3, "Track and Trace Specialist", "Freight Brokerage",
        company="Redwood Logistics")
    assert [p["title"] for p in out] == ["Track and Trace Specialist",
                                         "Load Planner"]
    assert out[0]["rate"] == "$10.25/hr" and out[1]["rate"] == ""
    assert out[1]["years"] == 9                      # clamped
    assert all(2 <= len(p["bullets"]) <= 3 for p in out)
    prompt = seen[0]
    assert "The first profile is for Track and Trace Specialist" in prompt
    assert "Redwood Logistics" in prompt and "Never write a name" in prompt


def test_buyer_titles_are_never_candidate_titles(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda: True)
    titles = fa._tm_profile_titles(
        "Owner/Principal, VP of Operations, Controller/CFO, Leasing Coordinator",
        "property management")
    assert titles[0] == "Leasing Coordinator"
    assert not any(fa._TM_BUYER_TITLE_RE.search(t) for t in titles)


def test_priced_profiles_come_first(monkeypatch):
    _fake_model(monkeypatch, {"profiles": [
        {"title": "Load Planner", "years": 4, "bullets": ["a b", "c d"]},
        {"title": "Track and Trace Specialist", "years": 4,
         "bullets": ["a b", "c d"]}]})
    out = fa._tm_generate_campaign_profiles(None, 3, "", "freight brokerage")
    assert [p["title"] for p in out] == ["Track and Trace Specialist",
                                         "Load Planner"]


def test_bullets_never_carry_pay_or_promises():
    for bad in ("Earns $12/hr", "Cut costs 40%", "Available to start Monday",
                "Resume attached", "On our newsletter list"):
        assert fa._tm_clean_profile_bullet(bad) == ""
    assert fa._tm_clean_profile_bullet("• works in QuickBooks.") == (
        "Works in QuickBooks")


def _camp():
    names = ["Step 1 - Intro", "Step 2 - Call", "Step 3 - The cost",
             "Step 4 - Who we would send you", "Step 5 - Close"]
    return {"emails": [
        {"name": n, "subject": "s",
         "body": "Hi {FirstName},<br><br>Para one.<br><br>Worth a call?",
         "step_type": "call" if "Call" in n else "email_auto"} for n in names]}


_PROFILES = [{"title": "Bookkeeper", "years": 5, "rate": "$9.50/hr",
              "bullets": ["Closes the month in QuickBooks Online",
                          "Reconciles bank and card feeds daily"]},
             {"title": "Staff Accountant", "years": 3, "rate": "",
              "bullets": ["Preps accruals", "Builds the AP aging"]},
             {"title": "Payroll Specialist", "years": 7, "rate": "$11.00/hr",
              "bullets": ["Runs ADP payroll", "Files state returns",
                          "Handles garnishments"]}]


def test_profiles_go_on_the_people_email_before_the_ask_and_rerun_cleanly():
    camp = _camp()
    for _ in range(2):
        out = fa._tm_add_campaign_profiles(None, camp, 3, "", "",
                                           profiles=_PROFILES)
    assert out["email"] == 3                         # "Who we would send you"
    body = camp["emails"][3]["body"]
    assert body.count(fa._TM_PROFILES_LEAD) == 1
    assert body.startswith("Hi {FirstName},<br><br>Para one.<br><br>"
                           + fa._TM_PROFILES_LEAD)
    assert body.endswith("<br><br>Worth a call?")
    assert "<b>Candidate A: Bookkeeper</b> · 5 years · Est. $9.50/hr" in body
    assert "<b>Candidate B: Staff Accountant</b> · 3 years<br>" in body
    assert "<b>Candidate C: Payroll Specialist</b>" in body
    assert body.count("<br>• ") == 7
    others = " ".join(e["body"] for i, e in enumerate(camp["emails"]) if i != 3)
    assert fa._TM_PROFILES_LEAD not in others
    # Stripping gives back the original email.
    assert fa._tm_strip_campaign_profiles(body) == (
        "Hi {FirstName},<br><br>Para one.<br><br>Worth a call?")


def test_old_woven_profiles_are_removed_before_the_new_set():
    dash = ("Hi {FirstName},<br><br>Intro.<br><br>Here are some of the candidate "
            "profiles in our pipeline:<br><br>- Estimator: five years<br><br>"
            "- Drafter: six years<br>- Coordinator: four<br><br>Worth a call?")
    inline = ("Hi {FirstName},<br><br>Intro.<br><br>Here are some of the "
              "candidate profiles in our pipeline: Drafter with five years. "
              "Estimator with six.<br><br>Worth a call?")
    for body in (dash, inline):
        assert fa._tm_strip_campaign_profiles(body) == (
            "Hi {FirstName},<br><br>Intro.<br><br>Worth a call?")
    camp = _camp()
    camp["emails"][2]["body"] = dash
    fa._tm_add_campaign_profiles(None, camp, 3, "", "", profiles=_PROFILES)
    bodies = [e["body"] for e in camp["emails"]]
    assert sum(fa._TM_PROFILES_LEAD in b for b in bodies) == 1
    assert "- Estimator" not in " ".join(bodies)


def test_profiles_never_go_on_the_first_email_or_a_call():
    camp = _camp()
    for e in camp["emails"]:
        e["name"] = "Step - x"
    i = fa._tm_profiles_email_index(camp["emails"])
    assert i == 2
    camp["emails"][2]["attachments"] = ["Staffing_Cost_Comparison_X.pdf"]
    assert fa._tm_profiles_email_index(camp["emails"]) == 3


def test_builder_adds_profiles_only_for_tm_without_real_candidates():
    src = inspect.getsource(fa._aicb_build_campaign_from_brief)
    assert ("_tm_profiles = (not cand_block\n"
            "                    and (camp_type or \"\").strip() in _TM_TYPE_KEYS)") in src
    assert "_tm_add_campaign_profiles(" in src
    assert "ai_profiles=ai_profiles" in inspect.getsource(fa.generate_aicb_campaign)
    assert 'spec.get("ai_profiles")' in inspect.getsource(fa._api_create_campaign_blocking)
    assert "Do not write candidate profiles" in fa._TM_PROFILES_WRITER_NOTE


def _std_camp():
    """Standard Outreach as built: seven emails with the model subjects,
    two calls and a LinkedIn step."""
    steps = [("Step 1 - Capacity", "More room for the work that matters"),
             ("Step 2 - Economics", "What would the role actually cost?"),
             ("Step 3 - Follow-up Call", ""), ("Step 4 - LinkedIn Connect", ""),
             ("Step 5 - Role scope", "A clearer scope for the role"),
             ("Step 6 - After the candidate joins", "After the candidate joins"),
             ("Step 7 - Quality and control",
              "What you would assess before hiring"),
             ("Step 8 - Follow-up Call 2", ""),
             ("Step 9 - Commitment", "Start with the role requirements"),
             ("Step 10 - Close", "Leaving this with you")]
    return {"emails": [
        {"name": n, "subject": sub,
         "body": "Hi {FirstName},<br><br>Para one.<br><br>Worth a call?",
         "step_type": ("call" if "Call" in n else "linkedin" if "LinkedIn" in n
                       else "email_auto")} for n, sub in steps]}


def test_standard_outreach_shows_the_candidates_three_times():
    """Mike 2026-10-02: introduced on email 3, sent again on email 5, and two
    of them on the close (email 7)."""
    camp = _std_camp()
    for _ in range(2):                      # reruns replace, never stack
        out = fa._tm_add_campaign_profiles(None, camp, 3, "", "",
                                           profiles=_PROFILES,
                                           camp_type="tm_fivebyseven")
    assert out["emails"] == [4, 6, 9]
    b = [e["body"] for e in camp["emails"]]
    assert b[4].count(fa._TM_PROFILES_LEAD) == 1
    assert b[4].count("<b>Candidate ") == 3
    assert b[6].count(fa._TM_PROFILES_AGAIN_LEAD) == 1
    assert b[6].count("<b>Candidate ") == 3
    assert b[9].count(fa._TM_PROFILES_LAST_LEAD) == 1
    assert b[9].count("<b>Candidate ") == 2
    assert "Candidate C" not in b[9]
    for i in (4, 6, 9):
        assert b[i].endswith("<br><br>Worth a call?")
        assert fa._tm_strip_campaign_profiles(b[i]) == (
            "Hi {FirstName},<br><br>Para one.<br><br>Worth a call?")
    others = [b[i] for i in range(len(b)) if i not in (4, 6, 9)]
    assert not any("<b>Candidate " in x for x in others)
    # The last lead never claims what happened to the third candidate.
    low = fa._TM_PROFILES_LAST_LEAD.lower()
    assert "placed one" not in low and "lost" not in low and "hired" not in low


def test_long_term_nurture_shows_the_candidates_every_third_email():
    """Mike 2026-10-08: emails 3, 6, 9 and 12, two of them on the close."""
    t = {x[0]: x for x in fa.AICB_CAMPAIGN_TYPES}["tm_twelveweek"]
    subjects = {n: s for n, s, _p in fa._TM_MODEL_EMAILS}
    models = fa._tm_step_models("tm_twelveweek")
    emails = []
    for line in t[6].split("\n"):
        m = re.match(r"(Step (\d+) - [^(]+?)\s*\(delay_days:\d+, step_type:(\w+)\)",
                     line)
        if m:
            emails.append({
                "name": m.group(1).strip(),
                "subject": subjects.get(models.get(int(m.group(2))), ""),
                "body": "Hi {FirstName},<br><br>Para one.<br><br>Worth a call?",
                "step_type": m.group(3)})
    camp = {"emails": emails}
    for _ in range(2):                      # reruns replace, never stack
        out = fa._tm_add_campaign_profiles(None, camp, 3, "", "",
                                           profiles=_PROFILES,
                                           camp_type="tm_twelveweek")
    # Steps 5, 9, 13 and 16 are emails 3, 6, 9 and 12.
    assert out["emails"] == [4, 8, 12, 15]
    b = [e["body"] for e in camp["emails"]]
    for i, lead, n in ((4, fa._TM_PROFILES_LEAD, 3),
                       (8, fa._TM_PROFILES_AGAIN_LEAD, 3),
                       (12, fa._TM_PROFILES_THIRD_LEAD, 3),
                       (15, fa._TM_PROFILES_LAST_LEAD, 2)):
        assert b[i].count(lead) == 1, i
        assert b[i].count("<b>Candidate ") == n, i
        assert b[i].endswith("<br><br>Worth a call?")
        assert fa._tm_strip_campaign_profiles(b[i]) == (
            "Hi {FirstName},<br><br>Para one.<br><br>Worth a call?")
    others = [b[i] for i in range(len(b)) if i not in (4, 8, 12, 15)]
    assert not any("<b>Candidate " in x for x in others)


def test_other_types_keep_one_profile_email():
    camp = _std_camp()
    out = fa._tm_add_campaign_profiles(None, camp, 3, "", "",
                                       profiles=_PROFILES,
                                       camp_type="tm_conversation")
    assert "emails" not in out
    assert sum("<b>Candidate " in e["body"] for e in camp["emails"]) == 1


def test_standard_outreach_close_asks_them_to_take_a_chance():
    row = next(t for t in fa.AICB_CAMPAIGN_TYPES if t[0] == "tm_fivebyseven")
    steps = row[-1]
    assert "stay in touch" in steps and "take a chance on one role" in steps
    assert "After the person joins" not in steps
    assert "After the candidate joins" in steps
