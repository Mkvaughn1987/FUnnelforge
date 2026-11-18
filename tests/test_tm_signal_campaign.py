"""Build a Campaign for One Company (tm_signal_campaign): the Buying Signals
card's link, the signal lookup, the people match, the step plan and the
AI Prompt hand-off."""
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tm_signal_campaign as tsc
import tm_signals

ROOT = Path(__file__).resolve().parent.parent

ROW = {
    "company": "Aline Accounting Partners", "location": "Tampa, FL",
    "signal": "growth", "headline": "Aline secures $206M financing",
    "date": "2026-11-12", "why_now": "Funds more acquisitions.",
    "offshore_history": "Hiring in Metro Manila.",
    "opener": "Congratulations on the $206 million financing.",
    "source_url": "https://example.com/aline",
}
ISSUES = [
    {"id": "new", "sections": [{"industry": "logistics", "companies": [
        dict(ROW, company="Other Co")]}]},
    {"id": "old", "sections": [{"industry": "accounting", "companies": [ROW]}]},
]


def _norm(s):
    import re
    s = str(s or "").lower()
    s = re.sub(r"\b(llc|inc|llp|cpas?)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def test_link_carries_only_issue_and_company():
    url = tsc.link_for("https://app.example", "20261118-0900", "Aline & Co")
    q = parse_qs(urlparse(url).query)
    assert q == {"open": ["tm_signal_campaign"], "issue": ["20261118-0900"],
                 "company": ["Aline & Co"]}


def test_email_card_links_to_the_one_company_page():
    sig = next(iter(tm_signals.SIGNAL_BY_ID))
    issue = {"id": "abc", "date": "2026-11-18", "sections": [
        {"industry": "accounting", "label": "Accounting", "news": [],
         "companies": [dict(ROW, signal=sig)]}]}
    html = tm_signals.render_email(issue, app_url="https://app.example")
    assert "open=tm_signal_campaign" in html
    assert "issue=abc" in html and "Aline+Accounting+Partners" in html
    assert "?open=tm_prompts" not in html


def test_find_signal_prefers_named_issue_then_falls_back():
    row, ind = tsc.find_signal(ISSUES, "old", "aline accounting partners")
    assert row["headline"] == ROW["headline"] and ind == "accounting"
    row, ind = tsc.find_signal(ISSUES, "gone", "Aline Accounting Partners")
    assert ind == "accounting"
    assert tsc.find_signal(ISSUES, "old", "Nobody") == (None, "")
    assert tsc.find_signal(ISSUES, "old", "") == (None, "")


def test_company_contacts_match_and_senior_first():
    people = [
        {"email": "a@x.com", "first_name": "Ann", "last_name": "Z",
         "company": "Aline Accounting Partners LLC", "title": "Staff Accountant"},
        {"email": "b@x.com", "first_name": "Bo", "last_name": "A",
         "company": "aline accounting partners", "title": "Managing Partner"},
        {"email": "B@x.com", "company": "Aline Accounting Partners",
         "title": "dup"},
        {"email": "c@x.com", "company": "Aline", "title": "CEO"},
        {"email": "d@x.com", "company": "Aline Accounting Partners Tampa",
         "title": "Controller"},
        {"email": "e@x.com", "company": "Other", "title": "Owner"},
    ]
    got = tsc.company_contacts(people, ROW["company"], _norm)
    emails = [p["email"] for p in got]
    assert set(emails[:2]) == {"b@x.com", "d@x.com"} and emails[2] == "a@x.com"
    assert tsc.default_picks(got) == {"b@x.com", "d@x.com"}


def test_default_picks_everyone_when_nobody_is_senior():
    ppl = [{"email": "a@x.com", "title": "Bookkeeper"},
           {"email": "b@x.com", "title": ""}]
    assert tsc.default_picks(ppl) == {"a@x.com", "b@x.com"}


def test_senior_titles():
    for t in ("Owner", "CFO", "VP Finance", "Director of Operations",
              "Head of Client Accounting", "Managing Partner", "Controller",
              "Firm Administrator"):
        assert tsc.is_senior(t), t
    for t in ("Staff Accountant", "Directory Assistant", "Bookkeeper", ""):
        assert not tsc.is_senior(t), t


def test_plan_opens_on_the_signal_with_profiles_and_pdf_later():
    steps, values = tsc.plan_steps(ROW, "accounting")
    assert len(steps) == 4 and all(s["type"] == "email" for s in steps)
    assert steps[0]["delay_days"] == 0
    assert ROW["headline"] in steps[0]["ai_prompt"]
    assert ROW["opener"] in steps[0]["ai_prompt"]
    assert not steps[0]["pdf"] and not steps[0]["profiles"]
    assert steps[1]["profiles"]
    assert steps[2]["pdf"] == "tm_how_it_works"     # already offshore
    import tm_custom_campaign as cc
    assert cc.profile_plan(steps) == [1]
    assert cc.pdf_plan(steps) == [(2, "tm_how_it_works")]
    assert values["Industry"] and values["Role"]
    steps, _ = tsc.plan_steps(dict(ROW, offshore_history=""), "accounting")
    assert steps[2]["pdf"] == "tm_role_blueprint"


def test_write_steps_takes_first_subject_and_feeds_earlier_drafts():
    steps, values = tsc.plan_steps(ROW, "accounting")
    seen = []

    def draft(steps, i, direction, values, with_subject):
        seen.append(sum(1 for s in steps if s["input"]))
        return ("Subject: Congrats on the raise\n\nHi {FirstName}, one."
                if with_subject else f"Hi {{FirstName}}, step {i + 1}.")
    tsc.write_steps(steps, values, draft)
    assert seen == [0, 1, 2, 3]
    assert steps[0]["subject"] == "Congrats on the raise"
    assert steps[0]["input"] == "Hi {FirstName}, one."
    emails = __import__("tm_custom_campaign").build_emails(steps)
    assert emails[0]["subject"] == "Congrats on the raise"
    assert emails[1]["subject"] == "Re: Congrats on the raise"


def test_attach_people():
    camp = tsc.attach_people({}, [{"email": "a@x.com"}, {"email": "b@x.com"}])
    assert camp["contact_count"] == 2
    assert camp["contact_emails"] == ["a@x.com", "b@x.com"]


def test_ai_prompt_request_is_filled_in():
    import tm_prompts
    req = tsc.ai_prompt_request(ROW, "accounting")
    assert req["routine"] == "tm_one_company"
    assert req["vals"]["company"] == ROW["company"]
    assert req["vals"]["vertical"] == "Accounting / CAS firms"
    assert ROW["headline"] in req["vals"]["why_now"]
    assert ROW["source_url"] in req["vals"]["why_now"]
    prompt = tm_prompts.build_prompt(req)
    assert "ONE company only: Aline Accounting Partners" in prompt
    assert "tm_campaign_edit" in prompt


def test_app_routes_the_page_and_the_deep_link():
    src = (ROOT / "flowdrip_app.py").read_text(encoding="utf-8")
    assert 'elif _open == "tm_signal_campaign" and _is_thrivemodal():' in src
    assert 'elif page == "tm_signal_campaign" and _is_thrivemodal():' in src
    assert '"tm_signal_campaign": "Build a Campaign for One Company"' in src
