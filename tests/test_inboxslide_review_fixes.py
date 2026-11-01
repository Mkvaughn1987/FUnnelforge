"""Fixes from the 2026-10-31 inboxslide walkthrough: acronyms in subjects,
My Day on the user's clock, renamed newsletters, capped profile fields.

flowdrip_app is imported inside each test (see conftest.py)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# ── subject title case ─────────────────────────────────────────────────────

def test_subject_title_case_keeps_possessive_and_plural_acronyms():
    import flowdrip_app as fa
    f = fa._title_case_subject
    assert "PM's Desk" in f("what's quietly piling up on your pm's desk")
    assert "CPA Firm" in f("the real reason clients stay with a cpa firm")
    assert f("three cpas walk into a bar").startswith("Three CPAs ")
    assert "TMS" in f("inside your tms after six")


def test_subject_title_case_does_not_shout_ordinary_words():
    import flowdrip_app as fa
    f = fa._title_case_subject
    assert f("join us for a look") == "Join Us for a Look"
    assert "IT" not in f("is it worth it")
    assert f("US freight desks after hours").startswith("US ")


# ── My Day date ────────────────────────────────────────────────────────────

def test_user_today_follows_the_users_timezone(monkeypatch):
    import flowdrip_app as fa
    for tz in ("Pacific/Kiritimati", "Pacific/Pago_Pago", "America/Denver"):
        monkeypatch.setattr(fa, "load_config", lambda tz=tz: {"user_timezone": tz})
        assert fa._user_today() == datetime.now(ZoneInfo(tz)).date()


def test_user_today_survives_a_bad_timezone(monkeypatch):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "load_config", lambda: {"user_timezone": "Mars/Olympus"})
    assert fa._user_today() is not None


# ── renamed newsletters ────────────────────────────────────────────────────

def test_newsletter_rename_follows_masthead_and_issue_names():
    import flowdrip_app as fa
    camp = {"name": "The Freight Desk", "newsletter_name": "Love Story",
            "emails": [{"name": "March 2027 - Love Story",
                        "subject": "Love Story - March 2027"},
                       {"name": "April 2027 - Love Story",
                        "subject": "Written by hand"}]}
    fa._follow_campaign_rename(camp, "Love Story")
    assert camp["newsletter_name"] == "The Freight Desk"
    assert camp["emails"][0]["name"] == "March 2027 - The Freight Desk"
    assert camp["emails"][0]["subject"] == "The Freight Desk - March 2027"
    assert camp["emails"][1]["subject"] == "Written by hand"


def test_newsletter_rename_leaves_a_hand_set_masthead_alone():
    import flowdrip_app as fa
    camp = {"name": "New Name", "newsletter_name": "The Denver Dirt", "emails": []}
    fa._follow_campaign_rename(camp, "Old Name")
    assert camp["newsletter_name"] == "The Denver Dirt"
    fa._follow_campaign_rename(camp, "")          # no old name: no-op
    assert camp["name"] == "New Name"


# ── capped profile fields ──────────────────────────────────────────────────

def test_profile_text_cap_cuts_at_a_sentence_not_mid_word():
    import flowdrip_app as fa
    s = ("ThriveModal recruits dedicated professionals in the Philippines "
         "for one seat on a U.S. team. You interview and choose; we employ "
         "them and handle HR, payroll and compliance. "
         + "No placement fee, " * 20)
    out = fa._clean_profile_value("company_tagline", s)
    assert len(out) <= 200
    assert out.endswith("compliance.")


def _newsletter(first_age_days, first_body="<p>written</p>"):
    import flowdrip_app as fa
    today = fa._user_today()
    first = today - timedelta(days=first_age_days)
    second = first + timedelta(days=31)
    return {"name": "N", "market_analysis": True, "emails": [
        {"name": "Issue 1", "subject": "s1", "body": first_body,
         "fixed_date": first.isoformat(), "step_type": "email_auto"},
        {"name": "Issue 2", "subject": "s2", "body": "<p>two</p>",
         "fixed_date": second.isoformat(), "step_type": "email_auto"},
    ]}


def test_new_enrollee_gets_this_months_written_issue(monkeypatch):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "load_config", lambda: {"user_timezone": "America/Denver"})
    assert fa._evergreen_start_step_for_enrollee(_newsletter(10)) == 0
    assert fa._newsletter_enroll_start_options(_newsletter(10))[0][0] == 0


def test_new_enrollee_skips_an_old_or_unwritten_issue(monkeypatch):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "load_config", lambda: {"user_timezone": "America/Denver"})
    assert fa._evergreen_start_step_for_enrollee(_newsletter(20)) == 1
    assert fa._evergreen_start_step_for_enrollee(_newsletter(10, "")) == 1
    assert fa._evergreen_start_step_for_enrollee(_newsletter(10, "[AI: draft]")) == 1
    assert fa._evergreen_start_step_for_enrollee(_newsletter(-3)) == 0   # all future


def test_profile_text_cap_falls_back_to_a_word_boundary():
    import flowdrip_app as fa
    out = fa._clean_profile_value("company_tagline", "word " * 100)
    assert len(out) <= 200 and out.endswith("word")
    long = fa._clean_profile_value("company_description", "x" * 5000)
    assert len(long) == 2000                        # long fields: plain cap
